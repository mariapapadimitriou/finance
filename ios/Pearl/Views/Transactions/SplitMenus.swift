import SwiftUI
import UIKit

// REFRESH-02 (Design refresh, section 11 1088:1695; THL-289, THL-291,
// THL-181): the split card's ••• menu and every screen after it, as Pearl
// views. Product owner, 2026-11-09: no `.alert`, `.confirmationDialog` or
// action sheet anywhere in these flows. Built from designBOT's kit 1088:1696
// (Option row, Primary / Secondary buttons, 44 pt Close and •••, Toast with
// Undo), on the iridescent background (REFRESH-05; pearl paper before), with
// ink amounts and no red (decisions 1 and 4).
// Motion comes later (note 1096:4483); nothing here depends on it.

// MARK: - The kit (1088:1696)

/// "Pearl/Close button (44)": the round Close on every sheet.
struct PearlCloseButton: View {
    var label = "Close"
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "xmark").font(.system(size: 17, weight: .medium))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Pearl.control))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// "Pearl/More button ••• (44)": a person's options on the split card.
struct PearlMoreButton: View {
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Pearl.control))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// "Pearl/Button primary": rose with white text, 50 high; while waiting,
/// a spinner and the waiting words in the button (note 1096:4483).
struct PearlPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var busy = false
    var busyLabel: String? = nil

    func makeBody(configuration: Configuration) -> some View {
        ZStack {
            configuration.label.opacity(busy ? 0 : 1)
            if busy {
                HStack(spacing: 8) {
                    ProgressView().tint(Pearl.onAction)
                    if let busyLabel = busyLabel { Text(busyLabel) }
                }
            }
        }
        .font(Pearl.text(.headline, .semibold))
        .foregroundColor(Pearl.onAction)
        .multilineTextAlignment(.center)
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity, minHeight: 50)
        .background(Capsule().fill(Pearl.action))
        .opacity(isEnabled || busy ? (configuration.isPressed ? 0.85 : 1) : 0.4)
        .contentShape(Capsule())
    }
}

/// "Pearl/Button secondary": the control fill with ink text.
struct PearlSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Pearl.text(.headline, .semibold))
            .foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 24)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Capsule().fill(Pearl.control))
            .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.5)
            .contentShape(Capsule())
    }
}

/// The 44-high pills on a payment card: View the e-Transfer, Unlink….
struct PearlPillButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Pearl.text(.callout, .medium))
            .foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(Capsule().fill(Pearl.control))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Capsule())
    }
}

/// A round 40 pt bubble holding a line icon: blush, or rose for the usual
/// action ("Mark paid back").
struct PearlBubble: View {
    let symbol: String
    var prominent = false
    var tone: Color = Pearl.action
    var size: CGFloat = 40

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.42, weight: .regular))
            .foregroundColor(prominent ? Pearl.onAction : tone)
            .frame(width: size, height: size)
            .background(Circle().fill(prominent ? Pearl.action : Pearl.bubble))
            .accessibilityHidden(true)
    }
}

/// A person's or a merchant's initials on blush (the sheets' faces).
struct PearlFace: View {
    let name: String
    var size: CGFloat = 44

    var body: some View {
        Text(letters)
            .font(.custom("Figtree-Medium", size: size * 0.32, relativeTo: .footnote))
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(Pearl.bubble))
            .accessibilityHidden(true)
    }

    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }
        if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        let out = words.prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "·" : out
    }
}

/// "Pearl/Option row": a bubble, a title over what happens, a chevron.
/// At least 60 high; VoiceOver reads the title, then what happens.
struct PearlOptionRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var prominent = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                PearlBubble(symbol: symbol, prominent: prominent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    if let sub = sub {
                        Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .medium))
                    .foregroundColor(Pearl.muted)
                    .accessibilityHidden(true)
            }
            .padding(.vertical, 10)
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(.isButton)
    }
}

/// A card of option rows, with the divider between them (glass in light,
/// REFRESH-05: S-40a–d, S-04u, S-05or, S-06r*).
struct PearlOptionCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 0, content: content)
            .padding(.horizontal, 16).padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .pearlCard(radius: Pearl.radiusTile)
    }
}

