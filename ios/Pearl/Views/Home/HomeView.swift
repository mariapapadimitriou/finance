import SwiftUI
import UserNotifications

/// Home (SC-40): the Allowance ring from O-11b (2026-11-07), what needs you,
/// and a way to Cash flow.
@MainActor
struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab

    @State private var home: Home?
    @State private var setup: SetupAgain?
    @State private var error: String?
    /// N-01's quiet hours, while it's showing.
    @State private var askingToNotify: NotificationSettings.Quiet?
    @State private var checkedNotify = false
    /// H-01's Reconnect.
    @State private var reconnecting: Home.Connection?
    /// H-01's "See accounts" for a disconnected bank.
    @State private var openAccounts = false

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
                        NeedsALookCard(count: home.reviewCount, pearlSorted: home.pearlSorted ?? 0)
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
    }

    /// O-11b on Home: the date above "Your Allowance", the ring
    /// with the pearl, and the line under it.
    private func allowanceHeader(_ home: Home) -> some View {
        VStack(spacing: 6) {
            Text((home.today.map { Format.day($0) } ?? "").uppercased()).font(Nacre.caption2).tracking(1.4)
                .foregroundColor(Pearl.ink)
            Text("Your Allowance").font(Nacre.largeTitle).tracking(0.4).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            AllowanceRing(overline: home.safeToSpend?.ringOverline(month: home.month)
                            ?? Format.monthName(home.month).uppercased(),
                          amount: home.safeToSpend?.ringAmount ?? "—",
                          progress: home.safeToSpend?.ringProgress ?? 0)
                .padding(.vertical, 12)
            if let caption = home.safeToSpend?.ringCaption, !caption.isEmpty {
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

/// "N transactions need a look", opening Needs a look.
struct NeedsALookCard: View {
    let count: Int
    var pearlSorted = 0

    var body: some View {
        PearlCard(spacing: 8) {
            Text(count == 1 ? "1 transaction needs a look" : "\(count) transactions need a look")
                .font(Pearl.cardTitle).foregroundColor(Pearl.ink)
            Text("We weren't sure how to sort these. Sorting them keeps your numbers right."
                 + (pearlSorted > 0 ? " Pearl sorted \(pearlSorted) more by itself." : ""))
                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
            NavigationLink {
                ReviewView()
            } label: {
                LinkLabel(text: "Review one by one")
            }
            .padding(.top, 4)
        }
    }
}

/// A month with a third paycheque: why it looks bigger, and nothing to do.
struct PaychequeNoteCard: View {
    let month: Review.PayMonth
    let onDismiss: () -> Void

    var body: some View {
        PearlCard(spacing: 8) {
            Text("\(Format.monthName(month.month)) had three paycheques, so it looks bigger. Nothing to do.")
                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Button("Got it", action: onDismiss)
                .font(Nacre.textButton).foregroundColor(Pearl.action)
                .padding(.top, 4)
        }
    }
}

/// "October so far": everything else about the month is on Cash flow.
struct MonthCard: View {
    let month: String
    let onTransactions: () -> Void

    var body: some View {
        Button(action: onTransactions) {
            PearlCard(spacing: 8) {
                Text("\(Format.monthName(month)) so far").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
                Text("Every transaction, what needs a look, and your month in pictures are on Cash flow.")
                    .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.leading)
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
