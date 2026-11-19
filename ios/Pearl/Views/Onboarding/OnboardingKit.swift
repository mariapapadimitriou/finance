import SwiftUI

// A+ onboarding and sign-in (REDESIGN-13; Claude Design boards G6-*, G5-Lock,
// G5-Setup; g6.py, kit.css): the 52 pt row with the glass Back, one progress
// strip for set-up ("Part n of 3 · …", approved 2026-11-18, replacing the
// three shells), the 34 pt Fraunces title, fields as visible wells, the
// password's rules, six code wells, and the actions pinned at the bottom
// (they ride above the keyboard, greyed until the answer is valid).

/// Set-up's one progress strip (g6.py `prog`): three 4 pt bars, `action`
/// for the parts reached, `track` for the rest, over the caps line.
struct SetupStrip: View {
    let part: Int
    let name: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                ForEach(0..<3, id: \.self) { i in
                    Capsule().fill(i < part ? Pearl.action : APlus.trackSoft).frame(height: 4)
                }
            }
            Text("Part \(part) of 3 \u{00B7} \(name)".uppercased())
                .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
        }
        .padding(.top, 10)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Part \(part) of 3, \(name)")
    }
}

/// `.ptitle` with its `muted` line (g6.py `title`).
struct OnbTitle: View {
    let title: String
    var line: String? = nil
    var centred = false

    var body: some View {
        VStack(alignment: centred ? .center : .leading, spacing: 6) {
            Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .multilineTextAlignment(centred ? .center : .leading)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let line = line {
                Text(line).font(Nacre.body).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(centred ? .center : .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
        .padding(.horizontal, 4)
        .padding(.top, 14)
    }
}

/// An onboarding page: the 52 pt row (glass Back, or nothing), the strip,
/// the content, and the actions along the bottom, 12 apart.
struct OnbScreen<Content: View, Actions: View>: View {
    var back = true
    var part: Int? = nil
    var partName = ""
    var scrolls = true
    @ViewBuilder var content: () -> Content
    @ViewBuilder var actions: () -> Actions
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            if scrolls {
                ScrollView { page }
                    .scrollDismissesKeyboard(.interactively)
            } else {
                page
                Spacer(minLength: 0)
            }
            VStack(spacing: 12, content: actions)
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 4)
        }
        .nacreScreen()
        .toolbar(.hidden, for: .navigationBar)
    }

    private var page: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                if back { APBackButton(identifier: "onboarding-back") { dismiss() } }
                Spacer()
            }
            .frame(height: 52)
            if let part = part { SetupStrip(part: part, name: partName) }
            content()
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 24)
    }
}

/// A centred message (g6.py `center_state`): the art, the title and a line.
struct OnbMessage<Art: View>: View {
    let title: String
    var line: String? = nil
    var top: CGFloat = 120
    @ViewBuilder var art: () -> Art

    var body: some View {
        VStack(spacing: 0) {
            art()
            Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .padding(.top, 32)
            if let line = line {
                Text(line).font(Nacre.body).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8).padding(.horizontal, 20)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, top)
    }
}

/// The 120 pt orb (g6.py `orb`): a line icon in `action` on the action wash.
struct OnbOrb: View {
    let symbol: String
    var tone: Color = Pearl.action
    var wash: Color = ProfileTone.actionWash

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 52, weight: .light))
            .foregroundColor(tone)
            .frame(width: 120, height: 120)
            .background(Circle().fill(wash))
            .accessibilityHidden(true)
    }
}

/// A primary that reads its waiting words with a spinner.
struct OnbPrimary: View {
    let title: String
    var busy = false
    var busyLabel: String? = nil
    var enabled = true
    var identifier: String? = nil
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .buttonStyle(APPrimaryButtonStyle(busy: busy, busyLabel: busyLabel))
            .disabled(!enabled || busy)
            .accessibilityIdentifier(identifier ?? title)
    }
}

/// A field as a visible well (REDESIGN-09, kit `fld`): the 13 pt label, the
/// 44 pt well, the eye on a password, a 2 pt action ring while typing and a
/// 2 pt danger ring with the reason under it on a real error.
struct OnbField: View {
    enum Kind { case text, email, secure, number }

    let label: String
    @Binding var text: String
    var prompt = ""
    var kind: Kind = .text
    var content: UITextContentType? = nil
    var error: String? = nil
    var focusOnAppear = false
    var submit: () -> Void = {}

