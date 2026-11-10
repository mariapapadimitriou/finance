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
    static func line(_ a: AccountsOverview.Account, states: Bool = false) -> String {
        let mask = (a.mask ?? "").isEmpty ? nil : "••\(a.mask!)"
        switch a.status {
        case "sign_in":
            return a.updatedAt.map { "Since \(Format.short($0))" } ?? (mask ?? "")
        case "retrying":
            return a.updatedAt.map { when($0).capitalizedFirst } ?? (mask ?? "")
        case "disconnected":
            return (a.disconnectedOn ?? a.updatedAt).map { "Since \(Format.short($0))" } ?? (mask ?? "")
        case "manual":
            return a.updatedAt.map { stale($0) ?? Format.short($0) } ?? ""
        default:
            // C-01: while a bank needs her, every row says how it's doing.
            if states { return "Up to date" }
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

    /// C-01: some bank needs her or isn't responding.
    static func trouble(_ a: AccountsOverview.Account) -> Bool {
        ["sign_in", "retrying", "disconnected"].contains(a.status ?? "")
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
    /// Stays until something replaces it, rather than leaving after a few seconds.
    var stays = false
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
        .swipeToDismiss(done)
        .transition(.move(edge: .top).combined(with: .opacity))
        .task(id: text) {
            guard !stays else { return }
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            done()
        }
        .accessibilityElement(children: .combine)
        .onAppear { UIAccessibility.post(notification: .announcement, argument: text) }
    }
}

/// Every toast closes with a swipe, whichever way (THL-254), as well as on
/// its own after a few seconds.
struct SwipeToDismiss: ViewModifier {
    let onDismiss: () -> Void
    @State private var offset: CGSize = .zero

    func body(content: Content) -> some View {
        content
            .offset(offset)
            .opacity(1 - min(0.5, Double(max(abs(offset.width), abs(offset.height))) / 240))
            .gesture(
                DragGesture(minimumDistance: 6)
                    .onChanged { offset = $0.translation }
                    .onEnded { v in
                        let moved = max(abs(v.translation.width), abs(v.translation.height))
                        let flung = max(abs(v.predictedEndTranslation.width), abs(v.predictedEndTranslation.height))
                        if moved > 44 || flung > 120 {
                            withAnimation(.easeOut(duration: 0.2)) { onDismiss() }
                        } else {
                            withAnimation(.spring()) { offset = .zero }
                        }
                    }
            )
            .accessibilityAction(named: "Dismiss") { withAnimation { onDismiss() } }
    }
}

extension View {
    func swipeToDismiss(_ onDismiss: @escaping () -> Void) -> some View {
        modifier(SwipeToDismiss(onDismiss: onDismiss))
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
            ProfileHeading(title: "Accounts", intro: states ? nil : updatedLine)
            if let first = linked.first(where: { $0.needsReconnect }) {
                ConnectionBanner(account: first) { reconnecting = first }
            }
            if !loaded && error == nil {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
            }
            if !linked.isEmpty {
                ProfileSection("Linked")
                GlassCard {
                    ForEach(Array(linked.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator(inset: 62) }
                        NavigationLink {
                            if a.status == "disconnected" {
                                DisconnectedAccountView(account: a)
                            } else {
                                AccountDetailView(account: a)
                            }
                        } label: { row(a) }
                        .buttonStyle(.plain)
                    }
                }
                if states { ProfileNote("If a bank isn’t responding, Pearl keeps trying.") }
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
            if states {
                // C-01: Reconnect is the one primary action on the page.
                Button("Link another bank") { Task { await link() } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .disabled(busy)
            } else {
                Button("Link another bank") { Task { await link() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy)
                Button("Add a balance by hand") { adding = true }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
        .overlay(alignment: .top) {
            if let toast = toast {
                UndoToast(text: toast) { withAnimation { self.toast = nil } }
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .onAppear(perform: showNotice)
        .onChange(of: app.accountsNotice) { _ in showNotice() }
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

    /// AM-13: what the page it came back from did.
    private func showNotice() {
        guard let notice = app.accountsNotice else { return }
        app.accountsNotice = nil
        withAnimation { toast = notice }
    }

    /// C-01: a bank needs her or isn't responding, so the rows say how each
    /// is doing instead of their balances.
    private var states: Bool { linked.contains(where: AccountWords.trouble) }

    private func row(_ a: AccountsOverview.Account) -> some View {
        ProfileRow(initials: AccountWords.bank(a), title: a.name, sub: AccountWords.line(a, states: states),
                   pill: AccountWords.listPill(a)) {
            if !states, let b = a.balance {
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

/// C-01's card for a bank that needs her: what's wrong, and Reconnect.
struct ConnectionBanner: View {
    let account: AccountsOverview.Account
    let reconnect: () -> Void

    var body: some View {
        GlassCard {
            VStack(spacing: 14) {
                HStack(spacing: 12) {
                    IconBubble(symbol: "arrow.triangle.2.circlepath")
                    Text(text).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Button("Reconnect", action: reconnect)
                    .buttonStyle(NacreButtonStyle())
            }
            .padding(16)
        }
    }

    private var text: String {
        account.status == "disconnected"
            ? "\(account.name) is disconnected."
            : "\(account.name) needs you to sign in again."
    }
}

extension String {
    /// "6 hours ago" → "6 hours ago"; "just now" → "Just now".
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}

// MARK: - C-04 Reconnect: tap 2 of 2

/// "Sign in to TD again": why, which account, and Continue to the bank.
@MainActor
struct ReconnectSheet: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()
    let bank: String
    let label: String
    let itemId: String?
    let updatedAt: String?
    let finished: (Bool) -> Void

    init(account: AccountsOverview.Account, finished: @escaping (Bool) -> Void) {
        self.init(bank: AccountWords.bank(account), label: account.label, itemId: account.itemId,
                  updatedAt: account.updatedAt, finished: finished)
    }

    init(bank: String, label: String, itemId: String?, updatedAt: String?, finished: @escaping (Bool) -> Void) {
        self.bank = bank
        self.label = label
        self.itemId = itemId
        self.updatedAt = updatedAt
        self.finished = finished
    }
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ProfileHeading(title: "Sign in to \(bank) again",
                           intro: "Banks ask you to sign in again every so often. It’s routine, and nothing is wrong with your account.")
                .padding(.top, 28)
            GlassCard {
                ProfileRow(initials: bank, title: label,
                           sub: updatedAt.map { "Last updated \(AccountWords.when($0))" }, chevron: false)
            }
            if let error = error { Hint(text: error) }
            Spacer(minLength: 0)
            Button("Continue to \(bank)") { Task { await go() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            Button("Not now") { finished(false) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            ProfileNote("You’ll sign in through Plaid. Pearl stays read-only.", centred: true)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
    }

    private func go() async {
        guard let item = itemId, !item.isEmpty else {
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
    /// C-06 shows its own facts.
    var facts = true

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

        if facts && !account.isHand {
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
    /// AM-12: removing the whole bank.
    @State private var removingBank = false
    @State private var busy = false
    @State private var toast: (text: String, undo: (() -> Void)?)?
    @State private var error: String?
    /// AM-08n (JOINT-B): turning Joint off with split purchases on it asks first.
    @State private var notJoint: [JointChange]?

    private var isInvestment: Bool { account.kind == "investment" }

    var body: some View {
        ProfilePage {
            heroCard
            if account.needsReconnect {
                ConnectionBanner(account: account) { reconnecting = true }
            }
            if joint {
                // AM-04: who it's shared with, under the balance.
                GlassCard {
                    NavigationLink { JointAccountView(account: account) } label: {
                        ProfileRow(title: "Shared with") {
                            Text(people).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                        }
                    }
                    .buttonStyle(.plain)
                }
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
                if sameBank.count > 1 {
                    // AM-11 (THL-262): every account on this bank login at once.
                    RowSeparator()
                    Button { removingBank = true } label: {
                        ProfileRow(title: "Remove \(AccountWords.bank(account)) entirely · \(sameBank.count == 2 ? "both accounts" : "all \(sameBank.count) accounts")",
                                   tone: Pearl.moneyOut, chevron: false)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
            }
            .padding(.top, 12)
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .sheet(isPresented: Binding(get: { notJoint != nil }, set: { if !$0 { notJoint = nil; syncState() } })) {
            if let changes = notJoint {
                JointChangeSheet(accountName: account.name, share: nil, was: nil, holders: account.jointPeople ?? [],
                                 changes: changes, onClose: { notJoint = nil; syncState() }) {
                    let reply: JointReply = try await app.api.put("api/accounts/\(account.id)/settings",
                                                                  ["joint_share": NSNull(), "confirm": true])
                    if let a = reply.account { account = a }
                    notJoint = nil
                    syncState()
                    app.changed()
                    let undo = reply.undo
                    withAnimation {
                        toast = ("\(account.name) isn’t joint any more. Your splits stay.", undo.map { u in {
                            Task {
                                guard let body = u.any as? [String: Any] else { return }
                                let _: OK? = try? await app.api.post("api/transactions/undo", body)
                                await refresh()
                                app.changed()
                            }
                        } })
                    }
                }
            }
        }
        .sheet(isPresented: $removingBank) {
            RemoveBankSheet(bank: AccountWords.bank(account), itemId: account.itemId ?? "", accounts: sameBank) { removed in
                removingBank = false
                if removed { app.changed(); dismiss() }
            }
            .background(SheetBackground())
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
        .overlay(alignment: .bottom) {
            // AM-03: the toast sits at the bottom, with Undo.
            if let toast = toast {
                UndoToast(text: toast.text, undo: toast.undo) { withAnimation { self.toast = nil } }
                    .padding(.bottom, 8)
            }
        }
        .onAppear {
            if gone { dismiss() } else { syncState() }
        }
        .reloads { await refresh() }
        .alert("Nickname", isPresented: $renaming) {
            TextField(account.name, text: $nickname)
            Button("Cancel", role: .cancel) {}
            Button("Save") { Task { await save(["nickname": nickname], saying: nil) } }
        } message: {
            Text("A name you’ll recognise. It shows everywhere in Pearl.")
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account, lastAtBank: sameBank.count == 1) { removed in
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

    /// Every linked account on this one's bank login.
    private var sameBank: [AccountsOverview.Account] {
        guard let item = account.itemId, !item.isEmpty else { return [] }
        return all.filter { $0.itemId == item }
    }

    /// "Sam and Alex", or "Add" before she's said.
    private var people: String {
        let names = (account.jointPeople ?? []).joined(separator: " and ")
        return names.isEmpty ? "Add" : names
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
        guard await save(["counted": on], saying: nil) != nil else { return }
        let text = on ? "\(name) is back in your budget." : "\(name) left your budget."
        withAnimation {
            toast = (text, { Task { await save(["counted": !on], saying: on ? "\(name) left your budget." : "\(name) is back in your budget.") } })
        }
    }

    private func setJoint(_ on: Bool) async {
        if on {
            await save(["joint_share": 50], saying: "Only your share of \(account.name) counts now: 50%.")
        } else {
            // AM-08n: split purchases on it are asked about first.
            do {
                let reply: JointReply = try await app.api.put("api/accounts/\(account.id)/settings", ["joint_share": NSNull()])
                if reply.needsConfirm == true {
                    notJoint = reply.changes ?? []
                    return
                }
                if let a = reply.account { account = a }
                syncState()
                error = nil
                app.changed()
                withAnimation { toast = ("\(account.name) is just yours again.", nil) }
            } catch {
                self.error = app.handle(error)
                syncState()
            }
        }
    }

    private func setAnchor(_ on: Bool) async {
        await save(["anchor": on], saying: on ? "\(account.name) counts toward your Anchor." : "\(account.name) no longer counts toward your Anchor.")
    }

}

// MARK: - AM-07 Remove an account

/// "Remove TD Visa?": the account, then keep or delete its transactions.
@MainActor
struct RemoveAccountSheet: View {
    @EnvironmentObject private var app: AppModel
    let account: AccountsOverview.Account
    /// C-06's "Remove it and its history" starts on Delete.
    var deleting = false
    /// AM-07b: the last account on its bank login, so the bank goes too.
    var lastAtBank = false
    let finished: (Bool) -> Void
    @State private var deleteHistory = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text("Remove \(account.name)?").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .lineLimit(1).accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { finished(false) } }
            .padding(.top, 20)
            HStack(spacing: 12) {
                RowAvatar(name: AccountWords.bank(account), size: 48, font: Nacre.headline)
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    Text(detail).font(Nacre.footnote).foregroundColor(Pearl.ink)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            if account.isHand {
                ProfileNote("Its balance comes off Home. This can’t be undone.")
            } else {
                GlassCard {
                    ChoiceLine(title: "Keep its transactions", sub: "Past months stay the same",
                               selected: !deleteHistory) { deleteHistory = false }
                    RowSeparator()
                    ChoiceLine(title: "Delete them too", sub: "This can’t be undone",
                               selected: deleteHistory) { deleteHistory = true }
                }
            }
            if let error = error { Hint(text: error) }
            Spacer(minLength: 0)
            Button("Remove account") { Task { await remove() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .onAppear { deleteHistory = deleting }
    }

    /// "••1203 · 388 transactions", or a balance by hand's amount.
    private var detail: String {
        let mask = (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"
        if account.isHand {
            return [mask, account.balance.map { Format.amount(abs($0)) }].compactMap { $0 }.joined(separator: " · ")
        }
        let n = account.transactions ?? 0
        let last = lastAtBank ? "the last \(AccountWords.bank(account)) account, so \(AccountWords.bank(account)) is disconnected too" : nil
        return [mask, "\(n.formatted()) transaction\(n == 1 ? "" : "s")", last].compactMap { $0 }.joined(separator: " · ")
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

// MARK: - C-06 A disconnected account

/// "Wealthsimple Cash · Balance on Oct 1 · Disconnected": what Pearl still
/// has, and three ways on: reconnect it, keep it as a balance by hand, or
/// remove it and its history.
@MainActor
struct DisconnectedAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let account: AccountsOverview.Account
    /// AM-07b: no other account on its bank login.
    @State private var lastAtBank = false
    @State private var reconnecting = false
    @State private var removing = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        ProfilePage {
            AccountHero(account: account, note: note, facts: false)
            GlassCard {
                fact("In Pearl", "\((account.transactions ?? 0).formatted()) transactions")
                RowSeparator()
                fact("History from", account.historyFrom.map { Format.month(String($0.prefix(7))) } ?? "—")
            }
            GlassCard {
                Button { removing = true } label: {
                    ProfileRow(title: "Remove it and its history", tone: Pearl.moneyOut, chevron: false)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 4)
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            Button("Reconnect") { reconnecting = true }
                .buttonStyle(NacreButtonStyle())
                .disabled(busy)
            Button("Keep as a manual account") { Task { await keepAsManual() } }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(busy)
        }
        .task {
            if let o: AccountsOverview = try? await app.api.get("api/accounts/overview"), let item = account.itemId {
                lastAtBank = (o.linked + (o.added ?? [])).filter { $0.itemId == item }.count <= 1
            }
        }
        .sheet(isPresented: $reconnecting) {
            ReconnectSheet(account: account) { ok in
                reconnecting = false
                if ok { app.changed(); dismiss() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account, deleting: true, lastAtBank: lastAtBank) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
    }

    /// "Balance on Oct 1 · ••7710".
    private var note: String {
        let mask = (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"
        let on = (account.disconnectedOn ?? account.updatedAt).map { "Balance on \(Format.short($0))" }
        return [on ?? "Balance when it disconnected", mask].compactMap { $0 }.joined(separator: " · ")
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

// MARK: - AM-12 Remove a bank entirely

/// "Remove TD entirely?": the accounts on the login, keep or delete their
/// transactions, then Remove TD. The login is revoked at Plaid, so the bank
/// can be linked again from scratch (THL-262).
@MainActor
struct RemoveBankSheet: View {
    @EnvironmentObject private var app: AppModel
    let bank: String
    let itemId: String
    let accounts: [AccountsOverview.Account]
    let finished: (Bool) -> Void
    @State private var deleteHistory = false
    @State private var busy = false
    @State private var error: String?

    private struct Reply: Decodable { let accounts: Int? }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text("Remove \(bank) entirely?").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .lineLimit(1).accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { finished(false) } }
            .padding(.top, 20)
            HStack(spacing: 12) {
                RowAvatar(name: bank, size: 48, font: Nacre.headline)
                VStack(alignment: .leading, spacing: 2) {
                    Text(bank).font(Nacre.title2).foregroundColor(Pearl.ink)
                    Text("\(accounts.count) accounts · Pearl disconnects \(bank) so it can be linked again from scratch")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            ScrollView {
                VStack(spacing: 12) {
                    GlassCard {
                        ForEach(Array(accounts.enumerated()), id: \.element.id) { i, a in
                            if i > 0 { RowSeparator(inset: 62) }
                            ProfileRow(initials: bank, title: a.name,
                                       sub: (a.mask ?? "").isEmpty ? AccountWords.kind(a) : "••\(a.mask!)", chevron: false)
                        }
                    }
                    GlassCard {
                        ChoiceLine(title: "Keep their transactions", sub: "Past months stay the same",
                                   selected: !deleteHistory) { deleteHistory = false }
                        RowSeparator()
                        ChoiceLine(title: "Delete them too", sub: "This can’t be undone",
                                   selected: deleteHistory) { deleteHistory = true }
                    }
                }
            }
            if let error = error { Hint(text: error) }
            Button("Remove \(bank)") { Task { await remove() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || itemId.isEmpty)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            let reply: Reply = try await app.api.post("api/banks/\(itemId)/remove",
                                                      ["transactions": deleteHistory ? "delete" : "keep"])
            let n = reply.accounts ?? accounts.count
            // AM-13, said on Accounts once this page has closed.
            app.accountsNotice = "\(bank) is removed. Its \(n) account\(n == 1 ? " is" : "s are") off your Accounts."
            finished(true)
        } catch {
            self.error = app.handle(error)
        }
    }
}
