import SwiftUI

// Profile › Accounts (Pearl iOS Handoff File, Settings page, section
// "Accounts · THL-120 / THL-121 / THL-172"):
//
// AM-01 / C-01  every account and how it is, with a reconnect for a bank
//               that needs her (THL-120, two taps: Reconnect, Continue)
// AM-02 / AM-03 a linked account: how it counts, saved on tap; leaving it
//               out of the budget has no confirmation, just Undo (THL-121)
// AM-06         a balance added by hand, and updating it
// AM-07         removing an account, keeping or deleting its history
// C-06          a disconnected account: reconnect, keep it by hand, remove
//
// JointMergeViews.swift has what these open: AM-08 who a joint account is
// shared with, AM-09 Same account twice?, and AM-10 add a balance by hand.

// MARK: - Words

enum AccountWords {
    /// The pill for an account's status, as on the web's Accounts page.
    static func pill(_ a: AccountsOverview.Account) -> (text: String, tone: StatusPill.Tone) {
        switch a.status {
        case "sign_in": return ("Sign in again", .attention)
        case "retrying": return ("Retrying", .info)
        case "disconnected": return ("Disconnected", .neutral)
        case "joint": return (a.jointShare.map { "Joint · \(Int($0.rounded()))%" } ?? "Joint", .joint)
        case "not_counted": return ("Not in budget", .neutral)
        case "manual": return ("Manual", .neutral)
        case "investment": return ("Investment", .neutral)
        default: return a.anchor == true ? ("Anchor", .info) : ("Up to date", .positive)
        }
    }

