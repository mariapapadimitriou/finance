import SwiftUI

// Pearl sorts for you, P1a (product owner, 2026-11-15; ios/bots/ai-plan.md;
// Figma Proposals 1313:3507, note 1316:5612). Python only: Pearl answers new
// rows the way she always has, says so, and each can be undone.
//
// AI-01  Home: "Pearl sorted 12 for you this week …" · See them
// AI-02  Needs a look › Pearl sorted (ReviewView): each row with its reason
// AI-03  Why Pearl sorted this (joint) · AI-03b (a category, 1321:5770)
// AI-04  Stop sorting like this? · AI-04f Forget this rule? (1322:6047)
// AI-05  Categories and rules: learned rules beside hers (CategoriesRulesView)
// AI-06  A learned rule (joint) · AI-06b (a category, 1322:5853)
// AI-07  Quick sort's caption when Pearl isn't sure (QuickSortView)
// AI-08  Privacy: "Pearl sorts for you" (PrivacyViews)

/// One row Pearl sorted, as AI-03 shows it.
struct PatternRecord: Decodable, Identifiable, Hashable {
    let id: String
    let txn: String
    let pattern: String
    let kind: String
    let line: String
    let answer: String
    let merchant: String
    let amount: Double
    let date: String
    let day: String
    var label: String? = nil
    var account: String? = nil
    var joint: String? = nil
    var patternCount: Int? = nil
    var patternMerchant: String? = nil
    var sortedByPattern: [String]? = nil
    var answered: [String]? = nil
    var learned: Bool? = nil

    enum CodingKeys: String, CodingKey {
        case id, txn, pattern, kind, line, answer, merchant, amount, date, day, label, account, joint, answered, learned
        case patternCount = "pattern_count"
        case patternMerchant = "pattern_merchant"
        case sortedByPattern = "sorted_by_pattern"
    }

    var isJoint: Bool { kind == "joint" }
    var firstName: String { answer.split(separator: " ").first.map(String.init) ?? answer }
}

/// A rule Pearl learned (AI-05, AI-06).
struct LearnedRule: Decodable, Identifiable, Hashable {
    let id: String
    let kind: String
    let merchant: String?
    let answer: String
    let label: String
    let count: Int
    var account: String? = nil
    var joint: String? = nil
    var rhythm: String? = nil
    let on: Bool
    let sorted: [String]
    var answered: [String]? = nil

    var isJoint: Bool { kind == "joint" }
    var name: String { merchant ?? answer }
    var firstName: String { answer.split(separator: " ").first.map(String.init) ?? answer }
    /// The rules list's line: "Ana's share of Joint · learned by Pearl", "Groceries · learned by Pearl".
    var words: String {
        (isJoint ? "\(label) of \(joint ?? account ?? "the joint account")" : label) + " · learned by Pearl"
    }
    /// AI-06's title: "Ana's deposits", "Farm Boy".
    var title: String { isJoint ? "\(possessive(firstName)) deposits" : name }
    /// How many answers it takes, for AI-04f: 8 for money from a person, else 5.
    var need: Int { isJoint ? 8 : 5 }
}

// MARK: - AI-01

/// "Pearl sorted 12 for you this week, the way you usually do. Undo any you like." · See them.
struct PearlSortedCard: View {
    let count: Int

