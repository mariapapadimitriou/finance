import SwiftUI
import UIKit

// Account setup (Pearl iOS Handoff File, Proposals › "Account setup"
// 1380:75770, note 1380:76572; THL-120, THL-172, THL-300, THL-294, THL-304,
// THL-305; approved by the product owner 2026-11-15), and Your accounts v2
// (Proposals › "Your accounts v2" 1415:6440, note 1415:88764; approved
// 2026-11-16):
//
// AS-01 v2 1415:87857 / 1415:88299  Your accounts, grouped: Everyday
//       (chequing and cards), Savings & borrowing, Not in your budget. A row
//       is the account's kind and its short name; a tag only where it
//       differs from the default (Joint · 50%, Anchor). Accounts left out of
//       the budget from one bank collapse into one row that opens in place.
//       "These look right" ends the list and scrolls with it; it finishes
//       the step, changed or not (decision 2). Part 3 of setup, and Set
//       Pearl up again's "Check your accounts" after Start over.
//       LT-04 1425:7857 / 1425:8059 (Less text, TEXT-01): the lead is "Check
//       what counts and what you share."; no footer over the button.
// AS-02 1380:76064 / 1380:76106  One account, every option on one page:
//       Include in my budget, Shared with someone (inline: who, O-09cr's
//       picker, and how purchases split), Part of my Anchor (savings only),
//       Nickname. Nothing is saved until Save. v2: the header shows the same
//       kind icon and short name as AS-01's row.
//
// They replace O-09b, O-09b2, O-09c and SU-02 ("Which accounts do you
// share?") and Set Pearl up again's two account items. Accounts › AM-02 and
// AM-04 stay as they are; AS-02 sends the same settings to the same
// endpoint (PUT api/accounts/<id>/settings).

enum AccountSetupWords {
    /// Counts toward Allowance: an investment never does (AS-02 greys it).
    static func counts(_ a: AccountsOverview.Account) -> Bool {
        a.kind != "investment" && (a.counted ?? true)
    }

    /// The server's short name (finance/account_names.py).
    static func name(_ a: AccountsOverview.Account) -> String { a.shortName ?? a.name }

    /// The library Category icon for the kind (1415:87857): cash for
    /// chequing, card, saved for savings and investing, rent for a mortgage
    /// or loan.
    static func symbol(_ a: AccountsOverview.Account) -> String {
        switch a.kind {
        case "card": return "creditcard"
        case "savings", "investment": return "lifepreserver"
        case "loan": return "house"
        default: return "banknote"
        }
    }

    /// AM-01's tags, only where the account differs from the default.
    static func tags(_ a: AccountsOverview.Account) -> [StatusPill] {
        var out: [StatusPill] = []
        if a.joint == true {
            out.append(StatusPill(text: a.jointShare.map { "Joint · \(Int($0.rounded()))%" } ?? "Joint", tone: .joint))
        }
        if a.anchor == true { out.append(StatusPill(text: "Anchor", tone: .info)) }
        return out
    }

    /// "7 in your budget · 1 shared · 3 not counted".
    static func summary(_ accounts: [AccountsOverview.Account]) -> String {
        let counted = accounts.filter(counts).count
        let shared = accounts.filter { $0.joint == true }.count
        return "\(counted) in your budget · \(shared) shared · \(accounts.count - counted) not counted"
    }

    /// VoiceOver (note 1415:88764): "TD Preferred Chequing, anchor account,
    /// in your budget"; "Scotia Preferred Package, joint, your share 50
    /// percent, in your budget".
    static func spoken(_ a: AccountsOverview.Account) -> String {
        var parts = [name(a)]
        if a.joint == true {
            parts.append("joint")
            if let s = a.jointShare { parts.append("your share \(Int(s.rounded())) percent") }
        }
        if a.anchor == true { parts.append("anchor account") }
        parts.append(counts(a) ? "in your budget" : "not in your budget")
        return parts.joined(separator: ", ")
    }

    /// A row in Not in your budget: one account, or a bank's together.
    enum LeftOut: Identifiable {
        case one(AccountsOverview.Account)
        case bank(String, [AccountsOverview.Account])

