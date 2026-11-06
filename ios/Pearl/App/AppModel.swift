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

    @Published var phase: Phase = .starting
    /// Bumped after any change, so every screen reloads what it shows.
    @Published var version = 0
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

    let api = APIClient()
    private var leftAt: Date?

    private static let faceIDKey = "pearl.faceID"

    /// Face ID unlocks Pearl on this iPhone (O-04, A-09, Settings).
    var faceIDOn: Bool {
        get { UserDefaults.standard.bool(forKey: Self.faceIDKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: Self.faceIDKey)
            objectWillChange.send()
            Task { await tellServerAboutFaceID() }
        }
    }

    /// With Face ID on, this iPhone stays signed in between opens and Face ID
    /// guards the app (SECURITY.md); with it off, the server's idle limit is back.
    private func tellServerAboutFaceID() async {
        let _: OK? = try? await api.post("api/auth/stay", ["on": faceIDOn])
    }

    /// On launch: is the saved session still good?
    func start() async {
        do {
            let status: AuthStatus = try await api.get("api/auth/status")
            contact = status.contact
            phase = status.signedIn ? .signedIn(status.user) : .signedOut
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
    }

    func changed() {
        version += 1
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
        justCreated = false
        locked = false
        phase = .signedOut
    }

    /// The server has deleted the account (D-04), so there's nothing to sign
    /// out of: forget it here too, and show D-05.
    func accountDeleted(sentTo: String?) {
        api.clearCookies()
        justCreated = false
        locked = false
        faceIDOn = false
        phase = .deleted(sentTo: sentTo)
    }

    // MARK: App lock (A-08)

    func wentToBackground() {
        leftAt = Date()
    }

    func cameBack() {
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

/// What the app shows while a piece of it is held back.
enum Features {
    /// Tags wait for THL-286: no Add tags row, no Tags tab in Categories and
    /// rules, no Tags filter. The server keeps them; turn this on to bring
    /// them back.
    static let tags = false
}
