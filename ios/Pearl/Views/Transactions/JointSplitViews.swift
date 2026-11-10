import Contacts
import SwiftUI
import UIKit

// JOINT-A, JOINT-B and SPLIT-C (product owner, 2026-11-09; Jira pending):
// Design refresh section 12 (1102:4466) and section 13 (1112:6476).
//
// JOINT-A  AM-08p–p7 the people picker (S-17 v2 with a joint header),
//          AM-08x Remove someone, O-09cr setup. S-17j: Split my part's Add
//          someone, joint account holders hidden.
// JOINT-B  S-03j's strip, S-04j's joint card, S-41j Remove the split?,
//          AM-21j Change your share?, AM-08n Not a joint account?
// SPLIT-C  S-03u's explainer, S-04u's card lines, S-45 Settle up, S-46
//          That's everything.
//
// Every sheet is a Pearl view on pearl paper (no .alert, .confirmationDialog
// or action sheet); spending is ink; 44 pt targets; no new motion yet.

// MARK: - S-17 v2 / AM-08p People picker (JOINT-A)

/// Someone she has split with (GET /api/people/recent).
struct RecentPerson: Decodable, Hashable, Identifiable {
    let name: String
    let merchant: String
    let date: String
    var id: String { name }
}

/// "Sam Lee" and "Sam": the same first name, as the server's split name
/// matcher says (finance/splits.py same_person).
func samePerson(_ a: String, _ b: String) -> Bool {
    func first(_ s: String) -> String {
        s.lowercased().split { !$0.isLetter && !$0.isNumber && $0 != "'" }.first.map(String.init) ?? ""
    }
    let x = first(a), y = first(b)
    return !x.isEmpty && x == y
}

/// The one picker for "who": people she's split with (newest first), her
/// contacts (A to Z, asked for only when it opens, never sent anywhere),
/// and Type a name. Several at once, up to `limit`. Names only.
@MainActor
struct PeoplePicker: View {
    let api: APIClient
    /// "SIMPLII CHEQUING · JOINT", "SPLIT MY PART · PIZZA NOVA".
    let overline: String
    let title: String
    var sub: String? = nil
    /// S-17j: the purchase, so the server leaves its account's holders out.
    var txn: String? = nil
    /// AM-08p4: already on the account, ticked and dimmed.
    var already: [String] = []
    /// Never offered, and refused when typed (S-17j: joint holders).
    var refused: [String] = []
    /// AM-08p4: six on a joint account.
    var limit: Int? = nil
    let onClose: () -> Void
    /// Saves; a thrown message shows as AM-08p7 with the ticks kept.
    let onAdd: ([String]) async throws -> Void

    enum ContactsState { case asking, on, off }

    @State private var recent: [RecentPerson]?
    @State private var contacts: [String] = []
    @State private var contactsState: ContactsState = .asking
    @State private var query = ""
    @State private var picked: [String] = []
    @State private var busy = false
    @State private var failed: String?
    @State private var loadFailed = false
    @FocusState private var searching: Bool