/// The 1 pt line between option rows.
struct PearlDivider: View {
    var body: some View { Rectangle().fill(Pearl.border).frame(height: 1) }
}

/// "CHANGE THE SPLIT", "PAID SO FAR": a section's small caps.
struct PearlSectionLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(Pearl.text(.footnote, .medium)).tracking(0.78)
            .foregroundColor(Pearl.muted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The champagne Banner for errors (never red). designBOT set its fill to
/// 22% champagne so the words read in dark too. Announced by VoiceOver.
struct CautionBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle").font(.system(size: 16))
                .accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Pearl.text(.callout, .medium))
        .foregroundColor(Pearl.ink)
        .padding(14)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
            .fill(Pearl.champagne.opacity(0.22)))
        .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
            .stroke(Pearl.champagne, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .onAppear { UIAccessibility.post(notification: .announcement, argument: text) }
    }
}

/// "ⓘ Loblaws already counts in full…": a quiet note on a card.
struct InfoNote: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "info.circle").font(.system(size: 16)).accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Pearl.text(.callout))
        .foregroundColor(Pearl.muted)
        .padding(14)
        .pearlCard(radius: Pearl.radiusChoice)
        .accessibilityElement(children: .combine)
    }
}

/// A sheet's top: a face or icon, the small caps, a Fraunces title and its
/// line, and Close (or Back on the left, S-06rb–rd).
struct PearlSheetHeader: View {
    var face: String? = nil
    var symbol: String? = nil
    let overline: String
    let title: String
    var sub: String? = nil
    var subTone: Color = Pearl.muted
    var back: (() -> Void)? = nil
    let close: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if let back = back {
                Button(action: back) {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(Pearl.card))
                        .shadow(color: Pearl.ink.opacity(0.1), radius: 5, y: 3)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Back")
            } else if let symbol = symbol {
                PearlBubble(symbol: symbol, size: 44)
            } else if let face = face {
                PearlFace(name: face)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(overline.uppercased())
                    .font(Pearl.text(.footnote, .medium)).tracking(0.78).foregroundColor(Pearl.muted)
                Text(title)
                    .font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let sub = sub {
                    Text(sub).font(Pearl.text(.callout)).foregroundColor(subTone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            PearlCloseButton(action: close)
        }
    }
}

/// Reads a view's height, so a sheet can size to what it holds.
private struct HeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// A Pearl sheet: a Pearl view, not a stock dialog (decision 4), on the
/// iridescent background with the Pearl dust (REFRESH-05: the sheet surface
/// is color/surface/page), sized to its content and scrolling past the large
/// detent (note 1096:4483), with the grabber.
struct PearlSheet<Content: View, Footer: View>: View {
    var dismissDisabled = false
    @ViewBuilder var content: () -> Content
    @ViewBuilder var footer: () -> Footer
    @State private var height: CGFloat = 360
    @State private var footerHeight: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 16, content: content)
                    .padding(.horizontal, 16).padding(.top, 24).padding(.bottom, 16)
                    .background(GeometryReader { g in Color.clear.preference(key: HeightKey.self, value: g.size.height) })
            }
            .scrollDismissesKeyboard(.interactively)
            footer()
                .background(GeometryReader { g in
                    Color.clear
                        .onAppear { footerHeight = g.size.height }
                        .onChange(of: g.size.height) { footerHeight = $0 }
                })
        }
        .background(SheetBackground())
        .onPreferenceChange(HeightKey.self) { h in height = h }
        .presentationDetents([.height(min(height + footerHeight + 16, UIScreen.main.bounds.height * 0.92)), .large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(dismissDisabled)
        .modifier(PaperBackground())
    }
}

extension PearlSheet where Footer == EmptyView {
    init(dismissDisabled: Bool = false, @ViewBuilder content: @escaping () -> Content) {
        self.dismissDisabled = dismissDisabled
        self.content = content
        self.footer = { EmptyView() }
    }
}

