import SwiftUI

// Profile › Income and bills › Your plan (THL-127, THL-45, THL-198, THL-117;
// Pearl iOS Handoff File, Proposals › "Your plan" 1353:10205, note 1353:11493):
//
// YP-01  1353:10206 / 1353:10356  proposed: each category's plan against her
//                                 usual, what it means, Use this plan
// YP-02  1353:10585 / 1353:10642  Use this plan? (asks first)
// YP-03  1353:10687 / 1353:10844  in use, with the toast after Use this plan;
//                                 Stop using this plan
// YP-04  1353:11034 / 1353:11103  change one category: Each month, Save, or
//                                 Remove from plan
// YP-05  1353:11157 / 1353:11213  Remove {category} from your plan?
// YP-06  1353:11257 / 1353:11337  empty: Suggest a plan
// YP-07  1356:9351 / 1356:9411    Stop using this plan? (asks first), and the
//                                 toast after it, with Undo
// YP-08  1356:9456 / 1356:9661    Add a category: NOT IN YOUR PLAN, Next, then
//                                 YP-04 with her usual filled in and "Add"
//
// The tick on a plan row was decoration and is gone (YP-01, YP-03); Remove
// lives in YP-04.
//
// Less text (LT-05 · YP-01 1425:72756 / 1425:72885; TEXT-01, approved
// 2026-11-16): "From your last 3 months.", EACH MONTH, YOUR ALLOWANCE "$1,180
// a month · plan total $1,160", rows "Usual $214"; YP-02, YP-04, YP-05 and
// YP-07 say the money in a line; YP-08 has no "Next: …" footnote.
//
// A plan only proposes: the Allowance follows it only after Use this plan and
// YP-02 (finance/your_plan.py). Every write returns the whole page again, so
// nothing here adds anything up. PC-13's "See it in Your plan" opens this
// page, which is YP-03 while the plan is in use and YP-01 otherwise.

/// GET /api/your-plan.
struct YourPlan: Decodable {
    struct Row: Decodable, Identifiable, Hashable {
        let category: String
        let amount: Double
        /// "pearl" (the suggestion), "chat" (set in Pearl chat) or "you".
        let source: String
        let usual: Double
        var id: String { category }
    }

    let rows: [Row]
    let inUse: Bool
    let since: String?
    let total: Double
    /// The Allowance a month this plan leaves with her income and bills;
    /// nil until she has an income.
    let allowance: Double?
    /// YP-07: the Allowance a month without the plan; nil until she has an
    /// income.
    var allowanceWithout: Double? = nil

    enum CodingKeys: String, CodingKey {
        case rows, since, total, allowance
        case inUse = "in_use"
        case allowanceWithout = "allowance_without"
    }
}

/// GET /api/your-plan/categories: YP-08's NOT IN YOUR PLAN.
struct PlanCategories: Decodable {
    struct Category: Decodable, Identifiable, Hashable {
        let category: String
        let usual: Double
        /// What YP-04 starts at: her usual to the nearest $5.
        let amount: Double
        var id: String { category }
    }

    let categories: [Category]
}

@MainActor
struct YourPlanView: View {
    @EnvironmentObject private var app: AppModel
    @State private var plan: YourPlan?
    @State private var sheet: Sheet?
    /// YP-03: "Plan in use · Allowance $1,180 a month" · Undo; YP-07: "Plan
    /// stopped · Allowance $1,240 a month" · Undo. Each Undo calls its own path.
    @State private var toast: (text: String, undo: String)?
    @State private var busy = false
    @State private var error: String?

    enum Sheet: Identifiable {
        case use, stop, add, edit(YourPlan.Row), adding(YourPlan.Row), remove(YourPlan.Row)

        var id: String {
            switch self {
            case .use: return "use"
            case .stop: return "stop"
            case .add: return "add"
            case .edit(let r): return "edit:" + r.id
            case .adding(let r): return "adding:" + r.id
            case .remove(let r): return "remove:" + r.id
            }
        }
    }