    private var room: Int { limit.map { max(0, $0 - already.count) } ?? Int.max }
    private var full: Bool { picked.count >= room }
    private var q: String { query.trimmingCharacters(in: .whitespaces) }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(overline: overline, title: title,
                             sub: full && limit != nil ? "Six is the most." : sub,
                             close: onClose)
                .disabled(busy)
            searchField
            if let refusal = refusal {
                CautionBanner(text: refusal)
            }
            if let recent = recent {
                let mine = recent.filter { r in matches(r.name) && !isRefused(r.name) }
                if !mine.isEmpty {
                    PearlSectionLabel(text: "People you’ve split with")
                    PearlOptionCard {
                        ForEach(Array(mine.enumerated()), id: \.element.id) { i, r in
                            if i > 0 { PearlDivider() }
                            row(r.name, sub: "Split \(r.merchant) · \(Format.short(r.date))")
                        }
                    }
                }
                contactsSection(recent)
            } else if loadFailed {
                CautionBanner(text: "Couldn’t load the people you’ve split with. You can still type a name.")
            } else {
                skeleton
            }
            typeRow
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : addLabel, busy: busy, busyLabel: "Adding…") {
                Task { await add() }
            }
            .disabled(names.isEmpty || refusal != nil)
        }
        .task { await load() }
        .onChange(of: picked.count) { n in
            UIAccessibility.post(notification: .announcement, argument: n == 1 ? "1 person picked" : "\(n) people picked")
        }
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Search or type a name").foregroundColor(Pearl.muted))
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .textInputAutocapitalization(.words).autocorrectionDisabled()
                .focused($searching)
                .submitLabel(.done)
                .onSubmit { if !q.isEmpty && !isRefused(q) { pick(q); query = "" } }
                .accessibilityLabel("Search or type a name")
        }
        .padding(.horizontal, 14).frame(minHeight: 44)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.control))
    }

    /// S-17j (REFRESH-03): "Sam Lee’s part is already off."
    private var refusal: String? {
        guard !q.isEmpty, let who = refused.first(where: { samePerson($0, q) }) else { return nil }
        return "\(possessive(who)) part is already off."
    }

    private func isRefused(_ name: String) -> Bool { refused.contains { samePerson($0, name) } }

    private func matches(_ name: String) -> Bool { q.isEmpty || name.localizedCaseInsensitiveContains(q) }

    @ViewBuilder private func contactsSection(_ recent: [RecentPerson]) -> some View {
        switch contactsState {
        case .asking:
            PearlSectionLabel(text: "From your contacts")
            skeleton
        case .off:
            PearlSectionLabel(text: "From your contacts")
            // AM-08p2: one element; Turn on in Settings is its action.
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 12) {
                    PearlBubble(symbol: "info.circle")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Contacts are off for Pearl").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                        Text("Pick from your splits, or type a name.")
                            .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                Button("Turn on in Settings", action: openSettings)
                    .font(Pearl.text(.callout, .semibold)).foregroundColor(Pearl.action)
                    .frame(minHeight: 44).padding(.leading, 52).buttonStyle(.plain)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: Pearl.radiusTile, style: .continuous).fill(Pearl.card))
            .overlay(RoundedRectangle(cornerRadius: Pearl.radiusTile, style: .continuous).stroke(Pearl.border, lineWidth: 1))
            .accessibilityElement(children: .combine)
            .accessibilityAction(named: "Turn on in Settings", openSettings)
        case .on:
            // Anyone already in the first list shows once (same name match).
            let shown = contacts.filter { c in matches(c) && !isRefused(c) && !recent.contains { samePerson($0.name, c) } }
            if !shown.isEmpty {
                PearlSectionLabel(text: "From your contacts")
                PearlOptionCard {
                    ForEach(Array(shown.prefix(60).enumerated()), id: \.element) { i, name in
                        if i > 0 { PearlDivider() }
                        row(name, sub: "In your contacts")
                    }
                }
            }
        }
    }

    /// AM-08p3: "Add “Maya” as a new name", or Type a name, always last.
    private var typeRow: some View {
        let typed = !q.isEmpty && !picked.contains(q) && !already.contains { samePerson($0, q) } && !isRefused(q)
        return PearlOptionCard {
            PearlOptionRow(symbol: "person", title: typed ? "Add “\(q)” as a new name" : "Type a name",
                           sub: typed ? "Only you can see it" : "For someone who isn’t here") {
                if typed { pick(q); query = "" } else { searching = true }
            }
            .disabled(typed && full)
        }
    }

    private var skeleton: some View {
        PearlOptionCard {
            ForEach(0..<3, id: \.self) { i in
                if i > 0 { PearlDivider() }
                HStack(spacing: 12) {
                    Circle().fill(Pearl.track).frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 6) {
                        Capsule().fill(Pearl.track).frame(width: 120, height: 12)
                        Capsule().fill(Pearl.track).frame(width: 170, height: 10)
                    }
                    Spacer()
                }
                .padding(.vertical, 10).frame(minHeight: 60)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
    }

    /// "Sam Lee, split Pizza Nova November 13, button, not selected."
    private func row(_ name: String, sub: String) -> some View {
        let isAlready = already.contains { samePerson($0, name) }
        let on = isAlready || picked.contains(name)
        let dim = isAlready || (!on && full)
        return Button { pick(name) } label: {
            HStack(alignment: .top, spacing: 12) {
                PearlFace(name: name, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    Text(isAlready ? "Already shared" : sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                tick(on)
            }
            .padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
            .opacity(dim ? 0.45 : 1)
        }
        .buttonStyle(.plain)
        .disabled(dim || busy)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(isAlready ? "\(name), already shared" : "\(name), \(sub)")
        .accessibilityValue(on ? "selected" : (full ? "dimmed, six people picked already" : "not selected"))
        .accessibilityAddTraits(.isButton)
    }

    private func tick(_ on: Bool) -> some View {
        ZStack {
            Circle().strokeBorder(on ? Pearl.action : Pearl.borderStrong, lineWidth: 1.5)
            if on {
                Circle().fill(Pearl.action)
                Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundColor(Pearl.onAction)
            }
        }
        .frame(width: 24, height: 24)
        .frame(width: 44, height: 44)
        .accessibilityHidden(true)
    }

    private func pick(_ name: String) {
        if let i = picked.firstIndex(of: name) {
            picked.remove(at: i)
        } else if !full {
            picked.append(name)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
        failed = nil
    }

    /// What Add saves: the ticked ones, or a typed name nobody ticked.
    private var names: [String] {
        if !picked.isEmpty { return picked }
        return !q.isEmpty && !isRefused(q) ? [q] : []
    }

    /// "Add 2 people", "Add Sam Lee".
    private var addLabel: String {
        switch names.count {
        case 0: return "Add"
        case 1: return "Add \(names[0])"
        default: return "Add \(names.count) people"
        }
    }

    private func add() async {
        let list = names
        guard !list.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            try await onAdd(list)
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            // AM-08p7: ticks kept.
            failed = "Couldn’t save. Your picks are kept. Try again."
        }
    }

    private func load() async {
        struct Reply: Decodable { let people: [RecentPerson] }
        do {
            let r: Reply = try await api.get("api/people/recent", query: txn.map { ["txn": $0] } ?? [:])
            recent = r.people
        } catch {
            recent = []
            loadFailed = true
        }
        await loadContacts()
    }

    /// Asked for only now, the first time the picker opens (AM-08p1).
    private func loadContacts() async {
        let store = CNContactStore()
        if CNContactStore.authorizationStatus(for: .contacts) == .notDetermined {
            _ = try? await store.requestAccess(for: .contacts)
        }
        let status = CNContactStore.authorizationStatus(for: .contacts)
        guard status != .denied && status != .restricted && status != .notDetermined else {
            contactsState = .off
            return
        }
        let found: [String] = await Task.detached {
            let keys = [CNContactGivenNameKey, CNContactFamilyNameKey] as [CNKeyDescriptor]
            var out: [String] = []
            let request = CNContactFetchRequest(keysToFetch: keys)
            request.sortOrder = .givenName
            try? store.enumerateContacts(with: request) { c, stop in
                let name = "\(c.givenName) \(c.familyName)".trimmingCharacters(in: .whitespaces)
                if !name.isEmpty { out.append(name) }
                if out.count >= 500 { stop.pointee = true }
            }
            return out
        }.value
        var seen = Set<String>()
        contacts = found.filter { seen.insert($0.lowercased()).inserted }
            .sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
        contactsState = .on
    }

    private func openSettings() {
        // iOS Settings › Pearl, never the web (JOINT-A note 1110:6476).
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }
}

// MARK: - S-03j's strip and S-04j's card (JOINT-B)

extension Transaction {
    /// JOINT-B: what a split of this purchase splits, her part or all of it.
    var splitBase: Double { splitting?.base ?? jointPart ?? fullAmount ?? amount }

    /// A fixed share (or her answer) takes part of it off: "Split my part".
    /// "All mine unless I mark it" is the usual "Split with others"
    /// (S-01jr2, PO 2026-11-09 (4)).
    var splitsMyPart: Bool {
        !joint.isEmpty && splitBase < (fullAmount ?? amount) - 0.005
    }

    /// "Sam Lee", "Sam Lee and Maya Reyes", or the account's label.
    var jointWho: String {
        jointPeople.isEmpty ? (joint.isEmpty ? "them" : joint) : Format.andList(jointPeople)
    }

    /// "50/50", "60/40", or nil without a set share.
    var jointRatio: String? {
        let whole = fullAmount ?? amount
        guard whole > 0, splitsMyPart else { return nil }
        let mine = Int((splitBase / whole * 100).rounded())
        return "\(mine)/\(100 - mine)"
    }
}

/// S-03j: "Sam Lee’s $50.00 stays theirs · joint 50/50", read only.
struct JointStrip: View {
    let t: Transaction

    var body: some View {
        let theirs = (t.fullAmount ?? t.amount) - t.splitBase
        HStack(spacing: 10) {
            Image(systemName: "person.2").font(.system(size: 16)).foregroundColor(Pearl.action)
                .accessibilityHidden(true)
            Text("\(possessive(t.jointWho)) \(Format.amount(theirs)) stays theirs" + (t.jointRatio.map { " · joint \($0)" } ?? ""))
                .font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.bubble))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(possessive(t.jointWho)) \(Format.amount(theirs)) stays theirs. Joint \(t.jointRatio?.replacingOccurrences(of: "/", with: " ") ?? "").")
    }
}

/// S-04j: JOINT WITH SAM LEE · 50/50, who's on the account (their part,
/// never owed) apart from who owes her.
struct JointPartCard: View {
    let t: Transaction
    let joint: Transaction.Splitting.Joint

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            PearlSectionLabel(text: "Joint with \(t.jointWho)" + (t.jointRatio.map { " · \($0)" } ?? ""))
                .padding(.horizontal, 4).padding(.top, 12)
            PearlOptionCard {
                ForEach(Array(holders.enumerated()), id: \.offset) { i, h in
                    if i > 0 { PearlDivider() }
                    line(face: h.name, title: h.name, sub: "On this account · their part", amount: h.amount)
                        .accessibilityLabel("\(h.name), on this account, their part, \(Format.amount(h.amount)), not owed to you")
                        // REFRESH-03 (S-04j): the footnote under the card is gone; this row says it.
                        .accessibilityHint("Only the people in your split owe you.")
                }
                PearlDivider()
                line(face: "Me", title: "Your part", sub: "Split below", amount: joint.part)
                    .accessibilityLabel("Your part, \(Format.amount(joint.part)), split below")
            }
        }
    }

    /// Each holder's part: the account's other part, shared among them.
    private var holders: [(name: String, amount: Double)] {
        let names = joint.people.isEmpty ? [joint.label] : joint.people
        let cents = Int((joint.theirs * 100).rounded())
        let each = cents / max(names.count, 1)
        return names.enumerated().map { i, n in
            (n, Double(each + (i == 0 ? cents - each * names.count : 0)) / 100)
        }
    }

    private func line(face: String, title: String, sub: String, amount: Double) -> some View {
        HStack(spacing: 12) {
            PearlFace(name: face, size: 40)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(Format.amount(amount)).font(Pearl.text(.headline)).monospacedDigit().foregroundColor(Pearl.ink)
        }
        .padding(.vertical, 10).frame(minHeight: 56)
        .accessibilityElement(children: .ignore)
    }
}