    /// AM-01's pill: only when there's something to say, so a healthy
    /// account's row is just its name and number.
    static func listPill(_ a: AccountsOverview.Account) -> StatusPill? {
        let p = pill(a)
        return p.tone == .positive ? nil : StatusPill(text: p.text, tone: p.tone)
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

    /// "••1203 · owing", "••1203 · last updated Oct 6", "Oct 1" for a
    /// balance added by hand; the balance itself sits at the row's end.
    static func line(_ a: AccountsOverview.Account) -> String {
        let mask = (a.mask ?? "").isEmpty ? nil : "••\(a.mask!)"
        switch a.status {
        case "sign_in", "retrying":
            return [mask, a.updatedAt.map { "last updated \(when($0))" }].compactMap { $0 }.joined(separator: " · ")
        case "disconnected":
            return [mask, (a.disconnectedOn ?? a.updatedAt).map { "since \(Format.short($0))" }]
                .compactMap { $0 }.joined(separator: " · ")
        case "manual":
            return a.updatedAt.map { stale($0) ?? Format.short($0) } ?? ""
        default:
            return [mask, a.owing == true ? "owing" : nil].compactMap { $0 }.joined(separator: " · ")
        }
    }

    /// "updated 32 days ago" once a hand-added balance is a month old.
    private static func stale(_ day: String, now: Date = Date()) -> String? {
        guard let d = Format.localDay(day),
              let days = Calendar.current.dateComponents([.day], from: d, to: now).day, days >= 30 else { return nil }
        return "updated \(days) days ago"
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
            ProfileHeading(title: "Accounts", intro: updatedLine)
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
                        if i > 0 { RowSeparator(inset: 62) }
                        NavigationLink { AccountDetailView(account: a) } label: { row(a) }
                            .buttonStyle(.plain)
                    }
                }
            }
            if !added.isEmpty {
                ProfileSection("Added by you")
                GlassCard {
                    ForEach(Array(added.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator(inset: 62) }
                        NavigationLink {
                            if a.isHand {
                                ManualAccountView(account: a)
                            } else {
                                AccountDetailView(account: a)
                            }
                        } label: { row(a) }
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
            AddHandBalanceSheet { await load() }
                .background(SheetBackground())
                .presentationDetents([.height(450), .large])
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
        ProfileRow(initials: AccountWords.bank(a), title: a.name, sub: AccountWords.line(a),
                   pill: AccountWords.listPill(a)) {
            if let b = a.balance {
                Text(Format.amount(abs(b))).font(Nacre.body).foregroundColor(Pearl.ink)
                    .monospacedDigit().lineLimit(1).fixedSize()
            }
        }
    }

    /// "Updated 5 minutes ago": when the banks were last read.
    private var updatedLine: String? {
        let stamps = linked.compactMap { $0.updatedAt }.compactMap { s in ProtectView.parse(s).map { (s, $0) } }
        guard let latest = stamps.max(by: { $0.1 < $1.1 }) else {
            return loaded && linked.isEmpty ? "Link a bank, or add a balance by hand." : nil
        }
        return "Updated \(AccountWords.when(latest.0))"
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

/// AM-02: the bank's initials, the name, the balance in Fraunces and the
/// line under it, centred over the page, with its pill; then, for a linked
/// account, how far back its history goes.
struct AccountHero: View {
    let account: AccountsOverview.Account
    var note: String

    var body: some View {
        VStack(spacing: 6) {
            RowAvatar(name: AccountWords.bank(account), size: 52, font: Nacre.headline)
                .padding(.bottom, 4)
            Text(account.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            Text(account.balance.map { Format.amount(abs($0)) } ?? "—")
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(note).font(Nacre.footnote).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            let pill = AccountWords.pill(account)
            StatusPill(text: pill.text, tone: pill.tone).padding(.top, 4)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 4).padding(.bottom, 8)
        .accessibilityElement(children: .combine)

        if !account.isHand {
            GlassCard {
                fact("History from", account.historyFrom.map { Format.month(String($0.prefix(7))) } ?? "—")
                RowSeparator()
                fact("Transactions", "\(account.transactions ?? 0)")
            }
        }
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer()
            Text(value).font(Nacre.body).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 50)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - AM-02 / AM-03 / C-06 A linked account

@MainActor
struct AccountDetailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var account: AccountsOverview.Account
    @State private var counted = true
    @State private var joint = false
    @State private var anchor = false
    /// Every account, to know whether this one could be a copy of another.
    @State private var all: [AccountsOverview.Account] = []
    /// Combined away while AM-09 was open: nothing left to show here.
    @State private var gone = false
    @State private var renaming = false
    @State private var nickname = ""
    @State private var removing = false
    @State private var reconnecting = false
    @State private var busy = false
    @State private var toast: (text: String, undo: (() -> Void)?)?
    @State private var error: String?

    private var isInvestment: Bool { account.kind == "investment" }

    var body: some View {
        ProfilePage {
            heroCard
            if account.needsReconnect { reconnectBlock }
            if !counted && !isInvestment {
                Notice(text: "This account isn’t in your budget. Its transactions stay here, but they don’t count toward Allowance, spending or your totals on Home.")
            }

            ProfileSection("Settings")
            GlassCard {
                toggleRow(title: "Include in my budget",
                          sub: isInvestment ? "Spending doesn’t happen from an investment account."
                              : "Its spending, bills and balance count toward Allowance and your totals on Home.",
                          on: $counted, disabled: isInvestment) { on in Task { await setCounted(on) } }
                if !isInvestment {
                    RowSeparator()
                    toggleRow(title: "Joint account",
                              sub: "Only your share counts. You choose the share.",
                              on: $joint) { on in Task { await setJoint(on) } }
                }
                if account.canAnchor == true {
                    RowSeparator()
                    toggleRow(title: "Part of my Anchor",
                              sub: "Savings accounts only", on: $anchor) { on in Task { await setAnchor(on) } }
                }
                if joint {
                    RowSeparator()
                    NavigationLink { JointAccountView(account: account) } label: {
                        ProfileRow(title: "Shared with", sub: sharedLine)
                    }
                    .buttonStyle(.plain)
                }
                RowSeparator()
                Button { nickname = account.nickname ?? ""; renaming = true } label: {
                    ProfileRow(title: "Nickname", sub: nil) {
                        Text((account.nickname ?? "").isEmpty ? "Add" : account.nickname!)
                            .font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
                if !account.copies(among: all).isEmpty {
                    RowSeparator()
                    NavigationLink {
                        SameAccountView(account: account, all: all) { text, goneId in
                            if goneId == account.id {
                                gone = true
                            } else {
                                withAnimation { toast = (text, nil) }
                            }
                        }
                    } label: {
                        ProfileRow(title: "Same account twice?")
                    }
                    .buttonStyle(.plain)
                }
            }

            GlassCard {
                Button { removing = true } label: {
                    ProfileRow(title: "Remove this account", tone: Pearl.moneyOut, chevron: false)
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
        .onAppear {
            if gone { dismiss() } else { syncState() }
        }
        .task(id: app.version) { await refresh() }
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

    /// "Sam and Alex · your share is 50%".
    private var sharedLine: String {
        let people = (account.jointPeople ?? []).joined(separator: " and ")
        let share = account.jointShare.map { "your share is \(Int($0.rounded()))%" } ?? "all yours unless you mark it"
        return people.isEmpty ? "Add who you share it with" : "\(people) · \(share)"
    }

    private var heroCard: some View { AccountHero(account: account, note: heroNote) }

    private var heroNote: String {
        let mask = (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"
        switch account.status {
        case "disconnected":
            return "Balance on \((account.disconnectedOn ?? account.updatedAt).map { Format.short($0) } ?? "the day it disconnected")"
        default:
            // "Owing · ••1203", "Chequing · ••6612".
            return [account.owing == true ? "Owing" : AccountWords.kind(account), mask]
                .compactMap { $0 }.joined(separator: " · ")
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

    /// A setting and its switch; what it does is VoiceOver's hint.
    private func toggleRow(title: String, sub: String, on: Binding<Bool>, disabled: Bool = false,
                           changed: @escaping (Bool) -> Void) -> some View {
        Toggle(isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) })) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action)
        .disabled(disabled || busy)
        .accessibilityHint(sub)
        .padding(.horizontal, 16).frame(minHeight: 50)
    }

    // MARK: Saving (on tap: there's no Save button)

    private func syncState() {
        counted = account.counted ?? true
        joint = account.joint == true
        anchor = account.anchor == true
    }

    /// What AM-08 or AM-09 changed while they were open, and the other
    /// accounts AM-09 could combine this one with.
    private func refresh() async {
        guard let overview: AccountsOverview = try? await app.api.get("api/accounts/overview") else { return }
        all = overview.linked + (overview.added ?? [])
        if let now = all.first(where: { $0.id == account.id }) {
            account = now
            syncState()
        }
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
                        note: account.updatedAt.map { "Added by you · \(AccountWords.updatedLine($0))" } ?? "Added by you")
            Button("Update balance") { updating = true }
                .buttonStyle(SecondaryButtonStyle())
                .padding(.top, 4)

            ProfileSection("Settings")
            GlassCard {
                toggle(title: "Show on Home", sub: "Counts in your balances and totals",
                       on: $counted) { on in Task { await save(["counted": on], saying: on ? "\(account.name) shows on Home." : "\(account.name) is off Home.") } }
                if account.canAnchor == true {
                    RowSeparator()
                    toggle(title: "Part of my Anchor", sub: "Savings accounts only",
                           on: $anchor) { on in Task { await save(["anchor": on], saying: on ? "\(account.name) counts toward your Anchor." : "\(account.name) no longer counts toward your Anchor.") } }
                }
                RowSeparator()
                Button { name = account.name; renaming = true } label: {
                    ProfileRow(title: "Name") {
                        Text(account.name).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
            }
            GlassCard {
                Button { removing = true } label: {
                    ProfileRow(title: "Remove this account", tone: Pearl.moneyOut, chevron: false)
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

    private func toggle(title: String, sub: String, on: Binding<Bool>,
                        changed: @escaping (Bool) -> Void) -> some View {
        Toggle(isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) })) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action).disabled(busy)
        .accessibilityHint(sub)
        .padding(.horizontal, 16).frame(minHeight: 50)
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
