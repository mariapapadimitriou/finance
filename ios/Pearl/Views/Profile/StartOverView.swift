import SwiftUI

// Profile › Your data › Start over (THL-214, THL-234): SO-02 what goes and
// what stays, SO-03 typing "start over", SO-04 what came back, and SO-05 when
// there's no bank to bring it back from.

// MARK: - SO-02 Start over, SO-03 Type "start over"

@MainActor
struct StartOverView: View {
    let goHome: () -> Void
    let downloadFirst: () -> Void

    @State private var confirming = false
    /// The server has cleared everything: SO-04 shows once the sheet has closed.
    @State private var started = false
    @State private var showFresh = false
    @State private var leaving = false

    /// G5-StartOver SO-02: what goes (rose dots) and what stays (teal dots).
    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 8) {
                DataHeading(title: "Start over", line: "Your banks stay. Everything else starts fresh.")
                DataCaption("What goes")
                DataCard {
                    APBullet(text: "Your transactions and how you sorted them")
                    APSeparator(afterFace: false)
                    APBullet(text: "Your rules and account setup")
                    APSeparator(afterFace: false)
                    APBullet(text: "Income, bills and budgets")
                    APSeparator(afterFace: false)
                    // Start over clears goals and the Anchor (Store.start_over, 2026-10-28).
                    APBullet(text: "Your Anchor and goals")
                }
                DataCaption("What stays")
                DataCard {
                    APBullet(text: "Your bank connections, and which accounts sync", dot: Nacre.teal)
                    APSeparator(afterFace: false)
                    APBullet(text: "Sign-in and privacy", dot: Nacre.teal)
                }
            }
        } bottom: {
            Button("Continue") { confirming = true }
                .buttonStyle(APPrimaryButtonStyle())
                .accessibilityIdentifier("start-over-continue")
            Button("Download a copy first", action: downloadFirst)
                .buttonStyle(APQuietTextStyle())
        }
        .toolbar(.hidden, for: .tabBar)
        .sheet(isPresented: $confirming, onDismiss: { if started { showFresh = true } }) {
            ConfirmStartOverSheet {
                started = true
                confirming = false
            }
            .background(SheetBackground())
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
        .fullScreenCover(isPresented: $showFresh, onDismiss: { if leaving { goHome() } }) {
            StartedOverView {
                leaving = true
                showFresh = false
            }
        }
    }
}

/// Nothing is cleared until she has typed the words and pressed the button.
@MainActor
struct ConfirmStartOverSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let done: () -> Void

    @State private var typed = ""
    @State private var busy = false
    @State private var error: String?

    /// However it's spaced or capitalised, as the server reads it.
    private var ready: Bool {
        typed.lowercased().split(whereSeparator: \.isWhitespace).joined(separator: " ") == "start over"
    }

    /// G5-StartOver SO-03: type "start over" in the well; Start over rides
    /// above the keyboard, greyed until the words are right. Couldn't: the
    /// reason, Try again and Keep everything.
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            APSheetTitle(title: "Start over?") { dismiss() }
                .padding(.top, 14)
            VStack(alignment: .leading, spacing: 8) {
                PearlField(label: "Type \u{201C}start over\u{201D}", placeholder: "start over", text: $typed,
                           identifier: "start-over-confirm") {
                    if ready { Task { await confirm() } }
                }
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                if let error = error {
                    APErrorLine(text: error)
                } else {
                    ProfileNote("Nothing changes until you do.")
                }
            }
            .padding(.top, 16)
            Spacer(minLength: 0)
            VStack(spacing: 12) {
                Button(error == nil ? "Start over" : "Try again") { Task { await confirm() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy, busyLabel: "Starting over\u{2026}"))
                    .disabled(!ready || busy)
                if error != nil || busy {
                    Button("Keep everything") { dismiss() }
                        .buttonStyle(APSecondaryButtonStyle())
                        .disabled(busy)
                }
            }
            .padding(.bottom, 8)
        }
        .padding(.horizontal, 16)
        .interactiveDismissDisabled(busy)
    }

    private func confirm() async {
        guard ready, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/data/start-over", ["confirm": "start over"])
            done()
        } catch {
            self.error = app.handle(error).map { _ in "Couldn\u{2019}t start over. Nothing changed. Try again." }
        }
    }
}

// MARK: - SO-04 You're starting fresh, SO-05 no linked bank

