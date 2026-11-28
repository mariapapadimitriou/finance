import SwiftUI

// Worth a look (REDESIGN-05, -06; AP-Home, AP-WorthAnswer, AP-WorthCatalogue;
// THL-125, THL-254, THL-213). At most three one-line items from
// GET /api/worth-a-look, ranked by the server: Pearl needs a yes, then
// heads-ups, then one piece of good news. Only a new subscription and a
// price rise answer inline (Yes / Not now, or Update the bill / Not now);
// every other item is one tap to where it lives. Clear hides them all, with
// Undo on the ink toast. Not now is for good for that same thing.

/// One item.
struct WorthItem: Decodable, Identifiable, Hashable {
    let id: String
    let kind: String
    let tier: String
    let title: String
    var amount: String? = nil
    var icon: String? = nil
    var tone: String? = nil
    /// The inline primary ("Yes", "Update the bill"); nil for one-tap items.
    var yes: String? = nil
    /// T-74 (AP-Paycheque): a lone "Got it" pill under the line.
    var ack: String? = nil
    var target: Target? = nil
    /// WL-20, WL-21 (THL-309): the line under the title ("Was $16.49 since March.").
    var sub: String? = nil
    /// The second pill ("Not this", "Not mine anymore"); nil is Not now.
    var no: String? = nil
    /// What a tap on the row opens: its fact card and the same two answers.
    var sheet: Sheet? = nil

    /// WL-20 / WL-21's sheet (`.card.fact`): the caps, the figure, its line,
    /// a now-vs-before bar for a price rise, and a note for a subscription.
    struct Sheet: Decodable, Hashable {
        let title: String
        let over: String
        let big: String
        let line: String
        var note: String? = nil
        var now: Double? = nil
        var before: Double? = nil
    }

    struct Target: Decodable, Hashable {
        var screen: String?
        var id: String?
        var name: String?
        var month: String?

        enum CodingKeys: String, CodingKey { case screen, id, name, month }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            screen = try? c.decodeIfPresent(String.self, forKey: .screen)
            name = try? c.decodeIfPresent(String.self, forKey: .name)
            month = try? c.decodeIfPresent(String.self, forKey: .month)
            if let s = try? c.decodeIfPresent(String.self, forKey: .id) {
                id = s
            } else if let n = try? c.decodeIfPresent(Int.self, forKey: .id) {
                id = String(n)
            }
        }
    }

    enum CodingKeys: String, CodingKey { case id, kind, tier, title, amount, icon, tone, yes, ack, target, sub, no, sheet }

    /// The line icon (SF Symbols for the boards' line icons).
    var symbol: String {
        switch icon ?? kind {
        case "subscription": return "tv"
        case "price": return "chart.line.uptrend.xyaxis"
        case "duplicate": return "square.on.square"
        case "trip": return "airplane"
        case "home": return "house"
        case "bill": return "doc.text"
        case "card": return "creditcard"
        case "pace": return "chart.pie"
        case "people": return "person.2"
        case "person": return "person"
        case "calendar": return "calendar"
        case "piggy": return "banknote"
        case "pay": return "banknote"
        case "trend_down": return "arrow.down.right"
        default: return "sparkles"
        }
    }

    /// `.icon`, `.icon.warn` or `.icon.good`.
    var iconView: APIcon {
        switch tone {
        case "warn": return APIcon.warn(symbol)
        case "good": return APIcon.good(symbol)
        default: return APIcon(symbol: symbol)
        }
    }

    /// Where a tap goes; nil when the item answers inline or has nowhere to go.
    var opens: Bool {
        guard yes == nil, let screen = target?.screen else { return false }
        // Your plan and Save are parked: nothing opens them.
        return ["transaction", "trip", "bill", "debt", "owed_person", "owed", "category", "review",
                "income", "allowance"].contains(screen)
    }
}

/// The reply to GET and POST /api/worth-a-look.
struct WorthReply: Decodable {
    var items: [WorthItem] = []
    var toast: String? = nil
    var cleared: [String]? = nil

    enum CodingKeys: String, CodingKey { case items, toast, cleared }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = ((try? c.decodeIfPresent([Lenient<WorthItem>].self, forKey: .items)) ?? nil)?.compactMap(\.value) ?? []
        toast = try? c.decodeIfPresent(String.self, forKey: .toast)
        cleared = try? c.decodeIfPresent([String].self, forKey: .cleared)
    }
}

// MARK: - The section

/// FOR YOU with Dismiss (P1a, TP-Words; was WORTH A LOOK · Clear), then one
/// card of up to three rows.
struct WorthALookSection: View {
    let items: [WorthItem]
    let onClear: () -> Void
    let onOpen: (WorthItem) -> Void
    let onYes: (WorthItem) -> Void
    let onNotNow: (WorthItem) -> Void
    let onGotIt: (WorthItem) -> Void
    /// WL-20 / WL-21: the row with a sheet was tapped.
    var onSheet: (WorthItem) -> Void = { _ in }
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            APSectionLabel(text: "For you", action: "Dismiss", act: onClear)
            APCard {
                ForEach(Array(items.prefix(3).enumerated()), id: \.element.id) { i, item in
                    if i > 0 { APSeparator(afterFace: false) }
                    WorthRow(item: item, onOpen: { onOpen(item) }, onYes: { onYes(item) },
                             onNotNow: { onNotNow(item) }, onGotIt: { onGotIt(item) },
                             onSheet: { onSheet(item) })
                        .transition(reduceMotion ? .opacity
                                    : .asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity),
                                                  removal: .move(edge: .leading).combined(with: .opacity)))
                }
            }
        }
        .animation(reduceMotion ? .easeInOut(duration: 0.2) : .spring(response: 0.3, dampingFraction: 0.85),
                   value: items.map(\.id))
    }
}

