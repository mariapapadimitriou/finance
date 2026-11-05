import SwiftUI

/// Signed out: Welcome, then creating an account (O-01 to O-03) or signing
/// back in (A-01 to A-07, A-10), as THL-114 and THL-119 design them. Email
/// and a strong password; a six-digit email code on a new iPhone.
@MainActor
struct AuthFlow: View {
    @EnvironmentObject private var app: AppModel
    @State private var path: [AuthRoute] = []

    var body: some View {
        NavigationStack(path: $path) {
            WelcomeView(path: $path)
                .navigationDestination(for: AuthRoute.self) { route in
                    switch route {
                    case .create(let email): CreateAccountView(path: $path, email: email)
                    case .verify(let email, let password, let resendIn):
                        VerifyEmailView(path: $path, email: email, password: password, resendIn: resendIn)
                    case .signIn(let email): SignInView(path: $path, email: email)
                    case .loginCode(let email, let resendIn): LoginCodeView(path: $path, email: email, resendIn: resendIn)
                    case .cantGetCode: CantGetCodeView(path: $path)
                    case .pause(let seconds): ShortPauseView(path: $path, seconds: seconds)
                    case .forgot(let email): ForgotPasswordView(path: $path, email: email)
                    case .resetSent: ResetSentView(path: $path)
                    case .newPassword(let token): NewPasswordView(path: $path, token: token)
                    case .faceID(let user): FaceIDOfferView(mode: .newIPhone) { app.signedIn(user) }
                    case .confirmDevice(let choices): ConfirmDeviceView(path: $path, choices: choices)
                    case .waitingApproval(let from): WaitingApprovalView(path: $path, from: from)
                    case .recoveryCode: RecoveryCodeView(path: $path)
                    }
                }
        }
        .tint(Pearl.ink)
        .onChange(of: app.resetToken) { token in
            if let token = token {
                path = [.newPassword(token: token)]
                app.resetToken = nil
            }
        }
        .onAppear {
            if let token = app.resetToken {
                path = [.newPassword(token: token)]
                app.resetToken = nil
            }
        }
    }
}

enum AuthRoute: Hashable {
    case create(email: String)
    case verify(email: String, password: String, resendIn: Int)
    case signIn(email: String)
    case loginCode(email: String, resendIn: Int)
    case cantGetCode
    case pause(seconds: Int)
    case forgot(email: String)
    case resetSent
    case newPassword(token: String)
    case faceID(PearlUser?)
    /// A-11, the wait for her other device, and A-12.
    case confirmDevice(DeviceChoices)
    case waitingApproval(from: String?)
    case recoveryCode
}

extension PearlUser: Hashable {
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

// MARK: - O-01 Welcome

@MainActor
struct WelcomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State private var showServer = false
    /// LG-01, LG-02, read in the app.
    @State private var doc: PearlDoc?

    var body: some View {
        VStack(spacing: 0) {
            Wordmark()
                .padding(.top, 16)
                .onLongPressGesture { showServer = true }
            HeroShell(width: 256).padding(.top, 58)
            VStack(spacing: 12) {
                (Text("Budgeting that lets\nyou ") + Text("shine.").foregroundColor(Color(hex: 0xC42F6A)))
                    .font(Nacre.largeTitle).tracking(0.4)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                Text("Assess, plan ahead, and start investing.")
                    .font(Nacre.body).multilineTextAlignment(.center)
            }
            .padding(.horizontal, 24)
            .padding(.top, 42)
            Spacer(minLength: 24)
            BottomActions {
                Button("Get started") { path.append(.create(email: "")) }
                    .buttonStyle(NacreButtonStyle())
            } secondary: {
                Button("I already have an account") { path.append(.signIn(email: "")) }
                    .buttonStyle(NacreTextButtonStyle())
                HStack(spacing: 4) {
                    Button("Privacy") { doc = .privacy }
                    Text("·")
                    Button("Terms") { doc = .terms }
                }
                .buttonStyle(.plain)
                .font(Nacre.caption2)
                .foregroundColor(Pearl.ink)
            }
        }
        .nacreScreen()
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $showServer) { ServerSheet() }
        .docSheet($doc)
    }
}

