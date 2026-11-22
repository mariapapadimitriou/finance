import SwiftUI

/// A Cash flow row's ⋯ (product owner, 2026-11-22): a Pearl sheet with what
/// the row can do from the list. A transfer line offers "Unlink from
/// transfer", after which each leg is its own row; a leg on its own offers
/// "Link to another transfer" (LinkTransfersSheet).
struct RowMenuSheet: View {
    let t: Transaction
    let onUnlink: () -> Void
    let onLink: () -> Void
    let onClose: () -> Void

    var body: some View {
        APSheet {
            APSheetHeader(overline: t.merchant, title: Format.amount(abs(t.amount)), close: onClose)
            APOptionCard {
                if t.transfer != nil {
                    option("Unlink from transfer", sub: "Each leg becomes its own row", symbol: "link", action: onUnlink)
                } else {
                    option("Link to another transfer", sub: "Pick the other legs of this move", symbol: "link",
                           action: onLink)
                }
            }
        }
    }

    private func option(_ title: String, sub: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                CFIcon(symbol: symbol)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundColor(Pearl.muted)
                    .accessibilityHidden(true)
            }
            .frame(minHeight: 64).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint(sub)
    }
}
