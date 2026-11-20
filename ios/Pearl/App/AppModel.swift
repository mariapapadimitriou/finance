import Foundation
import SwiftUI

/// Who is signed in, and the one connection to Pearl's server.
@MainActor
final class AppModel: ObservableObject {
    enum Phase: Equatable {
        case starting
        /// Couldn't reach the server at launch: still signed in, try again.
        case offline
        case signedOut
        case signedIn(PearlUser?)
        /// D-05: the account is gone; "Close" goes to signing in.
        case deleted(sentTo: String?)
    }

    @Published var phase: Phase = .starting {
        didSet {
            switch phase {
            case .signedOut, .deleted:
                // Her categories aren't the next account's.
                categories = []
                categoriesError = nil
                allowance = nil
                reviewCount = nil
                ledgerVersion = nil
            case .signedIn(let user):
                // Her kept answers and queued edits are her own folder's.
                screens.use(account: user?.id.map(String.init))
                outbox.use(directory: screens.directory)
            default: break
            }
        }
    }
    /// The categories she can pick, for every screen. One list, read when it's
    /// used: each screen keeping its own copy is how Quick sort came to open with
    /// none (2026-11-06). CategorySheet asks for it again if it's still empty.
    @Published private(set) var categories: [CategoryList.Category] = []
    /// Why the list couldn't load; CategorySheet says so and offers Try again.
    @Published private(set) var categoriesError: String?
    private var loadingCategories = false
    /// Bumped after any change, so every screen reloads what it shows.
    @Published var version = 0
    /// Perf rehaul (2026-11-19): the screen that made a change already
    /// shows it (`changed(by:)`), so it needn't ask for itself again. Each
    /// key names the version that screen is good for; `ReloadsOnChange`
    /// with the same key skips that one bump.
    private(set) var caughtUp: [String: Int] = [:]
    /// The Allowance as Home shows it: seeded by api/home, moved by every
    /// write's `changed.allowance`, so Home is right without a fetch.
    @Published var allowance: Allowance?
    /// How many rows Needs a look has, from the last write's `changed`;
    /// the badge takes it instead of asking api/review.
    @Published var reviewCount: Int?
    /// The `version` that `reviewCount` was set for.
    private(set) var reviewCountAt: Int?
    /// The ledger's version the phone last saw (ETags and `changed`), sent
    /// with every write as `X-Base-Version`.
    private(set) var ledgerVersion: Int?
    /// The rows the last write touched, for any list that holds them.
    @Published var changedRows: Changed?
    /// AM-13: said on Accounts once it's back on screen ("TD is removed…").
    @Published var accountsNotice: String?
    /// The account was made just now: setup starts at Face ID (O-04), not at
    /// "Let's finish setting up" (O-00).
    @Published var justCreated = false
    /// A-08: Face ID is on and Pearl has been away long enough to lock.
    @Published var locked = false
    /// A reset link opened the app (pearl://reset?token=…): A-07.
    @Published var resetToken: String?
    /// Where "Contact support" writes to (A-10).
    @Published var contact: String?
    /// Cash flow's Select (T-19) puts its own bar where the tab bar is.
    @Published var hidesTabBar = false
    /// A+ (REDESIGN-03): something in Profile needs her (a bank to sign in
    /// to again, Accounts' "needs you"): the dot on the profile circle.
    @Published var profileNeedsYou = false
    /// A toast that outlives the screen it was said on, at the top of every
    /// tab: Trips (TR-02c, TR-11–TR-13), where the trip's page may close or
    /// open under it ("Trip to Montréal made · 23 transactions · Undo").
    @Published var toast: AppToast?

    struct AppToast: Identifiable, Equatable {
        let id = UUID()
        let text: String
        /// Undo, when there is one; it says "Undone." once it has worked.
        let undo: (() async throws -> Void)?

        static func == (a: AppToast, b: AppToast) -> Bool { a.id == b.id }
    }

    func say(_ text: String, undo: (() async throws -> Void)? = nil) {
        withAnimation { toast = AppToast(text: text, undo: undo) }
    }

    let api = APIClient()
    /// The last answer to every read, kept on the iPhone (ScreenStore).
    let screens: ScreenStore
    /// Writes that are safe to send twice, queued when offline (Outbox).
    let outbox: Outbox
    private var leftAt: Date?

    init() {
        screens = ScreenStore(api: api)
        outbox = Outbox(api: api)
        outbox.app = self
        api.sawETag = { [weak self] tag in
            Task { @MainActor in self?.noteETag(tag) }
        }
    }

    private static let faceIDKey = "pearl.faceID"

    /// Face ID unlocks Pearl on this iPhone (O-04, A-09, Settings).
    var faceIDOn: Bool {
        get { UserDefaults.standard.bool(forKey: Self.faceIDKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: Self.faceIDKey)
            objectWillChange.send()
            if newValue { saveSignIn() } else { SavedSignIn.clear() }
            Task { await tellServerAboutFaceID() }
        }
    }