    @FocusState private var focused: Bool
    @State private var shown = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            HStack(spacing: 8) {
                field
                    .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                    .textContentType(content)
                    .keyboardType(kind == .email ? .emailAddress : kind == .number ? .numberPad : .default)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.next)
                    .focused($focused)
                    .onSubmit(submit)
                    .accessibilityLabel(label)
                if kind == .secure {
                    Button { shown.toggle() } label: {
                        Image(systemName: shown ? "eye.slash" : "eye")
                            .font(.system(size: 16)).foregroundColor(Pearl.muted)
                            .frame(width: 32, height: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(shown ? "Hide password" : "Show password")
                }
            }
            .padding(.leading, 14).padding(.trailing, kind == .secure ? 6 : 14)
            .frame(minHeight: 44)
            .wellStyle(focused: focused, error: error != nil)
            .contentShape(Rectangle())
            .onTapGesture { focused = true }
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger)
                    .padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .onAppear { if focusOnAppear { focused = true } }
    }

    @ViewBuilder private var field: some View {
        if kind == .secure && !shown {
            SecureField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
        } else {
            TextField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
        }
    }
}

/// The password's strength and its three rules (g6.py `strength`, `check`;
/// approved 2026-11-18): a rule met ticks green, only a failing rule is red,
/// one not decided yet is a `muted` dot.
struct PasswordChecks: View {
    let rules: PasswordRules
    /// "Not a common or leaked password" waits for the server once the
    /// password is long enough; before that it isn't judged.
    var commonChecked = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(APlus.trackSoft)
                        Capsule().fill(tone).frame(width: g.size.width * CGFloat(rules.segments) / 4)
                    }
                }
                .frame(height: 6)
                Text(rules.label).font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                    .foregroundColor(tone)
            }
            VStack(alignment: .leading, spacing: 6) {
                rule(rules.length ? .met : .failed,
                     rules.length ? "At least 12 characters" : "At least 12 characters \u{00B7} \(rules.more) more")
                rule(rules.common ? (commonChecked ? .met : .pending) : .failed, "Not a common or leaked password")
                rule(rules.email ? .met : .failed, "Doesn\u{2019}t include your email")
            }
        }
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Password strength: \(rules.label)")
    }

    private var tone: Color { rules.ok ? Pearl.moneyIn : Pearl.danger }

    enum Mark { case met, failed, pending }

    private func rule(_ s: Mark, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(s == .met ? "\u{2713}" : s == .failed ? "\u{2715}" : "\u{2022}").frame(width: 14, alignment: .leading)
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
        .font(Nacre.subheadline)
        .foregroundColor(s == .met ? Pearl.moneyIn : s == .failed ? Pearl.danger : Pearl.muted)
        .accessibilityLabel(s == .met ? "\(text), met" : s == .failed ? "\(text), not met" : "\(text), checking")
    }
}

/// Six code wells (kit `.code`): 46 × 56, radius 12, 8 apart; the next one
/// has the 2 pt action ring and the caret; a wrong code rings every well in
/// danger. One hidden field takes the digits, so iOS can fill it from Mail.
struct CodeWells: View {
    @Binding var code: String
    var failed = false
    var onComplete: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        ZStack {
            TextField("", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($focused)
                .foregroundColor(.clear).tint(.clear)
                .accessibilityLabel("Six-digit code")
                .onChange(of: code) { value in
                    let digits = String(value.filter(\.isNumber).prefix(6))
                    if digits != value { code = digits }
                    if digits.count == 6 { onComplete() }
                }
            HStack(spacing: 8) {
                ForEach(0..<6, id: \.self) { i in cell(i) }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 6)
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
        .onAppear { focused = true }
    }

    private func cell(_ i: Int) -> some View {
        let chars = Array(code)
        let current = focused && !failed && i == chars.count
        let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
        return ZStack {
            shape.fill(APlus.well)
            shape.strokeBorder(failed ? Pearl.danger : current ? Pearl.action : APlus.wellLine,
                               lineWidth: failed || current ? 2 : 1)
            if i < chars.count {
                Text(String(chars[i])).font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title))
                    .foregroundColor(Pearl.ink)
            } else if current {
                Capsule().fill(Pearl.action).frame(width: 2, height: 28)
            }
        }
        .frame(width: 46, height: 56)
    }
}

/// "Resend code in 0:38" (a `.note`), then the quiet "Resend code".
struct ResendLine: View {
    @Binding var wait: Int
    let resend: () -> Void

    var body: some View {
        Group {
            if wait > 0 {
                Text(String(format: "Resend code in %d:%02d", wait / 60, wait % 60))
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
            } else {
                APQuietButton(title: "Resend code", action: resend)
            }
        }
        .frame(maxWidth: .infinity)
        .task(id: wait > 0) {
            while wait > 0 {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if Task.isCancelled { return }
                wait -= 1
            }
        }
    }
}

/// "pearl" in Fraunces SemiBold 26 (g6.py `WORDMARK`).
struct OnbWordmark: View {
    var body: some View {
        Text("pearl").font(.custom("Fraunces-SemiBold", size: 26)).tracking(-0.5)
            .foregroundColor(Pearl.ink)
            .accessibilityLabel("Pearl")
    }
}
