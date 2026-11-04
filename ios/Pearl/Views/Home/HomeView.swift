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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                PageHeader(overline: home?.today.map { Format.day($0) }, title: greeting)

                if let home = home {
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
            Button("Hide this list") {
                Task {
                    let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                    onChanged()
                }
            }
            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
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
