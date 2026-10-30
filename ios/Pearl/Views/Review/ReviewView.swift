import SwiftUI

/// What an answer does on the server.
enum ReviewAnswer {
    /// Pearl's guess is right.
    case confirm(String)
    /// A different category, and maybe every one like it.
    case category(String, name: String, remember: Bool)
    /// "What was this?" answered: `case` and its details (finance/marks.py).
    case mark(String, body: [String: Any])
    /// The kind of income, for money already counted as income.
    case incomeType(String, kind: String)
    /// Skip for now.
    case skip(String)
}

/// Needs a look, one at a time: answer it, see what changed, Undo if it
/// wasn't right, and the next one is already up.
@MainActor
struct ReviewView: View {
    @EnvironmentObject private var app: AppModel

    @State private var review: Review?
    @State private var categories: [CategoryList.Category] = []
    @State private var last: (title: String, undo: JSONValue?)?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let review = review {
                    PageHeader(title: headline(review), sub: countWords(review))
                    if let last = last {
                        Sorted(text: last.title, onUndo: last.undo == nil ? nil : { Task { await undo() } })
                    }
                    if let error = error { Notice(text: error, tone: .caution) }
                    if let entry = review.entries.first {
                        ReviewCard(entry: entry, kinds: review.kinds ?? [:], categories: categories,
                                   busy: busy) { answer in Task { await send(answer) } }
                            .id(entry.id)
                    } else if review.webOnly > 0 {
                        PearlCard(spacing: 8) {
                            Text("The rest are on the web").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
                            Text(review.webOnly == 1 ? "1 more question can only be answered in Pearl on the web for now."
                                 : "\(review.webOnly) more questions can only be answered in Pearl on the web for now.")
                                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                            Link(destination: app.api.baseURL) { LinkLabel(text: "Open Pearl on the web") }
                                .padding(.top, 4)
                        }
                    } else {
                        AllSorted()
                    }
                } else {
                    LoadState(error: error) { Task { await load() } }
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 24)
        }
        .pearlPage()
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task { await load() }
    }

    /// "1 transaction needs a look".
    private func headline(_ review: Review) -> String {
        let n = review.entries.count + review.webOnly
        if n == 0 { return "Needs a look" }
        return n == 1 ? "1 transaction needs a look" : "\(n) transactions need a look"
    }

    private func countWords(_ review: Review) -> String {
        let n = review.entries.count + review.webOnly
        let skipped = review.count - (review.open ?? review.count)
        let left = n == 0 ? "Nothing left to review" : n == 1 ? "1 left to review" : "\(n) left to review"
        return skipped > 0 ? "\(left) · \(skipped) skipped" : left
    }

    private func load() async {
        do {
            review = try await app.api.get("api/review")
            if categories.isEmpty, let list: CategoryList = try? await app.api.get("api/categories") {
                categories = list.categories.filter { $0.hidden != true }
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func send(_ answer: ReviewAnswer) async {
        busy = true
        defer { busy = false }
        do {
            switch answer {
            case .confirm(let id):
                let reply: MarkReply = try await app.api.put("api/transactions/\(id)/confirm")
                last = ("Sorted. Pearl will remember it was right.", reply.undo)
            case .category(let id, let name, let remember):
                let reply: MarkReply = try await app.api.patch("api/transactions/\(id)",
                                                               ["category": name, "apply_to_merchant": remember])
                last = (remember ? "\(name), and every one like it from now on." : "Moved to \(name).", reply.undo)
            case .mark(let id, let body):
                let reply: MarkReply = try await app.api.post("api/transactions/\(id)/mark", body)
                last = (reply.title ?? "Sorted.", reply.undo)
            case .incomeType(let id, let kind):
                let reply: MarkReply = try await app.api.put("api/transactions/\(id)/income-type", ["kind": kind])
                last = ("Sorted as \(kindName(kind)).", reply.undo)
            case .skip(let key):
                let _: OK = try await app.api.post("api/review/skip", ["key": key, "skip": true])
                last = ("Moved to Skipped. It's still in Needs a look on the web.", nil)
            }
            error = nil
            await load()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func undo() async {
        guard let payload = last?.undo, let body = payload.any as? [String: Any] else { return }
        do {
            let _: OK = try await app.api.post("api/transactions/undo", body)
            last = ("Undone.", nil)
            await load()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func kindName(_ kind: String) -> String {
        (review?.kinds?[kind] ?? kind).lowercased()
    }
}

struct AllSorted: View {
    var body: some View {
        PearlCard(spacing: 8) {
            Image(systemName: "checkmark.circle.fill").font(.largeTitle).foregroundColor(Pearl.action)
            Text("All sorted").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
            Text("Your numbers are up to date. We'll let you know when something new needs a look.")
                .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
        }
    }
}

/// "✓ Sorted as Groceries." with Undo, after an answer.
struct Sorted: View {
    let text: String
    let onUndo: (() -> Void)?

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Label {
                Text(text).fixedSize(horizontal: false, vertical: true)
            } icon: {
                Image(systemName: "checkmark").font(.system(size: 12, weight: .bold))
            }
            .font(Pearl.text(.subheadline, .medium))
            .foregroundColor(Pearl.action)
            Spacer(minLength: 8)
            if let onUndo = onUndo {
                Button(action: onUndo) {
                    Label("Undo", systemImage: "arrow.uturn.backward")
                        .font(Pearl.text(.callout, .semibold))
                        .foregroundColor(Pearl.ink)
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(Pearl.card)
                        .clipShape(Capsule())
                        .overlay(Capsule().stroke(Pearl.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// One question and its answers.
struct ReviewCard: View {
    let entry: ReviewEntry
    let kinds: [String: String]
    let categories: [CategoryList.Category]
    let busy: Bool
    let answer: (ReviewAnswer) -> Void

    private enum Step { case first, kind, other }
    @State private var step: Step = .first
    @State private var picking = false

    private var t: BriefTransaction { entry.item.txn }

    var body: some View {
        PearlCard(padding: 16, spacing: 16, radius: Pearl.radiusSort) {
            TransactionHeader(name: t.name, date: t.date, account: t.accountName,
                              amount: abs(t.amount), inflow: t.inflow)
            if let reason = entry.item.reason, !reason.isEmpty {
                Text(reason).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
            }
            Text(title).font(Pearl.title).tracking(-0.24).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            VStack(spacing: 12) { choices }
                .disabled(busy)
            HStack {
                if step != .first {
                    Button { step = .first } label: {
                        Label("Back", systemImage: "arrow.left")
                    }
                }
                Spacer()
                Button("Skip for now") { answer(.skip(entry.item.key)) }
                    .disabled(busy)
            }
            .font(Pearl.text(.subheadline, .medium))
            .foregroundColor(Pearl.action)
        }
        .sheet(isPresented: $picking) {
            CategoryPicker(categories: categories, current: entry.item.guess?.text ?? t.category ?? "",
                           merchant: t.name) { name, remember in
                picking = false
                if entry.kind == .transfer {
                    mark("spending", ["category": name, "remember": remember])
                } else {
                    answer(.category(t.id, name: name, remember: remember))
                }
            }
        }
    }

    private var title: String {
        switch step {
        case .kind: return "What kind of income?"
        case .other: return "What was it?"
        case .first: return entry.question
        }
    }

    @ViewBuilder private var choices: some View {
        switch (entry.kind, step) {
        case (.category, _):
            if let guess = entry.item.guess?.text {
                ChoiceRow(label: "Yes, it's \(guess)") { answer(.confirm(t.id)) }
            }
            ChoiceRow(label: "Something else", detail: "Pick the category") { picking = true }
        case (.moneyIn, .first):
            ChoiceRow(label: "Yes, it's income") { step = .kind }
            ChoiceRow(label: "No, I moved my own money") { mark("own", ["remember": false]) }
            ChoiceRow(label: "No, it's a cash deposit") { mark("cash") }
            ChoiceRow(label: "No, something else") { step = .other }
        case (.moneyIn, .other):
            ChoiceRow(label: "Taken out of my savings") { mark("out_of_savings") }
            ChoiceRow(label: "Money I borrowed") { mark("borrowed") }
            ChoiceRow(label: "Paying back money I lent") { mark("lent_back") }
            ChoiceRow(label: "Not mine", detail: "Left out of all your numbers") { mark("not_mine", ["reason": ""]) }
            Notice(text: "Someone paying you back, a refund or a reimbursement: sort those in Pearl on the web for now, where you pick what it was for.")
        case (.moneyIn, .kind), (.incomeType, _):
            ChoiceRow(label: "My regular pay",
                      detail: "Every deposit from \(t.name) counts as your pay") {
                mark("regular_pay", ["remember": true])
            }
            ForEach(kindOrder, id: \.self) { kind in
                ChoiceRow(label: kinds[kind] ?? kind.capitalized,
                          selected: entry.kind == .incomeType && entry.item.guess?.text == kind) {
                    if entry.kind == .incomeType {
                        answer(.incomeType(t.id, kind: kind))
                    } else {
                        mark("pay", ["income_kind": kind])
                    }
                }
            }
        case (.transfer, _):
            ChoiceRow(label: "Moved between my accounts", detail: "Not spending or income") {
                mark("moved", ["remember": false])
            }
            ChoiceRow(label: "Put into savings", detail: "Adds to your total saved") {
                mark("saved", ["remember": false])
            }
            ChoiceRow(label: "A purchase", detail: "Pick the category") { picking = true }
            ChoiceRow(label: "Lent to someone", detail: "Pearl watches for it coming back") { mark("lent") }
        case (.other, _):
            Notice(text: "Pearl can't answer this kind of question on iPhone yet. Answer it in Pearl on the web, or skip it for now.")
        default:
            EmptyView()
        }
    }

    private var kindOrder: [String] {
        let order = ["salary", "bonus", "interest", "gifts", "government", "tax_refund", "other"]
        let known = order.filter { kinds[$0] != nil }
        return known.isEmpty ? order : known
    }

    private func mark(_ key: String, _ extra: [String: Any] = [:]) {
        var body = extra
        body["case"] = key
        answer(.mark(t.id, body: body))
    }
}