    /// The email and password she just signed in with, kept only in memory
    /// until Face ID is on to guard them (SavedSignIn).
    private var lastSignIn: (email: String, password: String)?

    /// Called with the password that just worked. Saved for Face ID sign-in
    /// now if Face ID is on, or when she turns it on.
    func remember(email: String, password: String) {
        lastSignIn = (email.trimmingCharacters(in: .whitespaces), password)
        if faceIDOn { saveSignIn() }
    }

    private func saveSignIn() {
        guard let s = lastSignIn else { return }
        SavedSignIn.save(email: s.email, password: s.password)
        lastSignIn = nil
    }

    /// With Face ID on, this iPhone stays signed in between opens and Face ID
    /// guards the app (SECURITY.md); with it off, the server's idle limit is back.
    private func tellServerAboutFaceID() async {
        do {
            let _: OK = try await api.post("api/auth/stay", ["on": faceIDOn])
        } catch {
            // Not a confirmed iPhone (yet): the 20-minute idle limit still
            // applies, and Face ID sign-in brings her back when it ends.
            print("Pearl: staying signed in was refused: \(error.localizedDescription)")
        }
    }

    func loadCategories() async {
        guard !loadingCategories else { return }
        loadingCategories = true
        defer { loadingCategories = false }
        categoriesError = nil
        do {
            // The kept list at once, then the server's if it changed.
            try await screens.load("api/categories", as: CategoryList.self) { self.use($0) }
        } catch is CancellationError {
            return
        } catch {
            categoriesError = handle(error)
        }
    }

    /// A list fetched elsewhere (Categories and rules, after she changes one).
    func use(_ list: CategoryList) {
        categories = list.categories.filter { $0.hidden != true }
        categoriesError = nil
    }

    /// On launch: is the saved session still good?
    func start() async {
        do {
            let status: AuthStatus = try await api.get("api/auth/status")
            contact = status.contact
            phase = status.signedIn ? .signedIn(status.user) : .signedOut
            if status.signedIn { Task { await loadCategories() } }
            // Opening Pearl with Face ID on asks for it first (THL-114). The
            // session outlasts the idle limit on the strength of this lock, so
            // Face ID being unavailable shows it too: the passcode still opens it.
            if status.signedIn && faceIDOn {
                locked = true
                await tellServerAboutFaceID()
            }
        } catch APIError.signedOut {
            phase = .signedOut
        } catch is CancellationError {
            return
        } catch {
            // Offline: the saved session is still good, so don't ask to sign in.
            phase = .offline
        }
    }

    func signedIn(_ user: PearlUser?) {
        phase = .signedIn(user)
        locked = false
        version += 1
        if faceIDOn { Task { await tellServerAboutFaceID() } }
        if categories.isEmpty { Task { await loadCategories() } }
    }

    /// Something changed: every screen checks its answer again (an ETag
    /// each). `by` names the screen that made the change and already shows
    /// it, so that one doesn't.
    func changed(by origin: String? = nil) {
        version += 1
        if let origin = origin { caughtUp[origin] = version }
    }

    /// A write's `changed` envelope applied: the Allowance, the review
    /// count and the ledger version move at once, lists get the rows, and
    /// the other screens are told. With no envelope (an older answer, an
    /// undo) everything reloads as before.
    func apply(_ changed: Changed?, by origin: String? = nil, bump: Bool = true) {
        guard let changed = changed else {
            if bump { self.changed() }
            return
        }
        ledgerVersion = max(ledgerVersion ?? 0, changed.version)
        if let allowance = changed.allowance {
            withAnimation(.easeInOut(duration: 0.3)) { self.allowance = allowance }
        }
        changedRows = changed
        if bump { self.changed(by: origin) }
        if let count = changed.reviewCount {
            reviewCount = count
            reviewCountAt = version
        }
    }

    /// Home's answer came: the Allowance it shows is the app's.
    func seed(_ home: Home) {
        if let sts = home.safeToSpend { allowance = sts }
    }

    private func noteETag(_ tag: String) {
        if let v = Changed.version(inETag: tag) { ledgerVersion = max(ledgerVersion ?? 0, v) }
        // A read got through: edits waiting for the network can go now.
        if !outbox.isEmpty { Task { await outbox.replay() } }
    }

    /// Any call that comes back "signed out" lands here.
    func handle(_ error: Error) -> String? {
        if error is CancellationError { return nil }
        if let api = error as? APIError, api == .signedOut {
            // A call still on its way when the account was deleted doesn't
            // take "Your account is deleted" off the screen.
            if case .deleted = phase { return nil }
            phase = .signedOut
            return nil
        }
        return error.localizedDescription
    }

