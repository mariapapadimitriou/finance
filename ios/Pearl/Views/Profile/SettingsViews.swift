import SwiftUI

// Profile's settings (S-01 to S-04): sign-in and security. The banks she's
// linked are Accounts (AccountsViews.swift). Passkeys (S-03) wait for the app's associated domain, so
// there's no passkey row yet.

/// A settings screen (G5 `nav`): the glass Back, the 34 pt title, its
/// sections, and any buttons along the bottom.
private struct SettingsPage<Content: View, Bottom: View>: View {
    let title: String
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        ProfilePage {
            ProfileHeading(title: title)
            content()
        } bottom: {
            bottom()
        }
    }
}

extension SettingsPage where Bottom == EmptyView {
    init(title: String, @ViewBuilder content: @escaping () -> Content) {
        self.init(title: title, content: content, bottom: { EmptyView() })
    }
}

private func settingsSection(_ text: String) -> some View {
    ProfileSection(text)
}

private func settingsNote(_ text: String) -> some View {
    ProfileNote(text)
}

/// "Password   Change ›": G5 `kv`.
private func settingsRow(_ title: String, value: String? = nil, chevron: Bool = false,
                         tone: Color = Pearl.ink) -> some View {
    APKeyValueRow(key: title, chevron: chevron) {
        if let value = value { Text(value).foregroundColor(Pearl.muted).lineLimit(1) }
    }
    .foregroundColor(tone)
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
    @State private var codes: RecoveryCodes?
    @State private var busy = false
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
        SettingsPage(title: "Sign-in and security") {
            settingsSection("Sign-in")
            APCard {
                NavigationLink { ChangeEmailView() } label: {
                    settingsRow("Email", value: app.user?.email ?? "Change", chevron: true)
                }
                .buttonStyle(.plain)
                APSeparator(afterFace: false)
                NavigationLink { ChangePasswordView() } label: {
                    settingsRow("Password", value: "Change", chevron: true)
                }
                .buttonStyle(.plain)
                APSeparator(afterFace: false)
                settingsRow("Code on new devices", value: "Always on")
            }

            if AppLock.available || app.faceIDOn || AppLock.turnedOff {
                settingsSection("Face ID")
                faceIDCard
            }

            // Recovery codes (SEC-08, SEC-09) are left out for now (2026-11-04).

            settingsSection("Your devices")
            devicesCard
            if devices.contains(where: { $0.this != true }) {
                APQuietButton(title: "Sign out other devices", identifier: "sign-out-others") { confirming = true }
                    .frame(maxWidth: .infinity)
                    .disabled(busy)
                    .padding(.top, 4)
            }
            if let error = error { APErrorLine(text: error).padding(.top, 4) }

            // At the bottom of Sign-in and security, not on Profile (2026-11-08).
            ResetPearlCard().padding(.top, 20)
            Color.clear.frame(height: 24)
        }
        .task {
            faceID = app.faceIDOn
            codesLeft = app.user?.recoveryCodes
            await load()
        }
        .sheet(item: $removingDevice) { d in
            // SEC-12r (TEST-06): a Pearl sheet, not a stock alert.
            let name = d.label ?? "this device"
            PearlConfirmSheet(overline: "Your devices", title: "Remove \(name)?",
                              message: "It’s signed out of Pearl and won’t be asked to approve sign-ins again.",
                              primary: "Remove \(name)", busyLabel: "Removing…", secondary: "Keep it",
                              failure: "Couldn’t remove \(name). Nothing changed. Try again.",
                              onClose: { removingDevice = nil }) {
                let _: OK = try await app.api.delete("api/auth/devices/\(d.id)")
                removingDevice = nil
                await load()
                // POLISH-01 audit 5: a toast, not a line left on the page. A
                // signed-out device can't be signed back in for her: no Undo.
                app.say("\(d.label ?? "That device") is signed out.")
            }
        }
        .sheet(item: $codes) { made in
            RecoveryCodesSheet(codes: made.codes)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $confirming) {
            // SEC-04r (TEST-06): one other device by name, or how many.
            PearlConfirmSheet(overline: "Your devices", title: "Sign out other devices?",
                              message: othersLine + " This iPhone stays signed in.",
                              primary: others.count == 1 ? "Sign out \(others[0].label ?? "the other device")"
                                                         : "Sign out \(others.count) devices",
                              busyLabel: "Signing out…",
                              failure: "Couldn’t sign out every device. Try again.",
                              onClose: { confirming = false }) {
                let n = others.count
                for d in others {
                    let _: OK = try await app.api.delete("api/auth/devices/\(d.id)")
                }
                confirming = false
                await load()
                app.say(n == 1 ? "Signed out of 1 other device." : "Signed out of \(n) other devices.")
            }
        }
    }

    /// G5-Security: "Unlock with Face ID · After a minute away"; with Face ID
    /// off for Pearl in iPhone Settings, the switch is greyed and Open Settings
    /// sits under it.
    @ViewBuilder private var faceIDCard: some View {
        APCard {
            if AppLock.turnedOff && !faceID {
                APToggleRow(symbol: "faceid", title: "Unlock with Face ID",
                            sub: "Turn on Face ID for Pearl in iPhone Settings first.",
                            isOn: .constant(false))
                    .disabled(true)
                APSeparator(afterFace: false)
                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                } label: {
                    ProfileRow(symbol: "chevron.right", title: "Open Settings", tone: Pearl.link, chevron: false)
                }
                .buttonStyle(.plain)
            } else {
                APToggleRow(symbol: "faceid", title: "Unlock with Face ID", sub: "After a minute away",
                            isOn: Binding(get: { faceID }, set: { on in Task { await setFaceID(on) } }),
                            identifier: "face-id-toggle")
            }
        }
    }

    /// Each device: its icon, its name over when it was last used, and Remove.
    private var devicesCard: some View {
        APCard {
            if devices.isEmpty {
                deviceRow(name: "This iPhone", when: "Now", symbol: "iphone", remove: nil)
            }
            ForEach(Array(devices.enumerated()), id: \.element.id) { i, d in
                if i > 0 { APSeparator(afterFace: false) }
                if d.this == true {
                    deviceRow(name: "This iPhone", when: "Now", symbol: "iphone", remove: nil)
                } else {
                    // SEC-11 (THL-287): each other device can be removed.
                    deviceRow(name: d.label ?? "Device", when: d.lastUsedAt.map(Self.ago) ?? "",
                              symbol: Self.symbol(d.label), remove: { removingDevice = d })
                }
            }
        }
    }

    private func deviceRow(name: String, when: String, symbol: String, remove: (() -> Void)?) -> some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                if !when.isEmpty { Text(when).font(Nacre.subheadline).foregroundColor(Pearl.muted) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            if let remove = remove {
                APQuietButton(title: "Remove", identifier: "remove-\(name)", action: remove)
                    .disabled(busy)
                    .accessibilityLabel("Remove \(name)")
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
    }

    /// "Mac · Chrome" → a laptop, "iPad" → a tablet, else a phone.
    static func symbol(_ label: String?) -> String {
        let l = (label ?? "").lowercased()
        if l.contains("ipad") || l.contains("tablet") { return "ipad" }
        if l.contains("mac") || l.contains("windows") || l.contains("chrome") || l.contains("safari") || l.contains("firefox") { return "laptopcomputer" }
        return "iphone"
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
        if others.count == 1 { return "Your \(others[0].label ?? "other device") will be signed out of Pearl." }
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

    /// G5-Email "Change password": three wells; a rule ticks green when it's
    /// met and only a failing one is red; "don't match" under Confirm.
    var body: some View {
        SettingsPage(title: "Change password") {
            SecureWell(label: "Current password", text: $current, content: .password)
                .padding(.top, 8)
            SecureWell(label: "New password", text: $new, content: .newPassword)
            if !new.isEmpty { PasswordRuleLines(rules: rules) }
            SecureWell(label: "Confirm", text: $confirm, content: .newPassword,
                       error: !confirm.isEmpty && !matches ? "The new passwords don\u{2019}t match." : nil)
            settingsNote("You\u{2019}ll be signed out on your other devices.")
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
        } bottom: {
            Button("Save password") { Task { await save() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(current.isEmpty || !rules.ok || !matches || busy)
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
            APCard {
                ForEach(Array(stride(from: 0, to: codes.count, by: 2)), id: \.self) { i in
                    if i > 0 { APSeparator(afterFace: false) }
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
            .buttonStyle(APSecondaryButtonStyle())
            Button("Done") { dismiss() }
                .buttonStyle(APPrimaryButtonStyle())
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
    @State private var typed = ""
    @State private var resetting = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // G5-Security: red only on this entry row; the sheet's button is the rose Primary.
            APCard {
                Button { confirming = true } label: {
                    ProfileRow(symbol: "arrow.counterclockwise", title: resetting ? "Resetting\u{2026}" : "Reset Pearl",
                               sub: "Unlinks your banks and starts again",
                               tone: Pearl.danger, chevron: false) {
                        if resetting { ProgressView() }
                    }
                }
                .buttonStyle(.plain)
                .disabled(resetting)
                .accessibilityIdentifier("reset-pearl")
            }
            if let error = error { APErrorLine(text: error) }
        }
        .sheet(isPresented: $confirming) {
            // SO-06 (TEST-06): WHAT GOES / WHAT STAYS, and Type "reset".
            PearlConfirmSheet(overline: "Reset Pearl", title: "Reset Pearl?",
                              message: "Pearl goes back to the start, banks included. You stay signed in.",
                              field: .init(label: "Type \u{201C}reset\u{201D}", prompt: "reset",
                                           note: "Nothing changes until you do.", needs: .words("reset"),
                                           identifier: "reset-confirm"),
                              text: $typed,
                              goes: [.init(title: "Your bank connections", sub: ""),
                                     .init(title: "Your transactions and setup", sub: "")],
                              primary: "Reset Pearl", busyLabel: "Resetting…", secondary: "Keep everything",
                              failure: "Couldn’t reset Pearl. Nothing changed. Try again.",
                              onClose: { confirming = false; typed = "" }) {
                struct Reply: Decodable { let user: PearlUser? }
                let reply: Reply = try await app.api.post("api/account/reset", ["confirm": "reset"])
                confirming = false
                error = nil
                app.justCreated = false
                app.signedIn(reply.user)
            }
        }
    }

}

/// A password well (REDESIGN-09): the 13 pt label, the 44 pt well with the
/// eye, a 2 pt danger ring and the reason under it when it's wrong.
struct SecureWell: View {
    let label: String
    @Binding var text: String
    var content: UITextContentType = .password
    var error: String? = nil
    @State private var shown = false
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            HStack(spacing: 8) {
                Group {
                    if shown {
                        TextField("", text: $text)
                    } else {
                        SecureField("", text: $text)
                    }
                }
                .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                .textContentType(content)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focused)
                .accessibilityLabel(label)
                Button { shown.toggle() } label: {
                    Image(systemName: shown ? "eye.slash" : "eye").font(.system(size: 16)).foregroundColor(Pearl.muted)
                        .frame(width: 32, height: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(shown ? "Hide password" : "Show password")
            }
            .padding(.leading, 14).padding(.trailing, 6)
            .frame(minHeight: 44)
            .wellStyle(focused: focused, error: error != nil)
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger).padding(.horizontal, 4)
            }
        }
    }
}

/// The password rules (G6-Create): ✓ green when met, ✕ red only once one
/// fails ("At least 12 characters · 4 more"), never red before she types.
struct PasswordRuleLines: View {
    let rules: PasswordRules

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            line(rules.length ? "At least 12 characters" : "At least 12 characters \u{00B7} \(rules.more) more", rules.length)
            line("Not a common or leaked password", rules.common)
            line("Doesn\u{2019}t include your email", rules.email)
        }
        .padding(.horizontal, 4)
    }

    private func line(_ text: String, _ met: Bool) -> some View {
        HStack(spacing: 8) {
            Text(met ? "\u{2713}" : "\u{2715}").frame(width: 14)
            Text(text)
        }
        .font(Nacre.subheadline)
        .foregroundColor(met ? Pearl.moneyIn : Pearl.danger)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(met ? "\(text), met" : "\(text), not yet")
    }
}
