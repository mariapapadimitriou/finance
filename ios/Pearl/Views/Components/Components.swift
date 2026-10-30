import SwiftUI

/// A white card with Pearl's soft border.
struct PearlCard<Content: View>: View {
    var padding: CGFloat = 20
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(padding)
            .background(Pearl.card)
            .clipShape(RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous)
                .stroke(Pearl.border, lineWidth: 1))
    }
}

/// The one main action on a screen.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Pearl.text(.body, .semibold))
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundColor(Pearl.onAction)
            .background(Pearl.action.opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.4))
            .clipShape(Capsule())
    }
}

/// A quieter action beside the main one.
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Pearl.text(.body, .semibold))
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundColor(Pearl.ink)
            .background(Pearl.card.opacity(configuration.isPressed ? 0.7 : 1))
            .clipShape(Capsule())
            .overlay(Capsule().stroke(Pearl.border, lineWidth: 1))
    }
}

/// One answer to a question: a full-width row you tap.
struct ChoiceRow: View {
    let label: String
    var detail: String? = nil
    var selected = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundColor(selected ? Pearl.action : Pearl.muted)
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).foregroundColor(Pearl.ink)
                    if let detail = detail {
                        Text(detail).font(Pearl.text(.subheadline)).foregroundColor(Pearl.muted)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Pearl.card)
            .clipShape(RoundedRectangle(cornerRadius: Pearl.radiusRow, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Pearl.radiusRow, style: .continuous)
                .stroke(selected ? Pearl.action : Pearl.border, lineWidth: selected ? 2 : 1))
        }
        .buttonStyle(.plain)
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
        .background(tone == .caution ? Pearl.cautionBackground : Pearl.blush.opacity(0.6))
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
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(name).font(Pearl.text(.body, .semibold)).foregroundColor(Pearl.ink)
                Text([Format.day(date), account].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(Pearl.text(.subheadline)).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text(Format.signed(amount, inflow: inflow))
                .font(Pearl.display(.title3))
                .foregroundColor(inflow ? Pearl.moneyIn : Pearl.ink)
        }
        .padding(16)
        .background(Pearl.answered)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
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

extension View {
    /// Pearl's page background behind a scrolling screen.
    func pearlPage() -> some View {
        self.background(Pearl.page.ignoresSafeArea())
    }
}