/// The sheet itself on the iridescent background where iOS lets us say so
/// (16.4+), so nothing white shows past the content.
private struct PaperBackground: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 16.4, *) {
            content.presentationBackground { SheetBackground() }
        } else {
            content
        }
    }
}

/// The primary and secondary buttons at a sheet's bottom.
struct PearlSheetButtons: View {
    let primary: String
    var busy = false
    var busyLabel: String? = nil
    var secondary: String? = nil
    let onPrimary: () -> Void
    var onSecondary: () -> Void = {}

    var body: some View {
        VStack(spacing: 12) {
            Button(primary, action: onPrimary)
                .buttonStyle(PearlPrimaryButtonStyle(busy: busy, busyLabel: busyLabel))
            if let secondary = secondary {
                Button(secondary, action: onSecondary).buttonStyle(PearlSecondaryButtonStyle())
            }
        }
        .disabled(busy)
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
    }
}

// MARK: - S-44 Toasts

/// "Pearl/Toast with Undo" (S-44a–i): ink, with a 44-high action. It stays
/// 6 s, longer while VoiceOver is on; it's announced, and its action is an
/// accessibility action too (note 1096:4483).
struct PearlToast: View {
    struct Model: Equatable {
        let id = UUID()
        let text: String
        /// "Undo", "Try again", or none.
        var action: String? = nil
        var failed = false
        var run: (() -> Void)? = nil

        static func == (a: Model, b: Model) -> Bool { a.id == b.id }
    }

    let model: Model
    let done: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: model.failed ? "info.circle" : "checkmark")
                .font(.system(size: 17, weight: .semibold))
                .accessibilityHidden(true)
            Text(model.text).font(Pearl.text(.callout, .medium))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let action = model.action, let run = model.run {
                Button(action) { run() }
                    .font(Pearl.text(.callout, .semibold))
                    .padding(.horizontal, 14).frame(minHeight: 44)
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
            }
        }
        .foregroundColor(Pearl.onInk)
        .padding(.leading, 16).padding(.trailing, 8).padding(.vertical, 6)
        .frame(minHeight: 56)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Pearl.ink))
        .shadow(color: .black.opacity(0.16), radius: 12, y: 8)
        .padding(.horizontal, 16)
        .swipeToDismiss(done)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityElement(children: .combine)
        .accessibilityActions {
            if let action = model.action, let run = model.run { Button(action) { run() } }
        }
        .task(id: model.id) {
            UIAccessibility.post(notification: .announcement, argument: model.text)
            let seconds: UInt64 = UIAccessibility.isVoiceOverRunning ? 15 : 6
            try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
            if !Task.isCancelled { done() }
        }
    }
}

// MARK: - S-40 Person options (one sheet, sections by state)

/// What she picked on S-40; it runs once the sheet has gone, so the next
/// sheet can open (handoff note 1096:4498).
enum PersonChoice {
    case markPaid, remind, letGo, undoLetGo, changeShare, remove
    case view(Transaction.LinkInfo), unlink(Transaction.LinkInfo)
}

