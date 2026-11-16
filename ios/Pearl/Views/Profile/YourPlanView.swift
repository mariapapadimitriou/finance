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

    enum CodingKeys: String, CodingKey {
        case rows, since, total, allowance
        case inUse = "in_use"
    }
}

@MainActor
struct YourPlanView: View {
    @EnvironmentObject private var app: AppModel
    @State private var plan: YourPlan?
    @State private var sheet: Sheet?
    /// YP-03: "Plan in use · Allowance $1,180 a month" · Undo.
    @State private var toast: String?
    @State private var busy = false
    @State private var error: String?

    enum Sheet: Identifiable {
        case use, edit(YourPlan.Row), remove(YourPlan.Row)

        var id: String {
            switch self {
            case .use: return "use"
            case .edit(let r): return "edit:" + r.id
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
                    // YP-03. The note asks first, "like YP-05", but has no
                    // words for it yet: it stops at once (engBOT, 2026-11-15).
                    Button("Stop using this plan") { Task { await stop() } }
                        .buttonStyle(SecondaryButtonStyle())
                        .disabled(busy)
                } else {
                    Button("Use this plan") { sheet = .use }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                        .disabled(busy)
                }
            }
        }
        .overlay(alignment: .top) {
            if let toast = toast {
                UndoToast(text: toast, undo: { Task { await undo() } }) { withAnimation { self.toast = nil } }
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
            CardCaption("Each month · Plan · Your usual")
            GlassCard {
                ForEach(Array(plan.rows.enumerated()), id: \.element.id) { i, row in
                    if i > 0 { RowSeparator(inset: 50) }
                    PlanLine(row: row) { sheet = .edit(row) }
                }
            }
            CardCaption("What it means")
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
        return "Pearl\u{2019}s suggestion from your last 3 months. Nothing changes until you use it."
    }

    /// WHAT IT MEANS: "Total $1,160 a month. With your income and bills, that
    /// leaves an Allowance of $1,180 a month."
    private func meaning(_ plan: YourPlan) -> String {
        let total = "Total \(Format.whole(plan.total)) a month."
        guard let allowance = plan.allowance else { return total }
        return total + " With your income and bills, that leaves an Allowance of \(allowance < 0 ? "-" : "")\(Format.whole(allowance)) a month."
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
                    toast = "Plan in use" + (reply.allowance.map { " \u{00B7} Allowance \(Format.whole($0)) a month" } ?? "")
                }
            }
        case .edit(let row):
            PlanAmountSheet(row: row, close: { sheet = nil }, remove: { sheet = .remove(row) }) { amount in
                let reply: YourPlan = try await app.api.put("api/your-plan/rows/\(row.category)", ["amount": amount])
                sheet = nil
                saved(reply)
            }
        case .remove(let row):
            PearlConfirmSheet(overline: "Your plan", title: "Remove \(row.category) from your plan?",
                              message: "\(row.category) goes back to your usual, \(Format.whole(row.usual)) a month. If the plan is in use, your Allowance changes with it.",
                              primary: "Remove", secondary: "Keep it",
                              onClose: { sheet = nil }) {
                let reply: YourPlan = try await app.api.delete("api/your-plan/rows/\(row.category)")
                sheet = nil
                saved(reply)
            }
        }
    }

    /// YP-02's body. Without an income there's no Allowance to name, so the
    /// first sentence waits for one.
    private var useMessage: String {
        let rest = "These plans replace your usual amounts in Income and bills. You can change or stop it any time."
        guard let allowance = plan?.allowance else { return rest }
        return "Your Allowance becomes \(allowance < 0 ? "-" : "")\(Format.whole(allowance)) a month, from today. " + rest
    }

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

    private func stop() async {
        await run("api/your-plan/stop")
        withAnimation { toast = nil }
    }

    /// Undo on YP-03's toast: back as it was before Use this plan.
    private func undo() async {
        withAnimation { toast = nil }
        await run("api/your-plan/undo")
    }
}

/// YP-01's Plan row: "✓ Groceries · Usual $412   $400  Edit", and
/// "Usual $214 · set in Pearl chat" for a plan set there. The tick says it's
/// in the plan; the row opens YP-04.
private struct PlanLine: View {
    let row: YourPlan.Row
    let edit: () -> Void

    var body: some View {
        Button(action: edit) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.circle.fill").font(.system(size: 22))
                    .foregroundColor(Pearl.action)
                    .accessibilityHidden(true)
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
        "Usual \(Format.whole(row.usual))" + (row.source == "chat" ? " \u{00B7} set in Pearl chat" : "")
    }
}

/// YP-04: one category's amount a month. Save keeps it to the nearest $5
/// (the server rounds); Remove from plan asks first (YP-05).
private struct PlanAmountSheet: View {
    let row: YourPlan.Row
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
            Text("Your usual is \(Format.whole(row.usual)) a month. Plans round to the nearest $5.")
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
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Save", busy: busy,
                              secondary: "Remove from plan",
                              onPrimary: { Task { await go() } }, onSecondary: remove)
        }
        .onAppear {
            text = String(Int(row.amount.rounded()))
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
