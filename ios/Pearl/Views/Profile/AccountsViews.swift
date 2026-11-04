import SwiftUI

// Profile › Accounts (Pearl iOS Handoff File, Settings page, section
// "Accounts · THL-120 / THL-121 / THL-172"):
//
// AM-01 / C-01  every account and how it is, with a reconnect for a bank
//               that needs her (THL-120, two taps: Reconnect, Continue)
// AM-02 / AM-03 a linked account: how it counts, saved on tap; leaving it
//               out of the budget has no confirmation, just Undo (THL-121)
// AM-04         a joint account's share (THL-172)
// AM-05 / AM-06 a balance added by hand, and updating it
// AM-07         removing an account, keeping or deleting its history
// C-06          a disconnected account: reconnect, keep it by hand, remove

// MARK: - Words

enum AccountWords {
    /// The pill for an account's status, as on the web's Accounts page.
    static func pill(_ a: AccountsOverview.Account) -> (text: String, tone: StatusPill.Tone) {
        switch a.status {
        case "sign_in": return ("Sign in again", .attention)
        case "retrying": return ("Retrying", .info)
        case "disconnected": return ("Disconnected", .neutral)
        case "joint": return ("Joint", .joint)
        case "not_counted": return ("Not in budget", .neutral)
        case "manual": return ("Manual", .neutral)
        case "investment": return ("Investment", .neutral)
        default: return ("Up to date", .positive)
        }
    }

    static func kind(_ a: AccountsOverview.Account) -> String {
        switch a.kind {
        case "savings": return "Savings"
        case "card": return "Credit card"
        case "loan": return "Loan"
        case "investment": return "Investment"
        default: return "Chequing"
        }
    }

    static func balance(_ a: AccountsOverview.Account) -> String? {
        guard let b = a.balance else { return nil }
        return Format.amount(abs(b)) + (a.owing == true ? " owing" : "")
    }

    /// "••4417 · $2,340.18", "••1203 · last updated Oct 6".
    static func line(_ a: AccountsOverview.Account) -> String {
        let mask = (a.mask ?? "").isEmpty ? nil : "••\(a.mask!)"
        switch a.status {
        case "sign_in", "retrying":
            return [mask, a.updatedAt.map { "last updated \(when($0))" }].compactMap { $0 }.joined(separator: " · ")
        case "disconnected":
            return [mask, (a.disconnectedOn ?? a.updatedAt).map { "since \(Format.short($0))" }]
                .compactMap { $0 }.joined(separator: " · ")
        case "manual":
            return [balance(a), a.updatedAt.map { updatedLine($0) }].compactMap { $0 }.joined(separator: " · ")
        default:
            return [mask, balance(a)].compactMap { $0 }.joined(separator: " · ")
        }
    }

    /// "5 minutes ago", "Tuesday, Oct 6".
    static func when(_ stamp: String, now: Date = Date()) -> String {
        guard let at = ProtectView.parse(stamp) ?? Format.date(stamp) else { return Format.short(stamp) }
        let minutes = max(0, Int(now.timeIntervalSince(at) / 60))
        if minutes < 1 { return "just now" }
        if minutes < 60 { return "\(minutes) minute\(minutes == 1 ? "" : "s") ago" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) hour\(hours == 1 ? "" : "s") ago" }
        return Format.short(stamp)
    }

    /// A hand-added balance: "updated October 1", or "Updated 32 days ago"
    /// once it's a month old (THL-121: stale, but no notification).
    static func updatedLine(_ day: String, now: Date = Date()) -> String {
        guard let d = Format.localDay(day) else { return "updated \(day)" }
        let days = Calendar.current.dateComponents([.day], from: d, to: now).day ?? 0
        if days >= 30 { return "updated \(days) days ago" }
        if days < 1 { return "updated today" }
        return "updated \(Format.short(day))"
    }

    static func bank(_ a: AccountsOverview.Account) -> String {
        (a.institution ?? "").isEmpty ? a.name : a.institution!
    }
}

