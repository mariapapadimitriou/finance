import SwiftUI

/// Home, bare (SC-40): the greeting, what needs you, and a way to Cash flow.
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

/// After Start over: what only you can set again, each step opening the web.
@MainActor
struct SetupAgainCard: View {
    @EnvironmentObject private var app: AppModel
    let setup: SetupAgain
    let onChanged: () -> Void

    var body: some View {
        PearlCard {
            Text("Set Pearl up again").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
            Text(setup.left == 1 ? "Start over cleared what only you can tell Pearl. 1 thing to set again."
                 : "Start over cleared what only you can tell Pearl. \(setup.left) things to set again.")
                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
            VStack(spacing: 0) {
                ForEach(Array(setup.steps.enumerated()), id: \.element.id) { index, step in
                    if index > 0 { Rectangle().fill(Pearl.rule).frame(height: 1) }
                    Link(destination: app.api.baseURL) { stepRow(step) }
                        .buttonStyle(.plain)
                        .accessibilityHint("Opens Pearl on the web")
                }
            }
            Button("Hide this list") {
                Task {
                    let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                    onChanged()
                }
            }
            .font(Pearl.text(.subheadline, .medium))
            .foregroundColor(Pearl.action)
        }
    }

    private func stepRow(_ step: SetupAgain.Step) -> some View {
        HStack(spacing: 12) {
            ZStack {
                if step.done {
                    Circle().fill(Pearl.action)
                } else {
                    Circle().strokeBorder(Pearl.border, lineWidth: 1.5)
                }
            }
            .frame(width: 22, height: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(step.title).font(Pearl.text(.body))
                    .foregroundColor(step.done ? Pearl.muted : Pearl.ink)
                Text(step.done ? "Done" : step.sub).font(Pearl.text(.subheadline, .medium))
                    .foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .multilineTextAlignment(.leading)
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Pearl.muted)
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityValue(step.done ? "Done" : "")
    }
}
