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
    var target: Target? = nil

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

    enum CodingKeys: String, CodingKey { case id, kind, tier, title, amount, icon, tone, yes, target }

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
        case "trend_down": return "arrow.down.right"
        default: return "sparkles"
        }
    }

    var iconTone: APIcon.Tone {
        switch tone {
        case "warn": return .warn
        case "good": return .good
        default: return .rose
        }
    }

    /// Where a tap goes; nil when the item answers inline or has nowhere to go.
    var opens: Bool {
        guard yes == nil, let screen = target?.screen else { return false }
        return ["transaction", "trip", "bill", "debt", "plan", "owed_person", "owed", "category", "review"].contains(screen)
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

/// WORTH A LOOK with Clear, then one card of up to three rows.
struct WorthALookSection: View {
    let items: [WorthItem]
    let onClear: () -> Void
    let onOpen: (WorthItem) -> Void
    let onYes: (WorthItem) -> Void
    let onNotNow: (WorthItem) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            APSectionLabel(text: "Worth a look", action: "Clear", act: onClear)
            APCard {
                ForEach(Array(items.prefix(3).enumerated()), id: \.element.id) { i, item in
                    if i > 0 { APSeparator(afterFace: false) }
                    WorthRow(item: item, onOpen: { onOpen(item) }, onYes: { onYes(item) },
                             onNotNow: { onNotNow(item) })
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

    var body: some View {
        if item.yes != nil {
            VStack(alignment: .leading, spacing: 6) {
                line
                HStack(spacing: 8) {
                    Button(item.yes ?? "Yes", action: onYes).buttonStyle(WorthPillStyle(primary: true))
                    Button("Not now", action: onNotNow).buttonStyle(WorthPillStyle(primary: false))
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
            APIcon(symbol: item.symbol, tone: item.iconTone)
            Text(item.title)
                .font(.custom("Figtree-Regular", size: 16, relativeTo: .body))
                .foregroundColor(Pearl.ink)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let amount = item.amount {
                Text(amount).font(.custom("Figtree-SemiBold", size: 16, relativeTo: .body))
                    .monospacedDigit().foregroundColor(Pearl.ink)
                    .pearlAmountFit().fixedSize()
            } else if item.opens {
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