/// S-40a owes · S-40b paid part · S-40c / c2 paid in full · S-40d let go.
/// Built from `Splitting.Person` and its `links` only (no new call).
struct PersonOptionsSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let p: Transaction.Splitting.Person
    let onClose: () -> Void
    let onChoose: (PersonChoice) -> Void

    private var links: [Transaction.LinkInfo] { p.links ?? [] }
    private var letGoAmount: Double { max(0, (p.letGo?.was ?? 0) - p.paid) }
    private var ways: Int { split.people.count + (split.you >= 0.005 ? 1 : 0) }

    var body: some View {
        if split.unsure { unsureBody } else { setBody }
    }

    /// S-40u (paid) / S-40u2 (nothing yet), SPLIT-C: PAID SO FAR, Mark paid
    /// back (any amount), Remind (no amount), Remove. No Let it go and no
    /// Change share: nothing is owed. Closed (S-46): only the links.
    private var unsureBody: some View {
        PearlSheet {
            PearlSheetHeader(face: p.name, overline: "\(t.merchant) · Not sure yet", title: p.name,
                             sub: p.paid >= 0.005 ? "Paid you \(Format.amount(p.paid)) so far" : "Nothing yet",
                             subTone: p.paid >= 0.005 ? Pearl.moneyIn : Pearl.muted, close: onClose)
            if !links.isEmpty {
                PearlSectionLabel(text: "Paid so far")
                ForEach(links) { link in paymentCard(link) }
            }
            if split.closedAt == nil {
                // REFRESH-03: the rows alone; no subtitles, no footnote.
                // The lead option is filled on S-40u and S-40u2, as on S-40a.
                PearlOptionCard {
                    PearlOptionRow(symbol: "banknote", title: "Mark paid back",
                                   prominent: true) { onChoose(.markPaid) }
                    PearlDivider()
                    PearlOptionRow(symbol: "envelope", title: "Remind \(p.name)") { onChoose(.remind) }
                }
                PearlSectionLabel(text: "Change the split")
                PearlOptionCard {
                    PearlOptionRow(symbol: "person", title: "Remove \(p.name)", sub: removeSub) {
                        onChoose(.remove)
                    }
                }
            }
        }
    }

    private var setBody: some View {
        PearlSheet {
            PearlSheetHeader(face: p.name, overline: "\(t.merchant) · split \(ways) ways", title: p.name,
                             sub: headline, subTone: paidInFull ? Pearl.moneyIn : Pearl.muted, close: onClose)
            if p.paid >= 0.005 && p.owes >= 0.005 {
                PaidBar(paid: p.paid, of: p.amount).accessibilityHidden(true)
            }
            if !links.isEmpty {
                PearlSectionLabel(text: paidInFull ? "Paid with" : "Paid so far")
                ForEach(links) { link in paymentCard(link) }
            }
            if p.letGo != nil {
                PearlOptionCard {
                    PearlOptionRow(symbol: "arrow.triangle.2.circlepath", title: "Undo let it go",
                                   sub: "\(p.name) owes you \(Format.amount(letGoAmount)) again", prominent: true) {
                        onChoose(.undoLetGo)
                    }
                }
            } else if p.owes >= 0.005 {
                let part = p.paid >= 0.005
                // REFRESH-03 (S-40a, S-40b): subtitles that only described the
                // row are gone; VoiceOver keeps them as hints. The one that
                // costs money ("becomes your spending") stays.
                PearlOptionCard {
                    PearlOptionRow(symbol: "arrow.uturn.backward", title: part ? "Mark the rest paid back" : "Mark paid back",
                                   prominent: true) { onChoose(.markPaid) }
                        .accessibilityHint("By bank, cash or another app")
                    PearlDivider()
                    PearlOptionRow(symbol: "envelope", title: "Remind \(p.name)") { onChoose(.remind) }
                        .accessibilityHint(part ? "Copies a message for the \(Format.amount(p.owes)) left"
                                                : "Copies a message for you to send")
                    PearlDivider()
                    PearlOptionRow(symbol: "forward", title: part ? "Let the rest go" : "Let it go",
                                   sub: "The \(Format.amount(p.owes)) becomes your spending") { onChoose(.letGo) }
                }
            }
            PearlSectionLabel(text: "Change the split")
            PearlOptionCard {
                PearlOptionRow(symbol: "person.2", title: "Change \(possessive(p.name)) share") { onChoose(.changeShare) }
                PearlDivider()
                PearlOptionRow(symbol: "person", title: "Remove \(p.name)", sub: removeSub) { onChoose(.remove) }
            }
        }
    }

    private var paidInFull: Bool { p.owes < 0.005 && p.letGo == nil && p.paid >= 0.005 }

    /// "Owes you $30.00 of $30.00", "Paid $10.00 of $30.00 · owes $20.00",
    /// "✓ Paid back in full · Nov 16", "You let $30.00 go · Nov 20".
    private var headline: String {
        if let gone = p.letGo { return "You let \(Format.amount(letGoAmount)) go · \(Format.short(gone.day))" }
        if p.owes >= 0.005 {
            return p.paid >= 0.005
                ? "Paid \(Format.amount(p.paid)) of \(Format.amount(p.amount)) · owes \(Format.amount(p.owes))"
                : "Owes you \(Format.amount(p.owes)) of \(Format.amount(p.amount))"
        }
        return "✓ Paid back in full" + (p.paidOn.map { " · \(Format.short($0))" } ?? "")
    }

    /// Remove's line: what it costs, or what asking first will say. None
    /// for someone let go (REFRESH-03, S-40d): it goes at once, with Undo.
    private var removeSub: String? {
        if p.paid < 0.005 {
            return p.letGo != nil ? nil : "The \(Format.amount(p.share)) goes back to your share"
        }
        if links.count > 1 { return links.count == 2 ? "Asks first: unlinks both payments" : "Asks first: unlinks \(links.count) payments" }
        guard let link = links.first else { return "Asks first" }
        switch link.kind {
        case "cash": return "Asks first: the \(Format.amount(link.amount)) cash is forgotten"
        case "app": return "Asks first: the \(Format.amount(link.amount)) \(link.noun) is forgotten"
        default:
            return (link.others ?? []).isEmpty ? "Asks first: unlinks the \(link.noun)"
                : "Asks first: unlinks only \(possessive(t.merchant)) \(Format.amount(link.amount))"
        }
    }

    /// One payment: what it was, how much of it was theirs here, then View
    /// (bank or a deposit only) and its own Unlink.
    private func paymentCard(_ link: Transaction.LinkInfo) -> some View {
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                PearlBubble(symbol: Self.symbol(link.kind), tone: Pearl.moneyIn)
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(Self.word(link)) · \(Format.short(link.date))")
                        .font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    Text(detail(link)).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text(Format.amount(link.amount)).font(Pearl.text(.headline, .semibold)).monospacedDigit()
                    .foregroundColor(Pearl.moneyIn)
            }
            .accessibilityElement(children: .combine)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { pills(link) }
                VStack(spacing: 8) { pills(link) }
            }
        }
        .padding(16)
        .pearlCard(radius: Pearl.radiusTile)
    }

    @ViewBuilder private func pills(_ link: Transaction.LinkInfo) -> some View {
        if let view = link.view {
            Button(view.label) { onChoose(.view(link)) }.buttonStyle(PearlPillButtonStyle())
                .accessibilityHint("Opens it here in Pearl")
        }
        Button(links.count == 1 && link.view != nil ? "Unlink…" : "Unlink \(Format.amount(link.amount))…") {
            onChoose(.unlink(link))
        }
        .buttonStyle(PearlPillButtonStyle())
    }

    /// "You marked this as cash", "Part of $60.00 · also paid back Pizza
    /// Nova" (S-40c, REFRESH-03), "From Dana Lee".
    private func detail(_ link: Transaction.LinkInfo) -> String {
        switch link.kind {
        case "cash":
            return link.deposit.map { "Deposited \(Format.short($0.date))" } ?? "You marked this as cash"
        case "app": return "You marked this as paid in \(Self.word(link))"
        case "part": return link.message
        default:
            if let others = link.others, !others.isEmpty, let whole = link.whole {
                return "Part of \(Format.amount(whole)) · also paid back \(Format.andList(others))"
            }
            if let r = link.sheet.name.range(of: " from ") { return "From " + link.sheet.name[r.upperBound...] }
            return link.message
        }
    }

    static func symbol(_ kind: String) -> String {
        switch kind {
        case "cash": return "banknote"
        case "app": return "iphone"
        case "refund": return "cart"
        case "reimbursement": return "briefcase"
        default: return "creditcard"
        }
    }

    /// "e-Transfer", "Cash", "PayPal", "Part of a deposit".
    static func word(_ link: Transaction.LinkInfo) -> String {
        switch link.kind {
        case "cash": return "Cash"
        case "app": return link.noun.replacingOccurrences(of: " payment", with: "")
        case "part": return "Part of a deposit"
        default: return link.noun == "e-Transfer" ? "e-Transfer" : link.noun.prefix(1).uppercased() + link.noun.dropFirst()
        }
    }
}

