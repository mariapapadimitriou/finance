import SwiftUI

/// Home: what needs you, then how the month is going.
@MainActor
struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab

    @State private var home: Home?
    @State private var setup: SetupAgain?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    if let today = home?.today {
                        Text(Format.day(today).uppercased())
                            .font(.caption.weight(.semibold)).tracking(1)
                            .foregroundColor(Pearl.muted)
                    }
                    Text(greeting).font(Pearl.display()).foregroundColor(Pearl.ink)
                }
                .padding(.top, 8)

                if let home = home {
                    if let setup = setup, setup.active {
                        SetupAgainCard(setup: setup, onChanged: { Task { await load() } })
                    }
                    if home.reviewCount > 0 {
                        NeedsALookCard(count: home.reviewCount)
                    }
                    MonthCard(home: home, onTransactions: { tab = .cashFlow })
                } else {
                    LoadState(error: error) { Task { await load() } }
                }
            }
            .padding(Pearl.gutter)
        }
        .pearlPage()
        .navigationBarHidden(true)
        .refreshable { await load() }
        .task(id: app.version) { await load() }
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
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// "N transactions need a look".
struct NeedsALookCard: View {
    let count: Int

    var body: some View {
        PearlCard {
            Text(count == 1 ? "1 transaction needs a look" : "\(count) transactions need a look")
                .font(Pearl.title).foregroundColor(Pearl.ink)
            Text("We weren't sure how to sort these. Sorting them keeps your numbers right.")
                .foregroundColor(Pearl.muted)
            NavigationLink {
                ReviewView()
            } label: {
                Text("Review one by one")
            }
            .buttonStyle(PrimaryButtonStyle())
        }
    }
}

/// "October so far": income in, and each kind of spending against your usual.
struct MonthCard: View {
    let home: Home
    let onTransactions: () -> Void

    var body: some View {
        PearlCard {
            Text("\(Format.monthName(home.month)) so far").font(Pearl.title).foregroundColor(Pearl.ink)
            ForEach(rows) { row in
                MonthRow(row: row)
                if row.id != rows.last?.id { Divider().overlay(Pearl.border) }
            }
            Button(action: onTransactions) {
                HStack(spacing: 4) {
                    Text("Transactions")
                    Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                }
                .foregroundColor(Pearl.action)
                .font(.body.weight(.semibold))
            }
            .padding(.top, 4)
        }
    }

    private var rows: [Home.Snapshot.Row] {
        (home.snapshot?.rows ?? []).filter { $0.lens == nil && $0.key != "savings" }
    }
}

struct MonthRow: View {
    let row: Home.Snapshot.Row

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(row.label ?? row.key.capitalized).foregroundColor(Pearl.ink)
                Spacer()
                Text(Format.whole(amount)).font(.body.weight(.semibold)).foregroundColor(Pearl.ink)
            }
            if let line = line {
                Text(line).font(.subheadline).foregroundColor(Pearl.muted)
            }
            if let progress = progress {
                ProgressView(value: min(progress, 1))
                    .tint(progress > 1 ? Pearl.caution : Pearl.action)
            }
        }
    }

    private var amount: Double { row.key == "income" ? (row.received ?? 0) : (row.spent ?? 0) }

    private var line: String? {
        if row.key == "income" {
            guard let expected = row.expected, expected > 0 else { return "Received so far" }
            return "Received of \(Format.whole(expected)) expected"
        }
        guard let usual = row.usualByToday, usual > 0 else { return nil }
        let diff = (row.spent ?? 0) - usual
        if abs(diff) < 1 { return "About usual for this point in the month" }
        return diff > 0 ? "\(Format.whole(diff)) more than usual by today"
                        : "\(Format.whole(diff)) less than usual by today"
    }

    private var progress: Double? {
        if row.key == "income" {
            guard let expected = row.expected, expected > 0 else { return nil }
            return (row.received ?? 0) / expected
        }
        guard let usual = row.usual, usual > 0 else { return nil }
        return (row.spent ?? 0) / usual
    }
}

/// After Start over: what only you can set again.
@MainActor
struct SetupAgainCard: View {
    @EnvironmentObject private var app: AppModel
    let setup: SetupAgain
    let onChanged: () -> Void

    var body: some View {
        PearlCard {
            Text("Set Pearl up again").font(Pearl.title).foregroundColor(Pearl.ink)
            Text(setup.left == 1 ? "Start over cleared what only you can tell Pearl. 1 thing to set again."
                 : "Start over cleared what only you can tell Pearl. \(setup.left) things to set again.")
                .foregroundColor(Pearl.muted)
            ForEach(setup.steps) { step in
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: step.done ? "checkmark.circle.fill" : "circle")
                        .foregroundColor(step.done ? Pearl.action : Pearl.muted)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(step.title).font(.body.weight(.semibold))
                            .foregroundColor(step.done ? Pearl.muted : Pearl.ink)
                        Text(step.done ? "Done" : step.sub).font(.subheadline).foregroundColor(Pearl.muted)
                    }
                }
            }
            Text("Each of these is done in Pearl on the web for now.")
                .font(.footnote).foregroundColor(Pearl.muted)
            HStack {
                Link("Open Pearl on the web", destination: app.api.baseURL)
                    .foregroundColor(Pearl.action).font(.body.weight(.semibold))
                Spacer()
                Button("Hide") {
                    Task {
                        let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                        onChanged()
                    }
                }
                .foregroundColor(Pearl.muted)
            }
        }
    }
}
