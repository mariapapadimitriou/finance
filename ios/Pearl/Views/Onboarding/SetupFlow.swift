import SwiftUI
import UserNotifications

/// Signed in, setup not finished (THL-119): Face ID, linking a bank with
/// Plaid, your accounts (AS-01), pay and bills, and the first Allowance. A new
/// account starts at Face ID (O-04); coming back later starts at O-00.
@MainActor
struct SetupFlow: View {
    @EnvironmentObject private var app: AppModel
    @State private var path: [SetupRoute] = []
    @StateObject private var plaid = PlaidLinker()

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if app.justCreated {
                    FaceIDOfferView(mode: .onboarding) { path.append(.linkBank) }
                } else {
                    FinishSetupView { path.append(.linkBank) }
                }
            }
            .navigationDestination(for: SetupRoute.self) { route in
                switch route {
                case .linkBank: LinkBankView(path: $path)
                case .reading(let link): ReadingAccountsView(path: $path, link: link)
                case .linked: BankLinkedView(path: $path)
                case .failed(let bank): LinkProblemView(path: $path, problem: .failed(bank))
                case .notSupported(let bank): LinkProblemView(path: $path, problem: .notSupported(bank))
                case .accounts: AccountSetupView(path: $path)
                case .payBills: PayAndBillsView(path: $path)
                case .saving: SavingShareView(path: $path)
                case .allowance: AllowanceView(path: $path, skipped: false)
                case .skipped: AllowanceView(path: $path, skipped: true)
                }
            }
        }
        .tint(Pearl.ink)
        .environmentObject(plaid)
        #if DEBUG
        // For checking a screen against Figma without linking a bank first:
        // launch with `-pearl-setup accounts|payBills|allowance`.
        .onAppear {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-pearl-setup"), i + 1 < args.count else { return }
            switch args[i + 1] {
            case "accounts", "joint": path = [.accounts]
            case "payBills": path = [.payBills]
            case "saving": path = [.saving]
            case "allowance": path = [.allowance]
            case "linked": path = [.linked]
            default: break
            }
        }
        #endif
    }
}

enum SetupRoute: Hashable {
    case linkBank
    case reading(PlaidLinker.Linked)
    case linked
    case failed(String)
    case notSupported(String)
    /// AS-01 Your accounts (part 3).
    case accounts
    case payBills
    /// O-10s: how much of each paycheque to save.
    case saving
    case allowance
    case skipped
}

/// Open Plaid from wherever she is, and follow what happens. The problem in
/// words when Plaid couldn't open.
@MainActor
func openPlaid(_ plaid: PlaidLinker, api: APIClient, path: Binding<[SetupRoute]>) async -> String? {
    do {
        let outcome = try await plaid.open(api: api)
        switch outcome {
        case .linked(let link): path.wrappedValue.append(.reading(link))
        case .cancelled: break                         // Not an error: she's back where she was.
        case .failed(let bank): path.wrappedValue.append(.failed(bank))
        case .notSupported(let bank): path.wrappedValue.append(.notSupported(bank))
        }
        return nil
    } catch {
        return error.localizedDescription
    }
}

// MARK: - O-00 Let's finish setting up

@MainActor
struct FinishSetupView: View {
    @EnvironmentObject private var app: AppModel
    let next: () -> Void

    var body: some View {
        // G6-Welcome O-00: the mark, the title and the next step.
        OnbScreen(back: false, scrolls: false) {
            OnbMessage(title: "Let\u{2019}s finish setting up", line: "Next: link your bank. It takes about a minute.",
                       top: 118) { APMark(width: 180) }
        } actions: {
            OnbPrimary(title: "Continue", action: next)
            APQuietButton(title: "Sign out") { Task { await app.signOut() } }
        }
    }
}

// MARK: - O-06 Pearl uses Plaid to link your bank

