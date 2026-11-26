import SwiftUI

// Payback question (Figma Proposals › "Payback question" 1418:88290, note
// 1419:89986; approved by the product owner 2026-11-16; THL-289, THL-291,
// THL-181, THL-231, THL-232, THL-301). Replaces T-70 and AnswerSheet's old
// list of three answers. Every word on it is the server's
// (finance/payback_question.py): each tile's title, the reason in a few
// words, and the toast.
//
// LT-03 · PQ-03, less text (1425:7351, dark 1425:7552; TEXT-01, approved
// 2026-11-16): the Why card is gone, the reason sits in the tile ("Oct 31 ·
// about a third · 2 days before"), "Then: income?", and no footer.
//
// PQ-03 (1418:88292, dark 1418:88584): one likely purchase.
// PQ-03b (1418:88874, dark 1418:89179): on a split and part-paid, with a
//   second likely purchase.
// PQ-03c (1419:89682, dark 1419:89834): a tap answers; the card leaves Needs
//   a look and the ink toast says "mPg paid back $20.00 for Añejo", with Undo.
// PQ-03p (1419:89482, dark 1419:89582): the deposit's page, with a dashed
//   question card and "Name them" in place of the Not counted pill.

// The model, PaybackQuestion, is in Models.swift (check_stack compiles it on its own).

/// PQ-03 / PQ-03b (LT-03): everything under the sheet's title, LOOKS LIKE
/// and the tiles. A tile answers at once (AnswerTile: 0.97 press, success
/// haptic, a cross-fade with Reduce Motion); there's no Continue.
struct PaybackQuestionBody: View {
    let question: PaybackQuestion
    let amount: String
    let date: String
    let onTile: (PaybackQuestion.Tile) -> Void
    /// Something else: find the purchase.
    let onElse: () -> Void
    /// Not a payback: on to the income question (T-08).
    let onNot: () -> Void
    /// Name them: T-14 Who sent this?.
    let onName: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            PaybackHeader(name: question.who, line: "\(amount) · \(Format.weekdayDay(date))",
                          onName: question.named ? nil : onName)
            QuestionCaption(text: "Looks like")
            ForEach(question.tiles) { tile in
                // PQ-03o, PQ-03s: "Yes, Corner Bistro · Georgia Klev’s share".
                AnswerTile(title: tile.guess == true && tile.kind == "split" ? "Yes, \(tile.title)" : tile.title, line: tile.line, symbol: CategorySheet.symbol(for: tile.category),
                           guess: tile.guess == true) { onTile(tile) }
            }
            AnswerGrid {
                AnswerTile(title: "Something else", line: "Find the purchase", symbol: "bag", action: onElse)
                AnswerTile(title: "Not a payback", line: "Then: income?",
                           symbol: "person.crop.circle.badge.xmark", action: onNot)
            }
        }
    }
}

/// "mPg" over "+$20.00 · Mon, Nov 2 · Name them": the name as it came, and
/// Name them in link colour while the bank's name is all Pearl has.
private struct PaybackHeader: View {
    let name: String
    let line: String
    let onName: (() -> Void)?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let big = typeSize.isAccessibilitySize
        HStack(spacing: 12) {
            if !big {
                // A+ (AP-Sheet, kit `.who`): the 44 pt ring.
                CFRing(name: name, size: 44)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(big ? 3 : 2)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("\(name), \(Format.spoken(line))")
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 0) { amountLine(dot: true); nameThem }
                    VStack(alignment: .leading, spacing: 2) { amountLine(dot: false); nameThem }
                }
            }
            Spacer(minLength: 0)
        }
    }

    private func amountLine(dot: Bool) -> some View {
        Text(line + (dot && onName != nil ? " · " : ""))
            .font(Nacre.subheadline).foregroundColor(Pearl.moneyIn)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
    }

    @ViewBuilder private var nameThem: some View {
        if let onName = onName {
            Button("Who sent this?", action: onName)
                .font(Nacre.subheadline).foregroundColor(Pearl.link)
                .buttonStyle(.plain)
                .accessibilityHint("Opens Who sent this?")
        }
    }
}