/// "Amex Business no longer counts. Allowance is now $738.58.  Undo",
/// dropped in under the status bar for a few seconds.
struct UndoToast: View {
    let text: String
    var undo: (() -> Void)? = nil
    let done: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
            Text(text).font(Nacre.footnote).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let undo = undo {
                Button("Undo", action: undo).font(Nacre.textButton).foregroundColor(Pearl.action)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(Capsule().fill(.ultraThinMaterial))
        .background(Capsule().fill(Nacre.glass))
        .overlay(Capsule().strokeBorder(Nacre.edge, lineWidth: 1))
        .padding(.horizontal, 16).padding(.top, 4)
        .transition(.move(edge: .top).combined(with: .opacity))
        .task(id: text) {
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            done()
        }
        .accessibilityElement(children: .combine)
        .onAppear { UIAccessibility.post(notification: .announcement, argument: text) }
    }
}

// MARK: - AM-01 / C-01 Accounts

@MainActor
struct AccountsView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()
    @State private var linked: [AccountsOverview.Account] = []
    @State private var added: [AccountsOverview.Account] = []
    @State private var loaded = false
    @State private var adding = false
    @State private var reconnecting: AccountsOverview.Account?
    @State private var busy = false
    @State private var toast: String?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            ProfileHeading(eyebrow: "Profile", title: "Accounts",
                           intro: "Pearl checks your banks a few times a day. Every balance shows when it was last updated.")
            if let first = linked.first(where: { $0.needsReconnect }) {
                reconnectNotice(first)
            }
            if !loaded && error == nil {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
            }
            if !linked.isEmpty {
                ProfileSection("Linked")
                GlassCard {
                    ForEach(Array(linked.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator(inset: 64) }
                        NavigationLink { AccountDetailView(account: a) } label: { row(a) }
                            .buttonStyle(.plain)
                    }
                }
            } else if loaded {
                ProfileNote("No banks are linked yet. Link one, or add a balance by hand.")
                    .padding(.top, 8)
            }
            if !added.isEmpty {
                ProfileSection("Added by you")
                GlassCard {
                    ForEach(Array(added.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator(inset: 64) }
                        NavigationLink { ManualAccountView(account: a) } label: { row(a) }
                            .buttonStyle(.plain)
                    }
                }
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            Button("Link another bank") { Task { await link() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            Button("Add a balance by hand") { adding = true }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
        }
        .overlay(alignment: .top) {
            if let toast = toast {
                UndoToast(text: toast) { withAnimation { self.toast = nil } }
            }
        }
        .refreshable { await load() }
        .task(id: app.version) { await load() }
        .sheet(isPresented: $adding) {
            AddBalanceSheet { await load() }
                .background(SheetBackground())
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $reconnecting) { a in
            ReconnectSheet(account: a) { ok in
                reconnecting = nil
                if ok { Task { await afterReconnect(a) } }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
    }

    private func row(_ a: AccountsOverview.Account) -> some View {
        let pill = AccountWords.pill(a)
        return ProfileRow(initials: AccountWords.bank(a), title: a.name, sub: AccountWords.line(a)) {
            StatusPill(text: pill.text, tone: pill.tone)
        }
    }

    /// C-01's banner for the first bank that needs her.
    private func reconnectNotice(_ a: AccountsOverview.Account) -> some View {
        let text = a.status == "disconnected"
            ? "\(a.name) is disconnected. New transactions won’t come in until you reconnect it."
            : "\(a.name) needs you to sign in again. Its purchases since \(a.updatedAt.map { Format.short($0) } ?? "then") aren’t counted yet."
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle").font(.system(size: 15))
            VStack(alignment: .leading, spacing: 6) {
                Text(text).font(Nacre.subheadline).fixedSize(horizontal: false, vertical: true)
                Button("Reconnect") { reconnecting = a }
                    .font(Nacre.headline).foregroundColor(Pearl.action)
            }
            Spacer(minLength: 0)
        }
        .foregroundColor(Pearl.caution)
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Pearl.cautionBackground))
    }

    private func load() async {
        do {
            let overview: AccountsOverview = try await app.api.get("api/accounts/overview")
            linked = overview.linked
            added = overview.added ?? []
            error = nil
        } catch {
            self.error = app.handle(error)
        }
        loaded = true
    }

    private func link() async {
        busy = true
        defer { busy = false }
        do {
            if case .linked(let l) = try await plaid.open(api: app.api) {
                let _: LinkedItem = try await app.api.post("api/plaid/exchange",
                                                           ["public_token": l.publicToken, "institution": l.institution])
                withAnimation { toast = "Linked \(l.institution). Your transactions are on their way." }
                app.changed()
            }
        } catch {
            self.error = app.handle(error)
        }
    }

    private func afterReconnect(_ a: AccountsOverview.Account) async {
        withAnimation { toast = "\(a.name) is up to date again." }
        app.changed()
    }
}