/// The paid-back bar under a person (S-04r v2): rose on the track.
struct PaidBar: View {
    let paid: Double
    let of: Double
    var tone: Color = Pearl.action

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Pearl.track)
                Capsule().fill(tone).frame(width: g.size.width * min(1, paid / max(of, 0.01)))
            }
        }
        .frame(height: 6)
    }
}

/// "Loblaws’ $30.00", "Pizza Nova’s $30.00".
func possessive(_ name: String) -> String {
    name.lowercased().hasSuffix("s") ? "\(name)’" : "\(name)’s"
}

// MARK: - S-07r Remind

/// S-07ra (owes) / S-07rb (part-paid): a message she can change, then
/// Copy. Pearl doesn't send anything (no server call; handoff 1096:4498).
struct RemindSheet: View {
    let t: Transaction
    let p: Transaction.Splitting.Person
    let onClose: () -> Void
    let onCopied: () -> Void
    @State private var text: String
    private var unsure: Bool { t.splitting?.unsure == true }

    init(t: Transaction, p: Transaction.Splitting.Person, onClose: @escaping () -> Void,
         onCopied: @escaping () -> Void) {
        self.t = t
        self.p = p
        self.onClose = onClose
        self.onCopied = onCopied
        _text = State(initialValue: Self.message(t: t, p: p))
    }