// MARK: - S-41j Remove the split? (JOINT-B)

/// What removing a joint purchase's split does, then Remove the split /
/// Keep the split. Saving and its error stay on the sheet (S-41j2).
struct RemoveSplitSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: t.merchant, overline: "\(t.merchant) · \(Format.money(t))",
                             title: "Remove the split?",
                             sub: "Your part \(Format.amount(split.base ?? t.splitBase)) counts as yours again.",
                             close: onClose)
                .disabled(busy)
            // REFRESH-03 (S-41j): only the people; the joint share row and the
            // divider under it are gone, since the joint share doesn't change.
            PearlOptionCard {
                ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { PearlDivider() }
                    if p.paid >= 0.005 {
                        row(face: p.name, title: "\(possessive(p.name)) \(Format.amount(p.paid)) goes back to sort", sub: nil)
                    } else if split.unsure {
                        row(face: p.name, title: "\(p.name) is off the split", sub: nil)
                    } else {
                        row(face: p.name, title: "\(p.name) won’t owe you \(Format.amount(p.owes))", sub: nil)
                    }
                }
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Remove the split", busy: busy,
                              busyLabel: "Removing…", secondary: "Keep the split",
                              onPrimary: { Task { await remove() } }, onSecondary: onClose)
        }
    }

    private func row(symbol: String? = nil, face: String? = nil, title: String, sub: String?) -> some View {
        HStack(spacing: 12) {
            if let symbol = symbol { PearlBubble(symbol: symbol) } else { PearlFace(name: face ?? "", size: 40) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                if let sub = sub { Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted) }
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 10).frame(minHeight: 56)
        .accessibilityElement(children: .combine)
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t remove the split. Nothing changed. Try again."
        }
    }
}

