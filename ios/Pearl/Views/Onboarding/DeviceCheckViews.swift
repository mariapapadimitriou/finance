import SwiftUI

// A new iPhone confirmed by her other device (THL-287, THL-114; Pearl iOS
// Handoff File, Pearl app page, "Approving a new device"):
//
// A-11   Confirm it's you: after the email code, when the server wants this
//        iPhone confirmed (finance/devices.py): approve it on her other
//        device, or use a recovery code
// A-11b  waiting for the other device to answer
// A-12   enter a recovery code
// SEC-10 on her signed-in iPhone: "Is this you signing in?", Approve or
//        No, it wasn't me (ApprovalPrompt, from MainTabs)

// MARK: - A-11 Confirm it's you

@MainActor
struct ConfirmDeviceView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let choices: DeviceChoices
    @State private var how: String
    @State private var busy = false
    @State private var error: String?

    init(path: Binding<[AuthRoute]>, choices: DeviceChoices) {
        _path = path
        self.choices = choices
        _how = State(initialValue: "approve")
    }

    /// G6-NewDevice A-11 (rethought, approved 2026-11-18): one line and one
    /// button. "Ask my Mac", or with no other device, "No other device to
    /// ask" and Contact support. Recovery codes are left out (2026-11-04).
    var body: some View {
        OnbScreen(scrolls: false) {
            if let approve = choices.approve {
                OnbMessage(title: "Confirm it’s you",
                           line: "This iPhone is new. Approve it on your \(Self.device(approve.label)).", top: 98) {
                    OnbOrb(symbol: "laptopcomputer")
                }
            } else {
                OnbMessage(title: "No other device to ask", line: "We’ll help you get back in.", top: 98) {
                    OnbOrb(symbol: "lock.slash")
                }
            }
            if let error = error { APErrorLine(text: error).padding(.top, 12) }
        } actions: {
            if let approve = choices.approve {
                OnbPrimary(title: "Ask my \(Self.device(approve.label))", busy: busy) { Task { await go() } }
            } else if let contact = app.contact, !contact.isEmpty, let mail = URL(string: "mailto:\(contact)") {
                Link(destination: mail) { Text("Contact support") }
                    .buttonStyle(APPrimaryButtonStyle())
            }
            APQuietButton(title: "Use a different email") { Task { await startOver() } }
        }
    }

    /// "Mac · Chrome" → "Mac"; nothing known → "other device".
    static func device(_ label: String?) -> String {
        let first = (label ?? "").components(separatedBy: " \u{00B7} ").first?
            .trimmingCharacters(in: .whitespaces) ?? ""
        return first.isEmpty ? "other device" : first
    }

    private func go() async {
        if how == "recovery" {
            path.append(.recoveryCode)
            return
        }
        busy = true
        defer { busy = false }
        struct Asked: Decodable { let from: String? }
        do {
            let asked: Asked = try await app.api.post("api/auth/device/ask")
            path.append(.waitingApproval(from: asked.from))
        } catch {
            if error.serverProblem?.expired == true { path = [] }
            self.error = app.handle(error)
        }
    }

    private func startOver() async {
        let _: OK? = try? await app.api.post("api/auth/device/cancel")
        path = []
    }
}

// MARK: - A-11b Waiting for the other device

@MainActor
struct WaitingApprovalView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let from: String?
    @State private var said: String?

    private struct Status: Decodable {
        let signedIn: Bool?
        let user: PearlUser?
        let state: String?
        enum CodingKeys: String, CodingKey {
            case user, state
            case signedIn = "signed_in"
        }
    }

    var body: some View {
        OnbScreen(back: false) {
            OnbMessage(title: "Check your other device",
                       line: "Open Pearl there and approve this sign-in\(from.map { " from \($0)" } ?? ""). This page carries on by itself.",
                       top: 98) {
                OnbOrb(symbol: "laptopcomputer")
            }
            if let said = said {
                APErrorLine(text: said)
            } else {
                // A-11b: "Waiting for your answer…".
                HStack(spacing: 8) {
                    ProgressView().tint(Pearl.muted)
                    Text("Waiting for your answer…").font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 8)
            }
        } actions: {
            Button("Cancel") { Task { await cancel() } }.buttonStyle(APSecondaryButtonStyle())
        }
        .task { await wait() }
    }

    private func wait() async {
        while !Task.isCancelled && said == nil {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard !Task.isCancelled else { return }
            do {
                let s: Status = try await app.api.get("api/auth/device/status")
                if s.signedIn == true {
                    app.signedIn(s.user)
                    return
                }
                switch s.state {
                case "refused": said = "It was turned down on your other device. If that wasn’t you, change your email password."
                case "expired": said = "That took too long. Go back and ask again."
                default: break
                }
            } catch {
                said = app.handle(error)
            }
        }
    }

    private func cancel() async {
        let _: OK? = try? await app.api.post("api/auth/device/cancel")
        path = []
    }
}

// MARK: - A-12 Enter a recovery code

@MainActor
struct RecoveryCodeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State private var code = ""
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focused: Bool

    var body: some View {
        OnbScreen {
            OnbTitle(title: "Enter a recovery code", line: "One of the ten codes you saved. Each works once.")
            TextField("", text: $code, prompt: Text("K7QF-2M9D").foregroundColor(Pearl.muted))
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .font(.system(size: 17, design: .monospaced)).foregroundColor(Pearl.ink)
                .focused($focused)
                .padding(.horizontal, 14).frame(minHeight: 44)
                .wellStyle(focused: focused)
                .accessibilityLabel("Recovery code")
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Sign in", busy: busy, enabled: code.trimmingCharacters(in: .whitespaces).count >= 6) {
                Task { await signIn() }
            }
        }
        .onAppear { focused = true }
    }

    private func signIn() async {
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/device/recovery",
                                                            ["code": code.trimmingCharacters(in: .whitespaces)])
            if reply.signedIn == true { app.signedIn(reply.user) }
        } catch {
            if error.serverProblem?.expired == true { path = [] }
            self.error = app.handle(error)
            code = ""
        }
    }
}

// MARK: - SEC-10 Is this you signing in?

/// On a signed-in iPhone: another device is asking to sign in as her.
/// G6-NewDevice SEC-10 (rethought, approved 2026-11-18): the device in one
/// line ("Mac · Chrome", "Near Toronto · just now"), then Yes, it's me and
/// No, it wasn't me. The close button leaves it unanswered; it runs out.
struct ApprovalPrompt: View {
    @Environment(\.dismiss) private var dismiss
    let approval: Approval
    let answer: (Bool) -> Void

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitle(title: "Is this you signing in?") { dismiss() }
                .padding(.top, 16)
            VStack(spacing: 4) {
                Image(systemName: "laptopcomputer").font(.system(size: 18)).foregroundColor(Pearl.action)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(ProfileTone.actionWash))
                    .accessibilityHidden(true)
                Text(approval.label ?? "A new device").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .padding(.top, 6)
                Text(where_).font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 14)
            .accessibilityElement(children: .combine)
            Spacer(minLength: 16)
            VStack(spacing: 12) {
                Button("Yes, it’s me") { answer(true) }
                    .buttonStyle(APPrimaryButtonStyle())
                    .accessibilityIdentifier("approval-yes")
                Button("No, it wasn’t me") { answer(false) }
                    .buttonStyle(APSecondaryButtonStyle())
                    .accessibilityIdentifier("approval-no")
            }
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .background(SheetBackground())
        .interactiveDismissDisabled()
    }

    /// "Near Toronto · just now".
    private var where_: String {
        approval.near.map { "Near \($0) \u{00B7} just now" } ?? "Just now"
    }
}