    /// S-07ra: "Hey Priya! Your share of Loblaws on Nov 11 is $30.00. Thanks!"
    /// S-07rb (product owner, 2026-11-09): "Hey Sam! Thanks for the $10.00.
    /// Your share of Loblaws on Nov 11 was $30.00, so $20.00 to go."
    static func message(t: Transaction, p: Transaction.Splitting.Person) -> String {
        if t.splitting?.unsure == true {
            // S-07u (SPLIT-C): no amount, because she hasn't set one.
            return "Hi \(p.name)! When you get a chance, could you send me your part of \(t.merchant) from \(Format.short(t.date))? Thanks!"
        }
        let on = "\(t.merchant) on \(Format.short(t.date))"
        if p.paid >= 0.005 {
            return "Hey \(p.name)! Thanks for the \(Format.amount(p.paid)). Your share of \(on) was "
                + "\(Format.amount(p.amount)), so \(Format.amount(p.owes)) to go."
        }
        return "Hey \(p.name)! Your share of \(on) is \(Format.amount(p.owes)). Thanks!"
    }

    var body: some View {
        PearlSheet {
            PearlSheetHeader(face: p.name, overline: unsure ? "Remind \(p.name)" : "Remind",
                             title: unsure ? "A friendly nudge" : "Remind \(p.name)",
                             sub: unsure ? nil : p.paid >= 0.005 ? "Owes you \(Format.amount(p.owes)) of \(Format.amount(p.amount))"
                                                  : "Owes you \(Format.amount(p.owes))",
                             close: onClose)
            TextField("", text: $text, axis: .vertical)
                .font(Pearl.text(.headline))
                .foregroundColor(Pearl.ink)
                .lineLimit(2...8)
                .padding(16)
                .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Pearl.bubble))
                .accessibilityLabel("Message to \(p.name)")
                .accessibilityHint("Tap to change the message.")
            // REFRESH-03 (S-07ra, S-07rb, S-07u): one line under the message.
            Text("Pearl doesn’t send it. You paste it.")
                .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
        } footer: {
            PearlSheetButtons(primary: "Copy message") {
                UIPasteboard.general.string = text
                onCopied()
            }
        }
    }
}

// MARK: - S-03fr Remove from the split?

/// What removing someone who paid does (S-03fr / S-03fr2, SPLIT-16 rules):
/// a line about what they paid, then WHAT CHANGES.
struct RemoveWords {
    let lead: String
    let changes: [String]
    /// A bank payment comes off: "Unlink and remove", else "Remove Sam".
    let unlinks: Bool

