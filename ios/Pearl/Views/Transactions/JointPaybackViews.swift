import SwiftUI

// Paybacks 2 (approved by the product owner 2026-11-16; THL-289, THL-291,
// THL-181, THL-301, THL-305, THL-172). Figma Proposals › "Paybacks 2"
// 1406:5084, notes 1408:6438–6441.
//
// PP-01 1406:5216 (dark 1406:5547): Who paid you back? behind PB-42 › Who
//        paid › A person. Search, ON THIS SPLIT (today's answer ticked),
//        FROM PAST SPLITS (joint-account people say so), Someone new. A tap
//        answers; PP-02 1406:5860 (dark 1406:5984) is PB-42 again with the
//        ink toast and Undo (PaybackLinkViews.swift).
// TP-01 1406:6098 (dark 1406:6232): "Mom paid me back" on a transfer in from
//        a joint account (TransactionDetailView's TF-01).
// TP-02 1407:6398 (dark 1407:6648): What was this? on the money-in end
//        (AnswerSheet's T-12 tiles, Paid back there).
// TP-03 1407:6896 (dark 1407:7113): PB-30 with Mom picked (no PB-11), her
//        shares ticked to the amount, and what happens to the pair
//        (PartsFlow.swift, `joint`).
// TP-04 1407:7328 (dark 1407:7487): the money in afterwards; Undo puts the
//        transfer back (finance/joint.py).
// TP-05 1406:6361 (dark 1406:6494): two accounts only hers: no Paid back,
//        and why (`NoPaidBackCallout`).
//
// Every step is a Pearl sheet, never a stock alert or confirmation dialog.

/// A transfer in from a joint account, about to be said to be one of its
/// other owners paying her back (TP-01, TP-02 › Paid back).
struct JointPaybackStart: Identifiable, Hashable {
    let deposit: PartsDeposit
    /// The joint account's other owners, and "Joint ··1123".
    let people: [String]
    let account: String
    /// The money out of the joint account (the transfer's other end).
    let out: String
    /// Who paid her back, once known (one owner, or PP-01's tap).
    var person: String? = nil

    var id: String { deposit.id + "|" + (person ?? "") }
}

/// TP-01 / TP-02 › Paid back: with one other owner, straight to PB-30 with
/// them picked (TP-03); with more, PP-01 asks who first. Saved, `onSaved`
/// gets the reply with its toast ("Mom paid back 3 purchases · $240.00")
/// and Undo.
struct JointPaybackFlow: ViewModifier {
    @Binding var start: JointPaybackStart?
    let api: APIClient
    let onSaved: (MarkReply) -> Void

    @State private var asking: JointPaybackStart?
    @State private var linking: JointPaybackStart?
    @State private var picked: JointPaybackStart?

    func body(content: Content) -> some View {
        content
            .onChange(of: start) { s in
                guard let s = s else { return }
                start = nil
                if s.people.count > 1 {
                    asking = s
                } else {
                    var one = s
                    one.person = s.people.first
                    linking = one
                }
            }
            .sheet(item: $asking, onDismiss: {
                // The picker has gone, so PB-30 can open.
                let next = picked
                picked = nil
                if let next = next { linking = next }
            }) { s in
                // PP-01 with the account's people (TP-01, more than one other owner).
                WhoPaidPicker(api: api, sub: "+\(Format.amount(s.deposit.amount)) · \(s.deposit.name) · \(Format.short(s.deposit.date))",
                              top: s.people.map { WhoPaidPicker.Row(name: $0, sub: "Your joint account") },
                              pastSplits: false, someoneNew: false,
                              onPick: { name in
                                  var next = s
                                  next.person = name
                                  picked = next
                                  asking = nil
                              },
                              onClose: { asking = nil })
            }
            .sheet(item: $linking) { s in
                // TP-03: PB-30 with them picked; PB-11 is skipped.
                PartsSheet(deposit: s.deposit, api: api, paidBack: true, payer: s.person, joint: s) { reply in
                    linking = nil
                    onSaved(reply)
                }
            }
    }
}

/// PP-01 "Who paid you back?": search, the people on this split first (her
/// answer today ticked), then people from past splits, then Someone new.
/// A tap answers. Library Person rows; one accessibility element each.
@MainActor
struct WhoPaidPicker: View {
    struct Row: Hashable, Identifiable {
        let name: String
        /// "Today’s answer · on this split", "Owes you $30.00 on this split".
        let sub: String
        var ticked = false
        var id: String { name }
    }