        var id: String {
            switch self {
            case .one(let a): return a.id
            case .bank(let bank, _): return "bank:" + bank
            }
        }
    }

    /// Accounts from one bank that are all left out collapse into one row
    /// ("Scotia iTRADE · 3 accounts"); a bank with one stays a plain row.
    static func leftOut(_ accounts: [AccountsOverview.Account]) -> [LeftOut] {
        var order: [String] = []
        var byBank: [String: [AccountsOverview.Account]] = [:]
        for a in accounts {
            let key = (a.shortBank ?? "").isEmpty ? "id:" + a.id : a.shortBank!
            if byBank[key] == nil { order.append(key) }
            byBank[key, default: []].append(a)
        }
        return order.map { key in
            let group = byBank[key] ?? []
            return group.count > 1 ? .bank(key, group) : .one(group[0])
        }
    }
}

// MARK: - AS-01 Your accounts

@MainActor
struct AccountSetupView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Binding var path: [SetupRoute]
    /// Set Pearl up again's "Check your accounts" (AS-04): the same page,
    /// without setup's progress, ending back where she came from.
    var onDone: (() async -> Void)? = nil
    @State private var accounts: [AccountsOverview.Account] = []
    /// The banks whose left-out accounts are open in place.
    @State private var open: Set<String> = []
    @State private var opened = false
    @State private var busy = false
    @State private var error: String?

    private var everyday: [AccountsOverview.Account] {
        accounts.filter { AccountSetupWords.counts($0) && $0.kind != "savings" && $0.kind != "loan" }
    }
    private var savings: [AccountsOverview.Account] {
        accounts.filter { AccountSetupWords.counts($0) && ($0.kind == "savings" || $0.kind == "loan") }
    }
    private var leftOut: [AccountsOverview.Account] { accounts.filter { !AccountSetupWords.counts($0) } }

    var body: some View {
        NacreScreen {
            if onDone == nil { ShellProgress(part: 3, name: "Your money", opened: opened) }
            Text("Your accounts").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("Check what counts and what you share.")
                .font(Nacre.body).fixedSize(horizontal: false, vertical: true)
            if !accounts.isEmpty {
                Text(AccountSetupWords.summary(accounts)).font(Nacre.footnote).foregroundColor(Pearl.muted)
                group("Everyday", everyday)
                group("Savings & borrowing", savings)
                leftOutGroup
            }
            if let error = error { Hint(text: error) }
            // At the end of the list, scrolling with it: it never covers a row.
            Button("These look right") { Task { await finish() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
        } actions: {
            EmptyView()
        }
        // Again on the way back from AS-02, so each row says what was saved.
        .onAppear {
            opened = false
            Task { await load() }
        }
    }

    @ViewBuilder
    private func group(_ title: String, _ rows: [AccountsOverview.Account]) -> some View {
        if !rows.isEmpty {
            ProfileSection(title)
            GlassCard(radius: 22) {
                ForEach(Array(rows.enumerated()), id: \.element.id) { i, a in
                    if i > 0 { RowSeparator() }
                    link(a, tags: AccountSetupWords.tags(a))
                }
            }
        }
    }

    /// Not in your budget: the header says so, so these rows carry no
    /// "not counted" tag.
    @ViewBuilder
    private var leftOutGroup: some View {
        let rows = AccountSetupWords.leftOut(leftOut)
        if !rows.isEmpty {
            ProfileSection("Not in your budget")
            GlassCard(radius: 22) {
                ForEach(Array(rows.enumerated()), id: \.element.id) { i, row in
                    if i > 0 { RowSeparator() }
                    switch row {
                    case .one(let a):
                        link(a, tags: AccountSetupWords.tags(a))
                    case .bank(let bank, let group):
                        bankRows(bank, group)
                    }
                }
            }
        }
    }

    /// "Scotia iTRADE · 3 accounts" over their short names; a tap opens
    /// them in place, and each opens AS-02.
    @ViewBuilder
    private func bankRows(_ bank: String, _ group: [AccountsOverview.Account]) -> some View {
        let isOpen = open.contains(bank)
        let names = Format.andList(group.map { $0.shortProduct ?? AccountSetupWords.name($0) })
        Button {
            withAnimation(reduceMotion ? .easeInOut(duration: 0.2) : .spring(response: 0.35, dampingFraction: 0.85)) {
                if isOpen { open.remove(bank) } else { open.insert(bank) }
            }
        } label: {
            AccountKindRow(symbol: AccountSetupWords.symbol(group[0]), title: "\(bank) · \(group.count) accounts",
                           sub: names, chevronTurned: isOpen)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(bank), \(group.count) accounts, \(names), not in your budget")
        .accessibilityValue(isOpen ? "Expanded" : "Collapsed")
        .accessibilityHint(isOpen ? "Hides the accounts" : "Shows the accounts")
        if isOpen {
            ForEach(group) { a in
                RowSeparator()
                link(a, tags: AccountSetupWords.tags(a))
            }
        }
    }

    private func link(_ a: AccountsOverview.Account, tags: [StatusPill]) -> some View {
        NavigationLink {
            AccountSetupPage(account: a) { await load() }
        } label: {
            AccountKindRow(symbol: AccountSetupWords.symbol(a), title: AccountSetupWords.name(a), tags: tags)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(AccountSetupWords.spoken(a))
    }

    private func load() async {
        do {
            let overview: AccountsOverview = try await app.api.get("api/accounts/overview")
            accounts = overview.linked
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Decision 2: done, even with nothing changed. In setup the third
    /// shell opens first (350 ms spring, a fade with Reduce Motion) with a
    /// success haptic (note 1415:88764).
    private func finish() async {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        if let onDone = onDone {
            busy = true
            await onDone()
            busy = false
            dismiss()
        } else {
            withAnimation(reduceMotion ? .easeInOut(duration: 0.35) : .spring(response: 0.35, dampingFraction: 0.6)) {
                opened = true
            }
            try? await Task.sleep(nanoseconds: 350_000_000)
            path.append(.payBills)
        }
    }
}

/// AS-01 v2's row (1415:87990): the kind's icon, the short name, a line
/// or the tags under it, and the chevron.
struct AccountKindRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var tags: [StatusPill] = []
    /// A bank's row turns its chevron down while its accounts are open.
    var chevronTurned = false

    var body: some View {
        HStack(spacing: 12) {
            KindAvatar(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !tags.isEmpty {
                    HStack(spacing: 6) { ForEach(Array(tags.enumerated()), id: \.offset) { $0.element } }
                }
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Pearl.muted)
                .rotationEffect(.degrees(chevronTurned ? 90 : 0))
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, sub == nil && tags.isEmpty ? 14 : 10)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// The circle that says what kind of account it is (1415:87991): a
/// Category icon in action rose on glass, with the shell-pink edge.
struct KindAvatar: View {
    let symbol: String
    var size: CGFloat = 36

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.5))
            .foregroundColor(Pearl.action)
            .frame(width: size, height: size)
            .background(Circle().fill(Nacre.glass))
            .overlay(Circle().strokeBorder(Nacre.edge, lineWidth: 1.5))
            .accessibilityHidden(true)
    }
}


// MARK: - AS-02 One account

@MainActor
struct AccountSetupPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var account: AccountsOverview.Account
    /// AS-01 reads the accounts again.
    let saved: () async -> Void

    /// HOW PURCHASES SPLIT: 50/50, her share, or every purchase hers until
    /// she marks one (joint_share "auto", finance/joint.py).
    enum Split: Hashable { case half, share, mine }

    @State private var counted = true
    @State private var shared = false
    @State private var anchor = false
    @State private var nickname = ""
    @State private var people: [String] = []
    @State private var split: Split = .half
    @State private var shareText = ""
    @State private var picking = false
    @State private var naming = false
    @State private var nameDraft = ""
    /// AM-21j / AM-08n: the server's needs_confirm, and what to send again.
    @State private var asking: Asking?
    @State private var busy = false
    @State private var error: String?
    @State private var started = false

    struct Asking: Identifiable {
        let body: [String: Any]
        let share: Double?
        let changes: [JointChange]
        let id = UUID()
    }

    private var isInvestment: Bool { account.kind == "investment" }
    private var enteredShare: Double? {
        Double(shareText.replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespaces))
    }
    private var shareIsValid: Bool { enteredShare.map { $0 >= 1 && $0 <= 99 } ?? false }

    /// The share to save: 50, hers, or nil for "Each purchase: mine unless I say".
    private var wantedShare: Double? {
        switch split {
        case .half: return 50
        case .share: return enteredShare
        case .mine: return nil
        }
    }

    var body: some View {
        ProfilePage {
            hero
            GlassCard {
                toggleRow(title: "Include in my budget",
                          hint: isInvestment ? "Spending doesn’t happen from an investment account."
                              : "Its spending, bills and balance count toward Allowance and your totals on Home.",
                          on: $counted, disabled: isInvestment)
                if !isInvestment {
                    RowSeparator()
                    toggleRow(title: "Shared with someone", hint: "Only your share counts.",
                              on: Binding(get: { shared }, set: { v in withAnimation { shared = v } }))
                }
                if account.canAnchor == true {
                    RowSeparator()
                    toggleRow(title: "Part of my Anchor", hint: "Savings accounts only", on: $anchor)
                }
                RowSeparator()
                Button { nameDraft = nickname; naming = true } label: {
                    ProfileRow(title: "Nickname", sub: nil) {
                        Text(nickname.isEmpty ? "Add" : nickname)
                            .font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
            if shared {
                GlassCard {
                    // O-09cr: who, picked, not typed.
                    Button { picking = true } label: {
                        ProfileRow(title: "Shared with") {
                            Text(people.isEmpty ? "Add" : people.joined(separator: " and "))
                                .font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    .accessibilityHint("Opens the people you’ve split with and your contacts")
                }
                .padding(.top, 4)
                ProfileSection("How purchases split")
                GlassCard {
                    PickRow(title: "Half each (50/50)", selected: split == .half) { split = .half }
                    RowSeparator()
                    PickRow(title: "A different share", selected: split == .share) {
                        if split != .share && shareText.isEmpty { shareText = "50" }
                        split = .share
                    }
                    RowSeparator()
                    PickRow(title: "Each purchase: mine unless I say", selected: split == .mine) { split = .mine }
                }
                if split == .share {
                    GlassCard {
                        InlineField(label: "Your share", text: $shareText, prompt: "50",
                                    keyboard: .decimalPad, suffix: "%")
                    }
                    .padding(.top, 4)
                }
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || (shared && split == .share && !shareIsValid))
        }
        .onAppear {
            // Once: coming back from the picker or the nickname sheet keeps
            // what she has changed on the page.
            guard !started else { return }
            started = true
            fill()
        }
        .sheet(isPresented: $picking) {
            // AM-08p from setup (O-09cr): the same picker. Nothing saves until Save.
            PeoplePicker(api: app.api, overline: "\(account.name) · Joint", title: "Shared with",
                         sub: "Up to six. Only you see this.", already: people, limit: 6,
                         onClose: { picking = false }) { picked in
                people = Array((people + picked.filter { !people.contains($0) }).prefix(6))
                picking = false
            }
        }
        .sheet(isPresented: $naming) {
            // AM-09n's sheet. The name is kept on the page until Save.
            PearlConfirmSheet(overline: [account.name, (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"]
                                .compactMap { $0 }.joined(separator: " "),
                              title: "Nickname", message: "A name you’ll recognise. It shows everywhere in Pearl.",
                              field: .init(label: "Nickname", prompt: account.name, identifier: "nickname"),
                              text: $nameDraft, primary: "Save",
                              onClose: { naming = false }) {
                nickname = nameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                naming = false
            }
        }
        .sheet(item: $asking) { a in
            JointChangeSheet(accountName: account.name, share: a.share, was: account.jointShare,
                             holders: account.jointPeople ?? [], changes: a.changes,
                             onClose: { asking = nil }) {
                var body = a.body
                body["confirm"] = true
                _ = try await put(body)
                asking = nil
                await saveRest()
            }
        }
    }

    // MARK: Parts

    /// AS-02's hero: the kind's icon and the short name, as on AS-01 v2's
    /// row (note 1415:88764), then the balance and the account's pill, as
    /// on AM-08.
    private var hero: some View {
        VStack(spacing: 10) {
            KindAvatar(symbol: AccountSetupWords.symbol(account), size: 56)
            Text(AccountSetupWords.name(account)).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            Text(account.balance.map { Format.amount(abs($0)) } ?? "—")
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .tracking(-0.88)
                .foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text([account.owing == true ? "Owing" : account.kindWord, (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"]
                .compactMap { $0 }.joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
            let pill = AccountWords.pill(account)
            StatusPill(text: pill.text, tone: pill.tone)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    /// A setting and its switch; what it does is VoiceOver's hint.
    private func toggleRow(title: String, hint: String, on: Binding<Bool>, disabled: Bool = false) -> some View {
        Toggle(isOn: on) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action)
        .disabled(disabled || busy)
        .accessibilityHint(hint)
        .padding(.horizontal, 16).frame(minHeight: 50)
    }

    private func fill() {
        counted = account.counted ?? true
        shared = account.joint == true
        anchor = account.anchor == true
        nickname = account.nickname ?? ""
        people = account.jointPeople ?? []
        switch (account.joint == true, account.jointShare) {
        case (true, nil): split = .mine
        case (_, let s?) where s != 50:
            split = .share
            shareText = s == s.rounded() ? "\(Int(s))" : "\(s)"
        default: split = .half
        }
    }

    // MARK: Saving

    /// Who shares it and how purchases split first, since a change there can
    /// ask first (AM-21j, AM-08n); then the rest.
    private func save() async {
        error = nil
        var joint: [String: Any] = [:]
        let wasJoint = account.joint == true
        if shared && !isInvestment {
            if !wasJoint || wantedShare != account.jointShare {
                // "auto": joint, every purchase hers until she marks one.
                joint["joint_share"] = wantedShare.map { $0 as Any } ?? "auto"
            }
            if people != (account.jointPeople ?? []) { joint["joint_people"] = people }
        } else if wasJoint {
            joint["joint_share"] = NSNull()
        }
        if !joint.isEmpty {
            busy = true
            let reply: JointReply?
            do {
                reply = try await put(joint)
            } catch {
                busy = false
                self.error = words(error)
                return
            }
            busy = false
            if reply?.needsConfirm == true {
                // AM-21j shows "Each purchase: mine unless I say" as all of each purchase.
                asking = Asking(body: joint, share: shared ? (wantedShare ?? 100) : nil,
                                changes: reply?.changes ?? [])
                return
            }
        }
        await saveRest()
    }

    /// Include in my budget, Part of my Anchor and Nickname, then back to AS-01.
    private func saveRest() async {
        var rest: [String: Any] = [:]
        if !isInvestment && counted != (account.counted ?? true) { rest["counted"] = counted }
        if anchor != (account.anchor == true) { rest["anchor"] = anchor }
        if nickname != (account.nickname ?? "") { rest["nickname"] = nickname }
        if !rest.isEmpty {
            busy = true
            defer { busy = false }
            do {
                _ = try await put(rest)
            } catch {
                self.error = words(error)
                return
            }
        }
        app.changed()
        await saved()
        dismiss()
    }

    /// The server's own words for a refusal on the page.
    private func words(_ error: Error) -> String? {
        (error as? SplitMenuError)?.words ?? app.handle(error)
    }

    /// The PUT; a server refusal comes back in its own words, for a sheet.
    private func put(_ body: [String: Any]) async throws -> JointReply? {
        do {
            let reply: JointReply = try await app.api.put("api/accounts/\(account.id)/settings", body)
            if let a = reply.account { account = a }
            return reply
        } catch let e as APIError {
            if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
            throw e
        }
    }
}
