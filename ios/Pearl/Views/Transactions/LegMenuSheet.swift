import SwiftUI

/// The ⋯ beside a leg of a transfer's Moved card (product owner,
/// 2026-11-22): a Pearl sheet, not a system menu, with what the leg can
/// do. "Unlink from transfer" takes that leg off the line: its row(s)
/// stand on their own in Cash flow, a transfer still, with one Undo.
struct LegMenuSheet: View {
    let account: String
    let onUnlink: () -> Void
    let onClose: () -> Void

    var body: some View {
        APSheet {
            APSheetHeader(overline: "Transfer", title: account, close: onClose)
            APOptionCard {
                Button(action: onUnlink) {
                    HStack(spacing: 12) {
                        CFIcon(symbol: "link")
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Unlink from transfer").font(Nacre.body).foregroundColor(Pearl.ink)
                            Text("This leg becomes its own row").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Pearl.muted).accessibilityHidden(true)
                    }
                    .frame(minHeight: 64).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }
}
