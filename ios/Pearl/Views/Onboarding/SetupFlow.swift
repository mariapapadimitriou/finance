import SwiftUI
import UserNotifications

/// Signed in, setup not finished (THL-119): Face ID, linking a bank with
/// Plaid, joint accounts, pay and bills, and the first Allowance. A new
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
                case .joint: JointAccountsView(path: $path)
                case .payBills: PayAndBillsView(path: $path)
                case .allowance: AllowanceView(path: $path, skipped: false)
                case .skipped: AllowanceView(path: $path, skipped: true)
                }
            }
        }
        .tint(Pearl.ink)
        .environmentObject(plaid)
        #if DEBUG
        // For checking a screen against Figma without linking a bank first:
        // launch with `-pearl-setup joint|payBills|allowance`.
        .onAppear {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-pearl-setup"), i + 1 < args.count else { return }
            switch args[i + 1] {
            case "joint": path = [.joint]
            case "payBills": path = [.payBills]
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
    case joint
    case payBills
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
        VStack(spacing: 0) {
            Wordmark().padding(.top, 16)
            HeroShell(width: 256).padding(.top, 58)
            VStack(spacing: 12) {
                Text("Let’s finish setting up").font(Nacre.title).tracking(0.4)
                    .accessibilityAddTraits(.isHeader)
                Text("Next: link your bank. It takes about a minute.").font(Nacre.body)
            }
            .multilineTextAlignment(.center)
            .padding(.horizontal, 24)
            .padding(.top, 42)
            Spacer(minLength: 24)
            BottomActions {
                Button("Continue", action: next).buttonStyle(NacreButtonStyle())
            } secondary: {
                Button("Sign out") { Task { await app.signOut() } }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .nacreScreen()
        .toolbar(.hidden, for: .navigationBar)
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
        NacreScreen {
            ShellProgress(part: 2, name: "Link your bank")
            HStack(spacing: 10) {
                Image("LogoMark").resizable().frame(width: 34, height: 28.3)
                    .frame(width: 52, height: 52)
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
                Text("···").font(.system(size: 20, weight: .bold))
                IconOrb(symbol: "lock", size: 44)
            }
            .frame(maxWidth: .infinity)
            .accessibilityHidden(true)
            Text("Pearl uses Plaid to link your bank").font(Nacre.title).tracking(0.4)
                .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                .accessibilityAddTraits(.isHeader)
            GlassCard {
                point("lock", "Bank-level encryption", "Encrypted and stored in Canada.")
                point("eye", "Read-only access", "Pearl can’t move your money.")
                point("checkmark", "Your data is never sold", "No ads. Delete your data anytime.")
                point("xmark", "Disconnect anytime", "In Settings, or at my.plaid.com.")
            }
            // The links sit outside the button, so tapping Terms opens it
            // rather than ticking the box.
            HStack(alignment: .top, spacing: 12) {
                Button { agreed.toggle() } label: {
                    Image(systemName: agreed ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 22))
                        .foregroundColor(agreed ? Pearl.action : Pearl.ink)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("I’m 19 or older and agree")
                VStack(alignment: .leading, spacing: 2) {
                    Button { agreed.toggle() } label: {
                        Text("I’m 19 or older and agree to:").font(Nacre.body)
                    }
                    .buttonStyle(.plain)
                    consentLine.font(Nacre.subheadline)
                        .environment(\.openURL, OpenURLAction { url in
                            guard let d = PearlDoc(url: url) else { return .systemAction }
                            doc = d
                            return .handled
                        })
                }
                Spacer(minLength: 0)
            }
            .accessibilityAddTraits(agreed ? .isSelected : [])
            .padding(.horizontal, 8)
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Continue") { Task { await link() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(!agreed || busy)
            } secondary: {
                Button("Link later") { path.append(.skipped) }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .docSheet($doc)
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
        return Text("Pearl’s ") + Text(terms) + Text(" and ") + Text(privacy)
            + Text(", and Plaid’s ") + Text(plaid) + Text(".")
    }

    private func point(_ symbol: String, _ title: String, _ line: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .medium))
                .frame(width: 40, height: 40)
                .background(Circle().fill(Nacre.glass))
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.heading(18, relativeTo: .headline))
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
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
        // Scrolls: a bank can bring a dozen accounts or more.
        NacreScreen(scrolls: true) {
            VStack(spacing: 12) {
                ZStack {
                    Circle().stroke(Color.white.opacity(0.5), lineWidth: 4)
                    Circle().trim(from: 0, to: 0.7)
                        .stroke(AngularGradient(colors: [Nacre.seaglass, Nacre.lilac, Nacre.rose], center: .center),
                                style: StrokeStyle(lineWidth: 4, lineCap: .round))
                        .rotationEffect(.degrees(spin ? 360 : 0))
                        .animation(.linear(duration: 2.4).repeatForever(autoreverses: false), value: spin)
                    Image("LogoMark").resizable().frame(width: 104, height: 86.7)
                }
                .frame(width: 200, height: 200)
                .padding(.bottom, 12)
                .accessibilityHidden(true)
                Text(longer ? "This is taking a little longer" : "Pearl is reading your accounts")
                    .font(Nacre.title).tracking(0.4).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Text(longer ? "Some banks need a few minutes. We can let you know when it’s ready." : "About a minute.")
                    .font(Nacre.body).multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 24)
            GlassCard {
                ForEach(Array(link.accounts.enumerated()), id: \.offset) { i, account in
                    if i > 0 { RowSeparator(inset: 60) }
                    HStack(spacing: 12) {
                        BankBadge(text: initials(link.institution))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(account.name).font(Nacre.body)
                            Text("••\(account.mask) · \(status(i))").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 8)
                        if done || i == 0 && longer { DonePill(text: "Done") }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
        } actions: {
            if longer && !done {
                BottomActions {
                    Button("Notify me") { Task { await askToNotify() } }
                        .buttonStyle(NacreButtonStyle())
                        .disabled(notify)
                } secondary: {
                    Button("Keep waiting") { longer = false }
                        .buttonStyle(NacreTextButtonStyle())
                }
            }
        }
        .navigationBarBackButtonHidden(true)
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
        NacreScreen {
            MessageBlock(title: cardOnly ? "Your card is linked" : "Your bank is linked", line: line) {
                Image("LogoMark").resizable().frame(width: 140, height: 116.7)
                    .overlay(alignment: .bottomTrailing) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 13, weight: .semibold))
                            .frame(width: 32, height: 32)
                            .background(Circle().fill(Nacre.glass))
                            .offset(x: 12, y: 6)
                    }
                    .accessibilityHidden(true)
            }
            .padding(.top, 0)
            if !accounts.isEmpty {
                GlassCard {
                    ForEach(Array(accounts.enumerated()), id: \.element.id) { i, account in
                        if i > 0 { RowSeparator(inset: 60) }
                        AccountLine(account: account, trailing: AnyView(DonePill(text: "Synced")))
                    }
                }
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                if cardOnly {
                    Button("Link chequing") { Task { error = await openPlaid(plaid, api: app.api, path: $path) } }
                        .buttonStyle(NacreButtonStyle())
                } else {
                    Button("Continue") { path.append(.joint) }
                        .buttonStyle(NacreButtonStyle())
                }
            } secondary: {
                if cardOnly {
                    Button("Continue with just my card") { path.append(.joint) }
                        .buttonStyle(NacreTextButtonStyle())
                } else {
                    Button("Link another bank") { Task { error = await openPlaid(plaid, api: app.api, path: $path) } }
                        .buttonStyle(NacreTextButtonStyle())
                }
            }
        }
        .navigationBarBackButtonHidden(true)
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
        if cardOnly { return "Link your chequing too, so we can see your pay and bills." }
        guard !accounts.isEmpty else { return "" }
        let count = "\(accounts.count) account\(accounts.count == 1 ? "" : "s")"
        let first = accounts.compactMap { $0.historyFrom.flatMap(Format.date) }.min()
        guard let first = first else { return count }
        let months = max(1, Calendar(identifier: .gregorian).dateComponents([.month], from: first, to: Date()).month ?? 1)
        return "\(count) · \(months) month\(months == 1 ? "" : "s") of history"
    }
}