    /// Signing out on the iPhone forgets it as a trusted device, so the next
    /// sign-in here asks for an email code again (THL-114).
    func signOut() async {
        let _: OK? = try? await api.post("api/auth/logout", ["forget_device": true])
        api.clearCookies()
        screens.clear()
        outbox.clear()
        // Signing out on purpose means Face ID shouldn't sign her straight back in.
        SavedSignIn.clear()
        lastSignIn = nil
        justCreated = false
        locked = false
        phase = .signedOut
    }

    /// The server has deleted the account (D-04), so there's nothing to sign
    /// out of: forget it here too, and show D-05.
    func accountDeleted(sentTo: String?) {
        // Her photo was on this iPhone only; the account is gone, so it goes too.
        if let id = user?.id { ProfilePhotoStore.shared.forget(account: String(id)) }
        api.clearCookies()
        screens.clear()
        outbox.clear()
        justCreated = false
        locked = false
        lastSignIn = nil
        faceIDOn = false
        phase = .deleted(sentTo: sentTo)
    }

    // MARK: App lock (A-08)

    func wentToBackground() {
        leftAt = Date()
    }

    func cameBack() {
        // Edits made while the network was away go now (Outbox).
        if case .signedIn = phase, !outbox.isEmpty { Task { await outbox.replay() } }
        guard case .signedIn = phase, faceIDOn, let left = leftAt else { return }
        if Date().timeIntervalSince(left) >= AppLock.after { locked = true }
        leftAt = nil
    }

    // MARK: Links into the app

    /// pearl://reset?token=… opens "Choose a new password" (A-07).
    func open(_ url: URL) {
        guard url.scheme == "pearl", url.host == "reset",
              let token = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "token" })?.value else { return }
        resetToken = token
        if case .signedIn = phase {
            Task { await signOut() }
        }
    }

    var user: PearlUser? {
        if case .signedIn(let user) = phase { return user }
        return nil
    }
}

/// Loads a screen when it first shows, when something changed (`app.version`)
/// while it's on screen, or when it comes back after a change or after
/// five minutes (2026-11-08). `.task(id: app.version)` ran again on every
/// appear: every tab switch and every Back reloaded the whole screen, and
/// every change reloaded the tabs nobody was looking at.
struct ReloadsOnChange: ViewModifier {
    @EnvironmentObject private var app: AppModel
    let load: () async -> Void
    /// The screen's name in `app.changed(by:)`: a bump it made itself,
    /// already shown, doesn't reload it (perf rehaul, 2026-11-19).
    var key: String? = nil
    @State private var loaded: Int?
    @State private var loadedAt = Date.distantPast
    @State private var visible = false
    /// The load under way: a change while it runs cancels it before the
    /// next starts (perf rehaul, 2026-11-19), so quick `version` bumps
    /// don't leave overlapping loads where the last to finish wins. The
    /// APIClient turns a cancelled request into `CancellationError`, which
    /// `app.handle` ignores.
    @State private var running: Task<Void, Never>?
    static let stale: TimeInterval = 300

    func body(content: Content) -> some View {
        content
            .onAppear {
                visible = true
                let ok = current
                if ok { loaded = app.version }
                if !ok || Date().timeIntervalSince(loadedAt) > Self.stale { go() }
            }
            .onDisappear { visible = false }
            .onChange(of: app.version) { _ in
                guard visible else { return }
                if current { loaded = app.version } else { go() }
            }
    }

    /// Whether what's shown is good for `app.version`: loaded at it, or
    /// one behind it with this screen the one that made the bump.
    private var current: Bool {
        guard let loaded = loaded else { return false }
        if loaded == app.version { return true }
        if let key = key, app.caughtUp[key] == app.version, loaded == app.version - 1 { return true }
        return false
    }

    private func go() {
        loaded = app.version
        loadedAt = Date()
        running?.cancel()
        running = Task { await load() }
    }
}

extension View {
    func reloads(key: String? = nil, _ load: @escaping () async -> Void) -> some View {
        modifier(ReloadsOnChange(load: load, key: key))
    }
}

/// The screen a pushed page belongs to (`app.changed(by:)`): Cash flow sets
/// it for its detail pages, so an edit made there counts as Cash flow's own.
struct ScreenKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    var screenKey: String? {
        get { self[ScreenKey.self] }
        set { self[ScreenKey.self] = newValue }
    }
}

/// What the app shows while a piece of it is held back.
enum Features {
    /// Tags wait for THL-286: no Add tags row, no Tags tab in Categories and
    /// rules, no Tags filter. The server keeps them; turn this on to bring
    /// them back.
    static let tags = false
    /// Pearl chat's plans (PC-12, PC-13): Set it adds the plan to Your plan
    /// (YP-01 to YP-06, Profile › Income and bills › Your plan), which
    /// PC-13's "See it in Your plan" opens.
    static let chatPlans = true
}
