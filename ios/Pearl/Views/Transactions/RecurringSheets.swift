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

// MARK: - Also 8 older ones? (OT-01)

/// What `GET /transactions/<id>/older` answers: the older payments of a bank
/// transfer she just sorted as spending, that Pearl had left as transfers
/// only for their age (REFRESH-17, 2026-11-25).
struct OlderOnes: Decodable, Identifiable {
    let id: String
    let category: String
    let account: String
    /// Her percent on a joint account that splits; nil anywhere else.
    let share: Double?
    let older: [Row]
    /// What to call it, from the screen that asked.
    var name = ""

    struct Row: Decodable, Identifiable, Hashable {
        let id: String
        let date: String
        let amount: Double
        /// Her part of it.
        let mine: Double
    }

    private enum CodingKeys: String, CodingKey { case id, category, account, share, older }

    /// The older ones to ask about, after an answer saved; nil when there are
    /// none or the answer isn't one to follow up (offline too: nothing to count).
    @MainActor
    static func after(_ answer: ReviewAnswer, id: String, name: String, api: APIClient) async -> OlderOnes? {
        guard answer.sortsSpendingAlone else { return nil }
        return await after(id: id, name: name, api: api)
    }

    @MainActor
    static func after(id: String, name: String, api: APIClient) async -> OlderOnes? {
        guard var found: OlderOnes = try? await api.get("api/transactions/\(id)/older"),
              !found.older.isEmpty else { return nil }
        found.name = name
        return found
    }
}

extension ReviewAnswer {
    /// The transaction a mark or a category is for.
    var rowID: String? {
        switch self {
        case .mark(let id, _), .category(let id, _, _): return id
        default: return nil
        }
    }

    /// Spending, for this one: the only answer OT-01 follows. With Always on
    /// the rule has moved the older ones already.
    var sortsSpendingAlone: Bool {
        switch self {
        case .mark(_, let body):
            return body["case"] as? String == "spending" && body["remember"] as? Bool != true
        case .category(_, _, let remember):
            return !remember
        default:
            return false
        }
    }
}

/// OT-01 (G1-OlderToo, G1-OlderMore): asked once her answer is saved, from
/// Needs a look, Quick sort and the page alike. Yes sorts them the same way,
/// with no rule; Leave them in Transfers is a no for good; ✕ and a swipe
/// change nothing and it asks again next time.
@MainActor
struct OlderOnesSheet: View {
    let ask: OlderOnes
    let api: APIClient
    let onSorted: (MarkReply) -> Void
    let onClose: () -> Void

    @State private var all = false
    @State private var busy = false
    @State private var failed = false

    /// Up to 8 are all listed; more show the newest 5 (OT-01b).
    private static let most = 8
    private static let first = 5

    private var count: Int { ask.older.count }
    private var rows: [OlderOnes.Row] {
        all || count <= Self.most ? ask.older : Array(ask.older.prefix(Self.first))
    }

    var body: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: ask.category, close: onClose).sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    Text(count == 1 ? "Also the older one?" : "Also \(count) older ones?")
                        .font(Nacre.title2).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 4)
                        .accessibilityAddTraits(.isHeader)
                    list
                }
                .padding(.horizontal, 16).padding(.bottom, 8)
                .sheetPart()
            }
            VStack(spacing: 0) {
                if failed {
                    Label("That didn’t save. Try again.", systemImage: "exclamationmark.circle")
                        .font(Nacre.subheadline).foregroundColor(Pearl.danger)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 20).padding(.top, 6)
                }
                PearlSheetButtons(primary: yes, busy: busy,
                                  secondary: count == 1 ? "Leave it in Transfers" : "Leave them in Transfers",
                                  onPrimary: { Task { await sort() } }, onSecondary: { Task { await leave() } })
            }
            .sheetPart()
        }
        .cfSheet()
        .fitsContent()
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(busy)
    }

    private var yes: String {
        switch count {
        case 1: return "Yes, this one too"
        case 2: return "Yes, both"
        default: return "Yes, all \(count)"
        }
    }

    /// "Maple Court" over "Joint ••1123 · your half".
    private var header: some View {
        HStack(spacing: 12) {
            CFRing(name: ask.name, size: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(ask.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(ask.share.map { "\(ask.account) · \(Self.part($0))" } ?? ask.account)
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }

    static func part(_ share: Double) -> String {
        abs(share - 50) < 0.005 ? "your half" : "your \(Int(share.rounded()))%"
    }

    private var list: some View {
        APCard {
            VStack(spacing: 0) {
                ForEach(rows) { r in
                    if r.id != rows.first?.id { APSeparator(afterFace: false) }
                    row(r)
                }
                if rows.count < count {
                    APSeparator(afterFace: false)
                    Button { withAnimation(.easeInOut(duration: 0.25)) { all = true } } label: {
                        HStack {
                            Text("Show all \(count)").font(Nacre.subheadline).foregroundColor(Pearl.link)
                            Spacer(minLength: 8)
                            Image(systemName: "chevron.down").font(.system(size: 14, weight: .semibold))
                                .foregroundColor(Pearl.muted).accessibilityHidden(true)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 44).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("older-show-all")
                }
            }
        }
    }

    /// "Sep 10 · of $64.18 · −$32.09": "of" only where part of it is hers.
    private func row(_ r: OlderOnes.Row) -> some View {
        HStack(spacing: 10) {
            Text(Self.day(r.date)).foregroundColor(Pearl.ink)
            Spacer(minLength: 8)
            if ask.share != nil {
                Text("of \(Format.amount(r.amount))").font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            Text("\u{2212}" + Format.amount(r.mine)).fontWeight(.semibold).foregroundColor(Pearl.moneyOut)
                .frame(minWidth: 64, alignment: .trailing)
        }
        .font(Nacre.subheadline).monospacedDigit()
        .padding(.horizontal, 16).padding(.vertical, 4).frame(minHeight: 40)
        .accessibilityElement(children: .combine)
    }

    /// "Sep 10"; the year only when it isn't this one.
    static func day(_ iso: String) -> String {
        let year = Calendar.current.component(.year, from: Date())
        return iso.hasPrefix("\(year)-") ? Format.short(iso) : "\(Format.short(iso)), \(iso.prefix(4))"
    }

    private func sort() async {
        busy = true
        failed = false
        defer { busy = false }
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(ask.id)/older",
                                                      ["ids": ask.older.map(\.id)])
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            onSorted(reply)
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            withAnimation { failed = true }
        }
    }

    private func leave() async {
        busy = true
        failed = false
        defer { busy = false }
        do {
            let _: OK = try await api.post("api/transactions/\(ask.id)/older/no")
            onClose()
        } catch {
            withAnimation { failed = true }
        }
    }
}
