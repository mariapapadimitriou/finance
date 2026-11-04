import SwiftUI

// The Profile pages' look (Pearl iOS Handoff File, Profile page, P-01 to
// P-03): glass cards of rows, each row led by a line icon in a frosted
// bubble, an eyebrow over the Fraunces title, and status pills.

/// A line icon in a round frosted bubble, at the start of a row.
struct IconBubble: View {
    let symbol: String
    var size: CGFloat = 36
    var tone: Color = Pearl.ink

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.42, weight: .regular))
            .foregroundColor(tone)
            .frame(width: size, height: size)
            .background(Circle().fill(Nacre.glass))
            .overlay(Circle().strokeBorder(Nacre.separator, lineWidth: 1))
            .accessibilityHidden(true)
    }
}

/// "MONEY": the small caps label over a card.
struct ProfileSection: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.caption2).tracking(0.4)
            .foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 14)
            .accessibilityAddTraits(.isHeader)
    }
}

/// A short note under a card.
struct ProfileNote: View {
    let text: String
    var centred = false

    init(_ text: String, centred: Bool = false) {
        self.text = text
        self.centred = centred
    }

    var body: some View {
        Text(text).font(Nacre.footnote).foregroundColor(Pearl.muted)
            .multilineTextAlignment(centred ? .center : .leading)
            .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
            .padding(.horizontal, 16)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// "PROFILE / How we protect you / What Pearl can and can't do…".
struct ProfileHeading: View {
    var eyebrow: String? = nil
    let title: String
    var intro: String? = nil
    var centred = false

    var body: some View {
        VStack(alignment: centred ? .center : .leading, spacing: 6) {
            if let eyebrow = eyebrow {
                Text(eyebrow.uppercased()).font(Nacre.caption2).tracking(1.4).foregroundColor(Pearl.muted)
            }
            Text(title).font(Nacre.title).foregroundColor(Pearl.ink)
                .multilineTextAlignment(centred ? .center : .leading)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let intro = intro {
                Text(intro).font(Nacre.body).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(centred ? .center : .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
        .padding(.bottom, 6)
    }
}

/// One row: an icon (or a bank's initials), a title, a line under it, and
/// whatever sits at the end.
struct ProfileRow<Trailing: View>: View {
    var symbol: String? = nil
    var initials: String? = nil
    let title: String
    var sub: String? = nil
    var tone: Color = Pearl.ink
    var chevron = true
    var trailing: Trailing

    var body: some View {
        HStack(spacing: 12) {
            if let symbol = symbol { IconBubble(symbol: symbol) }
            if let initials = initials { Initials(name: initials, size: 36) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(tone)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            trailing
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

extension ProfileRow {
    init(symbol: String? = nil, initials: String? = nil, title: String, sub: String? = nil,
         tone: Color = Pearl.ink, chevron: Bool = true, @ViewBuilder trailing: () -> Trailing) {
        self.symbol = symbol
        self.initials = initials
        self.title = title
        self.sub = sub
        self.tone = tone
        self.chevron = chevron
        self.trailing = trailing()
    }
}

extension ProfileRow where Trailing == EmptyView {
    init(symbol: String? = nil, initials: String? = nil, title: String, sub: String? = nil,
         tone: Color = Pearl.ink, chevron: Bool = true) {
        self.init(symbol: symbol, initials: initials, title: title, sub: sub, tone: tone,
                  chevron: chevron, trailing: EmptyView())
    }
}

/// "✓ Up to date", "⚠ 1 needs you": always an icon and words, never colour alone.
struct StatusPill: View {
    enum Tone { case positive, attention, info, neutral, joint }

    let text: String
    var tone: Tone = .positive

    var body: some View {
        HStack(spacing: 4) {
            if let symbol = symbol {
                Image(systemName: symbol).font(.system(size: 11, weight: .semibold))
            }
            Text(text).lineLimit(1)
        }
        .font(Nacre.footnote)
        .foregroundColor(foreground)
        .padding(.horizontal, 10).frame(height: 26)
        .background(Capsule().fill(background))
    }

    private var symbol: String? {
        switch tone {
        case .positive: return "checkmark"
        case .attention: return "exclamationmark.triangle"
        case .info: return "info.circle"
        case .joint: return "person.2"
        case .neutral: return nil
        }
    }

    private var foreground: Color {
        switch tone {
        case .positive: return Nacre.teal
        case .attention: return Pearl.caution
        case .info, .neutral, .joint: return Pearl.ink
        }
    }

    private var background: Color {
        switch tone {
        case .positive: return Nacre.mint
        case .attention: return Pearl.cautionBackground
        case .info, .joint: return Nacre.lilac.opacity(0.35)
        case .neutral: return Pearl.track
        }
    }
}

/// A Profile page: back, its content on the nacre, and any buttons along
/// the bottom.
struct ProfilePage<Content: View, Bottom: View>: View {
    @Environment(\.dismiss) private var dismiss
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8, content: content)
                .padding(.horizontal, Pearl.gutter)
                .padding(.top, 4)
                .padding(.bottom, 32)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if Bottom.self != EmptyView.self {
                VStack(spacing: 6, content: bottom)
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
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

extension ProfilePage where Bottom == EmptyView {
    init(@ViewBuilder content: @escaping () -> Content) {
        self.init(content: content, bottom: { EmptyView() })
    }
}

/// An email field as the design system's Input draws it: a footnote label
/// over a 52pt field, with a rose ring while typing.
struct EmailField: View {
    let label: String
    @Binding var text: String
    var hint: String? = nil
    var readOnly = false
    var submit: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.ink)
            Group {
                if readOnly {
                    Text(text).foregroundColor(Pearl.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    TextField("", text: $text, prompt: Text("you@example.com").foregroundColor(Pearl.muted))
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.send)
                        .focused($focused)
                        .onSubmit(submit)
                        .foregroundColor(Pearl.ink)
                }
            }
            .font(Nacre.body)
            .padding(.horizontal, 16)
            .frame(height: 52)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(focused ? Pearl.action : Nacre.edge, lineWidth: focused ? 1.5 : 1))
            .accessibilityLabel(label)
            if let hint = hint {
                Text(hint).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: - The detail sheets (src/pearl/docs.jsx)

/// What Pearl stores, who sees it, how Plaid works, help, and the drafts.
enum PearlDoc: String, Identifiable {
    case plaid, store, share, help, legal

    var id: String { rawValue }

    struct Fact: Hashable {
        let label: String
        let text: String
        var tag: String? = nil
    }

    struct Part: Hashable {
        var heading: String? = nil
        let text: String
    }

    var eyebrow: String {
        switch self {
        case .plaid: return "Linking a bank"
        case .store: return "What we store"
        case .share: return "Who we share with"
        case .help: return "Help"
        case .legal: return "Drafts"
        }
    }

    var title: String {
        switch self {
        case .plaid: return "How signing in through Plaid works"
        case .store: return "Your data, plainly"
        case .share: return "Who sees your data"
        case .help: return "Getting in"
        case .legal: return "Privacy policy and terms"
        }
    }

    static let storeFacts = [
        Fact(label: "We keep", text: "Account names and types, balances, transactions, and the categories and goals you set"),
        Fact(label: "We never keep", text: "Your bank username or password, or full card or account numbers"),
        Fact(label: "Where", text: "Our cloud database, encrypted when stored and when it moves. Bank connections are encrypted again with a key only Pearl holds."),
        Fact(label: "For how long", text: "While you use Pearl. When you delete your account, we delete your data straight away, and the last copies in our host’s backups within 30 days."),
    ]

    static let shareFacts = [
        Fact(label: "Plaid", text: "Connects to your bank, read-only", tag: "Needed"),
        Fact(label: "Our cloud host", text: "Runs Pearl and stores your data (Vercel and Neon)", tag: "Needed"),
        Fact(label: "Our email service", text: "Delivers your sign-in codes", tag: "Needed"),
        Fact(label: "An investing partner", text: "Only if you choose to go there when you’re ready to grow your money. We always ask first.", tag: "Your choice"),
    ]

    var facts: [Fact] {
        switch self {
        case .store: return Self.storeFacts
        case .share: return Self.shareFacts
        case .legal: return Self.storeFacts + Self.shareFacts
        default: return []
        }
    }

    var parts: [Part] {
        switch self {
        case .plaid:
            return [
                Part(text: "When you link a bank, Plaid opens in its own secure window. You sign in to your bank there, and your username and password go to your bank — Pearl never sees them."),
                Part(text: "Your bank then lets Plaid share a read-only view: your accounts, their balances and your transactions. Pearl can’t move money, make payments or change anything at your bank."),
                Part(text: "You can disconnect a bank any time from Profile › Accounts, and Pearl stops receiving anything from it."),
            ]
        case .help:
            return [
                Part(heading: "Signing in", text: "Use Face ID on this iPhone, or ask for a 6-digit code by email. Codes work for 10 minutes; ask for a new one if yours has run out."),
                Part(heading: "New phone or computer?", text: "Sign in with an email code. If you’ve signed in somewhere before, Pearl asks you to approve the new device there."),
                Part(heading: "Too many tries?", text: "Sign-in pauses for 15 minutes after too many attempts. Nothing about your money changes while it’s paused."),
            ]
        case .legal:
            return [
                Part(text: "These are plain-language drafts, not yet a formal privacy policy or terms of service."),
                Part(heading: "What Pearl is", text: "Pearl helps you see your Allowance and plan what’s next. It reads your accounts; it doesn’t move money, and it isn’t financial advice."),
                Part(heading: "Your part", text: "Keep your email and devices secure, since a code sent to your email or a passkey on your device is how you get in."),
                Part(heading: "Ending", text: "You can stop any time. Deleting your account in Profile › Your data disconnects your banks and deletes your data."),
            ]
        default:
            return []
        }
    }

    var closing: String? {
        switch self {
        case .store: return "You can download or delete your data any time in Profile › Your data."
        case .share: return "We don’t sell your data, and we don’t show you ads."
        default: return nil
        }
    }
}

/// One detail sheet, with "Got it" at the bottom.
struct DocSheet: View {
    @Environment(\.dismiss) private var dismiss
    let doc: PearlDoc

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ProfileHeading(eyebrow: doc.eyebrow, title: doc.title)
                        .padding(.top, 28)
                    ForEach(doc.parts, id: \.self) { part in
                        VStack(alignment: .leading, spacing: 4) {
                            if let heading = part.heading {
                                Text(heading).font(Nacre.headline).foregroundColor(Pearl.ink)
                            }
                            Text(part.text).font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if !doc.facts.isEmpty {
                        GlassCard {
                            ForEach(Array(doc.facts.enumerated()), id: \.element) { i, fact in
                                if i > 0 { RowSeparator() }
                                factRow(fact)
                            }
                        }
                    }
                    if let closing = doc.closing { ProfileNote(closing) }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            Button("Got it") { dismiss() }
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
    }

    private func factRow(_ fact: PearlDoc.Fact) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(fact.label.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                Text(fact.text).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let tag = fact.tag {
                StatusPill(text: tag, tone: tag == "Needed" ? .info : .neutral)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }
}

extension View {
    /// A detail sheet over a Profile page.
    func docSheet(_ doc: Binding<PearlDoc?>) -> some View {
        sheet(item: doc) { d in
            DocSheet(doc: d)
                .background(SheetBackground())
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }
}
