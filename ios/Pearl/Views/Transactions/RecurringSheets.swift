import SwiftUI

/// RS-01 (G1-TxRecurring, 2026-11-24): the transaction page's Recurring
/// row opens this. A transfer a recurring rule sorted says so, and this is
/// the way out: "Not this one" keeps its category as her own answer, the
/// rule skips it; "Stop the rule" removes the rule for every transfer like
/// it, as Profile › Recurring transfers › Stop treating it as recurring.
struct RecurringRowSheet: View {
    let rule: Transaction.RecurringRule
    let onNotThisOne: () -> Void
    let onStop: () -> Void
    let onClose: () -> Void

    /// "Into savings", "My other account", "Rent", or the category.
    static func words(_ category: String) -> String {
        RTWords.kinds.first { $0.category == category }?.label ?? category
    }

    private var line: String {
        let what = Self.words(rule.category)
        let since = rule.first.map { " since \(Self.month($0))" } ?? ""
        return "\(what) · \(rule.count) so far\(since)"
    }

    /// "September", from "2026-09-01".
    private static func month(_ day: String) -> String {
        guard let d = Format.date(day) else { return day }
        let f = DateFormatter()
        f.setLocalizedDateFormatFromTemplate("MMMM")
        return f.string(from: d)
    }

    var body: some View {
        let n = rule.count
        APSheet {
            APSheetHeader(heading: rule.when, line: line, close: onClose)
            APOptionCard {
                option(symbol: "1.circle", title: "Not this one",
                       line: "Keeps \(Self.words(rule.category)) as your own answer. The rule skips it.",
                       action: onNotThisOne)
                APSeparator()
                option(symbol: "xmark", title: "Stop the rule",
                       line: "\(n == 1 ? "It keeps its" : "The \(n) keep their") category. Pearl stops sorting new ones.",
                       tone: Pearl.danger, action: onStop)
            }
        }
    }

    private func option(symbol: String, title: String, line: String, tone: Color = Pearl.ink,
                        action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                CFIcon(symbol: symbol)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(tone)
                    Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Pearl.muted).accessibilityHidden(true)
            }
            .padding(.vertical, 10)
            .frame(minHeight: 64).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
