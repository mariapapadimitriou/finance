import SwiftUI

/// A card with padding: the one A+ card, light and dark.
struct PearlCard<Content: View>: View {
    var padding: CGFloat = 20
    var spacing: CGFloat = 12
    var radius: CGFloat = Pearl.radiusCard
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: spacing, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(padding)
            .pearlCard(radius: radius)
    }
}

/// The top of a page: a small line over a Fraunces title, and a line under it.
struct PageHeader: View {
    var overline: String? = nil
    var overlineTone: Color = Pearl.muted
    let title: String
    var sub: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let overline = overline {
                Text(overline.uppercased())
                    .font(Pearl.text(.footnote, .medium))
                    .foregroundColor(overlineTone)
            }
            // A+ `.hdr h1`: Fraunces 34 regular.
            Text(title)
                .font(Pearl.heading(34, relativeTo: .largeTitle))
                .foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let sub = sub {
                Text(sub).font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 8)
    }
}

/// "Transactions ›": a pink text link with a small chevron.
struct LinkLabel: View {
    let text: String
    var chevron = true

    var body: some View {
        HStack(spacing: 4) {
            Text(text)
            if chevron { Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)) }
        }
        .font(Pearl.text(.subheadline, .medium))
        .foregroundColor(Pearl.link)
    }
}

/// "CATEGORY": a small caps label, A+ `.label` (13/500, tracked 0.78).
struct Overline: View {
    let text: String
    var tone: Color = Pearl.muted

    init(_ text: String, tone: Color = Pearl.muted) {
        self.text = text
        self.tone = tone
    }

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.label).tracking(0.78)
            .foregroundColor(tone)
    }
}

/// The one main action on a screen: A+ `.btn`.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .modifier(APPrimaryLook(enabled: isEnabled, pressed: configuration.isPressed))
    }
}

/// A quieter action beside the main one: A+ `.btn2`, the `control` capsule.
struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .modifier(APSecondaryLook(enabled: isEnabled, pressed: configuration.isPressed))
    }
}

/// One answer to a question: a full-width row with a radio, you tap.
struct ChoiceRow: View {
    let label: String
    var detail: String? = nil
    var selected = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 12) {
                Radio(on: selected).padding(.top, 2)
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).font(Pearl.text(.body)).foregroundColor(Pearl.ink)
                    if let detail = detail {
                        Text(detail).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            // A+ `.tile`: `card` with its 1 pt line, radius 18; picked, 2 pt action.
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(APlus.card))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(selected ? Pearl.action : APlus.cardLine, lineWidth: selected ? 2 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// A+ `.radio`: 24 pt, a 1.5 pt `muted` ring; on, a 7 pt `action` ring.
struct Radio: View {
    let on: Bool

    var body: some View {
        Circle().strokeBorder(on ? Pearl.action : Pearl.muted, lineWidth: on ? 7 : 1.5)
            .frame(width: 24, height: 24)
            .accessibilityHidden(true)
    }
}

/// A calm message: information or something to check.
struct Notice: View {
    enum Tone { case info, caution }
    let text: String
    var tone: Tone = .info

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: tone == .caution ? "exclamationmark.circle" : "info.circle")
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Pearl.text(.subheadline))
        .foregroundColor(tone == .caution ? Pearl.caution : Pearl.ink)
        .padding(14)
        .background(tone == .caution ? Pearl.cautionBackground : APlus.chip)
        .clipShape(RoundedRectangle(cornerRadius: Pearl.radiusRow, style: .continuous))
    }
}

/// The transaction at the top of a question: who, when, how much.
struct TransactionHeader: View {
    let name: String
    let date: String
    let account: String?
    let amount: Double
    let inflow: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Pearl.text(.body)).foregroundColor(Pearl.ink)
                Text([Format.day(date), account].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(Pearl.text(.footnote, .medium)).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text((inflow ? "+" : "-") + Format.amount(amount))
                .font(Pearl.display(.title3)).tracking(-0.44)
                .foregroundColor(inflow ? Pearl.moneyIn : Pearl.moneyOut)
                .lineLimit(1).minimumScaleFactor(0.7)
        }
        .padding(16)
        .apCard(radius: Pearl.radiusTile)
    }
}

/// Loading, or what went wrong with a way to try again.
struct LoadState: View {
    let error: String?
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            if let error = error {
                Text(error).multilineTextAlignment(.center).foregroundColor(Pearl.muted)
                Button("Try again", action: retry).buttonStyle(SecondaryButtonStyle()).frame(maxWidth: 200)
            } else {
                ProgressView()
            }
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding()
    }
}