/// One line (`.wl .row`): the icon, the title 16, an amount 16/600 on the
/// right edge or a chevron; an inline item puts its two pills under the line.
struct WorthRow: View {
    let item: WorthItem
    let onOpen: () -> Void
    let onYes: () -> Void
    let onNotNow: () -> Void
    let onGotIt: () -> Void
    var onSheet: () -> Void = {}

    var body: some View {
        if let ack = item.ack {
            // T-74: the line opens that month's income; Got it under it.
            VStack(alignment: .leading, spacing: 6) {
                Button(action: onOpen) { line.contentShape(Rectangle()) }.buttonStyle(.plain)
                Button(ack, action: onGotIt).buttonStyle(WorthPillStyle(primary: true))
                    .padding(.leading, 48)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .frame(minHeight: 56)
        } else if item.yes != nil {
            VStack(alignment: .leading, spacing: 6) {
                if item.sheet != nil {
                    // WL-20 / WL-21: the row opens its fact card.
                    Button(action: onSheet) { line.contentShape(Rectangle()) }.buttonStyle(.plain)
                        .accessibilityHint("Shows what Pearl saw.")
                        .accessibilityIdentifier("worth-sheet-\(item.kind)")
                } else {
                    line
                }
                HStack(spacing: 8) {
                    Button(item.yes ?? "Yes", action: onYes).buttonStyle(WorthPillStyle(primary: true))
                    Button(item.no ?? "Not now", action: onNotNow).buttonStyle(WorthPillStyle(primary: false))
                }
                .padding(.leading, 48)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .frame(minHeight: 56)
        } else if item.opens {
            Button(action: onOpen) {
                line.padding(.horizontal, 16).padding(.vertical, 10)
                    .frame(minHeight: 56).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            line.padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 56)
        }
    }

    private var line: some View {
        HStack(spacing: 12) {
            item.iconView
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.custom("Figtree-Regular", size: 16, relativeTo: .body))
                    .foregroundColor(Pearl.ink)
                    .lineLimit(2)
                if let sub = item.sub {
                    // `.row .s`: 13, muted.
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let amount = item.amount {
                // WL-20 / WL-21: a bill's amount is spending (`money-out`).
                Text(amount).font(.custom("Figtree-SemiBold", size: 16, relativeTo: .body))
                    .monospacedDigit().foregroundColor(item.sheet != nil ? Pearl.moneyOut : Pearl.ink)
                    .pearlAmountFit().fixedSize()
            } else if item.opens && item.ack == nil {
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Pearl.muted)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// `.pill-btn`: 32 high, 15/600; Yes in `action` on `action-wash`, Not now
/// ink on `chip`; pressed, Yes fills with `action`.
struct WorthPillStyle: ButtonStyle {
    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.custom(primary ? "Figtree-SemiBold" : "Figtree-Medium", size: 15, relativeTo: .subheadline))
            .foregroundColor(primary ? (configuration.isPressed ? Pearl.onAction : Pearl.action) : Pearl.ink)
            .padding(.horizontal, 14)
            .frame(minHeight: 32)
            .background(Capsule().fill(primary ? (configuration.isPressed ? Pearl.action : APlus.actionWash) : APlus.chip))
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .tapTarget(vertical: 6, horizontal: 2)
    }
}

// MARK: - WL-20 / WL-21 · the sheet a row opens (THL-309)

/// "Netflix went up" or "Crave": the fact card (`.card.fact`), a note for a
/// subscription ("To stop it, cancel with Crave. Pearl can't cancel for
/// you."), then the row's two answers as the sheet's buttons.
struct WorthFactSheet: View {
    let item: WorthItem
    let sheet: WorthItem.Sheet
    let onYes: () -> Void
    let onNo: () -> Void
    let close: () -> Void

    var body: some View {
        PearlSheet {
            APSheetHeader(heading: sheet.title, close: close)
            AskFactCard {
                AskStyle.over(sheet.over)
                Text(sheet.big).font(AskStyle.big).foregroundColor(Pearl.moneyOut)
                    .monospacedDigit().pearlAmountFit().padding(.top, 2)
                Text(sheet.line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                if let now = sheet.now, let before = sheet.before {
                    AskCompare(spent: now, usual: before, spentLabel: "Now", usualLabel: "Before")
                }
            }
            .accessibilityElement(children: .combine)
            if let note = sheet.note {
                // `.sline`: 15, muted, under the card.
                Text(note).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
        } footer: {
            PearlSheetButtons(primary: item.yes ?? "Yes", secondary: item.no ?? "Not now",
                              onPrimary: onYes, onSecondary: onNo)
        }
    }
}
