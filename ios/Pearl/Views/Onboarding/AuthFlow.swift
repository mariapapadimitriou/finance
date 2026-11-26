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
            } else if path.isEmpty, let email = SavedSignIn.email {
                // Signed out by the server, not by her: straight to Face ID.
                path = [.signIn(email: email)]
            }
        }
    }
}

enum AuthRoute: Hashable {
    case create(email: String)
    case verify(email: String, password: String, resendIn: Int)
    case signIn(email: String)
    case loginCode(email: String, resendIn: Int)
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

// MARK: - O-01 Welcome (G6-Welcome)

@MainActor
struct WelcomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State private var showServer = false
    /// LG-01, LG-02, read in the app.
    @State private var doc: PearlDoc?

    var body: some View {
        VStack(spacing: 0) {
            OnbWordmark()
                .padding(.top, 8)
                .onLongPressGesture { showServer = true }
            APMark(width: 230).padding(.top, 70)
            VStack(spacing: 10) {
                VStack(spacing: 0) {
                    Text("Budgeting that lets")
                    HStack(spacing: 0) {
                        Text("you ")
                        ShineWord()
                    }
                }
                .font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Budgeting that lets you shine.")
                .accessibilityAddTraits(.isHeader)
                // Approved 2026-11-18: what Pearl is for, in one line.
                Text("See what\u{2019}s yours to spend, and plan ahead.")
                    .font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
            }
            .padding(.horizontal, 20)
            .padding(.top, 52)
            Spacer(minLength: 24)
            VStack(spacing: 12) {
                OnbPrimary(title: "Get started") { path.append(.create(email: "")) }
                Button("I already have an account") { path.append(.signIn(email: "")) }
                    .buttonStyle(APSecondaryButtonStyle())
                HStack(spacing: 18) {
                    APQuietButton(title: "Privacy", tone: Pearl.muted) { doc = .privacy }
                    APQuietButton(title: "Terms", tone: Pearl.muted) { doc = .terms }
                }
                .font(Nacre.footnote)
            }
            .padding(.horizontal, 16).padding(.bottom, 4)
        }
        .nacreScreen(.nacre)
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $showServer) { ServerSheet() }
        .docSheet($doc)
    }
}