    var body: some View {
        NavigationLink {
            ReviewView(startFilter: "pearl")
        } label: {
            PearlCard(spacing: 8) {
                HStack(alignment: .center, spacing: 12) {
                    Text("Pearl sorted \(count) for you this week, the way you usually do. Undo any you like.")
                        .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Text("See them").font(Nacre.textButton).foregroundColor(Pearl.link)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens Pearl sorted in Needs a look")
    }
}

// MARK: - AI-03 / AI-03b

/// Why Pearl sorted this: the reason, See the n, Change it…, then Undo this
/// one and Stop sorting like this (asks first, AI-04).
struct PatternWhySheet: View {
    @EnvironmentObject private var app: AppModel
    let recordID: String
    let onClose: () -> Void
    /// What happened, for the page's toast: "Undone · back in Needs a look".
    let onDone: (String) -> Void
    @State private var record: PatternRecord?
    @State private var stopping = false
    @State private var busy = false
    @State private var error: String?
    @State private var showing: [String]?
    @State private var opening: String?

    var body: some View {
        NavigationStack {
            PearlSheet {
                if let r = record {
                    content(r)
                } else if let error = error {
                    CautionBanner(text: error)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                }
            }
            .navigationDestination(isPresented: Binding(get: { showing != nil }, set: { if !$0 { showing = nil } })) {
                // AI-09 from AI-03: her own answers behind the pattern.
                PatternRowsView(title: "The \((showing ?? []).count) you sorted", ids: showing ?? [])
            }
            .navigationDestination(isPresented: Binding(get: { opening != nil }, set: { if !$0 { opening = nil } })) {
                if let id = opening { TransactionByID(id: id, categories: app.categories) }
            }
        }
        .task { await load() }
        .sheet(isPresented: $stopping) {
            if let r = record {
                StopPatternSheet(pattern: r.pattern, name: r.isJoint ? r.firstName : (r.patternMerchant ?? r.merchant),
                                 isJoint: r.isJoint, sorted: r.sortedByPattern?.count ?? 1,
                                 onClose: { stopping = false }) { title in
                    stopping = false
                    onDone(title)
                }
            }
        }
    }

    @ViewBuilder private func content(_ r: PatternRecord) -> some View {
        let n = r.patternCount ?? r.answered?.count ?? 0
        let sortedCount = r.sortedByPattern?.count ?? 1
        let amount = (r.amount < 0 ? "+" : "\u{2212}") + Format.amount(abs(r.amount))
        PearlSheetHeader(face: r.merchant, overline: "\(r.merchant) · \(amount)",
                         title: r.isJoint ? "\(r.label ?? r.answer) of \(r.joint ?? r.account ?? "Joint")" : (r.label ?? r.answer),
                         sub: "Pearl sorted this · \(Format.short(r.day))", subTone: Pearl.moneyIn, close: onClose)
        PearlSectionLabel(text: "Why")
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                PearlBubble(symbol: r.isJoint ? "person.2" : CategorySheet.symbol(for: r.answer), tone: r.isJoint ? Pearl.moneyIn : Pearl.action)
                VStack(alignment: .leading, spacing: 2) {
                    Text(r.isJoint ? "Like the last \(n) from \(r.firstName)" : "Like your last \(n) at \(r.patternMerchant ?? r.merchant)")
                        .font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    Text(r.isJoint ? "All into \(r.account ?? "the joint account"), all sorted as \(r.label ?? r.answer) by you"
                         : "All sorted as \(r.answer) by you")
                        .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            HStack(spacing: 8) {
                Button("See the \(n)") { showing = r.answered ?? [] }.buttonStyle(PearlPillButtonStyle())
                Button("Change it…") { opening = r.txn }.buttonStyle(PearlPillButtonStyle())
            }
        }
        .padding(16)
        .pearlCard(radius: Pearl.radiusTile)
        PearlSectionLabel(text: "Undo")
        PearlOptionCard {
            PearlOptionRow(symbol: r.isJoint ? "person.2" : "arrow.uturn.backward", title: "Undo this one") {
                Task { await undo(r) }
            }
            PearlDivider()
            PearlOptionRow(symbol: "person", title: "Stop sorting like this",
                           sub: "Asks first · undoes the \(sortedCount) and won’t learn it again") { stopping = true }
        }
        .disabled(busy)
        if let error = error { CautionBanner(text: error) }
    }

    private func load() async {
        do {
            record = try await app.api.get("api/pattern-sort/\(recordID)")
        } catch {
            self.error = app.handle(error)
        }
    }

    private func undo(_ r: PatternRecord) async {
        busy = true
        defer { busy = false }
        struct Reply: Decodable { let title: String? }
        do {
            let reply: Reply = try await app.api.post("api/pattern-sort/\(r.id)/undo", [:])
            app.changed()
            onDone(reply.title ?? "Undone · back in Needs a look")
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// AI-09 (`1325:6340` / `1325:6517`): See the n / See the n it sorted, a
/// plain list of those transactions, each opening its page, no totals card.
struct PatternRowsView: View {
    @EnvironmentObject private var app: AppModel
    /// "The 5 you sorted" from AI-03, "The 5 Pearl sorted" from AI-06.
    let title: String
    let ids: [String]
    @State private var rows: [Transaction] = []

    var body: some View {
        ScrollView {
            GlassCard {
                ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                    if i > 0 { RowSeparator(inset: 72) }
                    NavigationLink { TransactionByID(id: t.id, categories: app.categories) } label: {
                        TransactionRow(t: t)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.vertical, 16)
        }
        .nacreScreen()
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            var out: [Transaction] = []
            for id in ids {
                struct Detail: Decodable { let transaction: Transaction? }
                if let t: Transaction = try? await app.api.get("api/transactions/\(id)") { out.append(t) }
            }
            rows = out
        }
    }
}

// MARK: - AI-04 / AI-04f

/// Stop sorting Ana's deposits? Asks first, because it undoes them all.
struct StopPatternSheet: View {
    @EnvironmentObject private var app: AppModel
    let pattern: String
    let name: String
    let isJoint: Bool
    let sorted: Int
    let onClose: () -> Void
    let onDone: (String) -> Void

    var body: some View {
        PearlConfirmSheet(overline: "Learned by Pearl",
                          title: isJoint ? "Stop sorting \(possessive(name)) deposits?" : "Stop sorting \(name)?",
                          message: "The \(sorted) Pearl sorted this way go back to Needs a look, and Pearl won’t learn this again. New ones from \(name) go to Quick sort.",
                          primary: "Stop and undo \(sorted)", busyLabel: "Stopping…", secondary: "Keep it",
                          failure: "Couldn’t stop it. Nothing changed. Try again.", onClose: onClose) {
            struct Reply: Decodable { let title: String? }
            let reply: Reply = try await app.api.post("api/pattern-sort/rules/\(pattern)/stop", [:])
            app.changed()
            onDone(reply.title ?? "Stopped")
        }
    }
}

/// AI-04f: Forget Farm Boy? What Pearl sorted stays; it may learn it again.
struct ForgetRuleSheet: View {
    @EnvironmentObject private var app: AppModel
    let rule: LearnedRule
    let onClose: () -> Void
    let onDone: () -> Void

    var body: some View {
        let name = rule.isJoint ? rule.firstName : rule.name
        PearlConfirmSheet(overline: "Learned by Pearl", title: "Forget \(name)?",
                          message: "What Pearl already sorted stays. Pearl may learn it again once you’ve sorted \(name) the same way \(rule.need) more times.",
                          primary: "Forget", busyLabel: "Forgetting…", secondary: "Keep it",
                          failure: "Couldn’t forget it. Nothing changed. Try again.", onClose: onClose) {
            let _: OK = try await app.api.post("api/pattern-sort/rules/\(rule.id)/forget", [:])
            app.changed()
            onDone()
        }
    }
}

// MARK: - AI-06 / AI-06b

/// A learned rule: what Pearl does, the switch, what it sorted, Forget.
struct LearnedRuleView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let id: String
    @State private var rule: LearnedRule?
    @State private var busy = false
    @State private var forgetting = false
    @State private var error: String?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                if let rule = rule {
                    PageTitle(title: rule.title,
                              line: "Pearl learned this from \(rule.count) you sorted. Nothing new is shared.")
                    CardCaption("What Pearl does")
                    GlassCard(radius: cardRadius) {
                        PrivacyRow(symbol: "building.columns", title: "Sorts them as \(rule.label)",
                                   sub: rule.isJoint ? "Into \(rule.account ?? "the joint account")" : "Any card or account") { RowChevron() }
                        RowSeparator()
                        PrivacyRow(symbol: "chart.line.uptrend.xyaxis",
                                   title: rule.isJoint ? "e-Transfers from \(rule.name)" : "Purchases at \(rule.name)",
                                   sub: "Any amount" + (rule.rhythm.map { ", \($0)" } ?? "")) { RowChevron() }
                    }
                    CardCaption("Your choice")
                    GlassCard(radius: cardRadius) {
                        SwitchRow(symbol: "sparkle", title: "Pearl sorts these",
                                  sub: "Off: new ones go to Quick sort. What it sorted stays.",
                                  isOn: rule.on, disabled: busy) { on in Task { await set(on) } }
                    }
                    CardCaption("What it sorted")
                    GlassCard(radius: cardRadius) {
                        NavigationLink { PatternRowsView(title: "The \(rule.sorted.count) Pearl sorted", ids: rule.sorted) } label: {
                            PrivacyRow(title: "See the \(rule.sorted.count) it sorted") { RowChevron() }
                        }
                        .buttonStyle(.plain)
                        RowSeparator()
                        Button { forgetting = true } label: {
                            PrivacyRow(title: "Forget this rule") { RowChevron() }
                        }
                        .buttonStyle(.plain)
                    }
                } else if let error = error {
                    CautionBanner(text: error)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                }
                if rule != nil, let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
                }
            }
        }
        .task { await load() }
        .sheet(isPresented: $forgetting) {
            if let rule = rule {
                ForgetRuleSheet(rule: rule, onClose: { forgetting = false }) {
                    forgetting = false
                    dismiss()
                }
            }
        }
    }

    private func load() async {
        struct Reply: Decodable { let rule: LearnedRule }
        do {
            let reply: Reply = try await app.api.get("api/pattern-sort/rules/\(id)")
            rule = reply.rule
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func set(_ on: Bool) async {
        busy = true
        defer { busy = false }
        struct Reply: Decodable { let rule: LearnedRule }
        do {
            let reply: Reply = try await app.api.put("api/pattern-sort/rules/\(id)", ["on": on])
            rule = reply.rule
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}
