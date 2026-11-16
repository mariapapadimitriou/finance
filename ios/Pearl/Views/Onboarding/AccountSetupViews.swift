import SwiftUI

// Account setup (Pearl iOS Handoff File, Proposals › "Account setup"
// 1380:75770, note 1380:76572; THL-120, THL-172, THL-300, THL-294, THL-304,
// THL-305; approved by the product owner 2026-11-15):
//
// AS-01 1380:75771 / 1380:75917  Your accounts: every linked account and,
//       on one line, how it counts and who shares it. "These look right"
//       finishes the step, changed or not (decision 2). Part 3 of setup,
//       and Set Pearl up again's "Check your accounts" after Start over.
// AS-02 1380:76064 / 1380:76106  One account, every option on one page:
//       Include in my budget, Shared with someone (inline: who, O-09cr's
//       picker, and how purchases split), Part of my Anchor (savings only),
//       Nickname. Nothing is saved until Save.
//
// They replace O-09b, O-09b2, O-09c and SU-02 ("Which accounts do you
// share?") and Set Pearl up again's two account items. Accounts › AM-02 and
// AM-04 stay as they are; AS-02 sends the same settings to the same
// endpoint (PUT api/accounts/<id>/settings).

enum AccountSetupWords {
    /// AS-01's line: "In your budget · Joint, your share 50%", "In your
    /// budget · Just you · Anchor", "Not in your budget" (an investment).
    static func line(_ a: AccountsOverview.Account) -> String {
        if a.kind == "investment" { return "Not in your budget" }
        var parts = [(a.counted ?? true) ? "In your budget" : "Not in your budget"]
        if a.joint == true {
            // "Each purchase: mine unless I say" has no share to give.
            parts.append(a.jointShare.map { "Joint, your share \(JointChangeSheet.pct($0))" } ?? "Joint")
        } else {
            parts.append("Just you")
        }
        if a.anchor == true { parts.append("Anchor") }
        return parts.joined(separator: " · ")
    }
}

// MARK: - AS-01 Your accounts

@MainActor
struct AccountSetupView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @Binding var path: [SetupRoute]
    /// Set Pearl up again's "Check your accounts" (AS-04): the same page,
    /// without setup's progress, ending back where she came from.
    var onDone: (() async -> Void)? = nil
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NacreScreen {
            if onDone == nil { ShellProgress(part: 3, name: "Your money") }
            Text("Your accounts").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("Pearl set these up. Tap one to change how it counts or who shares it.").font(Nacre.body)
                .fixedSize(horizontal: false, vertical: true)
            if !accounts.isEmpty {
                GlassCard {
                    ForEach(Array(accounts.enumerated()), id: \.element.id) { i, account in
                        if i > 0 { RowSeparator(inset: 60) }
                        NavigationLink {
                            AccountSetupPage(account: account) { await load() }
                        } label: {
                            AccountLine(account: account, sub: AccountSetupWords.line(account),
                                        trailing: AnyView(Image(systemName: "chevron.right")
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundColor(Pearl.muted)
                                            .accessibilityHidden(true)))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("These look right") { Task { await finish() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy)
            }
        }
        // Again on the way back from AS-02, so each line says what was saved.
        .onAppear { Task { await load() } }
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

    /// Decision 2: done, even with nothing changed.
    private func finish() async {
        if let onDone = onDone {
            busy = true
            await onDone()
            busy = false
            dismiss()
        } else {
            path.append(.payBills)
        }
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

    /// AS-02's hero: the bank's letters, the name, the balance and the
    /// account's pill, as on AM-08.
    private var hero: some View {
        VStack(spacing: 10) {
            NacreAvatar(text: account.bankLetters, size: 56)
            Text(account.name).font(Nacre.title2).foregroundColor(Pearl.ink)
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
