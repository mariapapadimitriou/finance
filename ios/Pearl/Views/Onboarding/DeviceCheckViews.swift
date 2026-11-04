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
        _how = State(initialValue: choices.approve != nil ? "approve" : "recovery")
    }

    var body: some View {
        NacreScreen {
            IconOrb(symbol: "envelope")
            Text("Confirm it’s you").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("This iPhone is new to your account. Approve it from a device you’re signed in on, or use a recovery code.")
                .font(Nacre.body)
            GlassCard {
                if let approve = choices.approve {
                    ChoiceLine(title: "Approve on my other device", sub: deviceLine(approve),
                               selected: how == "approve") { how = "approve" }
                }
                if choices.recovery == true {
                    if choices.approve != nil { RowSeparator() }
                    ChoiceLine(title: "Use a recovery code", sub: "One of the ten you saved",
                               selected: how == "recovery") { how = "recovery" }
                }
            }
            if choices.approve == nil && choices.recovery != true {
                Hint(text: "There’s no other device or recovery code to confirm this iPhone with. Contact support to get back in.")
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Continue") { Task { await go() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy || (choices.approve == nil && choices.recovery != true))
            } secondary: {
                Button("Use a different email") { Task { await startOver() } }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
    }

    /// "Mac · Chrome, used today".
    private func deviceLine(_ a: DeviceChoices.Approve) -> String {
        let when = a.usedAt.map { SignInSecurityView.ago($0).lowercased() }
        return [a.label, when.map { "used \($0)" }].compactMap { $0 }.joined(separator: ", ")
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
        NacreScreen {
            IconOrb(symbol: "iphone")
            Text("Check your other device").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("Open Pearl there and approve this sign-in\(from.map { " from \($0)" } ?? ""). This page carries on by itself.")
                .font(Nacre.body)
            if let said = said {
                Hint(text: said)
            } else {
                ProgressView().padding(.top, 8)
            }
        } actions: {
            BottomActions {
                Button("Use a recovery code instead") { path.append(.recoveryCode) }
                    .buttonStyle(NacreButtonStyle())
            } secondary: {
                Button("Cancel") { Task { await cancel() } }
                    .buttonStyle(NacreTextButtonStyle())
            }
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
        NacreScreen {
            IconOrb(symbol: "key")
            Text("Enter a recovery code").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("One of the ten codes you saved. Each works once.").font(Nacre.body)
            TextField("", text: $code, prompt: Text("K7QF-2M9D").foregroundColor(Pearl.muted))
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .font(.system(size: 17, design: .monospaced)).foregroundColor(Pearl.ink)
                .focused($focused)
                .padding(.horizontal, 16).frame(height: 52)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(focused ? Pearl.action : Nacre.edge, lineWidth: focused ? 1.5 : 1))
                .accessibilityLabel("Recovery code")
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Sign in") { Task { await signIn() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy || code.trimmingCharacters(in: .whitespaces).count < 6)
            } secondary: {
                Button("Back") { path.removeLast() }
                    .buttonStyle(NacreTextButtonStyle())
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
struct ApprovalPrompt: View {
    let approval: Approval
    let answer: (Bool) -> Void

    var body: some View {
        VStack(spacing: 10) {
            Text("NEW DEVICE").font(Nacre.caption1).foregroundColor(Pearl.ink).padding(.top, 24)
            Text("Is this you signing in?").font(Nacre.title2).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            if let email = approval.account?.email, !email.isEmpty {
                Text("To Pearl as \(email)").font(Nacre.headline).foregroundColor(Pearl.ink)
            }
            Text("\(place), just now. Only approve it if you’re signing in yourself.")
                .font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Button("Approve") { answer(true) }
                .buttonStyle(NacreButtonStyle())
            Button("No, it wasn’t me") { answer(false) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
        }
        .padding(.horizontal, 20).padding(.bottom, 8)
        .background(SheetBackground())
        .interactiveDismissDisabled()
    }

    private var place: String {
        let label = approval.label ?? "A new device"
        return approval.near.map { "\(label), near \($0)" } ?? label
    }
}
