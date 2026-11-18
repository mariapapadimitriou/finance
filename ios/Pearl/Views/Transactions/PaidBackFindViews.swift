import SwiftUI

// Paid back from the purchase (Figma Proposals › "Paid back" 1351:8769,
// note 1352:10319; approved by the product owner 2026-11-15; THL-289,
// THL-291, THL-181). Her own row's ••• on a split starts with "Find what
// paid it back" (PB-20, in SplitMenus.swift), which opens "What paid this
// back?" (PB-22, as redrawn by LT-01), or "No money in matches" (PB-23). Once
// she picks the money, the usual steps run: PB-11 with the kind picked, then
// Work and The shop as T-09w / T-09rs (extras S-11w / S-11m). Money from
// someone on the split pays their share, so it goes straight to their Mark
// paid back, PB-13 / PB-13b (PartsFlow.swift). Money already paying back another purchase is
// PB-24: its free part links at once; taking more always asks. Pearl
// sheets, never a stock dialog.

/// GET /api/transactions/<purchase>/paid-back-find (finance/parts_api.py).
struct PaidBackFind: Decodable {
    let merchant: String
    /// The purchase's day: LIKELY is money in after it.
    let date: String
    /// The whole purchase, and her share of it.
    let amount: Double
    let share: Double
    /// PB-23's "about $60": what she typed, or her share.
    let about: Double
    let candidates: [Lenient<Candidate>]

    struct Candidate: Decodable, Identifiable, Hashable {
        let id: String
        let date: String
        /// LT-01's tidy name: "Northwind Ltd", "Sam" (not "Cash Received -
        /// Samlee").
        let payer: String
        let amount: Double
        /// "work", "shop" or "person": the answer PB-11 picks.
        let kind: String?
        /// Who on the split, for A person.
        let person: String?
        /// The one fact after the date: "work", "refund". Empty for someone
        /// on the split; their group header says it.
        let why: String
        /// PB-24: it already pays back another purchase.
        let taken: Taken?

        struct Taken: Decodable, Hashable {
            let free: Double
            let need: Double
            let more: Double
            let other: Other?

            struct Other: Decodable, Hashable {
                let id: String
                let merchant: String
            }
        }

        var who: PaidBackWho? {
            switch kind {
            case "work": return .work
            case "shop": return .shop
            case "person": return .person
            default: return nil
            }
        }

        /// PB-24 asks only when she needs more than is free and there's
        /// another purchase to take it from.
        var asks: Bool {
            guard let t = taken else { return false }
            return t.other != nil && t.more >= 0.005 && t.free < t.need - 0.005
        }
    }
}

/// PB-22 as LT-01 redraws it ("Less text", 1425:73658, dark 1425:73900;
/// TEXT-01; THL-289, THL-291, THL-181): "What paid this back?" and Close,
/// the purchase ("$120.00 · your share $60.00 · Nov 12"), "Search deposits,
/// or an amount", then YOUR SHARE (work and refunds) and one {NAME}'S SHARE
/// group per person on the split, each row a tidy name and "+$60.00" over
/// the date and one fact ("Nov 14 · work"), one picked (a checkmark), and
/// Next. No footnote: the next sheet says what's next. The sheet fits its
/// content. PB-23 (1359:9897, dark 1359:9978) when nothing matches: "No
/// money in matches" and Clear search.
struct PaidBackFindSheet: View {
    let purchaseId: String
    let api: APIClient
    /// Next on the picked money; the opener runs what comes after.
    let onNext: (PaidBackFind.Candidate) async -> String?
    let onClose: () -> Void

    @State private var found: PaidBackFind?
    @State private var query = ""
    @State private var pick: String?
    @State private var loading = true
    @State private var busy = false
    @State private var error: String?