/// Which Pearl server the app talks to: for trying it against a copy running
/// on a Mac. Opened by holding the wordmark on Welcome.
@MainActor
struct ServerSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var server = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("https://…", text: $server)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                } footer: {
                    Text("For developing: a Pearl server on your Mac, like http://localhost:5050.")
                }
                Section {
                    Button("Use Pearl's server") { server = APIClient.defaultServer }
                }
            }
            .navigationTitle("Server")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let trimmed = server.trimmingCharacters(in: .whitespacesAndNewlines)
                        if let url = URL(string: trimmed), url.scheme?.hasPrefix("http") == true {
                            app.api.baseURL = url
                            Task { await app.start() }
                        }
                        dismiss()
                    }
                }
            }
            .onAppear { server = app.api.baseURL.absoluteString }
        }
        .presentationDetents([.medium])
    }
}

// MARK: - O-02 Create your account (O-02a, O-02b)

@MainActor
struct CreateAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State var email: String
    @State private var password = ""
    @State private var rules = PasswordRules.local("", email: "")
    @State private var taken = false
    @State private var error: String?
    @State private var busy = false

    init(path: Binding<[AuthRoute]>, email: String) {
        _path = path
        _email = State(initialValue: email)
    }

    var body: some View {
        NacreScreen {
            ShellProgress(part: 1, name: "Your account")
            Text("Create your account").font(Nacre.title).tracking(0.4)
                .accessibilityAddTraits(.isHeader)
            GlassCard {
                FieldRow(label: "Email", text: $email, prompt: "you@example.com", kind: .email,
                         content: .username)
                RowSeparator()
                FieldRow(label: "Password", text: $password, prompt: "Create a password", kind: .secure,
                         content: .newPassword) { Task { await next() } }
            }
            if taken {
                Hint(text: "There’s already a Pearl account with this email.")
            } else if !password.isEmpty {
                PasswordMeter(rules: rules)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                if taken {
                    Button("Sign in instead") { path.append(.signIn(email: email)) }
                        .buttonStyle(NacreButtonStyle())
                } else {
                    Button("Continue") { Task { await next() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                        .disabled(!rules.ok || !looksLikeEmail || busy)
                }
            }
        }
        .onChange(of: email) { _ in taken = false; check() }
        .onChange(of: password) { _ in check() }
        .task(id: password + "|" + email) {
            // Ask the server about "common or leaked" once typing pauses.
            guard password.count >= 12 else { return }
            try? await Task.sleep(nanoseconds: 400_000_000)
            if let checked: PasswordRules = try? await app.api.post("api/auth/password/check",
                                                                   ["password": password, "email": email]) {
                rules = checked
            }
        }
    }

    private var looksLikeEmail: Bool {
        email.contains("@") && email.split(separator: "@").last?.contains(".") == true
    }

    private func check() {
        rules = PasswordRules.local(password, email: email)
        error = nil
    }

    private func next() async {
        guard rules.ok, looksLikeEmail, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let sent: CodeSent = try await app.api.post("api/auth/signup/start",
                                                        ["email": email, "password": password])
            path.append(.verify(email: sent.sentTo ?? email, password: password, resendIn: sent.resendIn ?? 30))
        } catch {
            if error.serverProblem?.taken == true {
                taken = true
            } else if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else {
                if error.serverProblem?.weak == true {
                    rules = PasswordRules(length: rules.length, common: false, email: rules.email,
                                          more: rules.more, ok: false, segments: 1, label: "Weak")
                }
                self.error = app.handle(error)
            }
        }
    }
}

// MARK: - O-03 Check your email (O-03a)

