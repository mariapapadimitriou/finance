import SwiftUI

// Paid back (Figma Proposals › "Paid back" 1351:8769, note 1352:10319;
// approved by the product owner 2026-11-15; THL-289, THL-291, THL-181,
// THL-231, THL-232). One "Paid back" tile (PB-10) replaces Paying me back,
// Money back and Work paying me back; "Who paid you back?" (PB-11) asks
// who, and a person's share is part or all of it on purpose (PB-13, in
// PartsFlow.swift), with "Let the other $45.00 go?" (PB-13b) when the money
// is less than they owe. Pearl sheets, never a stock dialog.

/// PB-11's three answers, in the approved order: a person first (decision 3).
enum PaidBackWho: Hashable {
    case person, shop, work
}

/// PB-11 "Who paid you back?" (1351:9324, dark 1351:9461): the Sheet header
/// (the sender's face, PAID BACK, "+$15.00 · e-Transfer from Sam Lee · Nov
/// 16" in money-in green), PICK ONE, then A person · The shop · Work. Each
/// row answers at once; ✕ and a swipe down keep the tiles as they were.
struct PaidBackWhoSheet: View {
    /// The face's initials: who it came from.
    let face: String
    /// "+$15.00 · e-Transfer from Sam Lee · Nov 16".
    let sub: String
    /// From the purchase (PB-22 → PB-11): the kind the match was, picked
    /// for her and listed first with why (PAID-02); any row still answers.
    var picked: PaidBackWho? = nil
    /// Who on the split it was from; the row says only "On this split"
    /// (less text 2), so this just says Pearl knows who.
    var pickedPerson: String? = nil
    let onPick: (PaidBackWho) -> Void
    let onClose: () -> Void

    /// A person first (decision 3), unless Pearl picked another.
    private var order: [PaidBackWho] {
        let all: [PaidBackWho] = [.person, .shop, .work]
        guard let p = picked else { return all }
        return [p] + all.filter { $0 != p }
    }

    /// G2-WhoPaid: the payment's name is the display title ("e-Transfer from
    /// Sam Lee") and the amount and day are its line ("+$15.00 · Nov 16").
    private var parts: (title: String, line: String) {
        let bits = sub.components(separatedBy: " · ")
        guard bits.count >= 3 else { return (sub, "") }
        return (bits[1...].dropLast().joined(separator: " · "), [bits[0], bits[bits.count - 1]].joined(separator: " · "))
    }

    var body: some View {
        APSheet {
            APSheetHeader(heading: "Who paid you back?", face: face, overline: "Paid back", title: parts.title,
                          sub: parts.line.isEmpty ? nil : parts.line, close: onClose)
            // G2-WhoPaid: the three kinds as tiles, two to a row.
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                ForEach(order, id: \.self) { who in tile(who) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Pick one")
        }
    }

    /// PAID-02: the picked tile says why ("On this split", "your employer",
    /// "this shop"); The shop otherwise says "A refund" (REDESIGN-09).
    private func tile(_ who: PaidBackWho) -> some View {
        let on = picked == who
        switch who {
        case .person:
            return APTile(symbol: "person", title: "A person",
                          sub: on && pickedPerson != nil ? "On this split" : nil, current: on) { onPick(.person) }
        case .shop:
            return APTile(symbol: "bag", title: "The shop", sub: on ? "this shop" : "A refund",
                          current: on) { onPick(.shop) }
        case .work:
            // "Other" (product owner, 2026-11-21): a reimbursement from
            // anyone who isn't a person on a split or the shop; work,
            // insurance, a landlord, the government.
            return APTile(symbol: "briefcase", title: "Other", sub: "Work, insurance or anyone else",
                          current: on) { onPick(.work) }
        }
    }
}

/// PB-13b "Let the other $45.00 go?" (1354:10841, dark 1354:10901): "All of
/// it" when the money is less than their share. The eyebrow names them and
/// the purchase ("SAM · PAI NORTHERN THAI"); Let it go marks them paid in
/// full and the rest stays hers; "Sam still owes it" records it as Part of
/// it (PB-14). ✕ goes back to PB-13 with nothing saved.
struct PaidBackLetGoSheet: View {
    /// "Sam".
    let name: String
    let merchant: String
    /// What came in for them, and their share still owed.
    let paid: Double
    let owes: Double
    let onLetGo: () -> Void
    let onStillOwes: () -> Void
    let onClose: () -> Void

    private var rest: Double { max(0, owes - paid) }

    var body: some View {
        APSheet {
            APSheetHeader(heading: "Let the other \(Format.amount(rest)) go?", close: onClose)
                .accessibilityHint("\(name) · \(merchant)")
            Text("\(name) paid \(Format.amount(paid)) of \(Format.amount(owes)). Letting it go marks \(name) paid in full, and the other \(Format.amount(rest)) stays yours.")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
        } footer: {
            PearlSheetButtons(primary: "Let it go", secondary: "\(name) still owes it",
                              onPrimary: onLetGo, onSecondary: onStillOwes)
        }
    }
}