    private var rows: [PaidBackFind.Candidate] { found?.candidates.compactMap(\.value) ?? [] }
    /// The first row shown is picked until she picks another.
    private var picked: PaidBackFind.Candidate? {
        rows.first { $0.id == pick } ?? groups.first?.rows.first
    }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "What paid this back?", close: onClose).sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if let f = found {
                        QuestionHeader(name: f.merchant,
                                       amount: "\(Format.amount(f.amount)) · your share \(Format.amount(f.share)) · \(Format.short(f.date))",
                                       tone: Pearl.muted, sub: nil)
                            .padding(.bottom, 4)
                    }
                    searchField
                    list
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                            .padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
            .scrollDismissesKeyboard(.interactively)
            if !rows.isEmpty {
                PearlSheetButtons(primary: "Next", busy: busy, onPrimary: {
                    guard let c = picked else { return }
                    Task {
                        busy = true
                        error = await onNext(c)
                        busy = false
                    }
                })
                .sheetPart()
            }
        }
        .background(SheetBackground())
        .fitsContent()
        .presentationDragIndicator(.visible)
        .task(id: query) {
            if !query.isEmpty { try? await Task.sleep(nanoseconds: 250_000_000) }
            if !Task.isCancelled { await load() }
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Search deposits, or an amount").foregroundColor(Pearl.muted))
                .font(Nacre.body).autocorrectionDisabled().textInputAutocapitalization(.never)
                .accessibilityLabel("Search deposits, or an amount")
        }
        .padding(.horizontal, 14).frame(height: 44)
        .background(Capsule().fill(Pearl.ink.opacity(0.08)))
    }

    @ViewBuilder private var list: some View {
        if loading && found == nil {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if let f = found, rows.isEmpty {
            // PB-23: what she looked for, said back; Clear search when she typed.
            EmptyStateBlock(title: "No money in matches",
                            line: "Nothing came in for about \(Format.amount(f.about)) after \(Format.short(f.date)). If it hasn’t arrived yet, Pearl asks when it does.",
                            action: query.isEmpty ? nil : "Clear search") { query = "" }
        } else if found != nil {
            ForEach(groups, id: \.key) { g in
                if let header = g.header {
                    Text(header.uppercased())
                        .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).padding(.top, 4)
                        .accessibilityAddTraits(.isHeader)
                }
                GlassCard {
                    ForEach(Array(g.rows.enumerated()), id: \.element.id) { i, c in
                        if i > 0 { RowSeparator() }
                        row(c, on: picked?.id == c.id)
                    }
                }
            }
        }
    }

    /// LT-01's groups, the reason said once in the header: YOUR SHARE (work
    /// and refunds), then "SAM'S SHARE" for each person on the split, in the
    /// order their money came. Money a search found that Pearl can't place
    /// (not work, a refund or someone on the split) sits last, under OTHER
    /// MONEY IN (less text 2), rows unchanged; PB-11 asks who it was.
    private var groups: [(key: String, header: String?, rows: [PaidBackFind.Candidate])] {
        var out: [(key: String, header: String?, rows: [PaidBackFind.Candidate])] = []
        let yours = rows.filter { $0.kind == "work" || $0.kind == "shop" }
        if !yours.isEmpty { out.append(("yours", "Your share", yours)) }
        var people: [String] = []
        for c in rows where c.kind == "person" {
            let name = c.person ?? c.payer
            if !people.contains(name) { people.append(name) }
        }
        for name in people {
            let first = name.split(separator: " ").first.map(String.init) ?? name
            let whose = first.lowercased().hasSuffix("s") ? "\(first)’" : "\(first)’s"
            out.append(("p:" + name, "\(whose) share",
                        rows.filter { $0.kind == "person" && ($0.person ?? $0.payer) == name }))
        }
        let other = rows.filter { $0.who == nil }
        if !other.isEmpty { out.append(("other", "Other money in", other)) }
        return out
    }

    /// "Northwind Ltd · +$60.00" over "Nov 14 · work"; someone on the split
    /// over the date alone.
    private func row(_ c: PaidBackFind.Candidate, on: Bool) -> some View {
        let sub = [Format.short(c.date), c.why.isEmpty ? nil : c.why].compactMap { $0 }.joined(separator: " · ")
        return Button { pick = c.id } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(c.payer) · +\(Format.amount(c.amount))")
                        .font(Nacre.body).foregroundColor(Pearl.ink).fixedSize(horizontal: false, vertical: true)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if on {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                        .accessibilityHidden(true)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(c.payer), \(Format.amount(c.amount)) in, \(Format.monthDay(c.date))\(c.why.isEmpty ? "" : ", " + c.why)")
        .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
    }

    private func load() async {
        loading = true
        defer { loading = false }
        let q = query.trimmingCharacters(in: .whitespaces)
        do {
            let f: PaidBackFind = try await api.get("api/transactions/\(purchaseId)/paid-back-find",
                                                    query: q.isEmpty ? [:] : ["q": q])
            found = f
            error = nil
            if !rows.contains(where: { $0.id == pick }) { pick = nil }
        } catch {
            if error is CancellationError { return }
            self.error = "Couldn’t load your money in. Try again."
        }
    }
}

