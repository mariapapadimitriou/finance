import SwiftUI

// SPLIT-25 (THL-291), restyled by REFRESH-02 (Design refresh section 11):
// a payment's options from the purchase it paid back (S-05or, 1090:2457)
// and its Unlink? sheet (S-34sr 1092:2716, S-34kr1–10 1092:2890–3332), as
// Pearl sheets on the iridescent background. Everything they say comes from the server's
// `LinkInfo`; the split card's people use S-40 (SplitMenus.swift) instead.

/// S-05or: a PAID BACK row on a purchase that isn't split, or a REFUNDED
/// BY row. "Jo paid back $30.00", where the money came from, then View…
/// (opens it here in Pearl, never the web) and Unlink….
struct PaybackOptionsSheet: View {
    let link: Transaction.LinkInfo
    /// "PAID BACK" or "REFUNDED BY".
    let overline: String
    let onClose: () -> Void
    let onView: () -> Void
    let onUnlink: () -> Void

    var body: some View {
        // G2-Payback: "Jo paid back $30.00" centred with ✕, where the money
        // came from under it, then View… and Unlink…. The overline is spoken.
        APSheet {
            APSheetHeader(heading: link.dialog, line: link.message, close: onClose)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(overline.capitalized), \(link.dialog), \(link.message)")
            APOptionCard {
                if let view = link.view {
                    // REFRESH-03 (S-05or): the title alone; it still opens here, never the web.
                    APOptionRow(symbol: "arrow.left.arrow.right", title: view.label, action: onView)
                    APSeparator()
                }
                APOptionRow(symbol: "link", title: link.kind == "refund" ? "Unlink refund…" : "Unlink…",
                            sub: Self.firstSentence(link.sheet.line), action: onUnlink)
            }
        }
    }

    /// "Sam owes you $30.00 again on Loblaws" from the sheet's line.
    static func firstSentence(_ line: String) -> String {
        guard let r = line.range(of: ". ") else { return line.hasSuffix(".") ? String(line.dropLast()) : line }
        return String(line[..<r.lowerBound])
    }
}

// MARK: - Unlink? from the purchase (S-34sr, S-34kr)

/// S-34sr / S-34kr1–10: Unlink? for one payment, from the purchase it paid
/// back. Title, line, card and buttons come from `LinkInfo.sheet`. While it
/// waits: a spinner in Unlink, both buttons off, no swipe-dismiss; a failure
/// keeps everything as it was and says so on the champagne banner.
@MainActor
struct UnlinkLinkSheet: View {
    let link: Transaction.LinkInfo
    /// The purchase it's unlinked from.
    let charge: String
    let api: APIClient
    let onCancel: () -> Void
    /// S-44a: the toast's title and its Undo.
    let onDone: (String, JSONValue?) -> Void
    @State private var busy = false
    @State private var failed = false

    private struct Reply: Decodable {
        let title: String?
        let undo: JSONValue?
    }

    private static let error = "Couldn’t unlink that. Nothing changed. Try again."

    /// "To unlink the whole $60.00, open the e-Transfer." for a payment that
    /// also paid back other purchases.
    private var wholeHint: String? {
        guard let others = link.others, !others.isEmpty, let whole = link.whole else { return nil }
        return "To unlink the whole \(Format.amount(whole)), open the \(link.noun)."
    }

    var body: some View {
        let s = link.sheet
        APSheet(dismissDisabled: busy) {
            // A+ confirmation (G2-LetGo's shape): the question centred with
            // ✕, the line, then the payment.
            APSheetHeader(heading: link.sheet.heading ?? s.ask ?? s.title, close: onCancel)
                .disabled(busy)
                .accessibilityHint(s.overline ?? "Unlink")
            Text(s.line).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let card = s.card {
                HStack(spacing: 12) {
                    APIcon(symbol: PersonOptionsSheet.symbol(link.kind), tone: Pearl.moneyIn)
                    // G2-AUnlink: who sent it over what it was ("e-Transfer
                    // from Jo Park · Nov 16" over "Part of $60.00").
                    VStack(alignment: .leading, spacing: 2) {
                        Text(cardTitle ?? card.label).font(Nacre.body).foregroundColor(Pearl.ink)
                        if let sub = cardSub {
                            Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Text(Format.amount(card.amount)).font(Nacre.headline).monospacedDigit()
                        .foregroundColor(Pearl.moneyIn)
                }
                .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                .apCard()
                .accessibilityElement(children: .combine)
                // S-34sr (REFRESH-03): the footnote about the whole payment is
                // gone from the sheet; VoiceOver keeps it on the payment row.
                .accessibilityHint(wholeHint ?? "")
            }
            if failed {
                // G2-AUnlink (S-34sr): the error is a red line under the card.
                Label(Self.error, systemImage: "exclamationmark.circle")
                    .font(Nacre.footnote).foregroundColor(Pearl.danger)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .combine)
            }
        } footer: {
            PearlSheetButtons(primary: failed ? "Try again" : (s.confirm ?? s.button), busy: busy,
                              busyLabel: s.overline == "FORGET" ? "Forgetting…" : "Unlinking…", secondary: s.keep ?? "Keep linked",
                              onPrimary: { Task { await unlink() } }, onSecondary: onCancel)
                // G2-AUnlink: no footnote under the buttons; VoiceOver keeps it.
                .accessibilityHint(s.note ?? "")
        }
    }

    /// "e-Transfer from Jo Park · Nov 16" (shared), "e-Transfer from Sam
    /// Lee", "Cash · Nov 12", "Refund from Costco".
    private var cardTitle: String? {
        switch link.kind {
        case "cash", "app": return "\(PersonOptionsSheet.word(link)) · \(Format.short(link.date))"
        default:
            let shared = !(link.others ?? []).isEmpty
            return shared ? "\(link.sheet.name) · \(Format.short(link.date))" : link.sheet.name
        }
    }

    /// "Part of $60.00", "You marked this as cash", or the day.
    private var cardSub: String? {
        switch link.kind {
        case "cash": return link.deposit.map { "Deposited \(Format.short($0.date))" } ?? "You marked this as cash"
        case "app": return "You marked this as paid in \(PersonOptionsSheet.word(link))"
        default:
            if let others = link.others, !others.isEmpty, let whole = link.whole { return "Part of \(Format.amount(whole))" }
            return Format.short(link.date)
        }
    }

    private func unlink() async {
        busy = true
        defer { busy = false }
        do {
            let reply: Reply
            switch link.kind {
            case "refund":
                reply = try await api.delete("api/transactions/\(link.inflow ?? link.id)/refund")
            case "cash", "app":
                reply = try await api.delete("api/transactions/\(charge)/split/cash/\(link.cashId ?? 0)")
            default:
                reply = try await api.delete("api/transactions/\(charge)/paybacks/\(link.inflow ?? link.id)")
            }
            failed = false
            onDone(reply.title ?? link.toast ?? "Unlinked", reply.undo)
        } catch {
            failed = true
        }
    }
}
