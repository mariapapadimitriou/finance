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
                AnswerTile(title: tile.title, line: tile.line, symbol: CategorySheet.symbol(for: tile.category),
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
            Button("Name them", action: onName)
                .font(Nacre.subheadline).foregroundColor(Pearl.link)
                .buttonStyle(.plain)
                .accessibilityHint("Opens Who sent this?")
        }
    }
}

/// PQ-03p: the flat "Not sorted yet" bar, as Pearl's guess in words on a
/// dashed card ("Paying you back for Añejo?"). It opens the question.
struct PaybackQuestionCard: View {
    let card: PaybackQuestion.Card
    let action: () -> Void

    var body: some View {
        // A+ (AP-Sheet): Pearl's guess on a dashed rose card, radius 18.
        let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
        Button(action: action) {
            HStack(spacing: 12) {
                CFIcon(symbol: "person.2")
                VStack(alignment: .leading, spacing: 2) {
                    Text(card.title).font(Nacre.headline).foregroundColor(Pearl.ink)
                    Text(card.line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(shape.fill(APlus.card))
            .overlay(shape.strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])))
            .contentShape(shape)
        }
        .buttonStyle(TilePress())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(card.title) \(card.line)")
        .accessibilityAddTraits(.isButton)
    }
}

/// PQ-03p: "Name them" under the name, in place of the grey Not counted pill.
struct NameThemPill: View {
    let action: () -> Void

    var body: some View {
        // A+ kit `.pill`, its word in `link`.
        Button("Name them", action: action)
            .font(Nacre.footnote).foregroundColor(Pearl.link)
            .padding(.horizontal, 12).frame(height: 28)
            .background(Capsule().fill(APlus.chip))
            .buttonStyle(.plain)
            .padding(.top, 4)
            .accessibilityHint("Opens Who sent this?")
    }
}