    /// `countsAgain` (S-03fu, a Not sure yet split): what the purchase counts
    /// as once their paybacks are unlinked, said instead of a share.
    init(_ p: Transaction.Splitting.Person, merchant: String, countsAgain: Double? = nil) {
        let name = p.name
        let shared = p.shared ?? []
        let kept = (p.cash ?? 0) + (p.app ?? 0)
        let bank = p.paid - kept - shared.map(\.here).reduce(0, +)
        let on = p.paidOn.map { " on \(Format.short($0))" } ?? ""
        var lead: [String] = [], changes: [String] = []
        // REFRESH-03: each consequence once, in a few words.
        for s in shared {
            let others = Format.andList(s.others)
            // S-03fr: "Jo paid $30.00 of a $60.00 e-Transfer."
            lead.append("\(name) paid \(Format.amount(s.here)) of a \(Format.amount(s.whole)) \(s.word).")
            changes.append("Only \(possessive(merchant)) \(Format.amount(s.here)) is unlinked. \(others) "
                           + "\(s.others.count == 1 ? "stays" : "stay") paid back.")
            changes.append("The \(Format.amount(s.here)) goes back to Needs a look.")
        }
        if bank >= 0.005 {
            // S-03f / S-03fu: "Priya’s $28.04 goes back to Needs a look."
            changes.append("\(possessive(name)) \(Format.amount(bank)) goes back to Needs a look.")
        }
        if kept >= 0.005 {
            let app = (p.app ?? 0) >= 0.005 && (p.cash ?? 0) < 0.005
            let day = p.payments?.last.map { " on \(Format.short($0.day))" } ?? on
            lead.append("\(name) paid you \(Format.amount(kept)) \(app ? "through another app" : "in cash")\(day).")
            // S-03fr2: "The $10.00 cash is forgotten."
            changes.append("The \(Format.amount(kept)) \(app ? "app payment" : "cash") is forgotten.")
        }
        if let counts = countsAgain {
            // S-03fu: "Pizza Nova counts as $100.00 again."
            changes.append("\(merchant) counts as \(Format.amount(counts)) again.")
        } else {
            changes.append("\(possessive(name)) \(Format.amount(p.share)) share becomes yours.")
        }
        self.lead = lead.joined(separator: " ")
        self.changes = changes
        self.unlinks = bank >= 0.005 || !shared.isEmpty
    }
}

/// S-03fr: "Remove Jo from the split?", WHAT CHANGES, then Unlink and
/// remove / Keep Jo. From S-40 it saves at once: a spinner in the button
/// (S-03fr loading), and the champagne banner if it fails (S-03fr error).
/// From How to split it only takes them off the list until Save.
struct RemovePersonSheet: View {
    let p: Transaction.Splitting.Person
    let merchant: String
    /// S-03fu (a Not sure yet split): what the purchase counts as after.
    var countsAgain: Double? = nil
    let onClose: () -> Void
    /// Throws a message to show, or nothing went wrong.
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    var body: some View {
        let words = RemoveWords(p, merchant: merchant, countsAgain: countsAgain)
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: p.name, overline: "Remove from split", title: "Remove \(p.name) from the split?",
                             close: onClose)
                .disabled(busy)
            if !words.lead.isEmpty {
                Text(words.lead).font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            PearlSectionLabel(text: "What changes")
            PearlOptionCard {
                ForEach(Array(words.changes.enumerated()), id: \.offset) { i, line in
                    if i > 0 { PearlDivider() }
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Circle().fill(Pearl.action).frame(width: 6, height: 6).accessibilityHidden(true)
                        Text(line).font(Pearl.text(.callout)).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 12)
                }
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : words.unlinks ? "Unlink and remove" : "Remove \(p.name)",
                              busy: busy, busyLabel: "Removing…", secondary: "Keep \(p.name)",
                              onPrimary: { Task { await remove() } }, onSecondary: onClose)
        }
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t remove \(p.name). Nothing changed. Try again."
        }
    }
}

/// A refusal the server put in words ("That cash is in a deposit…"), shown
/// on the banner instead of the general line.
struct SplitMenuError: Error { let words: String }