/// "shine." in the welcome's lilac-to-rose (g6.py `welcome`).
struct ShineWord: View {
    var body: some View {
        Text("shine.")
            .foregroundColor(.clear)
            .overlay(
                LinearGradient(colors: [Color(hex: 0x9B6FD9), Pearl.action], startPoint: .leading, endPoint: .trailing)
                    .mask(Text("shine."))
            )
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

// MARK: - O-02 Create your account (O-02a, O-02b; G6-Create)

@MainActor
struct CreateAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State var email: String
    @State private var password = ""
    @State private var rules = PasswordRules.local("", email: "")
    /// The password the server last judged "common or leaked" for.
    @State private var checkedFor = ""
    @State private var taken = false
    @State private var error: String?
    @State private var busy = false

    init(path: Binding<[AuthRoute]>, email: String) {
        _path = path
        _email = State(initialValue: email)
    }

    var body: some View {
        OnbScreen(part: 1, partName: "Your account") {
            OnbTitle(title: "Create your account")
            OnbField(label: "Email", text: $email, prompt: "you@example.com", kind: .email, content: .username,
                     error: taken ? "There\u{2019}s already a Pearl account with this email." : nil,
                     focusOnAppear: email.isEmpty)
                .padding(.top, 8)
            OnbField(label: "Password", text: $password, prompt: "Create a password", kind: .secure,
                     content: .newPassword) { Task { await next() } }
            if !taken && !password.isEmpty {
                PasswordChecks(rules: rules, commonChecked: password.count < 12 || checkedFor == password)
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            if taken {
                OnbPrimary(title: "Sign in instead") { path.append(.signIn(email: email)) }
                APQuietButton(title: "Use a different email") { email = ""; taken = false }
            } else {
                OnbPrimary(title: "Continue", busy: busy, enabled: rules.ok && looksLikeEmail) {
                    Task { await next() }
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
                checkedFor = password
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
                    checkedFor = password
                }
                self.error = app.handle(error)
            }
        }
    }
}

// MARK: - O-03 Check your email (O-03a; G6-Code)

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
        OnbScreen(part: 1, partName: "Your account") {
            OnbTitle(title: "Check your email", line: "Enter the code we sent to \(email).")
            CodeWells(code: $code, failed: failed) { Task { await verify() } }
                .padding(.top, 6)
            CodeFoot(failed: failed, error: error, wait: $wait) { Task { await resend() } }
        } actions: {
            OnbPrimary(title: "Continue", busy: busy, enabled: code.count == 6) { Task { await verify() } }
            if failed || error != nil {
                APQuietButton(title: "Resend code") { Task { await resend() } }
            }
            APQuietButton(title: "Change email") { path.removeLast() }
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
                app.remember(email: email, password: password)
                app.signedIn(reply.user)
            }
        } catch {
            let problem = error.serverProblem
            if problem?.paused == true {
                path.append(.pause(seconds: problem?.retryIn ?? 300))
            } else if problem?.wrong == true {
                failed = true
                self.error = "That code didn\u{2019}t match. Try again."
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

/// Under the code wells: the reason in `danger` (`.ferr`), or the resend note.
struct CodeFoot: View {
    let failed: Bool
    let error: String?
    @Binding var wait: Int
    let resend: () -> Void

    var body: some View {
        if failed || error != nil {
            Text(error ?? "That code didn\u{2019}t match. Try again.")
                .font(Nacre.footnote).foregroundColor(Pearl.danger)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
        } else {
            ResendLine(wait: $wait, resend: resend)
        }
    }
}

// MARK: - A-01 Sign in (G6-SignIn)

@MainActor
struct SignInView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    @State var email: String
    @State private var password = ""
    @State private var error: String?
    @State private var busy = false
    /// Face ID can sign her in with the password saved on this iPhone.
    @State private var faceID = false
    /// "Use my password" on the Face ID return screen.
    @State private var usePassword = false
    @State private var changed = false

    init(path: Binding<[AuthRoute]>, email: String) {
        _path = path
        _email = State(initialValue: email)
    }

    private var faceReturn: Bool { faceID && !usePassword }

    var body: some View {
        OnbScreen {
            if faceReturn {
                APMark(width: 150).frame(maxWidth: .infinity).padding(.top, 40)
                OnbTitle(title: "Welcome back", line: email, centred: true)
            } else if changed {
                OnbTitle(title: "Welcome back")
                APBanner(symbol: "key", text: "Your password has changed. Sign in with the new one.")
            } else {
                OnbTitle(title: "Welcome back", line: "Sign in to see your Allowance.")
            }
            if !faceReturn { fields }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            if faceReturn {
                Button {
                    Task { await signInWithFaceID() }
                } label: {
                    Label("Sign in with Face ID", systemImage: "faceid")
                }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(busy)
                APQuietButton(title: "Use my password") { usePassword = true }
                // Approved 2026-11-18: someone else on this iPhone signs in as themselves.
                APQuietButton(title: "Not you? Use a different email", identifier: "not-you") {
                    usePassword = true
                    faceID = false
                    email = ""
                    password = ""
                    error = nil
                }
            } else {
                OnbPrimary(title: "Sign in", busy: busy, enabled: !email.isEmpty && !password.isEmpty) {
                    Task { await signIn() }
                }
                APQuietButton(title: "New to Pearl? Create an account") { path.append(.create(email: email)) }
            }
        }
        .onChange(of: email) { value in
            error = nil
            faceID = canUseFaceID(for: value)
        }
        .onChange(of: password) { _ in error = nil }
        .task {
            faceID = canUseFaceID(for: email)
            if faceID { await signInWithFaceID() }
        }
    }

    private var fields: some View {
        VStack(alignment: .leading, spacing: 12) {
            OnbField(label: "Email", text: $email, prompt: "you@example.com", kind: .email, content: .username,
                     focusOnAppear: email.isEmpty)
            OnbField(label: "Password", text: $password, prompt: "Your password", kind: .secure,
                     content: .password, focusOnAppear: !email.isEmpty) { Task { await signIn() } }
            HStack {
                Spacer()
                APQuietButton(title: "Forgot password?") { path.append(.forgot(email: email)) }
            }
        }
        .padding(.top, 8)
    }

    private func canUseFaceID(for email: String) -> Bool {
        guard let saved = SavedSignIn.email, AppLock.available else { return false }
        return saved.caseInsensitiveCompare(email.trimmingCharacters(in: .whitespaces)) == .orderedSame
    }

    private func signInWithFaceID() async {
        guard !busy else { return }
        guard let saved = await SavedSignIn.password() else {
            // Cancelled, or the saved one is gone: the password still works.
            faceID = canUseFaceID(for: email)
            return
        }
        await signIn(password: saved, fromFaceID: true)
    }

    private func signIn() async {
        guard !password.isEmpty else { return }
        await signIn(password: password, fromFaceID: false)
    }

    private func signIn(password: String, fromFaceID: Bool) async {
        guard !email.isEmpty, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/login", [
                "email": email.trimmingCharacters(in: .whitespaces), "password": password, "two_step": "email"])
            if !fromFaceID { app.remember(email: email, password: password) }
            if reply.codeNeeded == true {
                path.append(.loginCode(email: reply.sentTo ?? email, resendIn: reply.resendIn ?? 30))
            } else if reply.signedIn == true {
                finish(reply.user)
            }
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                path.append(.pause(seconds: seconds))
            } else if fromFaceID, let said = error.serverProblem?.error,
                      said.contains("don't match") || said.contains("don’t match") {
                // The saved password stopped working (changed somewhere else).
                SavedSignIn.clear()
                faceID = false
                changed = true
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

// MARK: - A-02 Check your email (new iPhone), A-03 Code didn't match (G6-Code)

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
    /// A-10 Can't get the code? (a Pearl sheet over this page).
    @State private var cantGet = false

    var body: some View {
        OnbScreen {
            OnbTitle(title: "Check your email", line: "New iPhone? Enter the code we sent to \(email).")
            CodeWells(code: $code, failed: failed) { Task { await verify() } }
                .padding(.top, 6)
            CodeFoot(failed: failed, error: error, wait: $wait) { Task { await resend() } }
        } actions: {
            OnbPrimary(title: "Continue", busy: busy, enabled: code.count == 6) { Task { await verify() } }
            if failed || error != nil {
                APQuietButton(title: "Resend code") { Task { await resend() } }
            }
            APQuietButton(title: "Can\u{2019}t get the code?") { cantGet = true }
        }
        .onAppear { wait = resendIn }
        .onChange(of: code) { value in if !value.isEmpty && value.count < 6 { failed = false; error = nil } }
        .sheet(isPresented: $cantGet) {
            CantGetCodeSheet(path: $path, onSent: { seconds in
                cantGet = false
                wait = seconds
                failed = false
                error = nil
            }, onClose: { cantGet = false })
        }
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
                self.error = "That code didn\u{2019}t match. Try again."
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

// MARK: - A-10 Can't get the code? (G6-Code, a Pearl sheet)

@MainActor
struct CantGetCodeSheet: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let onSent: (Int) -> Void
    let onClose: () -> Void
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        PearlSheet {
            APSheetTitle(title: "Can\u{2019}t get the code?", close: onClose)
            Text("Check your spam folder, or send a new code. Still stuck? We\u{2019}ll help you get back in.")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let error = error { APErrorLine(text: error) }
        } footer: {
            VStack(spacing: 12) {
                OnbPrimary(title: "Send a new code", busy: busy) { Task { await resend() } }
                if let contact = app.contact, let url = URL(string: "mailto:\(contact)") {
                    Link("Contact support", destination: url).buttonStyle(APSecondaryButtonStyle())
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
        }
    }

    private func resend() async {
        busy = true
        defer { busy = false }
        do {
            let sent: CodeSent = try await app.api.post("api/auth/login/resend")
            onSent(sent.resendIn ?? 30)
        } catch {
            if let seconds = error.serverProblem?.retryIn, error.serverProblem?.paused == true {
                onClose()
                path.append(.pause(seconds: seconds))
            } else if error.serverProblem?.expired == true {
                // The sign-in waited too long: start again from the password.
                onClose()
                path = [.signIn(email: "")]
            } else {
                self.error = "Couldn\u{2019}t send a new code. Try again in a minute."
                _ = app.handle(error)
            }
        }
    }
}

// MARK: - A-04 Take a short pause (G6-Code)

@MainActor
struct ShortPauseView: View {
    @Binding var path: [AuthRoute]
    let seconds: Int

    var body: some View {
        OnbScreen(back: false, scrolls: false) {
            OnbMessage(title: "Take a short pause", line: line, top: 118) { APMark(width: 170) }
        } actions: {
            OnbPrimary(title: "OK") {
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
        }
    }

    private var line: String {
        let minutes = max(1, (seconds + 59) / 60)
        return "Too many tries. Try again in \(minutes) minute\(minutes == 1 ? "" : "s")."
    }
}

// MARK: - A-05 Reset your password, A-06 Reset link sent (G6-Forgot)

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
        OnbScreen {
            OnbTitle(title: "Reset your password", line: "We\u{2019}ll email you a link to reset it.")
            OnbField(label: "Email", text: $email, prompt: "you@example.com", kind: .email, content: .username,
                     focusOnAppear: true) { Task { await send() } }
                .padding(.top, 8)
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Send link", busy: busy, enabled: email.contains("@")) { Task { await send() } }
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
        OnbScreen(back: false, scrolls: false) {
            OnbMessage(title: "Check your email", line: "We sent a reset link. It expires in 15 minutes.", top: 98) {
                OnbOrb(symbol: "envelope")
            }
        } actions: {
            OnbPrimary(title: "Open Mail") { openURL(URL(string: "message://")!) }
            APQuietButton(title: "Back to sign in") {
                if let i = path.lastIndex(where: { if case .signIn = $0 { return true }; return false }) {
                    path = Array(path.prefix(i + 1))
                } else {
                    path = [.signIn(email: "")]
                }
            }
        }
    }
}

// MARK: - A-07 Choose a new password (G6-Forgot)

@MainActor
struct NewPasswordView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [AuthRoute]
    let token: String
    @State private var password = ""
    @State private var confirm = ""
    @State private var rules = PasswordRules.local("", email: "")
    @State private var checkedFor = ""
    @State private var error: String?
    @State private var busy = false

    private var mismatch: Bool { !confirm.isEmpty && confirm != password && confirm.count >= password.count }

    var body: some View {
        OnbScreen(back: false) {
            OnbTitle(title: "Choose a new password")
            OnbField(label: "New password", text: $password, prompt: "At least 12 characters", kind: .secure,
                     content: .newPassword, focusOnAppear: true)
                .padding(.top, 8)
            if !password.isEmpty {
                PasswordChecks(rules: rules, commonChecked: password.count < 12 || checkedFor == password)
            }
            OnbField(label: "Type it again", text: $confirm, prompt: "Type it again", kind: .secure,
                     content: .newPassword,
                     error: mismatch ? "The two passwords don\u{2019}t match yet." : nil) { Task { await save() } }
            ProfileNote("You\u{2019}ll be signed out on your other devices.")
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Save password", busy: busy, enabled: rules.ok && confirm == password) {
                Task { await save() }
            }
        }
        .onChange(of: password) { value in rules = PasswordRules.local(value, email: ""); error = nil }
        .task(id: password) {
            guard password.count >= 12 else { return }
            try? await Task.sleep(nanoseconds: 400_000_000)
            if let checked: PasswordRules = try? await app.api.post("api/auth/password/check", ["password": password]) {
                rules = checked
                checkedFor = password
            }
        }
    }

    private func save() async {
        guard rules.ok, confirm == password, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: SignInReply = try await app.api.post("api/auth/reset", ["token": token, "password": password])
            if reply.signedIn == true {
                // The old password is saved for Face ID no longer.
                SavedSignIn.clear()
                if let email = reply.user?.email { app.remember(email: email, password: password) }
                app.signedIn(reply.user)
            }
        } catch {
            self.error = app.handle(error)
        }
    }
}