@MainActor
struct LinkBankView: View {
    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var plaid: PlaidLinker
    @Binding var path: [SetupRoute]
    @State private var agreed = false
    /// LG-01, LG-02 from the consent line's links.
    @State private var doc: PearlDoc?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        // G6-Plaid O-06: part 2, what Plaid can and can't do, the agreement.
        OnbScreen(back: false, part: 2, partName: "Link your bank") {
            OnbTitle(title: "Pearl uses Plaid to link your bank")
            APCard {
                ProfileRow(symbol: "lock", title: "Bank-level encryption", sub: "Stored in Canada", chevron: false)
                APSeparator()
                ProfileRow(symbol: "eye", title: "Read-only", sub: "Pearl can\u{2019}t move your money", chevron: false)
                APSeparator()
                ProfileRow(symbol: "checkmark.shield", title: "Never sold", sub: "No ads. Delete your data anytime.",
                           chevron: false)
                APSeparator()
                // Approved 2026-11-18: where to disconnect, in the app; no web hand-off.
                ProfileRow(symbol: "personalhotspot", title: "Disconnect anytime", sub: "In Profile \u{203A} Accounts",
                           chevron: false)
            }
            .padding(.top, 6)
            agreement
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Continue", busy: busy, busyLabel: "Opening Plaid\u{2026}", enabled: agreed) {
                Task { await link() }
            }
            APQuietButton(title: "Link later") { path.append(.skipped) }
        }
        .docSheet($doc)
    }

    /// The tick box and the consent line; its links open the pages, so a tap
    /// on Terms reads it rather than ticking the box.
    private var agreement: some View {
        HStack(alignment: .top, spacing: 12) {
            Button { agreed.toggle() } label: { APTickBox(on: agreed) }
                .buttonStyle(.plain)
                .accessibilityLabel("I\u{2019}m 19 or older and agree")
                .accessibilityAddTraits(agreed ? .isSelected : [])
            consentLine.font(Nacre.subheadline).foregroundColor(Pearl.ink).tint(Pearl.link)
                .fixedSize(horizontal: false, vertical: true)
                .environment(\.openURL, OpenURLAction { url in
                    guard let d = PearlDoc(url: url) else { return .systemAction }
                    doc = d
                    return .handled
                })
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 4).padding(.top, 2)
    }

    private var consentLine: Text {
        var terms = AttributedString("Terms")
        terms.link = PearlDoc.terms.url
        terms.underlineStyle = .single
        var privacy = AttributedString("Privacy Policy")
        privacy.link = PearlDoc.privacy.url
        privacy.underlineStyle = .single
        var plaid = AttributedString("End User Privacy Policy")
        plaid.link = URL(string: "https://plaid.com/legal/#end-user-privacy-policy")
        plaid.underlineStyle = .single
        return Text("I’m 19 or older and agree to Pearl’s ") + Text(terms) + Text(" and ") + Text(privacy)
            + Text(", and Plaid’s ") + Text(plaid) + Text(".")
    }

    private func link() async {
        busy = true
        defer { busy = false }
        error = nil
        do {
            // THL-117: the agreements are recorded, with the time, before Plaid opens.
            let _: OK = try await app.api.post("api/onboarding", ["consents": ["terms": true, "read_data": true]])
        } catch {
            self.error = app.handle(error)
            return
        }
        error = await openPlaid(plaid, api: app.api, path: $path)
    }
}

// MARK: - O-08 Pearl is reading your accounts (O-08a, O-08b)