/// PQ-03p (G2-APQ): A QUESTION over a plain card: the purchase's icon,
/// "Paying you back for Añejo?" over "Oct 31 · about a third", and Yes /
/// Not this as pill buttons under it. Yes answers Pearl's guess (the first
/// tile) as the sheet's tile would; Not this opens the whole question.
struct PaybackQuestionCard: View {
    let question: PaybackQuestion
    let onYes: () -> Void
    let onNot: () -> Void

    var body: some View {
        let guess = question.tiles.first
        VStack(alignment: .leading, spacing: 8) {
            APSectionLabel(text: "A question")
            APCard {
                VStack(alignment: .leading, spacing: 0) {
                    // kit `.row.noface`: the 36 pt icon, the title (17) over its line (15).
                    HStack(spacing: 12) {
                        CFIcon(symbol: guess.map { CategorySheet.symbol(for: $0.category) } ?? "person.2")
                        VStack(alignment: .leading, spacing: 2) {
                            Text(question.card.title).font(Nacre.body).foregroundColor(Pearl.ink)
                            Text(Self.line(question)).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 4)
                    .accessibilityElement(children: .combine)
                    HStack(spacing: 8) {
                        if guess != nil {
                            APPillButton(title: "Yes", identifier: "payback-question-yes", action: onYes)
                                .accessibilityLabel("Yes, \(question.card.title.dropLast())")
                        }
                        APPillButton(title: "Not this", quiet: true, identifier: "payback-question-not", action: onNot)
                            .accessibilityHint("Shows the other answers")
                    }
                    .padding(.leading, 64).padding(.trailing, 16).padding(.bottom, 8)
                }
            }
        }
    }

    /// "Oct 31 · about a third": the server's "Pearl’s guess · about a
    /// third" with the purchase's day in place of the words (the card says
    /// it's a question already).
    static func line(_ q: PaybackQuestion) -> String {
        guard let tile = q.tiles.first else { return q.card.line }
        let rest = q.card.line.replacingOccurrences(of: "Pearl’s guess", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: " ·"))
        return [Format.short(tile.date), rest].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

/// PQ-03p (G2-APQ): "Who sent this?" (TP-Words; was "Name them") in `link` on its own line under the hero's
/// date, while the bank's name is all Pearl has. No pill in the corner.
struct NameThemLink: View {
    let action: () -> Void

    var body: some View {
        Button("Who sent this?", action: action)
            .font(Nacre.subheadline).foregroundColor(Pearl.link)
            .buttonStyle(.plain)
            .frame(minHeight: 44).padding(.vertical, -12)
            .contentShape(Rectangle())
            .accessibilityHint("Opens Who sent this?")
    }
}

extension PaybackQuestion {
    /// PQ-03's tile (2026-11-16): the person to open PB-30 for, with this
    /// purchase ticked, when the money is more than the tile's share and that
    /// person owes on other purchases; nil for the single tap. Offline, nil.
    /// Shared by the sheet's tile and PQ-03p's Yes.
    static func partsPerson(api: APIClient, id: String, amount: Double, tile: Tile) async -> String? {
        struct Reply: Decodable { let from: String?; let items: [Lenient<PartsSheet.Owing>] }
        let r: Reply? = try? await api.get("api/transactions/\(id)/owing",
                                           query: tile.person.map { ["person": $0] } ?? [:])
        let theirs = (r?.items ?? []).compactMap(\.value)
            .filter { $0.theirs == true && $0.unknown != true && $0.owes >= 0.005 }
        let cents: (Double) -> Int = { Int((abs($0) * 100).rounded()) }
        if let from = r?.from, let share = theirs.first(where: { $0.charge == tile.charge }),
           cents(amount) > cents(share.owes), theirs.count > 1 {
            return from
        }
        return nil
    }
}
