import SwiftUI
import UserNotifications

/// Home (SC-40, H-00r): the Allowance orb (REFRESH-05), what needs you, and
/// a way to Cash flow.
@MainActor
struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab

    @State private var home: Home?
    @State private var setup: SetupAgain?
    /// Who owes her on splits, for the owes-you card (H-00n).
    @State private var owed: OwedOverview?
    @State private var error: String?
    /// N-01's quiet hours, while it's showing.
    @State private var askingToNotify: NotificationSettings.Quiet?
    @State private var checkedNotify = false
    /// H-01's Reconnect.
    @State private var reconnecting: Home.Connection?
    /// H-01's "See accounts" for a disconnected bank.
    @State private var openAccounts = false
    /// H-00r's Sort now: Quick sort, straight from Home (TEST-04).
    @State private var quickSort: [Ask] = []
    @State private var quickSortNames: [String] = []
    @State private var opening = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let home = home {
                    // For now (2026-11-07): O-11b's Allowance ring heads Home.
                    allowanceHeader(home)
                    // H-02 (THL-120): every bank in trouble, worst first.
                    ForEach((home.connections ?? []).filter { ["needs_sign_in", "disconnected"].contains($0.state ?? "") }) { c in
                        BankAlertCard(connection: c, today: home.today) { openAccounts = true } reconnect: {
                            reconnecting = c
                        }
                    }
                    if let setup = setup, setup.active {
                        SetupAgainCard(setup: setup, onChanged: { Task { await load() } })
                    }
                    if home.reviewCount > 0 {
                        NeedsALookCard(count: home.reviewCount, pearlSorted: home.pearlSorted ?? 0,
                                       busy: opening) { Task { await sortNow() } }
                    }
                    // H-00n (SPLIT-13, THL-291): under Needs a look, once a share is a week old.
                    if let owed = owed, let line = OwedNudgeCard.line(owed, today: home.today) {
                        OwedNudgeCard(line: line)
                    }
                    if let note = home.paychequeNote {
                        PaychequeNoteCard(month: note) { Task { await dismissNote(note) } }
                    }
                    MonthCard(month: home.month, onTransactions: { tab = .cashFlow })
                } else {
                    LoadState(error: error) { Task { await load() } }
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.vertical, 24)
        }
        .nacreScreen()
        .navigationBarHidden(true)
        .refreshable { await load() }
        .reloads { await load() }
        .navigationDestination(isPresented: $openAccounts) { AccountsView() }
        .sheet(item: $reconnecting) { c in
            ReconnectSheet(bank: c.institution ?? "your bank", label: c.institution ?? "Your bank",
                           itemId: c.itemId, updatedAt: c.lastSynced) { ok in
                reconnecting = nil
                if ok { app.changed() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .fullScreenCover(item: $askingToNotify) { quiet in
            TurnOnNotificationsView(quiet: quiet)
        }
        .fullScreenCover(isPresented: Binding(get: { !quickSort.isEmpty }, set: { if !$0 { quickSort = [] } })) {
            QuickSortView(asks: quickSort, categories: app.categories, names: quickSortNames) {
                quickSort = []
                Task { await load() }
            }
        }
    }

    /// H-00r (REFRESH-00 decision 2): Sort now opens Quick sort with every
    /// open question, not only today's new ones.
    private func sortNow() async {
        guard !opening else { return }
        opening = true
        defer { opening = false }
        do {
            let prompt: QuickSortPrompt = try await app.api.get("api/quick-sort", query: ["all": "1"])
            quickSortNames = prompt.review?.people ?? []
            quickSort = prompt.asks
        } catch {
            self.error = app.handle(error)
        }
    }

    /// H-00 / H-00r (REFRESH-05): the date, then the Allowance orb with
    /// "Allowance" / the amount / "left in November" inside it (the orb's
    /// label is the heading, so there is no title above it), and the line
    /// under it when there is one.
    private func allowanceHeader(_ home: Home) -> some View {
        VStack(spacing: 6) {
            Text((home.today.map { Format.day($0) } ?? "").uppercased()).font(Nacre.caption2).tracking(1.4)
                .foregroundColor(Pearl.ink)
            AllowanceOrb(progress: home.safeToSpend?.ringProgress ?? 0,
                         label: "Allowance",
                         amount: home.safeToSpend?.ringAmount ?? "—",
                         sub: home.safeToSpend?.orbSub(month: home.month) ?? Allowance.orbSub(forMonth: home.month))
                .accessibilityAddTraits(.isHeader)
                .accessibilityHint(home.safeToSpend?.ringCaption == Allowance.restCaption ? Allowance.restCaption : "")
                .padding(.vertical, 12)
            // REFRESH-03 (H-00n, H-00u): the usual "Left to spend or save…" line
            // is gone, since the ring says Allowance; it stays as the ring's
            // VoiceOver hint. The other states (estimate, over, no income) keep theirs.
            if let caption = home.safeToSpend?.ringCaption, !caption.isEmpty, caption != Allowance.restCaption {
                Text(caption).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.bottom, 8)
    }

    /// Got it: the note doesn't come back.
    private func dismissNote(_ note: Review.PayMonth) async {
        let _: OK? = try? await app.api.post("api/review/dismiss", ["key": note.key])
        await load()
    }

    private func load() async {
        do {
            home = try await app.api.get("api/home")
            setup = try? await app.api.get("api/setup-again")
            owed = try? await app.api.get("api/owed")
            error = nil
            await offerNotifications()
        } catch {
            self.error = app.handle(error)
        }
    }

    /// N-01 (THL-139): once the Allowance has a number, if iOS hasn't asked
    /// yet (setup's O-08b may have) and N-01 hasn't been answered on any device.
    private func offerNotifications() async {
        guard !checkedNotify, home?.safeToSpend?.state == "ok" else { return }
        checkedNotify = true
        let status = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        guard status == .notDetermined,
              let settings: NotificationSettings = try? await app.api.get("api/notifications"),
              settings.prefs.prompt?.answer == nil else { return }
        askingToNotify = settings.prefs.quiet
    }
}

/// H-00r (TEST-04, REFRESH-00 decision 2): "8 to sort", about how long,
/// what Pearl sorted itself and a bar of how far along; Sort now opens Quick
/// sort, See the list opens Needs a look.
struct NeedsALookCard: View {
    let count: Int
    var pearlSorted = 0
    var busy = false
    let onSort: () -> Void

    /// About ten seconds a card.
    private var howLong: String {
        let minutes = Int((Double(count) * 10 / 60).rounded())
        return minutes <= 1 ? "About a minute." : "About \(minutes) minutes."
    }

    var body: some View {
        PearlCard(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "rectangle.stack").font(.system(size: 20)).foregroundColor(Pearl.action)
                    .frame(width: 44, height: 44)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Pearl.bubble))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(count) to sort").font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.ink)
                    Text(howLong + (pearlSorted > 0 ? " Pearl sorted \(pearlSorted) by itself." : ""))
                        .font(Pearl.text(.subheadline)).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            if pearlSorted > 0 {
                PaidBar(paid: Double(pearlSorted), of: Double(pearlSorted + count))
                    .accessibilityHidden(true)
            }
            Button("Sort now", action: onSort)
                .buttonStyle(PearlPrimaryButtonStyle(busy: busy, busyLabel: "Opening…"))
                .disabled(busy)
            NavigationLink {
                ReviewView()
            } label: {
                Text("See the list").font(Nacre.textButton).foregroundColor(Pearl.link)
                    .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }
}

/// H-00n (SPLIT-13, THL-291 "the Home owes-you nudge"; REFRESH-03 words):
/// "Sam and Priya owe you $70.10". It shows once the oldest share is a week
/// old, so a split made today doesn't nag, and goes when nothing is owed.
/// No dismiss, like Needs a look.
struct OwedNudgeCard: View {
    let line: String

    var body: some View {
        PearlCard(spacing: 8) {
            Text(line).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            NavigationLink {
                OwedView()
            } label: {
                LinkLabel(text: "See who owes you")
            }
            .padding(.top, 4)
        }
    }

    /// The card's words, or nil when it shouldn't show.
    static func line(_ owed: OwedOverview, today: String?) -> String? {
        let items = owed.owesYou.flatMap(\.items)
        let now = today.flatMap { Format.localDay($0) } ?? Date()
        func aWeek(_ day: String) -> Bool {
            guard let first = Format.localDay(day),
                  let days = Calendar.current.dateComponents([.day], from: first, to: now).day else { return false }
            return days >= 7
        }
        // H-00u (SPLIT-C decision 5): a Not sure yet split is never money
        // owed, so it adds no amount; once it's a week old, the same timing
        // as owes-you, a quiet "· 1 not settled" joins the line (REFRESH-03).
        let unsettled = (owed.notSettled ?? []).filter { aWeek($0.date) }
        guard owed.total >= 0.005, let oldest = items.map(\.date).min(), aWeek(oldest) else {
            // H-00u0: only a Not sure yet split: "Pizza Nova isn’t settled yet".
            guard !unsettled.isEmpty else { return nil }
            return unsettled.count == 1 ? "\(unsettled[0].merchant) isn’t settled yet"
                : "\(unsettled.count) splits aren’t settled yet"
        }
        // Up to two names, then "and N others".
        let names = owed.owesYou.map { $0.name.components(separatedBy: " ").first ?? $0.name }
        let who: String
        switch names.count {
        case 1: who = "\(names[0]) owes"
        case 2: who = "\(names[0]) and \(names[1]) owe"
        default:
            let others = names.count - 2
            who = "\(names[0]), \(names[1]) and \(others) other\(others == 1 ? "" : "s") owe"
        }
        // "Sam and Priya owe you $70.10"; H-00u adds " · 1 not settled".
        let line = "\(who) you \(Format.amount(owed.total))"
        return unsettled.isEmpty ? line : "\(line) · \(unsettled.count) not settled"
    }
}

/// A month with a third paycheque: why it looks bigger, and nothing to do.
struct PaychequeNoteCard: View {
    let month: Review.PayMonth
    let onDismiss: () -> Void

    var body: some View {
        PearlCard(spacing: 8) {
            // REFRESH-03 (H-00n): "October had 3 paycheques."
            Text("\(Format.monthName(month.month)) had 3 paycheques.")
                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Button("Got it", action: onDismiss)
                .font(Nacre.textButton).foregroundColor(Pearl.link)
                .padding(.top, 4)
        }
    }
}

/// "October so far", a way to Cash flow (REFRESH-03 took its footnote out).
struct MonthCard: View {
    let month: String
    let onTransactions: () -> Void

    var body: some View {
        Button(action: onTransactions) {
            PearlCard(spacing: 8) {
                Text("\(Format.monthName(month)) so far").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
                LinkLabel(text: "Transactions").padding(.top, 4)
            }
        }
        .buttonStyle(.plain)
    }
}

/// SU-01 Set Pearl up again (THL-300, THL-294): after Start over, what
/// only she can tell Pearl, each step opening its page in the app: shared
/// accounts (O-09b), Income and bills (IB-01), Accounts (AM-01) and Debts
/// (DB-01). Opening Accounts or Debts is the step; sharing is done when she
/// finishes O-09b; income when she confirms her income and bills.
@MainActor
struct SetupAgainCard: View {
    @EnvironmentObject private var app: AppModel
    let setup: SetupAgain
    /// SO-04b leaves Hide this list to Home.
    var hideable = true
    let onChanged: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Set Pearl up again").font(Nacre.title2).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            Text(setup.left == 1 ? "Start over cleared what only you can tell Pearl. 1 thing left to set again."
                 : "Start over cleared what only you can tell Pearl. \(setup.left) things left to set again.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            GlassCard {
                ForEach(Array(setup.steps.enumerated()), id: \.element.id) { index, step in
                    if index > 0 { RowSeparator(inset: 62) }
                    NavigationLink { destination(step) } label: {
                        ProfileRow(symbol: symbol(step.key), title: step.title,
                                   sub: step.done ? "Done" : step.sub)
                    }
                    .buttonStyle(.plain)
                    .accessibilityValue(step.done ? "Done" : "")
                }
            }
            if hideable {
            Button("Hide this list") {
                Task {
                    let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                    onChanged()
                }
            }
            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
    }

    @ViewBuilder
    private func destination(_ step: SetupAgain.Step) -> some View {
        switch step.key {
        case "shared":
            JointAccountsView(path: .constant([])) {
                Task {
                    await mark("shared")
                }
            }
        case "income":
            IncomeBillsView()
        case "debts":
            DebtsView().task { await mark("debts") }
        default:
            AccountsView().task { await mark("accounts") }
        }
    }

    private func symbol(_ key: String) -> String {
        ["shared": "person.2", "income": "dollarsign.square", "accounts": "building.columns",
         "debts": "creditcard"][key] ?? "checkmark.circle"
    }

    private func mark(_ key: String) async {
        let _: SetupAgain? = try? await app.api.post("api/setup-again", ["step": key])
        onChanged()
    }
}