// MARK: - AM-21j / AM-08n Change your share? (JOINT-B)

/// The server's needs_confirm: each split purchase a change of her part
/// changes, before anything is saved.
struct JointChange: Decodable, Hashable, Identifiable {
    let chargeId: String
    let merchant: String
    let date: String
    let mode: String
    let partWas: Double
    let partNow: Double
    let yoursWas: Double
    let yoursNow: Double
    let people: [Person]
    let paid: Bool
    var id: String { chargeId }

    struct Person: Decodable, Hashable {
        let name: String
        let paid: Double
        let shareWas: Double
        let shareNow: Double
        enum CodingKeys: String, CodingKey {
            case name, paid
            case shareWas = "share_was"
            case shareNow = "share_now"
        }
    }

    enum CodingKeys: String, CodingKey {
        case merchant, date, mode, people, paid
        case chargeId = "charge_id"
        case partWas = "part_was"
        case partNow = "part_now"
        case yoursWas = "yours_was"
        case yoursNow = "yours_now"
    }
}

/// What a joint change answered: saved, or asking first.
struct JointReply: Decodable {
    let ok: Bool?
    let needsConfirm: Bool?
    let notJoint: Bool?
    let changes: [JointChange]?
    let account: AccountsOverview.Account?
    let undo: JSONValue?
    let toast: String?