/// PB-24 (1359:10057, dark 1359:10117): she needs more than is free of a
/// deposit that already pays back another purchase. Eyebrow "NORTHWIND LTD ·
/// +$60.00 · NOV 14", "Take $40.00 from Air Canada?", and Take or Use only
/// the free part. With nothing free, the body starts "All of this deposit
/// pays back Air Canada." and the second button leaves it there.
struct PaidBackTakeSheet: View {
    let c: PaidBackFind.Candidate
    var busy = false
    var error: String? = nil
    let onTake: () -> Void
    let onFreeOnly: () -> Void
    let onClose: () -> Void

    var body: some View {
        let t = c.taken
        let free = t?.free ?? 0
        let more = Format.amount(t?.more ?? 0)
        let other = t?.other?.merchant ?? ""
        let none = free < 0.005
        PearlSheet {
            PearlSheetHeader(overline: "\(c.payer) · +\(Format.amount(c.amount)) · \(Format.short(c.date))",
                             title: "Take \(more) from \(other)?", close: onClose)
            Text(none
                 ? "All of this deposit pays back \(other). Taking it means \(other) counts \(more) more again."
                 : "\(Format.amount(free)) of this deposit is free, so it pays back your share first. The other \(more) pays back \(other). Taking it means \(other) counts \(more) more again.")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
            }
        } footer: {
            PearlSheetButtons(primary: "Take \(more)", busy: busy,
                              secondary: none ? "Leave it on \(other)" : "Use only the \(Format.amount(free))",
                              onPrimary: onTake, onSecondary: onFreeOnly)
        }
    }
}

/// Where a step of Find what paid it back is.
enum PaidBackStep: Identifiable {
    case find
    /// PB-11 with the match's kind picked.
    case who(PaidBackFind.Candidate)
    /// PB-24.
    case take(PaidBackFind.Candidate)
    /// PB-13 / PB-13b for a person's share of this purchase.
    case person(PaidBackFind.Candidate)
    /// S-11w / S-11m: her share is saved and more came in.
    case extra(PaidBackFind.Candidate, MarkReply.ShareExtra, refund: Bool)

    var id: String {
        switch self {
        case .find: return "find"
        case .who(let c): return "who" + c.id
        case .take(let c): return "take" + c.id
        case .person(let c): return "person" + c.id
        case .extra(let c, _, _): return "extra" + c.id
        }
    }
}

/// Runs Find what paid it back over the purchase's page: one sheet at a
/// time, the next opening once the last has gone. `done` gets the toast
/// and its Undo; `failed` what went wrong, nothing saved.
struct PaidBackFromPurchase: ViewModifier {
    @Binding var step: PaidBackStep?
    let purchase: Transaction
    let api: APIClient
    let done: (String, JSONValue?) -> Void
    let failed: (String) -> Void

    @State private var then: PaidBackStep?
    /// S-11w / S-11m closed without answering: her share stays saved.
    @State private var heldShare: MarkReply?
    @State private var busy = false
    @State private var error: String?

    func body(content: Content) -> some View {
        content.sheet(item: $step, onDismiss: {
            busy = false
            error = nil
            if let next = then {
                then = nil
                step = next
            } else if let held = heldShare {
                heldShare = nil
                done(held.title ?? "Sorted.", held.undo)
            }
        }) { s in
            sheet(s)
        }
    }

