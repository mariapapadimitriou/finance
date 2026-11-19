import SwiftUI

// A+ G7 (REDESIGN-14; Claude Design boards AP-Chat, G7-Chat, G7-Tell,
// G7-TellMore, G7-Confirm, G7-Unavailable): the pieces every chat screen is
// made of. Her words in a blush bubble on the right, Pearl's in plain 17 pt
// lines on the left, cards on the A+ card. Each is a small view of its own:
// the chat's bodies stay small on the stack (check_stack.py).

/// Her words: right, blush, 18 pt corners with the bottom right tucked to 4,
/// at most about four fifths of the width (G7: `you`).
struct ChatYou: View {
    let text: String

    var body: some View {
        Text(text)
            .font(Nacre.body).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(ChatBubbleShape().fill(Pearl.bubble))
            .padding(.leading, 72)
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding(.top, 14)
            .accessibilityLabel("You: \(text)")
    }
}

/// 18 pt corners, the bottom right 4 (iOS 16 has no uneven rounded rectangle).
struct ChatBubbleShape: Shape {
    func path(in r: CGRect) -> Path {
        let big = min(18, r.height / 2), small: CGFloat = 4
        var p = Path()
        p.move(to: CGPoint(x: r.minX + big, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - big, y: r.minY))
        p.addArc(center: CGPoint(x: r.maxX - big, y: r.minY + big), radius: big,
                 startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - small))
        p.addArc(center: CGPoint(x: r.maxX - small, y: r.maxY - small), radius: small,
                 startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX + big, y: r.maxY))
        p.addArc(center: CGPoint(x: r.minX + big, y: r.maxY - big), radius: big,
                 startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + big))
        p.addArc(center: CGPoint(x: r.minX + big, y: r.minY + big), radius: big,
                 startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        p.closeSubpath()
        return p
    }
}

/// Pearl's words: 17 on 24, ink, 4 in from the cards (G7: `pearl`).
struct ChatLine: View {
    let text: String
    var top: CGFloat = 14

    var body: some View {
        Text(text)
            .font(Nacre.body).foregroundColor(Pearl.ink)
            .lineSpacing(2)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4).padding(.top, top)
    }
}

/// G7-Tell-r (PC-05, PC-06): after the first card, her sentence cut short in
/// muted 15 pt, "2 of 7" in 15 semibold, then one 8 pt dash per card, lit for
/// the ones behind her (A+ `streak`: 4 apart, the gradient on).
struct ChatDeckProgress: View {
    let title: String
    let done: Int
    let total: Int

    private var count: String { "\(done + 1) of \(total)" }

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 10) {
                Text(title)
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Text(count)
                    .font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.ink)
                    .monospacedDigit()
            }
            HStack(spacing: 4) {
                ForEach(0..<max(total, 1), id: \.self) { i in
                    Capsule()
                        .fill(i < done
                              ? AnyShapeStyle(LinearGradient(colors: [APlus.streakFrom, APlus.streakTo],
                                                             startPoint: .leading, endPoint: .trailing))
                              : AnyShapeStyle(APlus.trackSoft))
                        .frame(height: 8)
                }
            }
        }
        .padding(.horizontal, 4).padding(.top, 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title.isEmpty ? count : "\(title), \(count)")
        .accessibilityIdentifier("chat-deck-progress")
    }
}

/// A small muted note: 13 pt (G7: `small`), "Skip forgets the split.".
struct ChatNote: View {
    let text: String
    var top: CGFloat = 12

    var body: some View {
        Text(text)
            .font(Nacre.footnote).foregroundColor(Pearl.muted)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4).padding(.top, top)
    }
}

/// The error line: ⓘ and the words in `danger`, 15 pt (kit `errline`).
struct ChatErrorLine: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.circle").font(.system(size: 16))
                .padding(.top, 1)
                .accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Nacre.subheadline).foregroundColor(Pearl.danger)
        .padding(.horizontal, 4).padding(.top, 12)
        .accessibilityElement(children: .combine)
    }
}

/// The 36 pt round icon on `action-wash` (kit `ic`); 40 on blush for the starters.
struct ChatIcon: View {
    let symbol: String
    var size: CGFloat = 36
    var blush = false
    var danger = false

    var body: some View {
        Image(systemName: symbol).font(.system(size: 17, weight: .medium))
            .foregroundColor(danger ? Pearl.danger : Pearl.action)
            .frame(width: size, height: size)
            .background(Circle().fill(blush ? Pearl.bubble : (danger ? Pearl.danger : Pearl.action).opacity(0.1)))
            .accessibilityHidden(true)
    }
}