    enum CodingKeys: String, CodingKey {
        case ok, changes, account, undo, toast
        case needsConfirm = "needs_confirm"
        case notJoint = "not_joint"
    }
}

/// AM-21j "Change your share to 60%?" (someone already paid her back on a
/// split purchase), or AM-08n "Not a joint account?" (her splits stay,
/// people owe the same, her share takes the rest).
struct JointChangeSheet: View {
    let accountName: String
    /// nil: not joint any more (AM-08n).
    let share: Double?
    let was: Double?
    let holders: [String]
    let changes: [JointChange]
    /// Whose was it? on one split purchase ("the same sheet for that one
    /// purchase", note 1110:6504): its part, not the account's share.
    var purchase = false
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var title: String {
        if purchase { return "Change your part to \(Format.amount(changes.first?.partNow ?? 0))?" }
        return share.map { "Change your share to \(Self.pct($0))?" } ?? "Not a joint account?"
    }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(symbol: "person.2",
                             overline: purchase ? "\(accountName) · Whose was it?"
                                 : share == nil ? accountName : "\(accountName) · Your share",
                             title: title,
                             sub: share == nil && !purchase ? "Every purchase on it will count as all yours."
                                 : "Someone already paid you back on \(purchase ? "this split" : "a split purchase").",
                             close: onClose)
                .disabled(busy)
            PearlSectionLabel(text: share == nil ? "Split purchases" : "Split purchases that change")
            PearlOptionCard {
                ForEach(Array(changes.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { PearlDivider() }
                    HStack(alignment: .top, spacing: 12) {
                        PearlFace(name: c.merchant, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(c.merchant) · \(Format.short(c.date))").font(Pearl.text(.headline, .medium))
                                .foregroundColor(Pearl.ink)
                            Text(line(c)).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 10)
                    .accessibilityElement(children: .combine)
                }
            }
            // REFRESH-03 (AM-08n, AM-21j).
            Text(share == nil && !purchase
                 ? "\(holders.isEmpty ? "No one" : Format.andList(holders)) \(holders.count > 1 ? "come" : "comes") off this account."
                 : "Typed amounts stay. Even, % and shares update.")
                .font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again"
                                  : purchase ? "Change my part"
                                  : share.map { "Change to \(Self.pct($0))" } ?? "Not joint any more",
                              busy: busy, busyLabel: "Saving…",
                              secondary: purchase ? "Keep it as it is" : share == nil ? "Keep it joint"
                                  : was.map { "Keep \(Self.pct($0))" } ?? "Keep it as it is",
                              onPrimary: { Task { await save() } }, onSecondary: onClose)
        }
    }

    /// REFRESH-03 (AM-21j, AM-08n): "Your part $50.00 → $60.00 · Jo owes
    /// $3.34 more", "Your part $20.00 → $24.00", "Your share $16.68 → $66.68".
    private func line(_ c: JointChange) -> String {
        if share == nil && !purchase {
            return "Your share \(Format.amount(c.yoursWas)) → \(Format.amount(c.yoursNow))"
        }
        var bits = ["Your part \(Format.amount(c.partWas)) → \(Format.amount(c.partNow))"]
        for p in c.people where p.paid >= 0.005 {
            let more = p.shareNow - p.paid
            if more >= 0.005 { bits.append("\(p.name) owes \(Format.amount(more)) more") }
            else if more <= -0.005 { bits.append("you owe \(p.name) \(Format.amount(-more))") }
        }
        return bits.joined(separator: " · ")
    }

    static func pct(_ x: Double) -> String { x == x.rounded() ? "\(Int(x))%" : String(format: "%.1f%%", x) }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t save that. Nothing changed. Try again."
        }
    }
}

// MARK: - AM-08x Remove someone from a joint account (JOINT-A)

