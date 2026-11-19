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

/// "Amex Business no longer counts. Allowance is now $738.58.  Undo".
/// UN-01 (Paybacks & undo, 1396:4365, note 1397:4699): the one Undo look,
/// PearlToast's ink (inverse in dark mode), at the bottom, never the top.
/// Every caller keeps its words and its Undo; this draws them.
struct UndoToast: View {
    let text: String
    var undo: (() -> Void)? = nil
    /// Stays until something replaces it, rather than leaving after a few seconds.
    var stays = false
    /// UN-01: the info icon for "Couldn’t undo" and other failures.
    var failed = false
    let done: () -> Void
    @State private var model: PearlToast.Model

    init(text: String, undo: (() -> Void)? = nil, stays: Bool = false, failed: Bool = false,
         done: @escaping () -> Void) {
        self.text = text
        self.undo = undo
        self.stays = stays
        self.failed = failed
        self.done = done
        _model = State(initialValue: PearlToast.Model(text: text, action: undo == nil ? nil : "Undo",
                                                      failed: failed, run: undo))
    }

    var body: some View {
        PearlToast(model: model, stays: stays, done: done)
            .onChange(of: text) { t in
                model = PearlToast.Model(text: t, action: undo == nil ? nil : "Undo", failed: failed, run: undo)
            }
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

// MARK: - AM-01 / C-01 Accounts (G5-Accounts, G5-Load)

@MainActor
struct AccountsView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()
    @State private var linked: [AccountsOverview.Account] = []
    @State private var added: [AccountsOverview.Account] = []
    @State private var loaded = false
    @State private var adding = false
    /// G5-Accounts "Add an account": a Pearl sheet, not the stock menu.
    @State private var choosingAdd = false
    @State private var afterAdd: AddChoice?
    @State private var reconnecting: AccountsOverview.Account?
    @State private var busy = false
    @State private var toast: String?
    @State private var error: String?

    enum AddChoice { case link, hand }

    var body: some View {
        ProfilePage(navTrailing: AnyView(APGlassButton(symbol: "plus", label: "Add an account") { choosingAdd = true }
            .accessibilityIdentifier("accounts-add"))) {
            ProfileHeading(title: "Accounts")
            content
        }
        .overlay(alignment: .bottom) {
            // UN-01: the toast sits at the bottom.
            if let toast = toast {
                UndoToast(text: toast) { withAnimation { self.toast = nil } }
                    .padding(.bottom, 12)
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .onAppear(perform: showNotice)
        .onChange(of: app.accountsNotice) { _ in showNotice() }
        .sheet(isPresented: $choosingAdd, onDismiss: runAdd) {
            AddAccountSheet { choice in
                afterAdd = choice
                choosingAdd = false
            } close: { choosingAdd = false }
        }
        .sheet(isPresented: $adding) {
            AddHandBalanceSheet { await load() }
                .background(SheetBackground())
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $reconnecting) { a in
            ReconnectSheet(account: a) { ok in
                reconnecting = nil
                if ok { Task { await afterReconnect(a) } }
            }
        }
    }

    @ViewBuilder private var content: some View {
        if !loaded && error == nil {
            // G5-Load: rows hold their place.
            ProfileSection(" ")
            APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }
            ProfileSection(" ")
            APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }
        } else if let error = error, linked.isEmpty && added.isEmpty {
            APEmptyState(title: "Couldn\u{2019}t load your accounts", line: error, top: 120) {
                IconBubble(symbol: "exclamationmark.triangle", kind: .warn)
            } actions: {
                Button("Try again") { Task { await load() } }.buttonStyle(APSecondaryButtonStyle())
            }
        } else if linked.isEmpty && added.isEmpty {
            APEmptyState(title: "No accounts yet", line: "Link a bank and Pearl does the sorting.", top: 90) {
                APMark(width: 120)
            } actions: {
                VStack(spacing: 4) {
                    Button("Link a bank") { Task { await link() } }
                        .buttonStyle(APPrimaryButtonStyle(busy: busy))
                        .disabled(busy)
                    APQuietButton(title: "Add a balance by hand") { adding = true }
                }
            }
        } else {
            if let first = linked.first(where: { $0.needsReconnect }) {
                ConnectionBanner(account: first) { reconnecting = first }
                    .padding(.top, 8)
            }
            ForEach(banks, id: \.self) { bank in
                ProfileSection(bank)
                APCard {
                    let rows = linked.filter { AccountWords.bank($0) == bank }
                    ForEach(Array(rows.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { APSeparator() }
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
            }
            if !added.isEmpty {
                ProfileSection("Added by you")
                APCard {
                    ForEach(Array(added.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { APSeparator() }
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
            if let error = error { APErrorLine(text: error).padding(.top, 8) }
            Color.clear.frame(height: 40)
        }
    }

    /// Each bank once, in the order the server lists them.
    private var banks: [String] {
        var seen: [String] = []
        for a in linked where !seen.contains(AccountWords.bank(a)) { seen.append(AccountWords.bank(a)) }
        return seen
    }

    /// The Add an account sheet has gone: now Plaid, or the hand-added balance.
    private func runAdd() {
        guard let choice = afterAdd else { return }
        afterAdd = nil
        switch choice {
        case .link: Task { await link() }
        case .hand: adding = true
        }
    }

    /// AM-13: what the page it came back from did.
    private func showNotice() {
        guard let notice = app.accountsNotice else { return }
        app.accountsNotice = nil
        withAnimation { toast = notice }
    }

    /// G5-Accounts: face, name over "••2210" (and its pill), the balance on
    /// the right edge; a disconnected account's balance is muted.
    private func row(_ a: AccountsOverview.Account) -> some View {
        ProfileRow(initials: AccountWords.bank(a), title: a.name, sub: AccountWords.line(a),
                   pill: AccountWords.listPill(a)) {
            if let b = a.balance {
                Text(Format.amount(abs(b))).font(Nacre.headline)
                    .foregroundColor(a.status == "disconnected" ? Pearl.muted : Pearl.ink)
                    .monospacedDigit().lineLimit(1).fixedSize()
            }
        }
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
                withAnimation { toast = "\(l.institution) is linked." }
                app.changed()
                await load()
            }
        } catch {
            self.error = app.handle(error)
        }
    }

    private func afterReconnect(_ a: AccountsOverview.Account) async {
        withAnimation { toast = "\(a.name) is up to date." }
        app.changed()
    }
}

/// G5-Accounts "Add an account": Link a bank, or add a balance by hand.
struct AddAccountSheet: View {
    let pick: (AccountsView.AddChoice) -> Void
    let close: () -> Void

    var body: some View {
        PearlSheet {
            APSheetTitle(title: "Add an account", close: close)
            APCard {
                Button { pick(.link) } label: {
                    ProfileRow(symbol: "building.columns", title: "Link a bank", sub: "Read-only, through Plaid")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("add-link-bank")
                APSeparator()
                Button { pick(.hand) } label: {
                    ProfileRow(symbol: "square.and.pencil", title: "Add a balance by hand",
                               sub: "For a bank Pearl can\u{2019}t link yet")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("add-by-hand")
            }
        }
    }
}

/// C-01's banner for a bank that needs her, with Reconnect at its end.
struct ConnectionBanner: View {
    let account: AccountsOverview.Account
    let reconnect: () -> Void

    var body: some View {
        APBanner(text: text, action: "Reconnect", act: reconnect)
            .accessibilityIdentifier("accounts-reconnect")
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
        PearlSheet {
            APSheetTitle(title: "Sign in to \(bank) again") { finished(false) }
            APWho(face: bank, name: label, line: updatedAt.map { "Last updated \(AccountWords.when($0))" })
            Text("Banks ask for this every so often. Nothing is wrong with your account.")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let error = error { APErrorLine(text: error) }
        } footer: {
            VStack(spacing: 0) {
                PearlSheetButtons(primary: "Continue to \(bank)", busy: busy, secondary: "Not now",
                                  onPrimary: { Task { await go() } }, onSecondary: { finished(false) })
                ProfileNote("Read-only, through Plaid", centred: true).padding(.bottom, 8)
            }
        }
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
        APHero(face: AccountWords.bank(account), name: account.name,
               amount: account.balance.map { Format.amount(abs($0)) } ?? "\u{2014}",
               amountTone: account.status == "disconnected" ? Pearl.muted : Pearl.ink,
               lines: [note], pill: heroPill)
            .padding(.top, 8)

        if facts && !account.isHand {
            APCard {
                APKeyValueRow(key: "History from", value: account.historyFrom.map { Format.month(String($0.prefix(7))) } ?? "\u{2014}")
                APSeparator(afterFace: false)
                APKeyValueRow(key: "Transactions", value: "\(account.transactions ?? 0)")
            }
            .padding(.top, 10)
        }
    }

    /// G5-Account: "Up to date" when it counts, "Not in your budget" when it doesn't.
    private var heroPill: StatusPill {
        if account.counted == false && !account.isHand { return StatusPill(text: "Not in your budget", tone: .neutral) }
        let p = AccountWords.pill(account)
        return StatusPill(text: p.text, tone: p.tone)
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
                APCard {
                    NavigationLink { JointAccountView(account: account) } label: {
                        ProfileRow(title: "Shared with") {
                            Text(people).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            ProfileSection("Settings")
            APCard {
                toggleRow(title: "Include in my budget",
                          sub: isInvestment ? "Not for an investment account" : "Counts toward your Allowance",
                          on: $counted, disabled: isInvestment) { on in Task { await setCounted(on) } }
                if !isInvestment {
                    APSeparator(afterFace: false)
                    toggleRow(title: "Shared with someone",
                              sub: "Only your share counts",
                              on: $joint) { on in Task { await setJoint(on) } }
                }
                if account.canAnchor == true {
                    APSeparator(afterFace: false)
                    toggleRow(title: "Part of my Anchor",
                              sub: "Savings accounts only", on: $anchor) { on in Task { await setAnchor(on) } }
                }
                APSeparator(afterFace: false)
                Button { nickname = account.nickname ?? ""; renaming = true } label: {
                    APKeyValueRow(key: "Nickname", value: (account.nickname ?? "").isEmpty ? "Add" : account.nickname!,
                                  link: (account.nickname ?? "").isEmpty)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("account-nickname")
                if !account.copies(among: all).isEmpty {
                    APSeparator(afterFace: false)
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

            // G5-Account: the destructive rows are the only red on the way.
            APCard {
                Button { removing = true } label: {
                    ProfileRow(symbol: "trash", title: "Remove this account", tone: Pearl.danger, chevron: false)
                }
                .buttonStyle(.plain)
                if sameBank.count > 1 {
                    // AM-11 (THL-262): every account on this bank login at once.
                    APSeparator()
                    Button { removingBank = true } label: {
                        ProfileRow(symbol: "minus.circle", title: "Remove \(AccountWords.bank(account)) entirely",
                                   sub: sameBank.count == 2 ? "Both accounts" : "All \(sameBank.count) accounts",
                                   tone: Pearl.danger, chevron: false)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
            }
            .padding(.top, 16)
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
            Color.clear.frame(height: 40)
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
        .sheet(isPresented: $renaming) {
            // AM-09n (TEST-06): a Pearl sheet; Save stays off while it's empty.
            PearlConfirmSheet(overline: [account.name, (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"]
                                .compactMap { $0 }.joined(separator: " "),
                              title: "Nickname", message: "A name you’ll recognise. It shows everywhere in Pearl.",
                              field: .init(label: "Nickname", prompt: account.name, identifier: "nickname"),
                              text: $nickname, primary: "Save", busyLabel: "Saving…",
                              failure: "Couldn’t save the nickname. Nothing changed. Try again.",
                              onClose: { renaming = false }) {
                let reply: AccountSaved = try await app.api.put("api/accounts/\(account.id)/settings",
                                                                 ["nickname": nickname])
                if let a = reply.account { account = a }
                syncState()
                renaming = false
                app.changed()
            }
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account, lastAtBank: sameBank.count == 1) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
        }
        .sheet(isPresented: $reconnecting) {
            ReconnectSheet(account: account) { ok in
                reconnecting = false
                if ok {
                    withAnimation { toast = ("\(account.name) is up to date again.", nil) }
                    app.changed()
                }
            }
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
        APToggleRow(title: title, sub: sub,
                    isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) }))
            .disabled(disabled || busy)
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
        guard await save(["counted": on], saying: nil) != nil else { return }
        // G5-Account (AM-03): the short toast, with Undo.
        let text = on ? "In your budget now" : "Not in your budget now"
        withAnimation {
            toast = (text, { Task { await save(["counted": !on], saying: on ? "Not in your budget now" : "In your budget now") } })
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
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: "Remove \(account.name)?") { finished(false) }
            APWho(face: AccountWords.bank(account), name: account.name, line: detail)
            if account.isHand {
                Text("Its balance comes off Home. This can\u{2019}t be undone.")
                    .font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                APCard {
                    ChoiceLine(title: "Keep its transactions", sub: "Past months stay the same",
                               selected: !deleteHistory) { deleteHistory = false }
                    APSeparator(afterFace: false)
                    ChoiceLine(title: "Delete them too", sub: "This can\u{2019}t be undone",
                               selected: deleteHistory) { deleteHistory = true }
                }
            }
            if let error = error { APErrorLine(text: error) }
        } footer: {
            // The final button is the rose Primary naming the action; no red here.
            PearlSheetButtons(primary: error == nil ? "Remove account" : "Try again", busy: busy,
                              busyLabel: "Removing\u{2026}", secondary: "Keep it",
                              onPrimary: { Task { await remove() } }, onSecondary: { finished(false) })
        }
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
            APCard {
                APKeyValueRow(key: "In Pearl", value: "\((account.transactions ?? 0).formatted()) transactions")
                APSeparator(afterFace: false)
                APKeyValueRow(key: "History from", value: account.historyFrom.map { Format.month(String($0.prefix(7))) } ?? "\u{2014}")
            }
            .padding(.top, 10)
            VStack(spacing: 12) {
                Button("Reconnect") { reconnecting = true }
                    .buttonStyle(APPrimaryButtonStyle())
                    .disabled(busy)
                Button("Keep as a manual account") { Task { await keepAsManual() } }
                    .buttonStyle(APSecondaryButtonStyle())
                    .disabled(busy)
            }
            .padding(.top, 10)
            APCard {
                Button { removing = true } label: {
                    ProfileRow(symbol: "trash", title: "Remove it and its history", tone: Pearl.danger, chevron: false)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 16)
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
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
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account, deleting: true, lastAtBank: lastAtBank) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
        }
    }

    /// "Balance on Oct 1 · ••7710".
    private var note: String {
        let mask = (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"
        let on = (account.disconnectedOn ?? account.updatedAt).map { "Balance on \(Format.short($0))" }
        return [on ?? "Balance when it disconnected", mask].compactMap { $0 }.joined(separator: " · ")
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

/// A choice with a line under it: the A+ radio row (G5-Remove).
struct ChoiceLine: View {
    let title: String
    var sub: String? = nil
    let selected: Bool
    let action: () -> Void

    var body: some View {
        APChoiceRow(title: title, sub: sub, selected: selected, action: action)
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
                .buttonStyle(APSecondaryButtonStyle())
                .padding(.top, 10)

            ProfileSection("Settings")
            APCard {
                toggle(title: "Show on Home", sub: "Counts in your balances and totals",
                       on: $counted) { on in Task { await save(["counted": on], saying: on ? "\(account.name) shows on Home." : "\(account.name) is off Home.") } }
                if account.canAnchor == true {
                    APSeparator(afterFace: false)
                    toggle(title: "Part of my Anchor", sub: "Savings accounts only",
                           on: $anchor) { on in Task { await save(["anchor": on], saying: on ? "\(account.name) counts toward your Anchor." : "\(account.name) no longer counts toward your Anchor.") } }
                }
                APSeparator(afterFace: false)
                Button { name = account.name; renaming = true } label: {
                    APKeyValueRow(key: "Name", value: account.name)
                }
                .buttonStyle(.plain)
            }
            APCard {
                Button { removing = true } label: {
                    ProfileRow(symbol: "trash", title: "Remove this account", tone: Pearl.danger, chevron: false)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 16)
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
        }
        .overlay(alignment: .bottom) {
            // UN-01: the toast sits at the bottom.
            if let toast = toast { UndoToast(text: toast) { withAnimation { self.toast = nil } }.padding(.bottom, 12) }
        }
        .onAppear { counted = account.counted ?? true; anchor = account.anchor == true }
        .sheet(isPresented: $renaming) {
            // AM-14n (TEST-06).
            PearlConfirmSheet(overline: "Added by hand", title: "Name",
                              message: "What you call this account. It shows everywhere in Pearl.",
                              field: .init(label: "Name", prompt: account.name, identifier: "account-name"),
                              text: $name, primary: "Save", busyLabel: "Saving…",
                              failure: "Couldn’t save the name. Nothing changed. Try again.",
                              onClose: { renaming = false }) {
                let reply: AccountSaved = try await app.api.put("api/accounts/\(account.id)/settings",
                                                                 ["nickname": name])
                if let a = reply.account { account = a }
                counted = account.counted ?? true
                anchor = account.anchor == true
                renaming = false
                app.changed()
            }
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
        }
        .sheet(isPresented: $removing) {
            RemoveAccountSheet(account: account) { removed in
                removing = false
                if removed { app.changed(); dismiss() }
            }
        }
    }

    private func toggle(title: String, sub: String, on: Binding<Bool>,
                        changed: @escaping (Bool) -> Void) -> some View {
        APToggleRow(title: title, sub: sub,
                    isOn: Binding(get: { on.wrappedValue }, set: { v in on.wrappedValue = v; changed(v) }))
            .disabled(busy)
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
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: "Update \(account.name)") { finished(nil) }
            PearlField(label: "Balance today", placeholder: "0.00", text: $balance, kind: .amount,
                       identifier: "balance-today")
            if let error = error { APErrorLine(text: error) }
        } footer: {
            PearlSheetButtons(primary: error == nil ? "Save" : "Try again", busy: busy, busyLabel: "Saving\u{2026}",
                              onPrimary: { Task { await save() } })
                .disabled(balance.isEmpty)
        }
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

/// "$ 3,000.00": a money field, the A+ well (REDESIGN-09).
struct AmountField: View {
    let label: String
    @Binding var text: String

    var body: some View {
        PearlField(label: label, placeholder: "0.00", text: $text, kind: .amount)
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
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: "Remove \(bank) entirely?") { finished(false) }
            APWho(face: bank, name: bank, line: "\(accounts.count) accounts \u{00B7} you can link \(bank) again later")
            APCard {
                ForEach(Array(accounts.enumerated()), id: \.element.id) { i, a in
                    if i > 0 { APSeparator() }
                    ProfileRow(initials: bank, title: a.name,
                               sub: (a.mask ?? "").isEmpty ? AccountWords.kind(a) : "\u{2022}\u{2022}\(a.mask!)", chevron: false)
                }
            }
            APCard {
                ChoiceLine(title: "Keep their transactions", sub: "Past months stay the same",
                           selected: !deleteHistory) { deleteHistory = false }
                APSeparator(afterFace: false)
                ChoiceLine(title: "Delete them too", sub: "This can\u{2019}t be undone",
                           selected: deleteHistory) { deleteHistory = true }
            }
            if let error = error { APErrorLine(text: error) }
        } footer: {
            PearlSheetButtons(primary: error == nil ? "Remove \(bank)" : "Try again", busy: busy,
                              busyLabel: "Removing\u{2026}", secondary: "Keep it",
                              onPrimary: { Task { await remove() } }, onSecondary: { finished(false) })
                .disabled(itemId.isEmpty)
        }
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