    @ViewBuilder private func sheet(_ s: PaidBackStep) -> some View {
        switch s {
        case .find:
            PaidBackFindSheet(purchaseId: purchase.id, api: api, onNext: next, onClose: { go(nil) })
        case .who(let c):
            // PB-11 (1351:9324): the face and the money, the kind picked.
            PaidBackWhoSheet(face: c.payer,
                             sub: "+\(Format.amount(c.amount)) · \(c.payer) · \(Format.short(c.date))",
                             picked: c.who, pickedPerson: c.person,
                             onPick: { who in pickWho(c, who) },
                             onClose: { go(nil) })
        case .take(let c):
            PaidBackTakeSheet(c: c, busy: busy, error: error,
                              onTake: { Task { await take(c, more: true) } },
                              onFreeOnly: {
                                  if (c.taken?.free ?? 0) < 0.005 { go(nil) } else { Task { await take(c, more: false) } }
                              },
                              onClose: { go(nil) })
        case .person(let c):
            // PB-13 / PB-13b, saved as the deposit side saves them (PB-14's toast and Undo).
            PartsSheet(deposit: PartsDeposit(id: c.id, name: c.payer, amount: c.amount, date: c.date), api: api,
                       paidBack: true, payer: c.kind == "person" ? c.person : nil, forCharge: purchase.id,
                       person: c.kind == "person" ? c.person : nil) { reply in
                go(nil)
                done(reply.title ?? "Sorted.", reply.undo)
            }
        case .extra(let c, let extra, let refund):
            // S-11w (1294:2157) / S-11m (1302:3494), as the deposit side asks them.
            PartsSheet(deposit: PartsDeposit(id: c.id, name: c.payer, amount: c.amount, date: c.date), api: api,
                       credited: [PartsSheet.Part(kind: refund ? "refund" : "reimbursement", amount: extra.share,
                                                  charge: extra.charge, merchant: extra.merchant, share: refund)],
                       shareLine: "\(Format.amount(extra.share)) \(refund ? "refunds" : "pays back") your share of \(extra.merchant).",
                       shareOwing: refund ? (extra.people ?? []) : nil) { reply in
                heldShare = nil
                go(nil)
                done(reply.title ?? "Sorted.", reply.undo)
            }
        }
    }

    /// Close this sheet, then open `next` (nil: none).
    private func go(_ next: PaidBackStep?) {
        then = next
        step = nil
    }

    /// PB-22's Next: PB-24 for money already paying back something else
    /// (its free part links at once when that's enough); someone on the
    /// split straight to their Mark paid back (LT-01: it pays their share,
    /// PB-13 / PB-13b); else PB-11.
    private func next(_ c: PaidBackFind.Candidate) async -> String? {
        if c.taken != nil {
            if c.asks { go(.take(c)); return nil }
            return await link(c, more: false)
        }
        if c.who == .person, c.person != nil {
            go(.person(c))
            return nil
        }
        go(.who(c))
        return nil
    }

    /// PB-11's answer. Work and The shop pay back her share of this
    /// purchase (T-09w / T-09rs), with S-11w / S-11m when more came in;
    /// A person is PB-13 for their share of it.
    private func pickWho(_ c: PaidBackFind.Candidate, _ who: PaidBackWho) {
        switch who {
        case .person:
            go(.person(c))
        case .work, .shop:
            let refund = who == .shop
            Task {
                do {
                    let reply: MarkReply = try await api.post("api/transactions/\(c.id)/mark",
                                                              ["case": refund ? "refund" : "reimbursement",
                                                               "charge": purchase.id, "share": true])
                    if let extra = reply.extra {
                        heldShare = reply
                        go(.extra(c, extra, refund: refund))
                    } else {
                        go(nil)
                        done(reply.title ?? "Sorted.", reply.undo)
                    }
                } catch {
                    go(nil)
                    failed((error as? APIError)?.problem?.error ?? "Couldn’t save that. Try again.")
                }
            }
        }
    }

    /// PB-24 Take, or Use only the free part.
    private func take(_ c: PaidBackFind.Candidate, more: Bool) async {
        busy = true
        if let problem = await link(c, more: more) {
            busy = false
            error = problem
        }
    }

    /// POST …/paid-back-take: "Linked $20.00 · Pai Northern Thai" or "Moved
    /// $40.00 from Air Canada", with Undo. Returns what went wrong, if it did.
    private func link(_ c: PaidBackFind.Candidate, more: Bool) async -> String? {
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(purchase.id)/paid-back-take",
                                                      ["deposit": c.id, "take": more])
            go(nil)
            done(reply.title ?? "Sorted.", reply.undo)
            return nil
        } catch {
            return (error as? APIError)?.problem?.error ?? "Couldn’t save that. Try again."
        }
    }
}