struct RemoveJointPersonSheet: View {
    let name: String
    let accountName: String
    let others: [String]
    let share: Double?
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var first: String { name.split(separator: " ").first.map(String.init) ?? name }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: name, overline: "Shared with · \(accountName)", title: "Remove \(name)?",
                             sub: "\(first) won’t be on this account any more.", close: onClose)
                .disabled(busy)
            // REFRESH-03 (AM-08x): two facts, each once.
            PearlOptionCard {
                row("person.2", share.map { "Your share stays \(JointChangeSheet.pct($0))" } ?? "Your purchases count as they do now",
                    others.isEmpty ? "The account stays joint, with no one named" : nil)
                PearlDivider()
                row("checkmark", "Earlier answers stay", nil)
            }
            Text("Nothing is sent to \(first).").font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity)
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Remove \(first)", busy: busy, busyLabel: "Removing…",
                              secondary: "Keep \(first)", onPrimary: { Task { await save() } }, onSecondary: onClose)
        }
    }

    private func row(_ symbol: String, _ title: String, _ sub: String?) -> some View {
        HStack(spacing: 12) {
            PearlBubble(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                if let sub = sub { Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted) }
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch {
            failed = "Couldn’t remove \(first). Nothing changed. Try again."
        }
    }
}

// MARK: - S-45 Settle up (SPLIT-C)

/// S-45a "How do you want to settle?": PAID SO FAR, then Use what each
/// paid (S-45b confirms) or Type amounts (How to split, S-45c–e).
struct SettleUpSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let onType: () -> Void
    /// S-45b's Settle up; throws to show S-45bx.
    let run: () async throws -> Void
    @State private var confirming = false
    @State private var busy = false
    @State private var failed: String?

    private var still: Double { split.still ?? split.you }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            if confirming { confirm } else { choose }
        } footer: {
            if confirming {
                PearlSheetButtons(primary: failed != nil ? "Try again" : "Settle up", busy: busy, busyLabel: "Settling…",
                                  secondary: "Back", onPrimary: { Task { await save() } },
                                  onSecondary: { confirming = false; failed = nil })
            }
        }
    }

    @ViewBuilder private var choose: some View {
        PearlSheetHeader(face: t.merchant, overline: "Settle up · \(t.merchant)", title: "How to settle?",
                         close: onClose)
        PearlSectionLabel(text: "Paid so far")
        PearlOptionCard {
            ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                if i > 0 { PearlDivider() }
                amountRow(p.name, sub: paidSub(p), amount: p.paid, tone: p.paid >= 0.005 ? Pearl.moneyIn : Pearl.muted)
            }
            PearlDivider()
            amountRow("You", sub: "What still counts as yours", amount: still, tone: Pearl.ink)
        }
        PearlOptionCard {
            // REFRESH-03 (S-45a): the amounts are in Paid so far above.
            PearlOptionRow(symbol: "checkmark", title: "Use what each paid", sub: "Nobody owes after this.") {
                confirming = true
            }
            PearlDivider()
            PearlOptionRow(symbol: "person.2", title: "Type amounts", sub: "Evenly, amounts, % or shares", action: onType)
        }
    }

    /// S-45b: WHAT CHANGES, and Allowance doesn't.
    @ViewBuilder private var confirm: some View {
        PearlSheetHeader(face: t.merchant, overline: "Settle up · \(t.merchant)", title: "Use what each paid?",
                         close: onClose)
            .disabled(busy)
        PearlSectionLabel(text: "What changes")
        PearlOptionCard {
            ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                if i > 0 { PearlDivider() }
                // Decision 3: someone who paid nothing stays, at $0.00.
                amountRow("\(possessive(p.name)) share", sub: p.paid >= 0.005 ? "Paid in full" : "Nothing to pay",
                          amount: p.paid, tone: p.paid >= 0.005 ? Pearl.moneyIn : Pearl.muted)
            }
            PearlDivider()
            amountRow("Your share", sub: t.label, amount: still, tone: Pearl.ink)
            PearlDivider()
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Allowance").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    Text("\(t.merchant) already counts as \(Format.amount(still))").font(Pearl.text(.callout))
                        .foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text("No change").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.muted)
            }
            .padding(.vertical, 10)
            .accessibilityElement(children: .combine)
        }
        if let failed = failed { CautionBanner(text: failed) }
    }

    private func paidSub(_ p: Transaction.Splitting.Person) -> String {
        guard p.paid >= 0.005 else { return "Nothing yet" }
        let how = p.links?.last.map { PersonOptionsSheet.word($0) } ?? "Paid"
        return [how, p.paidOn.map { Format.short($0) }].compactMap { $0 }.joined(separator: " · ")
    }

    private func amountRow(_ title: String, sub: String, amount: Double, tone: Color) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(Format.amount(amount)).font(Pearl.text(.headline, .semibold)).monospacedDigit().foregroundColor(tone)
        }
        .padding(.vertical, 10).frame(minHeight: 56)
        .accessibilityElement(children: .combine)
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t settle up. Nothing changed. Try again."
        }
    }
}