@MainActor
struct StartedOverView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()
    let close: () -> Void

    private enum Stage {
        case syncing
        case back(imported: Int, needsALook: Int)
        /// The bank hasn't sent it yet; the next sync brings it.
        case late
        case noBank
    }

    @State private var stage = Stage.syncing
    @State private var linking = false
    @State private var adding = false
    @State private var setup: SetupAgain?
    @State private var error: String?

    private struct Synced: Decodable { let imported: Int? }
    private struct Linked: Decodable {
        let sync: Synced?
        let syncError: String?
        enum CodingKeys: String, CodingKey {
            case sync
            case syncError = "sync_error"
        }
    }

    var body: some View {
        NavigationStack {
            content.navigationBarHidden(true)
        }
        .task {
            await bringBack()
            await loadSetup()
        }
    }

    @ViewBuilder private var content: some View {
        switch stage {
        case .syncing:
            DataResult(title: "You’re starting fresh",
                       line: "Downloading your history from your banks. It can take a minute.") {
                ProgressView().padding(.top, 4)
            } actions: {
                sortingButtons(enabled: false)
            }
        case .back(let imported, let needsALook):
            DataResult(title: "You’re starting fresh", line: backLine(imported) + lookLine(needsALook)) {
                setupList
            } actions: {
                sortingButtons(enabled: true)
            }
        case .late:
            DataResult(title: "You’re starting fresh",
                       line: "Your banks are still sending your history. It’ll show in Cash flow when it’s ready.") {
                setupList
            } actions: {
                sortingButtons(enabled: true)
            }
        case .noBank:
            // SO-05b: statement uploads are gone (THL-205), so a bank or a
            // balance by hand brings her money back.
            DataResult(title: "You’re starting fresh",
                       line: "Link a bank to bring your history back, or add a balance by hand.") {
                if let error = error { APErrorLine(text: error).padding(.top, 4) }
            } actions: {
                Button("Link a bank") { Task { await link() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: linking))
                    .disabled(linking)
                // G5-Extras SO-05b: the second way back is the grey secondary.
                Button("Add a balance by hand") { adding = true }
                    .buttonStyle(APSecondaryButtonStyle())
                    .padding(.top, 8)
                    .disabled(linking)
                Button("Not now", action: close)
                    .buttonStyle(APQuietTextStyle())
                    .disabled(linking)
            }
            .sheet(isPresented: $adding) {
                AddHandBalanceSheet { app.changed(); close() }
                    .background(SheetBackground())
                    .presentationDetents([.large])
                    .presentationDragIndicator(.visible)
            }
        }
    }

    /// SO-04b (THL-300; AP-SetupAgain, rethought 2026-11-18): one action
    /// (Start sorting); the steps wait on Home, so here it's one quiet note.
    @ViewBuilder private var setupList: some View {
        if let setup = setup, setup.active, setup.left > 0 {
            Text(setup.left == 1 ? "1 thing to set again waits on Home."
                 : "\(setup.left) things to set again wait on Home.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .padding(.top, 6)
        }
    }

    private func loadSetup() async {
        setup = try? await app.api.get("api/setup-again")
    }

    private func sortingButtons(enabled: Bool) -> some View {
        Group {
            NavigationLink { ReviewView() } label: { Text("Start sorting") }
                .buttonStyle(APPrimaryButtonStyle())
            Button("Go to Home", action: close)
                .buttonStyle(APQuietTextStyle())
        }
        .disabled(!enabled)
    }

    /// " 48 need a look."
    private func lookLine(_ n: Int) -> String {
        n > 0 ? " \(n.formatted()) need\(n == 1 ? "s" : "") a look." : ""
    }

    private func backLine(_ imported: Int) -> String {
        "\(imported.formatted()) transaction\(imported == 1 ? " is" : "s are") back."
    }

    /// Download the history again, then say what came back.
    private func bringBack() async {
        guard case .syncing = stage else { return }
        do {
            let privacy: Privacy = try await app.api.get("api/privacy")
            guard !privacy.connections.isEmpty else {
                stage = .noBank
                app.changed()
                return
            }
            let synced: Synced = try await app.api.post("api/plaid/sync", ["force": true])
            await arrived(synced.imported ?? 0)
        } catch is CancellationError {
            return
        } catch {
            // A long download can outlast the request. Cash flow syncs when it
            // opens, so this isn't something she has to fix.
            if app.handle(error) != nil { stage = .late }
            app.changed()
        }
    }

    /// SO-05's "Link a bank instead": the server syncs as it links.
    private func link() async {
        linking = true
        defer { linking = false }
        error = nil
        do {
            switch try await plaid.open(api: app.api) {
            case .linked(let linked):
                let reply: Linked = try await app.api.post("api/plaid/exchange",
                                                           ["public_token": linked.publicToken,
                                                            "institution": linked.institution])
                await arrived(reply.sync?.imported ?? 0)
            case .failed(let words), .notSupported(let words):
                error = words
            case .cancelled:
                break
            }
        } catch {
            self.error = app.handle(error)
        }
    }

    private func arrived(_ imported: Int) async {
        guard imported > 0 else {
            stage = .late
            app.changed()
            return
        }
        let review: Review? = try? await app.api.get("api/review")
        stage = .back(imported: imported, needsALook: review.map { $0.open ?? $0.count } ?? 0)
        app.changed()
    }
}