@MainActor
struct VerifyEmailView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let email: String
    let password: String
    let resendIn: Int

    @State private var code = ""
    @State private var failed = false
    @State private var error: String?
    @State private var busy = false
    @State private var wait = 0

    var body: some View {
        NacreScreen {
            ShellProgress(part: 1, name: "Your account")
            IconOrb(symbol: "envelope")
            Text("Check your email").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("Enter the code we sent to \(email).").font(Nacre.body)
            CodeBoxes(code: $code, failed: failed) { Task { await verify() } }
                .padding(.top, 4)
            if failed {
                Hint(text: error ?? "That code didn’t match. Try again.")
            } else if let error = error {
                Hint(text: error)
            } else {
                ResendLine(wait: $wait) { Task { await resend() } }
            }
        } actions: {
            BottomActions {
                Button("Continue") { Task { await verify() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(code.count < 6 || busy)
            } secondary: {
                Button("Change email") { path.removeLast() }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .onAppear { wait = resendIn }
        .onChange(of: code) { value in if !value.isEmpty && value.count < 6 { failed = false; error = nil } }
    }

    private func verify() async {
        guard code.count == 6, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/code/verify", ["email": email, "code": code])
            if reply.confirmDevice == true, let choices = reply.choices {
                path.append(.confirmDevice(choices))
            } else if reply.signedIn == true {
                app.justCreated = reply.created ?? true
                app.signedIn(reply.user)
            }
        } catch {
            let problem = error.serverProblem
            if problem?.paused == true {
                path.append(.pause(seconds: problem?.retryIn ?? 300))
            } else if problem?.wrong == true {
                failed = true
                self.error = "That code didn’t match. Try again."
                code = ""
            } else {
                failed = problem?.expired == true
                self.error = app.handle(error)
                code = ""
            }
        }
    }

    private func resend() async {
        do {
            let sent: CodeSent = try await app.api.post("api/auth/signup/start", ["email": email, "password": password])
            wait = sent.resendIn ?? 30
            error = nil
            failed = false
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else {
                self.error = app.handle(error)
            }
        }
    }
}

/// "Resend code in 0:38", then "Resend code".
struct ResendLine: View {
    @Binding var wait: Int
    let resend: () -> Void

    var body: some View {
        Group {
            if wait > 0 {
                Hint(text: String(format: "Resend code in %d:%02d", wait / 60, wait % 60), symbol: "clock")
            } else {
                Button(action: resend) {
                    Label("Resend code", systemImage: "arrow.clockwise").font(Nacre.subheadline)
                }
                .foregroundColor(Pearl.ink)
            }
        }
        .task(id: wait > 0) {
            while wait > 0 {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if Task.isCancelled { return }
                wait -= 1
            }
        }
    }
}

// MARK: - A-01 Sign in

@MainActor
struct SignInView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State var email: String
    @State private var password = ""
    @State private var error: String?
    @State private var busy = false

    init(path: Binding<[AuthRoute]>, email: String) {
        _path = path
        _email = State(initialValue: email)
    }

    var body: some View {
        NacreScreen {
            VStack(spacing: 12) {
                HeroShell(width: 140).padding(.bottom, 20)
                Text("Welcome back").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
                Text("Sign in to see your Allowance.").font(Nacre.body)
            }
            .frame(maxWidth: .infinity)
            GlassCard {
                FieldRow(label: "Email", text: $email, prompt: "you@example.com", kind: .email, content: .username)
                RowSeparator()
                FieldRow(label: "Password", text: $password, prompt: "Your password", kind: .secure,
                         content: .password) { Task { await signIn() } }
            }
            if let error = error { Hint(text: error) }
            Button("Forgot password?") { path.append(.forgot(email: email)) }
                .buttonStyle(NacreTextButtonStyle())
        } actions: {
            BottomActions {
                Button("Sign in") { Task { await signIn() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(email.isEmpty || password.isEmpty || busy)
            } secondary: {
                Button("New to Pearl? Create an account") { path.append(.create(email: email)) }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .onChange(of: email) { _ in error = nil }
        .onChange(of: password) { _ in error = nil }
    }

    private func signIn() async {
        guard !email.isEmpty, !password.isEmpty, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/login", [
                "email": email.trimmingCharacters(in: .whitespaces), "password": password, "two_step": "email"])
            if reply.codeNeeded == true {
                path.append(.loginCode(email: reply.sentTo ?? email, resendIn: reply.resendIn ?? 30))
            } else if reply.signedIn == true {
                finish(reply.user)
            }
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else {
                self.error = app.handle(error)
            }
        }
    }

    private func finish(_ user: PearlUser?) {
        if !app.faceIDOn && AppLock.available {
            path.append(.faceID(user))
        } else {
            app.signedIn(user)
        }
    }
}

// MARK: - A-02 Check your email (new iPhone), A-03 Code didn't match

@MainActor
struct LoginCodeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let email: String
    let resendIn: Int

    @State private var code = ""
    @State private var failed = false
    @State private var error: String?
    @State private var busy = false
    @State private var wait = 0

    var body: some View {
        NacreScreen {
            IconOrb(symbol: "envelope")
            Text("Check your email").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("New iPhone? Enter the code we sent to \(email).").font(Nacre.body)
            CodeBoxes(code: $code, failed: failed) { Task { await verify() } }
                .padding(.top, 4)
            if failed || error != nil {
                Hint(text: error ?? "That code didn’t match. Try again.")
            } else {
                ResendLine(wait: $wait) { Task { await resend() } }
            }
        } actions: {
            BottomActions {
                Button("Continue") { Task { await verify() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(code.count < 6 || busy)
            } secondary: {
                Button("Can’t get the code?") { path.append(.cantGetCode) }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .onAppear { wait = resendIn }
        .onChange(of: code) { value in if !value.isEmpty && value.count < 6 { failed = false; error = nil } }
    }

    private func verify() async {
        guard code.count == 6, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/login/code", ["code": code])
            if reply.confirmDevice == true, let choices = reply.choices {
                // A-11: the server wants this iPhone confirmed first.
                path.append(.confirmDevice(choices))
            } else if reply.signedIn == true {
                if !app.faceIDOn && AppLock.available {
                    path.append(.faceID(reply.user))
                } else {
                    app.signedIn(reply.user)
                }
            }
        } catch {
            let problem = error.serverProblem
            code = ""
            if problem?.paused == true {
                path.append(.pause(seconds: problem?.retryIn ?? 300))
            } else if problem?.wrong == true {
                failed = true
                self.error = "That code didn’t match. Try again."
            } else if problem?.expired == true {
                failed = true
                self.error = "That code has expired. Send a new one."
                wait = 0
            } else {
                self.error = app.handle(error)
            }
        }
    }

    private func resend() async {
        do {
            let sent: CodeSent = try await app.api.post("api/auth/login/resend")
            wait = sent.resendIn ?? 30
            error = nil
            failed = false
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else {
                self.error = app.handle(error)
            }
        }
    }
}

// MARK: - A-10 Can't get the code?

@MainActor
struct CantGetCodeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        NacreScreen(scrolls: false) {
            MessageBlock(title: "Can’t get the code?",
                         line: "Check your spam folder, or send a new code. Still stuck? We’ll help you get back in.") {
                IconOrb(symbol: "envelope", size: 120)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Send a new code") { Task { await resend() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
            } secondary: {
                if let contact = app.contact, let url = URL(string: "mailto:\(contact)") {
                    Link("Contact support", destination: url)
                        .buttonStyle(NacreTextButtonStyle())
                }
            }
        }
    }

    private func resend() async {
        busy = true
        defer { busy = false }
        do {
            let sent: CodeSent = try await app.api.post("api/auth/login/resend")
            path.removeLast()
            if case .loginCode(let email, _) = path.last {
                path[path.count - 1] = .loginCode(email: email, resendIn: sent.resendIn ?? 30)
            }
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else if error.serverProblem?.expired == true {
                // The sign-in waited too long: start again from the password.
                path = [.signIn(email: "")]
            } else {
                self.error = app.handle(error)
            }
        }
    }
}

// MARK: - A-04 Take a short pause

@MainActor
struct ShortPauseView: View {
    @Binding var path: [AuthRoute]
    let seconds: Int

    var body: some View {
        NacreScreen(scrolls: false) {
            MessageBlock(title: "Take a short pause", line: line) {
                Image("ShellClosed").resizable().frame(width: 140, height: 116.7).accessibilityHidden(true)
            }
        } actions: {
            BottomActions {
                Button("OK") {
                    // Back to where she typed her email.
                    if let i = path.lastIndex(where: {
                        if case .signIn = $0 { return true }
                        if case .create = $0 { return true }
                        return false
                    }) {
                        path = Array(path.prefix(i + 1))
                    } else {
                        path.removeLast()
                    }
                }
                .buttonStyle(NacreButtonStyle())
            }
        }
    }

    private var line: String {
        let minutes = max(1, (seconds + 59) / 60)
        return "Too many tries. Try again in \(minutes) minute\(minutes == 1 ? "" : "s")."
    }
}

// MARK: - A-05 Reset your password, A-06 Reset link sent

@MainActor
struct ForgotPasswordView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State var email: String
    @State private var error: String?
    @State private var busy = false

    init(path: Binding<[AuthRoute]>, email: String) {
        _path = path
        _email = State(initialValue: email)
    }

    var body: some View {
        NacreScreen {
            VStack(spacing: 12) {
                IconOrb(symbol: "key", size: 96).padding(.bottom, 8)
                Text("Reset your password").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
                Text("We’ll email you a link to reset it.").font(Nacre.body)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 8)
            GlassCard {
                FieldRow(label: "Email", text: $email, prompt: "you@example.com", kind: .email, content: .username) {
                    Task { await send() }
                }
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Send link") { Task { await send() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(!email.contains("@") || busy)
            }
        }
    }

    private func send() async {
        guard email.contains("@"), !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/auth/forgot", ["identifier": email])
            path.append(.resetSent)
        } catch {
            self.error = app.handle(error)
        }
    }
}