// MARK: - S-46a That's everything? (SPLIT-C)

struct ThatsEverythingSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var still: Double { split.still ?? split.you }

    var body: some View {
        let paid = split.people.filter { $0.paid >= 0.005 }
        let none = split.people.filter { $0.paid < 0.005 }
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: t.merchant, overline: "That’s everything · \(t.merchant)", title: "That’s everything?",
                             close: onClose)
                .disabled(busy)
            Text(lead(paid)).font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            PearlSectionLabel(text: "What changes")
            PearlOptionCard {
                row(t.label, "Stays your spending", Format.amount(still), Pearl.ink)
                ForEach(none) { p in
                    PearlDivider()
                    row(p.name, "Won’t show as owing", "Done", Pearl.muted)
                }
                PearlDivider()
                row("Allowance", "Already counts the \(Format.amount(still))", "No change", Pearl.muted)
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "That’s everything", busy: busy, busyLabel: "Closing…",
                              secondary: "Keep it open", onPrimary: { Task { await close() } }, onSecondary: onClose)
        }
    }

    /// S-46a (REFRESH-03): "$80.00 stays yours. Nobody owes for Pizza Nova."
    private func lead(_ paid: [Transaction.Splitting.Person]) -> String {
        "\(Format.amount(still)) stays yours. Nobody owes for \(t.merchant)."
    }

    private func row(_ title: String, _ sub: String, _ value: String, _ tone: Color) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(value).font(Pearl.text(.headline, .medium)).monospacedDigit().foregroundColor(tone)
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private func close() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch {
            failed = "Couldn’t close it. Nothing changed. Try again."
        }
    }
}

// MARK: - S-45e What's the extra? when settling (SPLIT-C decision 6)

/// The SPLIT-19 extra step (S-11c) for a settled share below what someone
/// already paid: they overpaid, it pays their share on another purchase, a
/// gift, or she gave it back. One person at a time; nothing is saved until
/// every extra is said, then the split saves with it.
struct SettleExtraSheet: View {
    let api: APIClient
    let merchant: String
    let chargeId: String
    /// Name → how much they paid over their new share.
    let over: [(name: String, amount: Double)]
    let onClose: () -> Void
    /// The pieces for each name, to send as the split's `extra`; throws to show the error.
    let run: ([String: [[String: Any]]]) async throws -> Void

    @State private var at = 0
    @State private var pieces: [String: [[String: Any]]] = [:]
    @State private var choosing = false
    @State private var shares: [MarkPaidSheet.OpenShare] = []
    @State private var ticked: [String: Double] = [:]
    @State private var busy = false
    @State private var failed: String?