    var body: some View {
        ProfilePage {
            if let plan = plan {
                if plan.rows.isEmpty { empty } else { content(plan) }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            if let plan = plan, !plan.rows.isEmpty {
                if plan.inUse {
                    // YP-03; asks first (YP-07).
                    Button("Stop using this plan") { sheet = .stop }
                        .buttonStyle(SecondaryButtonStyle())
                        .disabled(busy)
                } else {
                    Button("Use this plan") { sheet = .use }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                        .disabled(busy)
                }
            }
        }
        .overlay(alignment: .bottom) {
            // UN-01: the toast sits at the bottom.
            if let toast = toast {
                UndoToast(text: toast.text, undo: { Task { await undo(toast.undo) } }) {
                    withAnimation { self.toast = nil }
                }
                .padding(.bottom, 12)
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .sheet(item: $sheet) { which in sheetView(which) }
    }

    // MARK: YP-01, YP-03

    @ViewBuilder
    private func content(_ plan: YourPlan) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your plan").font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            Text(lead(plan)).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            CardCaption("Each month")
            GlassCard {
                ForEach(Array(plan.rows.enumerated()), id: \.element.id) { i, row in
                    if i > 0 { RowSeparator(inset: 16) }
                    PlanLine(row: row) { sheet = .edit(row) }
                }
                RowSeparator(inset: 16)
                // YP-01, YP-03: "⊕ Add a category" opens YP-08.
                AddLine(title: "Add a category") { sheet = .add }
            }
            if plan.allowance != nil { CardCaption("Your Allowance") }
            Text(meaning(plan)).font(Nacre.footnote).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
    }

    /// YP-01's proposal, or YP-03's "In use since Nov 15".
    private func lead(_ plan: YourPlan) -> String {
        if plan.inUse {
            let since = plan.since.map { " since \(Format.short($0))" } ?? ""
            return "In use\(since). Your Allowance follows it."
        }
        return "From your last 3 months."
    }

    /// YOUR ALLOWANCE: "$1,180 a month · plan total $1,160" (LT-05). With no
    /// income there's no Allowance to name: "Plan total $1,160", no caption.
    private func meaning(_ plan: YourPlan) -> String {
        guard let allowance = plan.allowance else { return "Plan total \(Format.whole(plan.total))" }
        return "\(allowance < 0 ? "-" : "")\(Format.whole(allowance)) a month \u{00B7} plan total \(Format.whole(plan.total))"
    }

    // MARK: YP-06

    private var empty: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your plan").font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            EmptyStateBlock(title: "No plan yet",
                            line: "Pearl can suggest one from your last 3 months, or ask in Pearl chat for one category.",
                            action: "Suggest a plan") { Task { await suggest() } }
                .disabled(busy)
        }
    }

    // MARK: YP-02, YP-04, YP-05

    @ViewBuilder
    private func sheetView(_ which: Sheet) -> some View {
        switch which {
        case .use:
            let n = plan?.rows.count ?? 0
            PearlConfirmSheet(overline: "Your plan \u{00B7} \(n) \(n == 1 ? "category" : "categories")",
                              title: "Use this plan?", message: useMessage,
                              primary: "Use this plan", secondary: "Not now",
                              onClose: { sheet = nil }) {
                let reply: YourPlan = try await app.api.post("api/your-plan/use")
                sheet = nil
                saved(reply)
                withAnimation {
                    toast = ("Plan in use" + allowanceWords(reply.allowance), "api/your-plan/undo")
                }
            }
        case .stop:
            // YP-07.
            PearlConfirmSheet(overline: "Your plan", title: "Stop using this plan?", message: stopMessage,
                              primary: "Stop using it", secondary: "Keep using it",
                              onClose: { sheet = nil }) {
                let reply: YourPlan = try await app.api.post("api/your-plan/stop")
                sheet = nil
                saved(reply)
                withAnimation {
                    toast = ("Plan stopped" + allowanceWords(reply.allowanceWithout), "api/your-plan/resume")
                }
            }
        case .add:
            AddCategorySheet(close: { sheet = nil }) { picked in
                sheet = .adding(YourPlan.Row(category: picked.category, amount: picked.amount,
                                             source: "you", usual: picked.usual))
            }
        case .edit(let row):
            PlanAmountSheet(row: row, close: { sheet = nil }, remove: { sheet = .remove(row) }) { amount in
                let reply: YourPlan = try await app.api.put("api/your-plan/rows/\(row.category)", ["amount": amount])
                sheet = nil
                saved(reply)
            }
        case .adding(let row):
            // YP-08's Next: YP-04 with her usual filled in, and "Add".
            PlanAmountSheet(row: row, adding: true, close: { sheet = nil }, remove: {}) { amount in
                let reply: YourPlan = try await app.api.put("api/your-plan/rows/\(row.category)", ["amount": amount])
                sheet = nil
                saved(reply)
            }
        case .remove(let row):
            PearlConfirmSheet(overline: "Your plan", title: "Remove \(row.category) from your plan?",
                              message: "Back to your usual, \(Format.whole(row.usual)).",
                              primary: "Remove", secondary: "Keep it",
                              onClose: { sheet = nil }) {
                let reply: YourPlan = try await app.api.delete("api/your-plan/rows/\(row.category)")
                sheet = nil
                saved(reply)
            }
        }
    }

    /// " · Allowance $1,180 a month" on a toast, once she has an income.
    private func allowanceWords(_ allowance: Double?) -> String {
        allowance.map { " \u{00B7} Allowance \($0 < 0 ? "-" : "")\(Format.whole($0)) a month" } ?? ""
    }

    /// YP-07's body: "Allowance back to $1,240 a month." (TEXT-01). Without
    /// an income there's no Allowance to name, so it says how to get one.
    private var stopMessage: String? {
        guard let without = plan?.allowanceWithout else { return Self.noIncome }
        return "Allowance back to \(without < 0 ? "-" : "")\(Format.whole(without)) a month."
    }

    /// YP-02's body: "Allowance $1,180 a month, from today." (TEXT-01).
    /// Without an income there's no Allowance to name, so it says how to get one.
    private var useMessage: String? {
        guard let allowance = plan?.allowance else { return Self.noIncome }
        return "Allowance \(allowance < 0 ? "-" : "")\(Format.whole(allowance)) a month, from today."
    }

    /// YP-02 and YP-07 with no income: the one body line (designBOT, less text 2).
    private static let noIncome = "Add your income to see your Allowance."

    // MARK: Loading and saving

    private func load() async {
        do {
            plan = try await app.api.get("api/your-plan")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func saved(_ reply: YourPlan) {
        plan = reply
        error = nil
        app.changed()
    }

    private func run(_ path: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: YourPlan = try await app.api.post(path)
            saved(reply)
        } catch {
            self.error = app.handle(error)
        }
    }

    /// YP-06's Suggest a plan.
    private func suggest() async { await run("api/your-plan/suggest") }

    /// Undo on a toast: YP-03's goes back to before Use this plan
    /// (api/your-plan/undo); YP-07's uses it again, since the same day
    /// (api/your-plan/resume).
    private func undo(_ path: String) async {
        withAnimation { toast = nil }
        await run(path)
    }
}