    let api: APIClient
    /// "$26.65 toward Pizza Nova · e-Transfer, Nov 14".
    let sub: String
    /// ON THIS SPLIT (PB-42), or the joint account's people (TP-01).
    let top: [Row]
    /// "On this split"; none over the joint account's people.
    var topLabel: String? = nil
    var pastSplits = true
    var someoneNew = true
    /// FROM PAST SPLITS limited to these people (2026-11-16, A person from
    /// a sender Pearl can't match): whoever owes her, each with the line
    /// /api/people/recent gives them, or this row's until it has loaded.
    var onlyPast: [Row]? = nil
    let onPick: (String) -> Void
    let onClose: () -> Void

    @State private var query = ""
    @State private var recent: [Past]?
    @State private var typing = false

    /// GET /api/people/recent, with PP-01's "4 splits" and joint flag.
    struct Past: Decodable, Hashable {
        let name: String
        let date: String
        var splits: Int? = nil
        var joint: Bool? = nil
    }

    private var q: String { query.trimmingCharacters(in: .whitespaces) }
    private func matches(_ name: String) -> Bool { q.isEmpty || name.localizedCaseInsensitiveContains(q) }

    var body: some View {
        PearlSheet {
            PearlSheetHeader(overline: "Paid back · Who paid", title: "Who paid you back?", sub: sub, close: onClose)
            searchField
            let shown = top.filter { matches($0.name) }
            if !shown.isEmpty {
                if let label = topLabel { PearlSectionLabel(text: label) }
                card(shown)
            }
            if let only = onlyPast {
                let past = only.filter { matches($0.name) }.map { r in
                    (recent ?? []).first { $0.name == r.name }.map { Row(name: r.name, sub: pastLine($0)) } ?? r
                }
                if !past.isEmpty {
                    PearlSectionLabel(text: "From past splits")
                    card(past)
                }
            } else if pastSplits, let recent = recent {
                // Anyone already on this split shows once (the same name match).
                let past = recent.filter { p in matches(p.name) && !top.contains { samePerson($0.name, p.name) } }
                    .map { Row(name: $0.name, sub: pastLine($0)) }
                if !past.isEmpty {
                    PearlSectionLabel(text: "From past splits")
                    card(past)
                }
            }
            if someoneNew {
                PearlOptionCard {
                    Button { typing = true } label: {
                        HStack(spacing: 12) {
                            Text("+").font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote))
                                .foregroundColor(Pearl.ink)
                                .frame(width: 40, height: 40).background(Circle().fill(Pearl.bubble))
                                .accessibilityHidden(true)
                            texts("Someone new", "Type their name")
                            Spacer(minLength: 8)
                            Image(systemName: "chevron.right").font(.system(size: 14, weight: .medium))
                                .foregroundColor(Pearl.muted)
                        }
                        .padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Someone new, type their name")
                    .accessibilityAddTraits(.isButton)
                }
            }
        }
        .task { if pastSplits || onlyPast != nil { await load() } }
        .sheet(isPresented: $typing) {
            // Someone new: the people picker's name entry (AM-08p3), one name.
            PeoplePicker(api: api, overline: "Paid back · Who paid", title: "Who paid you back?", sub: sub,
                         limit: 1,
                         onClose: { typing = false }) { names in
                typing = false
                if let name = names.first { onPick(name) }
            }
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Search people").foregroundColor(Pearl.muted))
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .textInputAutocapitalization(.words).autocorrectionDisabled()
                .submitLabel(.search)
                .accessibilityLabel("Search people")
        }
        .padding(.horizontal, 14).frame(minHeight: 44)
        .background(Capsule().fill(Pearl.control))
    }

    private func card(_ rows: [Row]) -> some View {
        PearlOptionCard {
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, r in
                if i > 0 { PearlDivider() }
                row(r)
            }
        }
    }

    /// "Sam Lee" over "Today’s answer · on this split", with the tick.
    private func row(_ r: Row) -> some View {
        Button { onPick(r.name) } label: {
            HStack(spacing: 12) {
                PearlFace(name: r.name, size: 40)
                texts(r.name, r.sub)
                Spacer(minLength: 8)
                if r.ticked {
                    Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundColor(Pearl.onAction)
                        .frame(width: 26, height: 26).background(Circle().fill(Pearl.action))
                }
            }
            .padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(r.name), \(r.sub)")
        .accessibilityAddTraits(r.ticked ? [.isButton, .isSelected] : .isButton)
    }

    private func texts(_ title: String, _ sub: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.ink)
            Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// "Your joint account · 4 splits", "Last split Oct 2".
    private func pastLine(_ p: Past) -> String {
        if p.joint == true {
            let n = p.splits ?? 1
            return "Your joint account · \(n) split\(n == 1 ? "" : "s")"
        }
        return "Last split \(Format.short(p.date))"
    }

    private func load() async {
        struct Reply: Decodable { let people: [Lenient<Past>] }
        let r: Reply? = try? await api.get("api/people/recent")
        recent = (r?.people ?? []).compactMap { $0.value }
    }

    /// PB-42's ON THIS SPLIT: who's on it, and what each has done.
    static func onSplit(_ people: [Transaction.Splitting.Person], answer: String) -> [Row] {
        people.map { p in
            if samePerson(p.name, answer) || p.name == answer {
                return Row(name: p.name, sub: "Today’s answer · on this split", ticked: true)
            }
            if p.owes >= 0.005 {
                return Row(name: p.name, sub: "Owes you \(Format.amount(p.owes)) on this split")
            }
            if p.paid >= 0.005, let on = p.paidOn {
                return Row(name: p.name, sub: "Paid back · \(Format.short(on))")
            }
            return Row(name: p.name, sub: "On this split")
        }
    }
}