@MainActor
struct ReadingAccountsView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @Binding var path: [SetupRoute]
    let link: PlaidLinker.Linked
    @State private var done = false
    @State private var longer = false
    @State private var notify = false
    @State private var spin = false

    var body: some View {
        // G6-Reading O-08: the ring round the mark, then each account's state.
        // Scrolls: a bank can bring a dozen accounts or more.
        OnbScreen(back: false) {
            ReadingRing(spin: spin, longer: longer)
            APCard {
                ForEach(Array(link.accounts.enumerated()), id: \.offset) { i, account in
                    if i > 0 { APSeparator() }
                    HStack(spacing: 12) {
                        RowAvatar(name: initials(link.institution))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(account.name).font(Nacre.body).foregroundColor(Pearl.ink)
                            Text(status(i)).font(Nacre.subheadline)
                                .foregroundColor(!done && i == 0 ? Pearl.action : Pearl.muted)
                        }
                        Spacer(minLength: 8)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .frame(minHeight: 64)
                    .accessibilityElement(children: .combine)
                }
            }
            .padding(.top, 12)
        } actions: {
            if longer && !done {
                OnbPrimary(title: "Notify me", enabled: !notify) { Task { await askToNotify() } }
                APQuietButton(title: "Keep waiting") { longer = false }
            }
        }
        .onAppear { spin = true }
        .task { await exchange() }
        .task {
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            if !done { longer = true }
        }
    }

    private func status(_ i: Int) -> String {
        if done { return "Done" }
        return i == 0 ? "Reading transactions…" : "Waiting"
    }

    private func exchange() async {
        do {
            let _: LinkedItem = try await app.api.post("api/plaid/exchange",
                                                       ["public_token": link.publicToken, "institution": link.institution])
            done = true
            if notify && scenePhase != .active { postReady() }
            path.append(.linked)
        } catch {
            path.removeLast()
            path.append(.failed(link.institution))
        }
    }

    /// O-08b: the system asks "“Pearl” Would Like to Send You Notifications".
    private func askToNotify() async {
        let granted = (try? await UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        notify = granted
    }

    private func postReady() {
        let content = UNMutableNotificationContent()
        content.title = "Your bank is linked"
        content.body = "Pearl has read your accounts. Pick up where you left off."
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "pearl.linked", content: content,
                                                                     trigger: nil))
    }
}

/// G6-Reading: the 150 pt ring (action over track) round the mark on a card
/// disc, the title and its line.
struct ReadingRing: View {
    let spin: Bool
    let longer: Bool

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                Circle().stroke(APlus.trackSoft, lineWidth: 6)
                Circle().trim(from: 0, to: 0.38)
                    .stroke(Pearl.action, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(spin ? 270 : -90))
                    .animation(.linear(duration: 2.4).repeatForever(autoreverses: false), value: spin)
                Circle().fill(APlus.card).padding(6)
                APMark(width: 90)
            }
            .frame(width: 150, height: 150)
            .padding(.bottom, 18)
            .accessibilityHidden(true)
            Text(longer ? "This is taking a little longer" : "Pearl is reading your accounts")
                .font(Nacre.largeTitle).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(longer ? "Some banks need a few minutes. We can let you know when it\u{2019}s ready." : "About a minute.")
                .font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 28)
    }
}

func initials(_ name: String) -> String {
    let words = name.split(separator: " ").filter { $0.first?.isLetter == true }
    if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
    return words.prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
}

// MARK: - O-09 Your bank is linked, O-09d Your card is linked

@MainActor
struct BankLinkedView: View {
    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var plaid: PlaidLinker
    @Binding var path: [SetupRoute]
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var error: String?