/// YP-01's Plan row: "Groceries · Usual $412   $400  Edit", wherever the
/// plan was set (TEXT-01 cut "· set in Pearl chat"). The row opens YP-04. No
/// tick: it was decoration (note 1353:11493).
private struct PlanLine: View {
    let row: YourPlan.Row
    let edit: () -> Void

    var body: some View {
        Button(action: edit) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.category).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Text(Format.whole(row.amount)).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .pearlAmountFit()
                Text("Edit").font(Nacre.subheadline).foregroundColor(Pearl.action)
            }
            .padding(.horizontal, 16).padding(.vertical, 11)
            .frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(row.category), \(Format.whole(row.amount)) a month. \(sub)")
        .accessibilityHint("Change it")
        .accessibilityAddTraits(.isButton)
    }

    private var sub: String {
        "Usual \(Format.whole(row.usual))"
    }
}

/// YP-04: one category's amount a month. Save keeps it to the nearest $5
/// (the server rounds); Remove from plan asks first (YP-05). From YP-08 it
/// starts at her usual and its button reads "Add"; there's nothing to remove.
private struct PlanAmountSheet: View {
    let row: YourPlan.Row
    var adding = false
    let close: () -> Void
    let remove: () -> Void
    let save: (Double) async throws -> Void

    @State private var text = ""
    @State private var busy = false
    @State private var failed: String?
    @FocusState private var typing: Bool