/// PP-01 for a payback onto a split she set up, from a sender Pearl can't
/// place on it (2026-11-16, `WhoPaidAsk`): only the split's people, no past
/// splits and no Someone new, so a payback never adds a person to her split.
/// A tap opens PB-30 for that person (Paybacks & undo, 1395:3405) with this
/// purchase ticked and their others as they add up, in this same sheet;
/// saved, `onPick` gets `.done` with its toast and one Undo. Someone who
/// owes nothing with an amount (a Not sure yet split) gets the same
/// payback as before.
@MainActor
struct WhoPaidAskSheet: View {
    let ask: WhoPaidAsk
    let api: APIClient
    let onPick: (ReviewAnswer) -> Void
    let onClose: () -> Void
    @State private var pb30: String?

    var body: some View {
        if let name = pb30, let deposit = ask.deposit {
            PartsSheet(deposit: PartsDeposit(id: deposit, name: ask.sender, amount: ask.amount, date: ask.date ?? ""),
                       api: api, paidBack: true, payer: name, person: name, mustTick: ask.charge) { reply in
                onPick(.done(reply))
            }
        } else {
            picker
        }
    }

    /// Their shares with an amount (…/owing?person=, as PB-30 reads them).
    private func picked(_ name: String) async {
        struct Reply: Decodable { let from: String?; let items: [Lenient<PartsSheet.Owing>] }
        if let deposit = ask.deposit,
           let r: Reply = try? await api.get("api/transactions/\(deposit)/owing", query: ["person": name]),
           r.from != nil,
           r.items.compactMap(\.value).contains(where: { $0.theirs == true && $0.unknown != true && $0.owes >= 0.005 }) {
            pb30 = name
            return
        }
        if let answer = ask.answer(name) { onPick(answer) } else { onClose() }
    }

    private var picker: some View {
        WhoPaidPicker(api: api, sub: "\(Format.amount(ask.amount)) toward \(ask.merchant) · \(ask.sender)",
                      top: ask.people.map { p in
                          WhoPaidPicker.Row(name: p.name, sub: (p.owes ?? 0) >= 0.005
                                            ? "Owes you \(Format.amount(p.owes ?? 0)) on this split" : "On this split")
                      },
                      topLabel: "On this split", pastSplits: false, someoneNew: false,
                      onPick: { name in Task { await picked(name) } },
                      onClose: onClose)
    }
}

/// TP-05: "Why there’s no Paid back here" under a transfer between two
/// accounts only hers.
struct NoPaidBackCallout: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "info.circle").font(.system(size: 18)).foregroundColor(Pearl.ink)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Why there’s no Paid back here").font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.ink)
                Text("Both accounts are only yours, so this is your own money moving. If someone else sent it, tap This isn’t a transfer. Then it’s money in, and What was this? offers Paid back.")
                    .font(Pearl.text(.callout)).foregroundColor(Pearl.ink)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .pearlCard(radius: Pearl.radiusTile)
        .accessibilityElement(children: .combine)
    }
}
