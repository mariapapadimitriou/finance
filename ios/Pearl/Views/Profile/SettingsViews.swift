import SwiftUI

// Profile's settings (S-01 to S-04): sign-in and security. The banks she's
// linked are Accounts (AccountsViews.swift). Passkeys (S-03) wait for the app's associated domain, so
// there's no passkey row yet.

/// A settings screen: back, a large title, its sections, and any buttons
/// along the bottom, all on the nacre.
private struct SettingsPage<Content: View, Bottom: View>: View {
    @Environment(\.dismiss) private var dismiss
    let title: String
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.bottom, 8)
                content()
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if Bottom.self != EmptyView.self {
                VStack(spacing: 6, content: bottom)
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
                    .background(.regularMaterial)
                    .overlay(alignment: .top) { Rectangle().fill(Nacre.separator).frame(height: 0.5) }
            }
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                }
                .accessibilityLabel("Back")
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
    }
}

extension SettingsPage where Bottom == EmptyView {
    init(title: String, @ViewBuilder content: @escaping () -> Content) {
        self.init(title: title, content: content, bottom: { EmptyView() })
    }
}

private func settingsSection(_ text: String) -> some View {
    Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
        .padding(.horizontal, 16).padding(.top, 12)
        .accessibilityAddTraits(.isHeader)
}

private func settingsNote(_ text: String) -> some View {
    Text(text).font(Nacre.footnote).foregroundColor(Pearl.muted)
        .padding(.horizontal, 16)
        .fixedSize(horizontal: false, vertical: true)
}