    private var amount: Double? {
        let cleaned = text.replacingOccurrences(of: ",", with: "").replacingOccurrences(of: "$", with: "")
            .trimmingCharacters(in: .whitespaces)
        guard let value = Double(cleaned), value > 0 else { return nil }
        return value
    }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(overline: "Your plan", title: row.category, close: close)
                .disabled(busy)
            Text("Usual \(Format.whole(row.usual))")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 6) {
                Text("Each month").font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                HStack(spacing: 2) {
                    Text("$").font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                        .accessibilityHidden(true)
                    TextField("", text: $text)
                        .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                        .keyboardType(.decimalPad)
                        .focused($typing)
                        .accessibilityLabel("Each month, in dollars")
                        .accessibilityIdentifier("plan-amount")
                        .disabled(busy)
                }
                .padding(.horizontal, 16).frame(minHeight: 52)
                .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.card))
                .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
                    .strokeBorder(typing ? Pearl.action : Pearl.border, lineWidth: typing ? 2 : 1))
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : (adding ? "Add" : "Save"), busy: busy,
                              secondary: adding ? nil : "Remove from plan",
                              onPrimary: { Task { await go() } }, onSecondary: remove)
        }
        .onAppear {
            // A category with no spending starts empty (usual $0).
            text = row.amount > 0 ? String(Int(row.amount.rounded())) : ""
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { typing = true }
        }
    }

    private func go() async {
        guard let amount = amount, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            try await save(amount)
            failed = nil
        } catch APIError.server(let problem) where problem.error != nil {
            // The server's own words ("Plans start at $5 a month.").
            failed = problem.error
        } catch {
            failed = "Something went wrong. Nothing changed. Try again."
        }
    }
}

/// YP-08: Add a category. "NOT IN YOUR PLAN", one row a category, "{Category}
/// · usual {$x}" (those with no spending last, at $0), one picked at a time
/// with Pearl's tick, then Next. Empty when every category is already in
/// the plan (PLAN-03, note 1353:11493): "Everything’s in your plan" · Done.
@MainActor
private struct AddCategorySheet: View {
    @EnvironmentObject private var app: AppModel
    let close: () -> Void
    let next: (PlanCategories.Category) -> Void

    @State private var categories: [PlanCategories.Category]?
    @State private var picked: PlanCategories.Category?
    @State private var failed: String?

    var body: some View {
        PearlSheet {
            // The centred title, then Your plan's row (1356:9490, 1356:9494).
            HStack {
                Spacer()
                Text("Add a category").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .frame(minHeight: 44)
            .overlay(alignment: .trailing) { PearlCloseButton(action: close) }
            HStack(spacing: 12) {
                PearlFace(name: "Your plan", size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Your plan").font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    Text("Categories not in your plan yet").font(Pearl.text(.subheadline))
                        .foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
            if let categories = categories {
                if !categories.isEmpty {
                    PearlSectionLabel(text: "Not in your plan")
                    PearlOptionCard {
                        ForEach(Array(categories.enumerated()), id: \.element.id) { i, c in
                            if i > 0 { PearlDivider() }
                            CategoryChoice(category: c, on: picked == c) { picked = c }
                        }
                    }
                } else {
                    EmptyStateBlock(title: "Everything\u{2019}s in your plan",
                                    line: "Change any category from Your plan.", action: nil) {}
                }
            } else if failed == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 120)
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            if categories?.isEmpty == true {
                // YP-08 empty: nothing to add, so Done closes the sheet.
                PearlSheetButtons(primary: "Done", onPrimary: close)
            } else {
                PearlSheetButtons(primary: "Next", onPrimary: { if let p = picked { next(p) } })
                    .disabled(picked == nil)
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            let reply: PlanCategories = try await app.api.get("api/your-plan/categories")
            categories = reply.categories
            failed = nil
        } catch {
            failed = app.handle(error)
        }
    }
}

/// YP-08's row: "Health · usual $84", with Pearl's tick when picked.
private struct CategoryChoice: View {
    let category: PlanCategories.Category
    let on: Bool
    let pick: () -> Void

    var body: some View {
        Button(action: pick) {
            HStack(spacing: 12) {
                Text("\(category.category) \u{00B7} usual \(Format.whole(category.usual))")
                    .font(Pearl.text(.body)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Pearl.action)
                    .opacity(on ? 1 : 0)
                    .accessibilityHidden(true)
            }
            .frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isSelected] : [])
    }
}