/// H-01 (THL-120, THL-123): a bank that needs her, at the top of Home: the
/// same card as Accounts' C-01. Disconnected opens Accounts; a bank that
/// isn't responding needs nothing from her.
struct BankAlertCard: View {
    let connection: Home.Connection
    let today: String?
    let openAccounts: () -> Void
    let reconnect: () -> Void

    var body: some View {
        GlassCard {
            VStack(spacing: 14) {
                HStack(spacing: 12) {
                    IconBubble(symbol: connection.state == "bank_down" ? "clock" : "arrow.triangle.2.circlepath")
                    Text(text).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                switch connection.state {
                case "needs_sign_in":
                    Button("Reconnect", action: reconnect).buttonStyle(NacreButtonStyle())
                case "disconnected":
                    Button("See accounts", action: openAccounts).buttonStyle(NacreButtonStyle())
                default:
                    EmptyView()
                }
            }
            .padding(16)
        }
    }

    private var text: String {
        let bank = connection.institution ?? "Your bank"
        switch connection.state {
        case "needs_sign_in":
            let what = connection.cardsOnly == true ? "Its purchases" : "Its transactions"
            let since = connection.lastSynced.map { " since \(Format.short($0))" } ?? ""
            return "\(bank) needs you to sign in again. \(what)\(since) aren’t counted yet."
        case "disconnected":
            return "\(bank) is no longer connected, so its transactions aren’t coming in."
        default:
            return "\(bank) isn’t responding right now. Pearl keeps trying; there’s nothing you need to do."
        }
    }
}