@MainActor
struct ResetSentView: View {
    @Binding var path: [AuthRoute]
    @Environment(\.openURL) private var openURL

    var body: some View {
        NacreScreen(scrolls: false) {
            MessageBlock(title: "Check your email", line: "We sent a reset link. It expires in 15 minutes.") {
                IconOrb(symbol: "envelope", size: 120)
            }
        } actions: {
            BottomActions {
                Button("Open Mail") { openURL(URL(string: "message://")!) }
                    .buttonStyle(NacreButtonStyle())
            } secondary: {
                Button("Back to sign in") {
                    if let i = path.lastIndex(where: { if case .signIn = $0 { return true }; return false }) {
                        path = Array(path.prefix(i + 1))
                    } else {
                        path = [.signIn(email: "")]
                    }
                }
                .buttonStyle(NacreTextButtonStyle())
            }
        }
    }
}

// MARK: - A-07 Choose a new password

@MainActor
struct NewPasswordView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let token: String
    @State private var password = ""
    @State private var confirm = ""
    @State private var rules = PasswordRules.local("", email: "")
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        NacreScreen {
            Text("Choose a new password").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            GlassCard {
                FieldRow(label: "New password", text: $password, prompt: "At least 12 characters", kind: .secure,
                         content: .newPassword)
                RowSeparator()
                FieldRow(label: "Confirm", text: $confirm, prompt: "Type it again", kind: .secure,
                         content: .newPassword) { Task { await save() } }
            }
            if !password.isEmpty { PasswordMeter(rules: rules) }
            if !confirm.isEmpty && confirm != password {
                Hint(text: "The two passwords don’t match yet.")
            }
            Text("You’ll be signed out on your other devices.").font(Nacre.footnote).padding(.horizontal, 4)
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Save password") { Task { await save() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(!rules.ok || confirm != password || busy)
            }
        }
        .onChange(of: password) { value in rules = PasswordRules.local(value, email: ""); error = nil }
        .task(id: password) {
            guard password.count >= 12 else { return }
            try? await Task.sleep(nanoseconds: 400_000_000)
            if let checked: PasswordRules = try? await app.api.post("api/auth/password/check", ["password": password]) {
                rules = checked
            }
        }
    }

    private func save() async {
        guard rules.ok, confirm == password, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/reset", ["token": token, "password": password])
            if reply.signedIn == true { app.signedIn(reply.user) }
        } catch {
            self.error = app.handle(error)
        }
    }
}
