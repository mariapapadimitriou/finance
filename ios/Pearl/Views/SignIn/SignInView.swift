import SwiftUI

/// Signing in, as on the web: an email code (or a username and password), and
/// on a new device, approval from a device you've already confirmed or a
/// recovery code.
@MainActor
struct SignInView: View {
    @EnvironmentObject private var app: AppModel

    private enum Step: Equatable {
        case email, code, password, confirm, waiting, recovery
    }

    @State private var step: Step = .email
    @State private var email = ""
    @State private var code = ""
    @State private var username = ""
    @State private var password = ""
    @State private var recovery = ""
    @State private var server = ""
    @State private var showServer = false
    @State private var choices: DeviceChoices?
    @State private var busy = false
    @State private var error: String?
    @State private var info: String?
    @State private var waitState: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                content
                if let error = error { Notice(text: error, tone: .caution) }
                if let info = info { Notice(text: info) }
                serverSetting
            }
            .padding(24)
            .frame(maxWidth: 520)
            .frame(maxWidth: .infinity)
        }
        .pearlPage()
        .onAppear { server = app.api.baseURL.absoluteString }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            Circle()
                .fill(Pearl.nacre)
                .frame(width: 56, height: 56)
                .overlay(Circle().stroke(Color.white.opacity(0.8), lineWidth: 2))
                .padding(.top, 32)
            Text(title).font(Pearl.display()).foregroundColor(Pearl.ink)
            Text(subtitle).foregroundColor(Pearl.muted)
        }
    }

    private var title: String {
        switch step {
        case .email: return "Welcome back"
        case .code: return "Check your email"
        case .password: return "Sign in"
        case .confirm, .waiting, .recovery: return "Confirm it's you"
        }
    }

    private var subtitle: String {
        switch step {
        case .email: return "Sign in to Pearl with your email. We'll send you a code."
        case .code: return "We sent a 6-digit code to \(email)."
        case .password: return "With the username and password you set up."
        case .confirm: return "This iPhone is new to your account. Approve it from a device you've signed in on before."
        case .waiting:
            let on = choices?.approve?.label ?? "your other device"
            return "Open Pearl on \(on) and approve this sign-in."
        case .recovery: return "Enter one of the recovery codes you saved."
        }
    }

    // MARK: Steps

    @ViewBuilder private var content: some View {
        switch step {
        case .email:
            field("Email", text: $email, keyboard: .emailAddress, content: .emailAddress)
            Button(busy ? "Sending…" : "Send me a code") { run(sendCode) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy || !email.contains("@"))
            Button("Use a username and password instead") { go(.password) }
                .foregroundColor(Pearl.action)
        case .code:
            field("6-digit code", text: $code, keyboard: .numberPad, content: .oneTimeCode)
            Button(busy ? "Checking…" : "Continue") { run(verifyCode) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy || code.filter(\.isNumber).count < 6)
            Button("Send a new code") { run(sendCode) }.foregroundColor(Pearl.action)
            Button("Use a different email") { code = ""; go(.email) }.foregroundColor(Pearl.action)
        case .password:
            field("Username", text: $username, keyboard: .default, content: .username)
            SecureField("Password", text: $password)
                .textContentType(.password)
                .padding(14)
                .background(Pearl.card)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Pearl.border))
            Button(busy ? "Signing in…" : "Sign in") { run(signInWithPassword) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy || username.isEmpty || password.isEmpty)
            Button("Use an email code instead") { go(.email) }.foregroundColor(Pearl.action)
        case .confirm:
            if let label = choices?.approve?.label {
                Button("Approve on \(label)") { run(askApproval) }.buttonStyle(PrimaryButtonStyle())
            }
            if choices?.recovery == true {
                Button("Use a recovery code") { go(.recovery) }.buttonStyle(SecondaryButtonStyle())
            }
            Button("Cancel") { run(cancelPending) }.foregroundColor(Pearl.action)
        case .waiting:
            HStack(spacing: 12) {
                ProgressView()
                Text(waitWords).foregroundColor(Pearl.muted)
            }
            Button("Ask again") { run(askApproval) }.buttonStyle(SecondaryButtonStyle())
            if choices?.recovery == true {
                Button("Use a recovery code instead") { go(.recovery) }.foregroundColor(Pearl.action)
            }
            Button("Cancel") { run(cancelPending) }.foregroundColor(Pearl.action)
        case .recovery:
            field("Recovery code", text: $recovery, keyboard: .asciiCapable, content: .oneTimeCode)
            Button(busy ? "Checking…" : "Continue") { run(useRecovery) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy || recovery.trimmingCharacters(in: .whitespaces).isEmpty)
            Button("Back") { go(.confirm) }.foregroundColor(Pearl.action)
        }
    }

    private var waitWords: String {
        switch waitState {
        case "refused": return "That sign-in was turned down."
        case "expired": return "That request expired. Ask again."
        default: return "Waiting for your approval…"
        }
    }

    private func field(_ label: String, text: Binding<String>, keyboard: UIKeyboardType,
                       content: UITextContentType) -> some View {
        TextField(label, text: text)
            .keyboardType(keyboard)
            .textContentType(content)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding(14)
            .background(Pearl.card)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Pearl.border))
    }

    // MARK: Server address

    private var serverSetting: some View {
        DisclosureGroup(isExpanded: $showServer) {
            VStack(alignment: .leading, spacing: 8) {
                TextField("https://…", text: $server)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(Pearl.card)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Pearl.border))
                HStack {
                    Button("Save") { saveServer() }.foregroundColor(Pearl.action)
                    Spacer()
                    Button("Use Pearl's server") {
                        server = APIClient.defaultServer
                        saveServer()
                    }
                    .foregroundColor(Pearl.action)
                }
            }
            .padding(.top, 8)
        } label: {
            Text("Server").font(.subheadline).foregroundColor(Pearl.muted)
        }
        .padding(.top, 24)
    }

    private func saveServer() {
        let trimmed = server.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), url.scheme == "https" || url.scheme == "http" else {
            error = "Enter an address that starts with https://"
            return
        }
        app.api.baseURL = url
        error = nil
        info = "Pearl will sign in at \(url.host ?? trimmed)."
    }

    // MARK: Actions

    private func go(_ next: Step) {
        error = nil
        info = nil
        step = next
    }

    private func run(_ action: @escaping () async throws -> Void) {
        busy = true
        error = nil
        Task {
            do {
                try await action()
            } catch {
                self.error = error.localizedDescription
            }
            busy = false
        }
    }

    private func sendCode() async throws {
        let sent: CodeSent = try await app.api.post("api/auth/code/start",
                                                    ["email": email.trimmingCharacters(in: .whitespaces)])
        step = .code
        info = "Code sent to \(sent.sentTo ?? email)."
    }

    private func verifyCode() async throws {
        let reply: SignInReply = try await app.api.post("api/auth/code/verify", [
            "email": email.trimmingCharacters(in: .whitespaces),
            "code": code.filter(\.isNumber),
        ])
        handle(reply)
    }

    private func signInWithPassword() async throws {
        let reply: SignInReply = try await app.api.post("api/auth/login",
                                                        ["username": username, "password": password])
        handle(reply)
    }

    private func handle(_ reply: SignInReply) {
        if reply.signedIn == true {
            app.signedIn(reply.user)
        } else if reply.confirmDevice == true {
            choices = reply.choices
            info = nil
            step = .confirm
        } else {
            error = "That didn't work. Try again."
        }
    }

    private func askApproval() async throws {
        let _: OK = try await app.api.post("api/auth/device/ask")
        waitState = "pending"
        step = .waiting
        Task { await poll() }
    }

    /// Ask the server every few seconds until the other device answers.
    private func poll() async {
        while step == .waiting {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard step == .waiting else { return }
            do {
                let status: DeviceStatus = try await app.api.get("api/auth/device/status")
                if status.signedIn == true {
                    let me: AuthStatus = try await app.api.get("api/auth/status")
                    app.signedIn(me.user ?? status.user)
                    return
                }
                waitState = status.state
                if status.state == "refused" || status.state == "expired" { return }
            } catch {
                self.error = error.localizedDescription
                return
            }
        }
    }

    private func useRecovery() async throws {
        let reply: SignInReply = try await app.api.post("api/auth/device/recovery",
                                                        ["code": recovery.trimmingCharacters(in: .whitespaces)])
        if reply.signedIn == true {
            let me: AuthStatus = try await app.api.get("api/auth/status")
            app.signedIn(me.user ?? reply.user)
        } else {
            error = "That recovery code didn't work."
        }
    }

    private func cancelPending() async throws {
        let _: OK = try await app.api.post("api/auth/device/cancel")
        go(.email)
    }
}
