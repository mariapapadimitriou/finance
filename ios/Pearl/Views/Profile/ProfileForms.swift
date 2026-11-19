import SwiftUI

// Profile's typing sheets, A+ (Claude Design G5-Profile P-01n, G5-Email P-02
// and SEC-02): the centred title with ✕, a nacre-ring icon or the live
// initials circle, the fields in a glass card, and the one primary button
// riding above the keyboard, greyed until the answer is good.

/// A full-height Pearl sheet for typing: the title bar, what's asked, and
/// the buttons pinned along the bottom (above the keyboard while it's up).
struct ProfileFormSheet<Content: View, Bottom: View>: View {
    let title: String
    let close: () -> Void
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitle(title: title, close: close)
                .padding(.horizontal, 16).padding(.top, 14)
            ScrollView {
                VStack(spacing: 14, content: content)
                    .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 12, content: bottom)
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .modifier(FormSheetCorners())
    }
}

private struct FormSheetCorners: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 16.4, *) {
            content.presentationBackground { SheetBackground() }.presentationCornerRadius(38)
        } else {
            content
        }
    }
}

/// A+ `.ring` icon: a line icon on the disc inside the 1.2 pt nacre ring
/// (G5-Email's envelope at 60, SEC-02's key at 36).
struct NacreRingIcon: View {
    let symbol: String
    var size: CGFloat = 60

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.32, weight: .regular))
            .foregroundColor(Pearl.action)
            .frame(width: size - 2.4, height: size - 2.4)
            .background(Circle().fill(APlus.circleDisc))
            .padding(1.2)
            .background(Circle().fill(APlus.nacreRing))
            .accessibilityHidden(true)
    }
}

/// G5-Email `.cardpad`: fields on the glass card, 14 in.
struct ProfileFormCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12, content: content)
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .apCard()
    }
}

// MARK: - P-01n Your name

/// P-01n "Your name" (G5-Profile, THL-104): the initials circle following
/// what she types, one Name well, and Save above the keyboard, off while the
/// name is empty. Saving says "Name changed to Maya Lin" with Undo.
@MainActor
struct YourNameSheet: View {
    @EnvironmentObject private var app: AppModel
    let close: () -> Void
    @State private var name = ""
    @State private var busy = false
    @State private var error: String?

    private struct Reply: Decodable { let user: PearlUser? }

    private var trimmed: String { name.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
    private var was: String { app.user?.firstName ?? "" }

    var body: some View {
        ProfileFormSheet(title: "Your name", close: close) {
            ProfileAvatar(initials: ProfileName.initials(name: name, email: app.user?.email), size: 64,
                          font: .custom("Figtree-SemiBold", size: 20, relativeTo: .title3))
                .frame(maxWidth: .infinity)
            ProfileFormCard {
                PearlField(label: "Name", placeholder: "Your name", text: $name,
                           error: error, identifier: "your-name-field",
                           submit: { if !trimmed.isEmpty { Task { await save() } } }, autofocus: true)
                    .textContentType(.name)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
            }
        } bottom: {
            Button("Save") { Task { await save() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(trimmed.isEmpty || busy)
                .accessibilityIdentifier("your-name-save")
        }
        .onAppear { name = was }
        .onChange(of: name) { _ in error = nil }
    }

    private func save() async {
        guard !trimmed.isEmpty, !busy else { return }
        // Nothing changed: nothing to say.
        guard trimmed != was else { close(); return }
        busy = true
        defer { busy = false }
        do {
            let reply: Reply = try await app.api.post("api/account/name", ["first_name": trimmed])
            if let user = reply.user { app.phase = .signedIn(user) }
            close()
            let before = was
            app.say("Name changed to \(reply.user?.firstName ?? trimmed)",
                    undo: before.isEmpty ? nil : { [app] in
                        let back: Reply = try await app.api.post("api/account/name", ["first_name": before])
                        if let user = back.user { app.phase = .signedIn(user) }
                    })
        } catch {
            self.error = app.handle(error) ?? "Couldn\u{2019}t save your name. Try again."
        }
    }
}

// MARK: - SEC-02 the password checks

/// SEC-02 (G5-Email): "At least 12 characters" ticks teal once it's met;
/// "The new passwords don't match" is red until Confirm matches, then
/// "Both new passwords match" ticks teal. A common or leaked password, or
/// one with her email in it, only shows when it's the problem.
struct ChangePasswordChecks: View {
    let rules: PasswordRules
    let new: String
    let confirm: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            line(rules.length ? "At least 12 characters" : "At least 12 characters \u{00B7} \(rules.more) more",
                 state: rules.length ? .met : .waiting)
            if !new.isEmpty && !rules.common { line("Not a common or leaked password", state: .wrong) }
            if !new.isEmpty && !rules.email { line("Doesn\u{2019}t include your email", state: .wrong) }
            if confirm.isEmpty {
                line("Both new passwords match", state: .waiting)
            } else if confirm == new {
                line("Both new passwords match", state: .met)
            } else {
                line("The new passwords don\u{2019}t match", state: .wrong)
            }
        }
        .padding(.horizontal, 2)
    }

    private enum State { case met, waiting, wrong }

    private func line(_ text: String, state: State) -> some View {
        let tone: Color = state == .wrong ? Pearl.danger : (state == .met ? Pearl.ink : Pearl.muted)
        return HStack(spacing: 8) {
            Group {
                if state == .met {
                    Image(systemName: "checkmark.circle.fill").foregroundColor(Nacre.teal)
                } else {
                    Image(systemName: "circle").foregroundColor(state == .wrong ? Pearl.danger : Pearl.muted)
                }
            }
            .font(.system(size: 16))
            .accessibilityHidden(true)
            Text(text).font(Nacre.subheadline).foregroundColor(tone)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(state == .met ? "\(text), met" : "\(text), not yet")
    }
}