/// One linked account: "TD Chequing / ••4417 · $2,340.18".
struct AccountLine: View {
    let account: AccountsOverview.Account
    var sub: String? = nil
    var trailing: AnyView? = nil

    var body: some View {
        HStack(spacing: 12) {
            BankBadge(text: initials(account.institution ?? account.name))
            VStack(alignment: .leading, spacing: 2) {
                Text(account.name).font(Nacre.body)
                Text(sub ?? detail).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            if let trailing = trailing { trailing }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var detail: String {
        var parts: [String] = []
        if let mask = account.mask, !mask.isEmpty { parts.append("••\(mask)") }
        if let balance = account.balance {
            parts.append(Format.amount(balance) + (account.owing == true ? " owing" : ""))
        }
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
        NacreScreen(scrolls: false) {
            MessageBlock(title: title, line: line) {
                Image("ShellClosed").resizable().frame(width: 140, height: 116.7).accessibilityHidden(true)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button(primary) { Task { await again() } }
                    .buttonStyle(NacreButtonStyle())
            } secondary: {
                if case .notSupported = problem {
                    Button("Skip for now") { path.append(.skipped) }
                        .buttonStyle(NacreTextButtonStyle())
                } else {
                    Button("Choose another bank") { Task { await again() } }
                        .buttonStyle(NacreTextButtonStyle())
                }
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
        case .notSupported: return "Choose another bank, or skip for now and link later."
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

// MARK: - O-09b Any joint accounts? (O-09b2, O-09c)

@MainActor
struct JointAccountsView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @Binding var path: [SetupRoute]
    /// Home's "Which accounts do you share?" after Start over (SU-01): the
    /// same question, without setup's progress, ending back on Home.
    var onDone: (() -> Void)? = nil
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var editing: AccountsOverview.Account?
    @State private var error: String?

    var body: some View {
        NacreScreen {
            if onDone == nil { ShellProgress(part: 3, name: "Your money") }
            Text("Any joint accounts?").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("Tap one you share. We’ll only count your part.").font(Nacre.body)
            if !accounts.isEmpty {
                GlassCard {
                    ForEach(Array(accounts.enumerated()), id: \.element.id) { i, account in
                        if i > 0 { RowSeparator(inset: 60) }
                        Button { editing = account } label: {
                            AccountLine(account: account, sub: shared(account),
                                        trailing: AnyView(Image(systemName: "chevron.right")
                                            .font(.system(size: 13, weight: .semibold))))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button(onDone == nil ? "Continue" : "Done") {
                    if let onDone = onDone {
                        onDone()
                        dismiss()
                    } else {
                        path.append(.payBills)
                    }
                }
                .buttonStyle(NacreButtonStyle())
            }
        }
        .task { await load() }
        .sheet(item: $editing) { account in
            JointSheet(account: account) { await load() }
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
                .background(NacreBackground().opacity(0.35))
                .background(Pearl.page)
        }
    }

    private func shared(_ account: AccountsOverview.Account) -> String {
        guard account.joint == true else { return "Just you" }
        let people = (account.jointPeople ?? []).joined(separator: ", ")
        let share = account.jointShare.map { " · \(Int($0.rounded()))%" } ?? ""
        return people.isEmpty ? "Joint account\(share)" : "Joint with \(people)\(share)"
    }

    private func load() async {
        do {
            let overview: AccountsOverview = try await app.api.get("api/accounts/overview")
            accounts = overview.linked
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// O-09c: who it's shared with, and her share.
@MainActor
struct JointSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let account: AccountsOverview.Account
    let saved: () async -> Void
    @State private var name = ""
    @State private var share = 50
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        VStack(spacing: 0) {
            // Scrolls, so the keyboard shortens the sheet instead of squeezing
            // its rows into each other.
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(account.name).font(Nacre.title2)
                            Text("Joint account" + (account.mask.map { " · ••\($0)" } ?? "")).font(Nacre.subheadline)
                        }
                        Spacer()
                        CloseButton { dismiss() }
                    }
                    VStack(spacing: 0) {
                        FieldRow(label: "Shared with", text: $name, prompt: "Their name")
                        RowSeparator()
                        // The percentage is its own text and the stepper has no
                        // label, so the − / + sits on the row's line.
                        HStack(spacing: 12) {
                            Text("Your share").font(Nacre.body)
                            Spacer(minLength: 8)
                            Text("\(share)%").font(Nacre.body).monospacedDigit()
                            Stepper("Your share", value: $share, in: 1...99, step: 5)
                                .labelsHidden()
                                .fixedSize()
                        }
                        .padding(.horizontal, 16)
                        .frame(height: 52)
                        .accessibilityElement(children: .combine)
                    }
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Pearl.card))
                    Text("Type their name, or leave it blank. Only you can see this.").font(Nacre.footnote)
                    if let error = error { Hint(text: error) }
                }
                .padding(16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 6) {
                Button("Save") { Task { await save(joint: true) } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                Button("Not a joint account") { Task { await save(joint: false) } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .foregroundColor(Pearl.ink)
        .onAppear {
            name = account.jointPeople?.first ?? ""
            share = Int((account.jointShare ?? 50).rounded())
        }
    }

    private func save(joint: Bool) async {
        busy = true
        defer { busy = false }
        do {
            let trimmed = name.trimmingCharacters(in: .whitespaces)
            // The server refuses an empty list of people, so a blank name and
            // "Not a joint account" send none. Anyone after the first stays.
            var body: [String: Any] = ["joint_share": joint ? share as Any : NSNull()]
            if joint && !trimmed.isEmpty {
                body["joint_people"] = [trimmed] + (account.jointPeople ?? []).dropFirst()
            }
            let _: OK = try await app.api.put("api/accounts/\(account.id)/settings", body)
            await saved()
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// The round × that closes a sheet.
struct CloseButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "xmark")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Nacre.glass))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Close")
    }
}
