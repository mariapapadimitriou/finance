import SwiftUI
import UserNotifications

/// Home, bare (SC-40): the greeting, what needs you, and a way to Cash flow.
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
                PageHeader(overline: home?.today.map { Format.day($0) }, title: greeting)

                if let home = home {
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
                        NeedsALookCard(count: home.reviewCount)
                    }
                    MonthCard(month: home.month, onTransactions: { tab = .cashFlow })
                } else {
                    LoadState(error: error) { Task { await load() } }
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.vertical, 24)
        }
        .pearlPage()
        .navigationBarHidden(true)
        .refreshable { await load() }
        .task(id: app.version) { await load() }
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

    private var greeting: String {
        let name = app.user?.name ?? ""
        return name.isEmpty ? Format.greeting() : "\(Format.greeting()), \(name)"
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

    var body: some View {
        PearlCard(spacing: 8) {
            Text(count == 1 ? "1 transaction needs a look" : "\(count) transactions need a look")
                .font(Pearl.cardTitle).foregroundColor(Pearl.ink)
            Text("We weren't sure how to sort these. Sorting them keeps your numbers right.")
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