// MARK: - C-04 Reconnect: tap 2 of 2

/// "Sign in to TD again": why, which account, and Continue to the bank.
@MainActor
struct ReconnectSheet: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()
    let account: AccountsOverview.Account
    let finished: (Bool) -> Void
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ProfileHeading(title: "Sign in to \(AccountWords.bank(account)) again",
                           intro: "Banks ask you to sign in again every so often. It’s routine, and nothing is wrong with your account.")
                .padding(.top, 28)
            GlassCard {
                ProfileRow(initials: AccountWords.bank(account), title: account.label,
                           sub: account.updatedAt.map { "Last updated \(AccountWords.when($0))" }, chevron: false)
            }
            if let error = error { Hint(text: error) }
            Spacer(minLength: 0)
            Button("Continue to \(AccountWords.bank(account))") { Task { await go() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            Button("Not now") { finished(false) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            ProfileNote("You’ll sign in through Plaid. Pearl stays read-only.", centred: true)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
    }

    private func go() async {
        guard let item = account.itemId, !item.isEmpty else {
            error = "This account isn’t linked to a bank any more. Remove it and link the bank again."
            return
        }
        busy = true
        defer { busy = false }
        do {
            switch try await plaid.open(api: app.api, itemId: item) {
            case .linked:
                let _: OK? = try? await app.api.post("api/plaid/sync", ["force": true])
                finished(true)
            case .cancelled:
                break
            case .failed(let bank), .notSupported(let bank):
                error = "\(bank) didn’t finish signing in. Try again in a minute."
            }
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - The top of an account's page

/// The bank, the name, its pill, the balance in Fraunces, and its facts.
struct AccountHero: View {
    let account: AccountsOverview.Account
    var note: String

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Initials(name: AccountWords.bank(account), size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.name).font(Nacre.headline).foregroundColor(Pearl.ink)
                    Text([(account.mask ?? "").isEmpty ? nil : "••\(account.mask!)", AccountWords.kind(account)]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                let pill = AccountWords.pill(account)
                StatusPill(text: pill.text, tone: pill.tone)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(account.balance.map { Format.amount(abs($0)) } ?? "—")
                    .font(Pearl.display(.title)).foregroundColor(Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.7)
                Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            if !account.isHand {
                Rectangle().fill(Nacre.separator).frame(height: 0.5)
                HStack(alignment: .top, spacing: 12) {
                    fact("History from", account.historyFrom.map { Format.month(String($0.prefix(7))) } ?? "—")
                    fact("Transactions", "\(account.transactions ?? 0)")
                }
            }
            }
            .padding(18)
        }
        .accessibilityElement(children: .combine)
    }

    private func fact(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted)
            Text(value).font(Nacre.subheadline).foregroundColor(Pearl.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - AM-02 / AM-03 / AM-04 / C-06 A linked account

@MainActor
struct AccountDetailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var account: AccountsOverview.Account
    @State private var counted = true
    @State private var joint = false
    @State private var anchor = false
    @State private var customShare = false
    @State private var shareText = ""
    @State private var renaming = false
    @State private var nickname = ""
    @State private var removing = false
    @State private var reconnecting = false
    @State private var busy = false
    @State private var toast: (text: String, undo: (() -> Void)?)?
    @State private var error: String?

    private var isInvestment: Bool { account.kind == "investment" }
    private var share: Int { Int((account.jointShare ?? 50).rounded()) }

    var body: some View {
        ProfilePage {
            heroCard
            if account.needsReconnect { reconnectBlock }
            if !counted && !isInvestment {
                Notice(text: "This account isn’t in your budget. Its transactions stay here, but they don’t count toward Allowance, spending or your totals on Home.")
            }

            ProfileSection("How it counts")
            GlassCard {
                toggleRow(symbol: "target", title: "Count in my budget",
                          sub: isInvestment ? "Spending doesn’t happen from an investment account."
                              : "Its spending, bills and balance count toward Allowance and your totals on Home.",
                          on: $counted, disabled: isInvestment) { on in Task { await setCounted(on) } }
                if !isInvestment {
                    RowSeparator(inset: 64)
                    toggleRow(symbol: "person.2", title: "This is a joint account",
                              sub: "Only your share counts. You choose the share.",
                              on: $joint) { on in Task { await setJoint(on) } }
                }
                if account.canAnchor == true {
                    RowSeparator(inset: 64)
                    toggleRow(symbol: "lifepreserver", title: "Counts toward my Anchor",
                              sub: "Savings accounts only", on: $anchor) { on in Task { await setAnchor(on) } }
                }
            }

            if joint { shareBlock }

            ProfileSection("Details")
            GlassCard {
                Button { nickname = account.nickname ?? ""; renaming = true } label: {
                    ProfileRow(symbol: "pencil", title: "Nickname", sub: nil) {
                        Text((account.nickname ?? "").isEmpty ? "Add" : account.nickname!)
                            .font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
            }

            GlassCard {
                Button { removing = true } label: {
                    Text("Remove this account").font(Nacre.body).foregroundColor(Pearl.action)
                        .frame(maxWidth: .infinity, minHeight: 52)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 12)
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .overlay(alignment: .top) {
            if let toast = toast {
                UndoToast(text: toast.text, undo: toast.undo) { withAnimation { self.toast = nil } }
            }
        }
        .onAppear(perform: syncState)
        .alert("Nickname", isPresented: $renaming) {
            TextField(account.name, text: $nickname)
            Button("Cancel", role: .cancel) {}
            Button("Save") { Task { await save(["nickname": nickname], saying: nil) } }
        } message: {
            Text("A name you’ll recognise. It shows everywhere in Pearl.")
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $reconnecting) {
            ReconnectSheet(account: account) { ok in
                reconnecting = false
                if ok {
                    withAnimation { toast = ("\(account.name) is up to date again.", nil) }
                    app.changed()
                }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
    }

    // MARK: Parts

    private var heroCard: some View { AccountHero(account: account, note: heroNote) }

    private var heroNote: String {
        let what = account.owing == true ? "Owing" : "Balance"
        switch account.status {
        case "disconnected":
            return "Balance on \((account.disconnectedOn ?? account.updatedAt).map { Format.short($0) } ?? "the day it disconnected")"
        default:
            return [what, account.updatedAt.map { "updated \(AccountWords.when($0))" }].compactMap { $0 }.joined(separator: " · ")
        }
    }

    /// C-04 / C-06: sign in again, or keep it as a balance by hand.
    private var reconnectBlock: some View {
        VStack(spacing: 6) {
            Notice(text: account.status == "disconnected"
                   ? "Disconnected\((account.disconnectedOn).map { " on \(Format.short($0))" } ?? ""). Your past transactions stay in Pearl, but new ones won’t come in."
                   : "\(AccountWords.bank(account)) needs you to sign in again. Purchases since \(account.updatedAt.map { Format.short($0) } ?? "then") aren’t counted yet.",
                   tone: .caution)
            Button("Reconnect") { reconnecting = true }
                .buttonStyle(NacreButtonStyle())
                .padding(.top, 6)
            if account.status == "disconnected" {
                Button("Keep it as a manual account") { Task { await keepAsManual() } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .disabled(busy)
            }
        }
    }

    /// AM-04: half, or a share she types.
    private var shareBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProfileSection("Your share")
            GlassCard {
                shareChoice("Half (50%)", selected: !customShare && share == 50) {
                    customShare = false
                    Task { await save(["joint_share": 50], saying: "Your share of \(account.name) is 50%.") }
                }
                RowSeparator()
                shareChoice("A different share", selected: customShare || share != 50) {
                    customShare = true
                    shareText = share == 50 ? "" : "\(share)"
                }
                if customShare || share != 50 {
                    RowSeparator()
                    HStack(spacing: 12) {
                        Text("Your share").font(Nacre.body).foregroundColor(Pearl.ink)
                        TextField("50", text: $shareText)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                            .font(Nacre.body).foregroundColor(Pearl.ink)
                            .accessibilityLabel("Your share, in percent")
                        Text("%").font(Nacre.body).foregroundColor(Pearl.muted)
                        Button("Save") { Task { await saveShare() } }
                            .font(Nacre.headline).foregroundColor(Pearl.action)
                            .disabled(Int(shareText) == nil)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
            ProfileNote("Between 1% and 99%. Only your share of its spending, income and balance counts. Change it any time.")
        }
    }

    private func shareChoice(_ label: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer()
                if selected {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func toggleRow(symbol: String, title: String, sub: String, on: Binding<Bool>, disabled: Bool = false,
                           changed: @escaping (Bool) -> Void) -> some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Toggle(title, isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) }))
                .labelsHidden()
                .tint(Pearl.action)
                .disabled(disabled || busy)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
    }

    // MARK: Saving (on tap: there's no Save button)

    private func syncState() {
        counted = account.counted ?? true
        joint = account.joint == true
        anchor = account.anchor == true
        customShare = joint && share != 50
    }

    @discardableResult
    private func save(_ body: [String: Any], saying: String?, undo: (() -> Void)? = nil) async -> AccountSaved? {
        busy = true
        defer { busy = false }
        do {
            let reply: AccountSaved = try await app.api.put("api/accounts/\(account.id)/settings", body)
            if let a = reply.account { account = a }
            syncState()
            error = nil
            if let saying = saying { withAnimation { toast = (saying, undo) } }
            app.changed()
            return reply
        } catch {
            self.error = app.handle(error)
            syncState()
            return nil
        }
    }

    /// AM-03: no confirmation; the toast says what changed, with Undo.
    private func setCounted(_ on: Bool) async {
        let name = account.name
        guard let reply = await save(["counted": on], saying: nil) else { return }
        let allowance = reply.safeToSpend.map { " Allowance is now \(Format.amount($0))." } ?? ""
        let text = on ? "\(name) counts again.\(allowance)" : "\(name) no longer counts.\(allowance)"
        withAnimation {
            toast = (text, { Task { await save(["counted": !on], saying: on ? "\(name) no longer counts." : "\(name) counts again.") } })
        }
    }

    private func setJoint(_ on: Bool) async {
        if on {
            await save(["joint_share": 50], saying: "Only your share of \(account.name) counts now: 50%.")
        } else {
            await save(["joint_share": NSNull()], saying: "\(account.name) is just yours again.")
        }
    }

    private func saveShare() async {
        guard let n = Int(shareText), (1...99).contains(n) else {
            error = "Enter a share between 1% and 99%."
            return
        }
        await save(["joint_share": n], saying: "Your share of \(account.name) is \(n)%.")
    }

    private func setAnchor(_ on: Bool) async {
        await save(["anchor": on], saying: on ? "\(account.name) counts toward your Anchor." : "\(account.name) no longer counts toward your Anchor.")
    }

    private func keepAsManual() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/accounts/\(account.id)/keep-as-manual")
            app.changed()
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - AM-07 Remove an account

@MainActor
struct RemoveAccountSheet: View {
    @EnvironmentObject private var app: AppModel
    let account: AccountsOverview.Account
    let finished: (Bool) -> Void
    @State private var deleteHistory = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ProfileHeading(title: "Remove \(account.name)?",
                           intro: account.isHand
                               ? "Its balance comes off Home. This can’t be undone."
                               : "Pearl stops syncing it and disconnects it from your bank straight away.")
                .padding(.top, 28)
            if !account.isHand {
                ProfileSection("Its \(account.transactions ?? 0) transactions")
                GlassCard {
                    ChoiceLine(title: "Keep them", sub: "Past months stay accurate. Nothing new comes in.",
                               selected: !deleteHistory) { deleteHistory = false }
                    RowSeparator()
                    ChoiceLine(title: "Delete them too", sub: "Your averages will change. This can’t be undone.",
                               selected: deleteHistory) { deleteHistory = true }
                }
            }
            if let error = error { Hint(text: error) }
            Spacer(minLength: 0)
            Button("Remove account") { Task { await remove() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            Button("Keep it") { finished(false) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/accounts/\(account.id)/remove",
                                               ["transactions": deleteHistory ? "delete" : "keep"])
            finished(true)
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// A choice with a line under it and a tick when it's the one (iOS has no
/// radio buttons; the Choice component's Radio type).
struct ChoiceLine: View {
    let title: String
    var sub: String? = nil
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let sub = sub {
                        Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if selected {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

// MARK: - AM-06 A balance added by hand

@MainActor
struct ManualAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var account: AccountsOverview.Account
    @State private var counted = true
    @State private var anchor = false
    @State private var updating = false
    @State private var renaming = false
    @State private var name = ""
    @State private var removing = false
    @State private var busy = false
    @State private var toast: String?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            AccountHero(account: account,
                        note: account.updatedAt.map { "You \(AccountWords.updatedLine($0))" } ?? "Added by you")
            Button("Update balance") { updating = true }
                .buttonStyle(SecondaryButtonStyle())
                .padding(.top, 4)
            ProfileNote("Added by you. Pearl can’t see its transactions, so it only shows in your balances on Home.")

            ProfileSection("How it counts")
            GlassCard {
                toggle(symbol: "house", title: "Show on Home", sub: "Counts in your balances and totals",
                       on: $counted) { on in Task { await save(["counted": on], saying: on ? "\(account.name) shows on Home." : "\(account.name) is off Home.") } }
                if account.canAnchor == true {
                    RowSeparator(inset: 64)
                    toggle(symbol: "lifepreserver", title: "Counts toward my Anchor", sub: "Savings accounts only",
                           on: $anchor) { on in Task { await save(["anchor": on], saying: on ? "\(account.name) counts toward your Anchor." : "\(account.name) no longer counts toward your Anchor.") } }
                }
            }

            ProfileSection("Details")
            GlassCard {
                Button { name = account.name; renaming = true } label: {
                    ProfileRow(symbol: "pencil", title: "Name") {
                        Text(account.name).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
            }
            GlassCard {
                Button { removing = true } label: {
                    Text("Remove this account").font(Nacre.body).foregroundColor(Pearl.action)
                        .frame(maxWidth: .infinity, minHeight: 52)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 12)
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .overlay(alignment: .top) {
            if let toast = toast { UndoToast(text: toast) { withAnimation { self.toast = nil } } }
        }
        .onAppear { counted = account.counted ?? true; anchor = account.anchor == true }
        .alert("Name", isPresented: $renaming) {
            TextField("Name", text: $name)
            Button("Cancel", role: .cancel) {}
            Button("Save") { Task { await save(["nickname": name], saying: nil) } }
        }
        .sheet(isPresented: $updating) {
            UpdateBalanceSheet(account: account) { a in
                updating = false
                if let a = a {
                    account = a
                    withAnimation { toast = "Updated. \(a.name) is \(a.balance.map { Format.amount($0) } ?? "saved")." }
                    app.changed()
                }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
    }

    private func toggle(symbol: String, title: String, sub: String, on: Binding<Bool>,
                        changed: @escaping (Bool) -> Void) -> some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Toggle(title, isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) }))
                .labelsHidden().tint(Pearl.action).disabled(busy)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
    }

    private func save(_ body: [String: Any], saying: String?) async {
        busy = true
        defer { busy = false }
        do {
            let reply: AccountSaved = try await app.api.put("api/accounts/\(account.id)/settings", body)
            if let a = reply.account { account = a }
            counted = account.counted ?? true
            anchor = account.anchor == true
            error = nil
            if let saying = saying { withAnimation { toast = saying } }
            app.changed()
        } catch {
            self.error = app.handle(error)
            counted = account.counted ?? true
            anchor = account.anchor == true
        }
    }
}

/// AM-06's "Update balance": what it holds today.
@MainActor
struct UpdateBalanceSheet: View {
    @EnvironmentObject private var app: AppModel
    let account: AccountsOverview.Account
    let finished: (AccountsOverview.Account?) -> Void
    @State private var balance = ""
    @State private var busy = false
    @State private var error: String?

    private struct Reply: Decodable { let account: AccountsOverview.Account? }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ProfileHeading(title: "Update \(account.name)", intro: "What it holds today. Pearl shows it on Home from now on.")
                .padding(.top, 28)
            AmountField(label: "Balance today", text: $balance)
            if let error = error { Hint(text: error) }
            Spacer(minLength: 0)
            Button("Save balance") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(balance.isEmpty || busy)
            Button("Cancel") { finished(nil) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .onAppear { balance = account.balance.map { String(format: "%.2f", abs($0)) } ?? "" }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let reply: Reply = try await app.api.put("api/accounts/\(account.id)/balance", ["balance": balance])
            finished(reply.account)
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// "$ 3,000.00": a money field with the design system's Input look.
struct AmountField: View {
    let label: String
    @Binding var text: String
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.ink)
            HStack(spacing: 4) {
                Text("$").foregroundColor(Pearl.muted)
                TextField("0.00", text: $text).keyboardType(.decimalPad).focused($focused)
                    .foregroundColor(Pearl.ink)
            }
            .font(Nacre.body)
            .padding(.horizontal, 16).frame(height: 52)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(focused ? Pearl.action : Nacre.edge, lineWidth: focused ? 1.5 : 1))
            .accessibilityLabel(label)
        }
    }
}

// MARK: - AM-05 Add a balance by hand

@MainActor
struct AddBalanceSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let added: () async -> Void
    @State private var name = ""
    @State private var kind = "savings"
    @State private var last4 = ""
    @State private var balance = ""
    @State private var busy = false
    @State private var error: String?

    private let kinds: [(id: String, title: String, sub: String?)] = [
        ("chequing", "Chequing", nil),
        ("savings", "Savings", "Can count toward your Anchor"),
        ("investment", "Investment", "Not part of your Anchor"),
        ("credit", "Credit card", "Counts as money you owe"),
    ]

    private var canAdd: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && !balance.isEmpty
            && (last4.isEmpty || last4.count == 4)
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top) {
                        ProfileHeading(title: "Add a balance by hand",
                                       intro: "For a bank Pearl can’t link yet. The balance shows on Home. Transactions won’t come in, so it won’t change your spending.")
                        CloseButton { dismiss() }
                    }
                    .padding(.top, 20)
                    LabeledText(label: "Name", text: $name, prompt: "Meridian Savings")
                    ProfileSection("Type")
                    GlassCard {
                        ForEach(Array(kinds.enumerated()), id: \.element.id) { i, k in
                            if i > 0 { RowSeparator() }
                            ChoiceLine(title: k.title, sub: k.sub, selected: kind == k.id) { kind = k.id }
                        }
                    }
                    if kind == "savings" || kind == "investment" {
                        LabeledText(label: "Last four digits (optional)", text: $last4, prompt: "5521",
                                    hint: "Transfers to an account ending in these digits are sorted as Saved automatically.",
                                    numbers: true)
                    }
                    AmountField(label: "Balance today", text: $balance)
                    if let error = error { Hint(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 6) {
                Button("Add account") { Task { await add() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(!canAdd || busy)
                Button("Cancel") { dismiss() }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .onChange(of: last4) { v in
            let digits = String(v.filter(\.isNumber).prefix(4))
            if digits != v { last4 = digits }
        }
    }

    private func add() async {
        busy = true
        defer { busy = false }
        do {
            var body: [String: Any] = ["name": name, "kind": kind, "balance": balance]
            if kind == "savings" || kind == "investment", !last4.isEmpty { body["last4"] = last4 }
            let _: OK = try await app.api.post("api/accounts/manual", body)
            app.changed()
            await added()
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// A plain text field with the Input look: label above, hint below.
struct LabeledText: View {
    let label: String
    @Binding var text: String
    var prompt = ""
    var hint: String? = nil
    var numbers = false
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.ink)
            TextField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                .keyboardType(numbers ? .numberPad : .default)
                .textInputAutocapitalization(numbers ? .never : .words)
                .focused($focused)
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .padding(.horizontal, 16).frame(height: 52)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(focused ? Pearl.action : Nacre.edge, lineWidth: focused ? 1.5 : 1))
                .accessibilityLabel(label)
            if let hint = hint {
                Text(hint).font(Nacre.footnote).foregroundColor(Pearl.muted).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