    var body: some View {
        // G6-Linked O-09 / O-09d: part 2, the green tick, the accounts.
        OnbScreen(back: false, part: 2, partName: "Link your bank") {
            LinkedHead(title: cardOnly ? "Your card is linked" : "Your bank is linked", line: line)
            if !accounts.isEmpty {
                APCard {
                    ForEach(Array(accounts.enumerated()), id: \.element.id) { i, account in
                        if i > 0 { APSeparator() }
                        AccountLine(account: account)
                    }
                }
                .padding(.top, 10)
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            if cardOnly {
                OnbPrimary(title: "Link chequing") { Task { error = await openPlaid(plaid, api: app.api, path: $path) } }
                APQuietButton(title: "Continue with just my card") { path.append(.accounts) }
            } else {
                OnbPrimary(title: "Continue") { path.append(.accounts) }
                APQuietButton(title: "Link another bank") {
                    Task { error = await openPlaid(plaid, api: app.api, path: $path) }
                }
            }
        }
        .task {
            do {
                let overview: AccountsOverview = try await app.api.get("api/accounts/overview")
                accounts = overview.linked
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private var cardOnly: Bool { !accounts.isEmpty && accounts.allSatisfy(\.isCard) }

    private var line: String {
        if cardOnly { return "Link your chequing too, so Pearl sees your pay and bills." }
        guard !accounts.isEmpty else { return "" }
        let count = "\(accounts.count) account\(accounts.count == 1 ? "" : "s")"
        let first = accounts.compactMap { $0.historyFrom.flatMap(Format.date) }.min()
        guard let first = first else { return count }
        let months = max(1, Calendar(identifier: .gregorian).dateComponents([.month], from: first, to: Date()).month ?? 1)
        return "\(count) · \(months) month\(months == 1 ? "" : "s") of history"
    }
}

/// G6-Linked's top: the 96 pt green tick, the title and its line.
struct LinkedHead: View {
    let title: String
    let line: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: "checkmark").font(.system(size: 40, weight: .semibold))
                .foregroundColor(Pearl.moneyIn)
                .frame(width: 96, height: 96)
                .background(Circle().fill(ProfileTone.goodWash))
                .accessibilityHidden(true)
            Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
                .padding(.top, 16)
            if !line.isEmpty {
                Text(line).font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 20)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 58)
    }
}

/// One linked account: "TD Chequing / ••4417 · $2,340.18".
struct AccountLine: View {
    let account: AccountsOverview.Account
    var sub: String? = nil
    var trailing: AnyView? = nil

    var body: some View {
        // G6-Linked: the face, the name over "••4417", the balance on the right edge.
        HStack(spacing: 12) {
            RowAvatar(name: initials(account.institution ?? account.name))
            VStack(alignment: .leading, spacing: 2) {
                Text(account.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(sub ?? detail).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let trailing = trailing {
                trailing
            } else if let balance = account.balance {
                Text(Format.amount(abs(balance))).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.ink).pearlAmountFit().fixedSize()
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var detail: String {
        var parts: [String] = []
        if let mask = account.mask, !mask.isEmpty { parts.append("••\(mask)") }
        if account.owing == true { parts.append("owing") }
        return parts.joined(separator: " · ")
    }
}

// MARK: - O-09a We couldn't link TD, O-09f We can't connect to Alterna yet

@MainActor
struct LinkProblemView: View {
    enum Problem { case failed(String), notSupported(String) }

    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var plaid: PlaidLinker
    @Binding var path: [SetupRoute]
    let problem: Problem
    @State private var error: String?

    var body: some View {
        // G6-Linked O-09a / O-09f.
        OnbScreen(back: false, scrolls: false) {
            OnbMessage(title: title, line: line, top: 118) { APMark(width: 170) }
            if let error = error { APErrorLine(text: error).padding(.top, 12) }
        } actions: {
            OnbPrimary(title: primary) { Task { await again() } }
            if case .notSupported = problem {
                APQuietButton(title: "Skip for now") { path.append(.skipped) }
            } else {
                APQuietButton(title: "Choose another bank") { Task { await again() } }
            }
        }
    }

    private var title: String {
        switch problem {
        case .failed(let bank): return "We couldn’t link \(bank)"
        case .notSupported(let bank): return "We can’t connect to \(bank) yet"
        }
    }

    private var line: String {
        switch problem {
        case .failed: return "Nothing was saved."
        case .notSupported: return "Choose another bank, or link later."
        }
    }

    private var primary: String {
        if case .notSupported = problem { return "Choose another bank" }
        return "Try again"
    }

    private func again() async {
        path.removeLast()
        error = await openPlaid(plaid, api: app.api, path: $path)
    }
}

// AS-01 / AS-02 Account setup (part 3) replaced O-09b, O-09b2 and O-09c:
// AccountSetupViews.swift.

/// The round × that closes a sheet.
struct CloseButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "xmark")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Pearl.control))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Close")
    }
}