/// "Password   Change ›".
private func settingsRow(_ title: String, value: String? = nil, chevron: Bool = false,
                         tone: Color = Pearl.ink) -> some View {
    HStack(spacing: 8) {
        Text(title).font(Nacre.body).foregroundColor(tone)
        Spacer(minLength: 8)
        if let value = value {
            Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
        }
        if chevron {
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
    }
    .padding(.horizontal, 16).frame(minHeight: 52)
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
}

// MARK: - S-01 Sign-in & security, S-04 Sign out other devices

@MainActor
struct SignInSecurityView: View {
    @EnvironmentObject private var app: AppModel
    @State private var devices: [Device] = []
    @State private var faceID = false
    @State private var confirming = false
    /// SEC-12: the device she's removing.
    @State private var removingDevice: Device?
    /// SEC-08: recovery codes she has left; SEC-09: the new ones, shown once.
    @State private var codesLeft: Int?
    @State private var askingCodes = false
    @State private var codes: RecoveryCodes?
    @State private var busy = false
    @State private var message: String?
    @State private var error: String?

    struct Device: Decodable, Identifiable, Hashable {
        let id: String
        let label: String?
        /// Seconds since 1970.
        let lastUsedAt: Double?
        let this: Bool?

        enum CodingKeys: String, CodingKey {
            case id, label, this
            case lastUsedAt = "last_used_at"
        }
    }

    var body: some View {
        SettingsPage(title: "Sign-in & security") {
            settingsSection("Sign-in")
            GlassCard {
                NavigationLink { ChangeEmailView() } label: {
                    settingsRow("Email", value: app.user?.email ?? "Change", chevron: true)
                }
                .buttonStyle(.plain)
                RowSeparator()
                NavigationLink { ChangePasswordView() } label: {
                    settingsRow("Password", value: "Change", chevron: true)
                }
                .buttonStyle(.plain)
                RowSeparator()
                settingsRow("Email code on new devices", value: "On")
            }
            settingsNote("Two-step sign-in is always on.")

            if AppLock.available || app.faceIDOn {
                settingsSection("Face ID")
                GlassCard {
                    Toggle(isOn: Binding(get: { faceID }, set: { on in Task { await setFaceID(on) } })) {
                        Text("Unlock with Face ID").font(Nacre.body).foregroundColor(Pearl.ink)
                    }
                    .tint(Pearl.action)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                }
                settingsNote("Asks for Face ID when you come back to Pearl after a minute away.")
            }

            // Recovery codes (SEC-08, SEC-09) are left out for now (2026-11-04).

            settingsSection("Your devices")
            GlassCard {
                ForEach(Array(devices.enumerated()), id: \.element.id) { i, d in
                    if i > 0 { RowSeparator() }
                    if d.this == true {
                        settingsRow("This iPhone", value: "Now")
                    } else {
                        // SEC-11 (THL-287): each other device can be removed.
                        HStack {
                            Text([d.label ?? "Device", d.lastUsedAt.map(Self.ago)].compactMap { $0 }.joined(separator: " · "))
                                .font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Spacer()
                            Button("Remove") { removingDevice = d }
                                .font(Nacre.body).foregroundColor(Pearl.action)
                                .buttonStyle(.plain)
                                .disabled(busy)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                    }
                }
                if devices.contains(where: { $0.this != true }) {
                    RowSeparator()
                    Button { confirming = true } label: {
                        settingsRow("Sign out other devices", tone: Pearl.action)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if devices.isEmpty {
                    settingsRow("This iPhone", value: "Now")
                }
            }
            if let message = message { settingsNote(message) }
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
            }

            // At the bottom of Sign-in & security, not on Profile (2026-11-08).
            ResetPearlCard().padding(.top, 16)
        }
        .task {
            faceID = app.faceIDOn
            codesLeft = app.user?.recoveryCodes
            await load()
        }
        .alert("Remove \(removingDevice?.label ?? "this device")?",
               isPresented: Binding(get: { removingDevice != nil }, set: { if !$0 { removingDevice = nil } })) {
            Button("Cancel", role: .cancel) {}
            Button("Remove", role: .destructive) {
                if let d = removingDevice { Task { await remove(d) } }
            }
        } message: {
            Text("It’s signed out of Pearl and won’t be asked to approve sign-ins again.")
        }
        .alert("Make new recovery codes?", isPresented: $askingCodes) {
            Button("Cancel", role: .cancel) {}
            Button("Make new codes") { Task { await makeCodes() } }
        } message: {
            Text("Your old ones stop working.")
        }
        .sheet(item: $codes) { made in
            RecoveryCodesSheet(codes: made.codes)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .alert("Sign out of other devices?", isPresented: $confirming) {
            Button("Cancel", role: .cancel) {}
            Button("Sign out") { Task { await signOutOthers() } }
        } message: {
            Text(othersLine)
        }
    }

    private var others: [Device] { devices.filter { $0.this != true } }

    private var codesValue: String {
        guard let left = codesLeft, left > 0 else { return "Make them" }
        return "\(left) of 10 left"
    }

    private func makeCodes() async {
        busy = true
        defer { busy = false }
        do {
            let reply: RecoveryCodes = try await app.api.post("api/auth/recovery-codes")
            codesLeft = reply.codes.count
            codes = reply
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// "Your iPad will be signed out of Pearl."
    private var othersLine: String {
        if others.count == 1 { return "\(others[0].label ?? "Your other device") will be signed out of Pearl." }
        return "Your \(others.count) other devices will be signed out of Pearl."
    }

    /// "2 days ago", "Today", from when it was last used.
    static func ago(_ seconds: Double) -> String {
        let day = Date(timeIntervalSince1970: seconds)
        let days = Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: day),
                                                   to: Calendar.current.startOfDay(for: Date())).day ?? 0
        switch days {
        case ..<1: return "Today"
        case 1: return "Yesterday"
        default: return "\(days) days ago"
        }
    }

    private func load() async {
        struct Reply: Decodable { let devices: [Lenient<Device>] }
        do {
            let reply: Reply = try await app.api.get("api/auth/devices")
            devices = reply.devices.compactMap { $0.value }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func setFaceID(_ on: Bool) async {
        if on {
            guard await AppLock.unlock(reason: "Unlock Pearl quickly and privately.") else {
                faceID = false
                error = AppLock.turnedOff ? "Turn on Face ID for Pearl in iPhone Settings first." : nil
                return
            }
        }
        app.faceIDOn = on
        faceID = on
        error = nil
    }

    private func remove(_ d: Device) async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.delete("api/auth/devices/\(d.id)")
            await load()
            message = "\(d.label ?? "That device") is signed out."
        } catch {
            self.error = app.handle(error)
        }
    }

    private func signOutOthers() async {
        busy = true
        defer { busy = false }
        let n = others.count
        do {
            for d in others {
                let _: OK = try await app.api.delete("api/auth/devices/\(d.id)")
            }
            await load()
            message = n == 1 ? "Signed out of 1 other device." : "Signed out of \(n) other devices."
        } catch {
            self.error = app.handle(error)
            await load()
        }
    }
}

// MARK: - S-02 Change password

@MainActor
struct ChangePasswordView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var current = ""
    @State private var new = ""
    @State private var confirm = ""
    @State private var rules = PasswordRules.local("", email: "")
    @State private var busy = false
    @State private var error: String?

    private var email: String { app.user?.email ?? "" }
    private var matches: Bool { !confirm.isEmpty && confirm == new }

    var body: some View {
        Group {
            SettingsPage(title: "Change password") {
                GlassCard {
                    FieldRow(label: "Current password", text: $current, kind: .secure, content: .password)
                    RowSeparator()
                    FieldRow(label: "New password", text: $new, kind: .secure, content: .newPassword)
                    RowSeparator()
                    FieldRow(label: "Confirm", text: $confirm, kind: .secure, content: .newPassword)
                }
                if !new.isEmpty {
                    PasswordMeter(rules: rules).padding(.horizontal, 4).padding(.top, 8)
                }
                if !confirm.isEmpty && !matches {
                    settingsNote("The new passwords don’t match.")
                }
                settingsNote("You’ll be signed out on your other devices.").padding(.top, 4)
                if let error = error { Hint(text: error).padding(.top, 4) }
            } bottom: {
                Button("Save password") { Task { await save() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(current.isEmpty || !rules.ok || !matches || busy)
            }
        }
        .onChange(of: new) { value in
            rules = PasswordRules.local(value, email: email)
            error = nil
        }
        .task(id: new) {
            // Ask the server about "common or leaked" once typing pauses.
            guard new.count >= 12 else { return }
            try? await Task.sleep(nanoseconds: 400_000_000)
            if let checked: PasswordRules = try? await app.api.post("api/auth/password/check",
                                                                   ["password": new, "email": email]) {
                rules = checked
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/auth/password", ["current": current, "new": new])
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - SEC-09 Your recovery codes

struct RecoveryCodes: Decodable, Identifiable {
    let codes: [String]
    var id: String { codes.joined() }
}

/// Ten codes, shown once: keep them somewhere safe; each works once.
struct RecoveryCodesSheet: View {
    @Environment(\.dismiss) private var dismiss
    let codes: [String]
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text("Recovery codes").font(Nacre.headline).foregroundColor(Pearl.ink).accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { dismiss() } }
            .padding(.top, 20)
            Text("Keep them somewhere safe, like a password manager. Each works once. Making new ones turns these off.")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            GlassCard {
                ForEach(Array(stride(from: 0, to: codes.count, by: 2)), id: \.self) { i in
                    if i > 0 { RowSeparator() }
                    HStack {
                        Text(codes[i])
                        Spacer()
                        if i + 1 < codes.count { Text(codes[i + 1]) }
                    }
                    .font(.system(size: 17, design: .monospaced)).foregroundColor(Pearl.ink)
                    .textSelection(.enabled)
                    .padding(.horizontal, 16).frame(minHeight: 44)
                }
            }
            Spacer(minLength: 0)
            Button(copied ? "Copied" : "Copy codes") {
                UIPasteboard.general.string = codes.joined(separator: "\n")
                copied = true
            }
            .buttonStyle(SecondaryButtonStyle())
            Button("Done") { dismiss() }
                .buttonStyle(NacreButtonStyle())
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .background(SheetBackground())
        .interactiveDismissDisabled(!copied)
    }
}


/// Reset Pearl: unlinks her banks and clears her transactions and setup,
/// then starts setup again (POST /api/account/reset). She stays signed in.
@MainActor
struct ResetPearlCard: View {
    @EnvironmentObject private var app: AppModel
    @State private var confirming = false
    @State private var resetting = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            GlassCard {
                Button(role: .destructive) { confirming = true } label: {
                    ProfileRow(symbol: "arrow.counterclockwise", title: resetting ? "Resetting…" : "Reset Pearl",
                               tone: Pearl.moneyOut, chevron: false) {
                        if resetting { ProgressView() }
                    }
                }
                .buttonStyle(.plain)
                .disabled(resetting)
            }
            ProfileNote("Unlinks your banks and clears your transactions and setup, then starts setup again. You stay signed in.")
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
            }
        }
        .confirmationDialog("Reset Pearl?", isPresented: $confirming, titleVisibility: .visible) {
            Button("Reset", role: .destructive) { Task { await reset() } }
        } message: {
            Text("Your banks are unlinked and your transactions and setup are cleared. Your email, password and Face ID stay. This can't be undone.")
        }
    }

    private func reset() async {
        resetting = true
        defer { resetting = false }
        do {
            struct Reply: Decodable { let user: PearlUser? }
            let reply: Reply = try await app.api.post("api/account/reset", ["confirm": "reset"])
            error = nil
            app.justCreated = false
            app.signedIn(reply.user)
        } catch {
            self.error = app.handle(error)
        }
    }
}
