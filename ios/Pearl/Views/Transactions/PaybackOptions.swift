import SwiftUI

// SPLIT-25 (THL-291), restyled by REFRESH-02 (Design refresh section 11):
// a payment's options from the purchase it paid back (S-05or, 1090:2457)
// and its Unlink? sheet (S-34sr 1092:2716, S-34kr1–10 1092:2890–3332), as
// Pearl sheets on pearl paper. Everything they say comes from the server's
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
        PearlSheet {
            HStack(alignment: .top, spacing: 12) {
                PearlBubble(symbol: PersonOptionsSheet.symbol(link.kind), size: 44)
                VStack(alignment: .leading, spacing: 1) {
                    Text(overline).font(Pearl.text(.footnote, .medium)).tracking(0.78).foregroundColor(Pearl.muted)
                    Text(link.dialog).font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text(link.message).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                PearlCloseButton(action: onClose)
            }
            PearlOptionCard {
                if let view = link.view {
                    // REFRESH-03 (S-05or): the title alone; it still opens here, never the web.
                    PearlOptionRow(symbol: "eye", title: view.label, action: onView)
                    PearlDivider()
                }
                PearlOptionRow(symbol: "xmark", title: link.kind == "refund" ? "Unlink refund…" : "Unlink…",
                               sub: Self.firstSentence(link.sheet.line), action: onUnlink)
            }
        }
    }

    /// "Jo will owe you $30.00 again on Pizza Nova" from the sheet's line.
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
        PearlSheet(dismissDisabled: busy) {
            HStack(alignment: .top, spacing: 12) {
                if link.kind == "refund" || link.kind == "reimbursement" {
                    PearlBubble(symbol: PersonOptionsSheet.symbol(link.kind), size: 44)
                } else {
                    PearlFace(name: s.face)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(s.overline ?? "UNLINK").font(Pearl.text(.footnote, .medium)).tracking(0.78)
                        .foregroundColor(Pearl.muted)
                    Text(link.sheet.heading ?? s.ask ?? s.title).font(Pearl.heading(22, relativeTo: .title2))
                        .foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                PearlCloseButton(action: onCancel).disabled(busy)
            }
            Text(s.line).font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let card = s.card {
                HStack(spacing: 12) {
                    PearlBubble(symbol: PersonOptionsSheet.symbol(link.kind), tone: Pearl.moneyIn, size: 36)
                    Text(card.label).font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Text(Format.amount(card.amount)).font(Pearl.text(.callout, .semibold)).monospacedDigit()
                        .foregroundColor(Pearl.moneyIn)
                }
                .padding(12)
                .background(RoundedRectangle(cornerRadius: Pearl.radiusRow, style: .continuous).fill(Pearl.card))
                .overlay(RoundedRectangle(cornerRadius: Pearl.radiusRow, style: .continuous).stroke(Pearl.border, lineWidth: 1))
                .accessibilityElement(children: .combine)
                // S-34sr (REFRESH-03): the footnote about the whole payment is
                // gone from the sheet; VoiceOver keeps it on the payment row.
                .accessibilityHint(wholeHint ?? "")
            }
            if failed { CautionBanner(text: Self.error) }
        } footer: {
            VStack(spacing: 0) {
                PearlSheetButtons(primary: failed ? "Try again" : (s.confirm ?? s.button), busy: busy,
                                  busyLabel: "Unlinking…", secondary: s.keep ?? "Keep linked",
                                  onPrimary: { Task { await unlink() } }, onSecondary: onCancel)
                if let note = s.note {
                    Text(note).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.bottom, 12)
                }
            }
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