    private var who: String { over[min(at, over.count - 1)].name }
    private var whole: Double { over[min(at, over.count - 1)].amount }
    private var left: Double {
        let said = (pieces[who] ?? []).compactMap { $0["amount"] as? Double }.reduce(0, +)
        return max(0, ((whole - said) * 100).rounded() / 100)
    }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: who, overline: "Settle up · \(merchant)",
                             title: choosing ? "Which of \(possessive(who)) shares?" : "What’s the extra \(Format.amount(left))?",
                             sub: "\(who) already paid you more than their share.",
                             back: choosing ? { choosing = false } : nil, close: onClose)
                .disabled(busy)
            if choosing { shareList } else {
                CaseGrid(cases: CaseTile.cashExtra(who: who, app: false),
                         chosen: Binding(get: { nil }, set: { key in if let key = key { take(key) } }))
                    .disabled(busy)
                Text("\(possessive(who)) share of \(merchant) is set, so the other \(Format.amount(left)) needs saying. Nothing is saved until you do.")
                    .font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            if choosing {
                PearlSheetButtons(primary: "Next", busy: busy) { takeShares() }
                    .disabled(ticked.isEmpty)
            } else if failed != nil {
                PearlSheetButtons(primary: "Try again", busy: busy, busyLabel: "Saving…") { Task { await save() } }
            }
        }
    }

    private var shareList: some View {
        VStack(alignment: .leading, spacing: 8) {
            if shares.isEmpty {
                Text("\(who) doesn’t owe you on anything else.").font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            } else {
                PearlOptionCard {
                    ForEach(Array(shares.enumerated()), id: \.element.id) { i, s in
                        if i > 0 { PearlDivider() }
                        let on = ticked[s.id] != nil
                        Button {
                            if on { ticked[s.id] = nil } else {
                                let room = Int((left * 100).rounded()) - ticked.values.map { Int(($0 * 100).rounded()) }.reduce(0, +)
                                if room > 0 { ticked[s.id] = Double(min(Int((s.owes * 100).rounded()), room)) / 100 }
                            }
                        } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.merchant).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                                    Text("Owes \(Format.amount(s.owes)) · \(Format.short(s.date))")
                                        .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                                }
                                Spacer(minLength: 8)
                                Text(Format.amount(ticked[s.id] ?? s.owes)).font(Pearl.text(.headline)).monospacedDigit()
                                    .foregroundColor(Pearl.ink)
                                Image(systemName: on ? "checkmark.circle.fill" : "circle").font(.system(size: 22))
                                    .foregroundColor(on ? Pearl.action : Pearl.muted).frame(width: 44, height: 44)
                            }
                            .frame(minHeight: 56).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(on ? .isSelected : [])
                    }
                }
            }
        }
    }

    private func take(_ key: String) {
        failed = nil
        if key == "payback" {
            Task { await loadShares() }
            return
        }
        pieces[who, default: []].append(["kind": key, "amount": left])
        next()
    }

    private func takeShares() {
        for s in shares {
            guard let use = ticked[s.id], use >= 0.005 else { continue }
            pieces[who, default: []].append(["kind": "payback", "amount": use, "charge": s.charge, "person": s.person])
        }
        ticked = [:]
        choosing = false
        next()
    }

    /// The next person's extra, or save once all of it is said.
    private func next() {
        if left >= 0.005 { return }
        if at + 1 < over.count { at += 1 } else { Task { await save() } }
    }

    /// Their other open shares (Paying me back: S-09 for the extra).
    private func loadShares() async {
        struct Item: Decodable {
            let chargeId: String
            let merchant: String
            let date: String
            let owes: Double
            enum CodingKeys: String, CodingKey { case chargeId = "charge_id"; case merchant, date, owes }
        }
        struct Row: Decodable { let name: String; let items: [Lenient<Item>] }
        struct Reply: Decodable { let owesYou: [Lenient<Row>]; enum CodingKeys: String, CodingKey { case owesYou = "owes_you" } }
        do {
            let r: Reply = try await api.get("api/owed")
            shares = r.owesYou.compactMap(\.value).filter { samePerson($0.name, who) }.flatMap { row in
                row.items.compactMap(\.value).filter { $0.chargeId != chargeId }.map {
                    MarkPaidSheet.OpenShare(charge: $0.chargeId, merchant: $0.merchant, date: $0.date,
                                            person: row.name, owes: $0.owes, theirs: true)
                }
            }
            choosing = true
        } catch {
            failed = "Couldn’t load who owes you. Try again."
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run(pieces)
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t settle up. Nothing changed. Try again."
        }
    }
}

// MARK: - S-03u's method list at accessibility sizes (SPLIT-C)

/// The five methods in a Pearl list sheet, for when the segments don't fit
/// (note 1120:9270: same pattern as Edit split).
struct SplitMethodSheet: View {
    let modes: [(tag: String, label: String)]
    let chosen: String
    let onPick: (String) -> Void
    let onClose: () -> Void

    var body: some View {
        PearlSheet {
            PearlSheetHeader(overline: "How to split", title: "Pick a method", close: onClose)
            PearlOptionCard {
                ForEach(Array(modes.enumerated()), id: \.element.tag) { i, m in
                    if i > 0 { PearlDivider() }
                    Button { onPick(m.tag) } label: {
                        HStack {
                            Text(m.label).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                            Spacer()
                            if m.tag == chosen {
                                Image(systemName: "checkmark").foregroundColor(Pearl.action).accessibilityHidden(true)
                            }
                        }
                        .frame(minHeight: 52).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(m.label), split method, \(i + 1) of \(modes.count)")
                    .accessibilityAddTraits(m.tag == chosen ? .isSelected : [])
                }
            }
        }
    }
}