/// The nacre ring round a face: 44 pt, initials 15 (kit `ring sm`); 56 with 17.
struct ChatRing: View {
    let name: String
    var size: CGFloat = 44
    var trip = false

    var body: some View {
        Text(letters)
            .font(.custom("Figtree-Medium", size: size >= 56 ? 17 : 15))
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(APlus.face))
            .overlay(Circle().strokeBorder(APlus.nacreRing, lineWidth: 1.2))
            .accessibilityHidden(true)
    }

    /// "MO" for Montréal: a trip's face is always two letters.
    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }
        if trip, words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        return APFace.initials(name)
    }
}

/// The confirming card (kit `qcard`): radius 28, the overline in rose caps,
/// the ring, who, how much in Fraunces, when, the question in Fraunces,
/// then a line and whatever the card adds (PC-06's pill).
struct ChatQuestionCard<Extra: View>: View {
    let over: String
    let face: String
    var trip = false
    let name: String
    let amount: String
    var amountTone: Color = Pearl.ink
    let line: String
    let question: String
    var sub: String? = nil
    @ViewBuilder var extra: () -> Extra

    var body: some View {
        VStack(spacing: 0) {
            Text(over.uppercased())
                .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                .foregroundColor(Pearl.action)
                .multilineTextAlignment(.center)
            ChatRing(name: face, trip: trip).padding(.top, 12)
            Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.top, 8)
            Text(amount)
                .font(.custom("Fraunces-SemiBold", size: 32, relativeTo: .largeTitle))
                .foregroundColor(amountTone)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
            Text(question)
                .font(.custom("Fraunces-SemiBold", size: 22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(3).minimumScaleFactor(0.7)
                .padding(.top, 10)
            if let sub = sub {
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 6)
            }
            extra()
        }
        .padding(.horizontal, 18).padding(.vertical, 20)
        .frame(maxWidth: .infinity)
        .background(APCardSurface(radius: 28))
        .padding(.top, 14)
    }
}

/// G7-Chat's "working it out": three rose dots in a card-coloured pill,
/// the note under them. The dots take turns (still with Reduce Motion).
struct ChatWorking: View {
    @Environment(\.accessibilityReduceMotion) private var still

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            TimelineView(.periodic(from: .now, by: 0.35)) { context in
                let step = still ? 0 : Int(context.date.timeIntervalSinceReferenceDate / 0.35) % 3
                HStack(spacing: 5) {
                    ForEach(0..<3, id: \.self) { i in
                        Circle().fill(Pearl.action)
                            .opacity([1, 0.6, 0.3][(i - step + 3) % 3])
                            .frame(width: 7, height: 7)
                    }
                }
                .padding(.horizontal, 14).padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(APlus.card))
            }
            .padding(.horizontal, 4).padding(.top, 14)
            ChatNote(text: ChatWords.working)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(ChatWords.working)
    }
}

/// One starter on PC-03 (AP-Chat): the icon on blush, 17 semibold, a line
/// under it when it has one, the chevron. At least 60 high.
struct ChatStarterRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil

    var body: some View {
        HStack(spacing: 12) {
            ChatIcon(symbol: symbol, size: 40, blush: true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            ChatChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 60)
        .contentShape(Rectangle())
    }
}

/// The row chevron: 8 × 14, muted.
struct ChatChevron: View {
    var body: some View {
        Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
            .foregroundColor(Pearl.muted)
            .accessibilityHidden(true)
    }
}

/// A key and its value in a card (kit `kv`): "Dining, October   $286".
struct ChatKeyValue: View {
    let key: String
    let value: String
    var tone: Color = Pearl.muted
    var strong = false

    var body: some View {
        HStack {
            Text(key).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            Spacer(minLength: 8)
            Text(value).font(strong ? Nacre.headline : Nacre.body).foregroundColor(tone)
                .monospacedDigit().pearlAmountFit()
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 52)
        .accessibilityElement(children: .combine)
    }
}

/// A card with an icon, a title and a line (G7-Confirm's plan card).
struct ChatIconCard: View {
    let symbol: String
    let title: String
    var sub: String? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ChatIcon(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
        .apCard()
        .padding(.top, 12)
        .accessibilityElement(children: .combine)
    }
}

/// A quiet link, centred under a card: "See it in Your plan".
struct ChatQuietLink: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
            .foregroundColor(Pearl.link)
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity, minHeight: 44)
            .contentShape(Rectangle())
            .padding(.top, -2)
    }
}

extension View {
    /// The chat's page: 16 at the sides, room at the bottom.
    func chatPage() -> some View {
        frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16).padding(.bottom, 24)
    }
}
