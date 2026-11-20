import SwiftUI

/// Pearl chat (note 1340:8893, THL-117, THL-139, THL-213, THL-254), the
/// Pearl tab since A+ (REDESIGN-02, -03, -14): a full tab screen with the
/// tab bar showing. The conversation stays across tab switches; "New chat"
/// asks first on a Pearl sheet, then clears it. One exchange at a time, as
/// the Claude Design boards draw it (AP-Chat, G7-*):
///
/// PC-03  AP-Chat / G7-Chat 1  "Pearl", Start with…, On this iPhone only, Message Pearl
///        G7-Chat 2            typing: the composer rides just above the keyboard
///        G7-Chat 3            her bubble, the dots, "Pearl is working it out"
/// PC-04  G7-Chat 4            an answer: the line, its totals, the rows (each opens its page)
/// PC-05/06/08/09 G7-Tell, G7-TellMore  the cards (ChatCards.swift)
/// PC-07  G7-TellMore 1        "Sorted 7. 2 left for later." · 2 back in Needs a look · See the 2
/// PC-10  G7-TellMore 4        couldn't match · Tell it differently
/// PC-11  G7-Unavailable 1     needs Apple Intelligence · Search instead (the tab stays; the bar keeps 5)
///        G7-Unavailable 2     couldn't answer · Try again
///        G7-Unavailable 3     Start a new chat? (a Pearl sheet)
/// PC-12  G7-Confirm 1         a plan to set: Set it · Not now
/// PC-13  G7-Confirm 2         "Done. Dining out plan set to $220 a month." · See it in Your plan · toast with Undo
///        G7-Confirm 3         "Okay, nothing changed."
///        G7-Confirm 4         "Done. Trip to Montréal made." · its row · toast with Undo
@MainActor
struct PearlChatView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var engine: ChatEngine
    @State private var text = ""
    @FocusState private var composing: Bool
    @State private var path: [Route] = []
    @State private var available = PearlIntelligence.available
    /// Opened once: the conversation then stays until New chat.
    @State private var opened = false
    @State private var askingNewChat = false
    /// PC-11's Search instead: Cash flow's search.
    let onSearch: () -> Void

    enum Route: Hashable {
        case transaction(String)
        case needsALook
        case trip(String)
        case rules
        /// PC-13's See it in Your plan: YP-03 while the plan is in use, else YP-01.
        case plan
    }

    /// PC-12/PC-13 plans in chat. Your plan is parked with Save (product
    /// owner, 2026-11-18), so the chat never offers a plan card, never links
    /// "See it in Your plan" and never opens it while YourPlanGate.shown is off.
    static var plans: Bool { Features.chatPlans && YourPlanGate.shown }

    init(api: APIClient, describe: @escaping (Error) -> String, onSearch: @escaping () -> Void) {
        _engine = StateObject(wrappedValue: ChatEngine(
            brain: PearlIntelligence.brain(plans: Self.plans), reader: ChatReader(APIChatReading(api: api)),
            executor: ChatExecutor(writer: APIChatWriting(api: api)), allowsPlans: Self.plans,
            describe: describe))
        self.onSearch = onSearch
    }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                ChatTop(large: largeTitle) { askingNewChat = true }
                content.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                if available {
                    ChatComposer(text: $text, composing: $composing, onDevice: isStart, off: isThinking, send: send)
                }
            }
            .nacreScreen()
            // The profile circle, as on every main tab (in this stack, so
            // Profile pushes here and a chat page covers it).
            .profileCircleSlot()
            .navigationBarHidden(true)
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .transaction(let id): TransactionByID(id: id, categories: app.categories)
                case .needsALook: ReviewView()
                case .trip(let id): TripPage(id: id)
                case .rules: CategoriesRulesView()
                case .plan:
                    // Parked with Save: no way into Your plan from chat.
                    if YourPlanGate.shown { YourPlanView() }
                }
            }
        }
        .task {
            available = PearlIntelligence.available
            guard available, !opened else { return }
            opened = true
            await engine.open()
        }
        .sheet(isPresented: $askingNewChat) {
            // G7-Unavailable 3 (REDESIGN-14): asks first, on a Pearl sheet.
            APConfirmSheet(title: "Start a new chat?",
                           message: "What you told Pearl here is forgotten. Nothing it sorted changes.",
                           primary: "New chat", secondary: "Keep this one",
                           onConfirm: {
                               askingNewChat = false
                               text = ""
                               composing = false
                               path = []
                               Task { await engine.newChat() }
                           },
                           onClose: { askingNewChat = false })
        }
        .onChange(of: engine.mode) { mode in
            // Tell Pearl what you did · Ask about my spending: her words next.
            if mode != nil { composing = true }
        }
    }

    // MARK: The top

    private var isStart: Bool {
        if case .start = engine.screen { return true }
        return false
    }

    private var isThinking: Bool {
        if case .thinking = engine.screen { return true }
        return false
    }

    /// AP-Chat: "Pearl" as a large title on the start and where Apple
    /// Intelligence can't run; over an exchange, "Pearl" inline and centred
    /// with New chat on the right. No Close: it's a tab.
    private var largeTitle: Bool { !available || isStart }

    // MARK: The screens

    @ViewBuilder private var content: some View {
        if !available {
            ChatUnavailable(onSearch: onSearch)
        } else {
            switch engine.screen {
            case .start:
                ChatStarters { mode in Task { await engine.pick(mode) } }
            case .thinking(let said):
                ScrollView { VStack(spacing: 0) { ChatYou(text: said); ChatWorking() }.chatPage() }
            case .reply(let said, let text, let answer, let rows):
                ChatReply(said: said, text: text, answer: answer, rows: rows)
            case .cards(let deck):
                ChatDeckView(engine: engine, deck: deck)
            case .sorted(let sorted, let left):
                ChatSorted(said: engine.heard, sorted: sorted, left: left) { path.append(.needsALook) }
            case .nothing(let line):
                ChatNothing(said: engine.heard, line: line) {
                    // PC-10's Tell it differently puts her back in the composer.
                    engine.restart()
                    engine.mode = .tell
                    composing = true
                }
            case .plan(let said, let p):
                ChatPlanAsk(engine: engine, said: said, plan: p)
            case .done(let said, let notes):
                ChatDone(said: said, notes: notes) { link in path.append(route(link)) }
            case .noChange(let said, let plan):
                ChatNoChange(said: said, plan: plan)
            case .failed(let said):
                ChatFailed(said: said, busy: engine.busy) { Task { await engine.retry() } }
            }
        }
    }

    /// Where a confirmation lives. PC-13's "See it in Your plan" opens Your
    /// plan, which shows YP-03 while the plan is in use and YP-01 otherwise.
    private func route(_ link: DoneLink) -> Route {
        switch link {
        case .trip(let id): return .trip(id)
        case .rules: return .rules
        case .plan: return .plan
        }
    }

    private func send() {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let said = text
        text = ""
        composing = false
        Task { await engine.send(said) }
    }
}

// MARK: - The top

/// The large "Pearl" (Fraunces 34, AP-Chat) or the inline one with New chat.
/// Both sit on the profile circle's line (`ProfileSlot`); the circle is
/// pinned top right, so New chat moved to the bar's left end.
private struct ChatTop: View {
    let large: Bool
    let newChat: () -> Void

    var body: some View {
        if large {
            Text("Pearl").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
                .frame(maxWidth: .infinity, minHeight: ProfileSlot.size, alignment: .leading)
                .padding(.leading, 20).padding(.trailing, ProfileSlot.clearance)
                .padding(.top, ProfileSlot.top)
        } else {
            ZStack {
                Text("Pearl").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                HStack {
                    Button("New chat", action: newChat)
                        .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.link)
                        .buttonStyle(.plain)
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                        .accessibilityHint("Asks first. What you told Pearl here is forgotten.")
                        .accessibilityIdentifier("chat-new")
                    Spacer()
                }
                .padding(.leading, 20).padding(.trailing, ProfileSlot.clearance)
            }
            // Full width, so "Pearl" stays centred on the screen.
            .frame(maxWidth: .infinity)
            .frame(height: ProfileSlot.size)
            .padding(.top, ProfileSlot.top)
        }
    }
}

// MARK: - PC-03 · the start

/// AP-Chat: START WITH, then the four starters on one card.
private struct ChatStarters: View {
    let pick: (ChatMode) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                APSectionLabel(text: "Start with").padding(.top, 40)
                APCard {
                    starter("sparkles", "Tell Pearl what you did", nil, .tell)
                    APSeparator(afterFace: false)
                    starter("bag", "Ask about my spending", "A short answer, with the transactions behind it", .ask)
                    APSeparator(afterFace: false)
                    starter("tv", "Find subscriptions", nil, .subscriptions)
                    APSeparator(afterFace: false)
                    starter("airplane", "Was this a trip?", nil, .trips)
                }
            }
            .chatPage()
        }
    }

    private func starter(_ symbol: String, _ title: String, _ sub: String?, _ mode: ChatMode) -> some View {
        Button { pick(mode) } label: { ChatStarterRow(symbol: symbol, title: title, sub: sub) }
            .buttonStyle(.plain)
            .accessibilityIdentifier("chat-starter-\(mode.rawValue)")
    }
}

// MARK: - PC-04 · an answer

/// G7-Chat 4: her bubble, Pearl's line, the totals ("Dining, October $286",
/// "Usual month $214") and the rows behind them, each opening its page.
private struct ChatReply: View {
    let said: String?
    let text: String
    let answer: SpendingAnswer?
    let rows: [BriefTransaction]

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let said = said { ChatYou(text: said) }
                ChatLine(text: text)
                if let a = answer, let total = a.total {
                    APCard {
                        ChatKeyValue(key: a.title ?? "", value: Format.whole(total), tone: Pearl.moneyOut, strong: true)
                        if let usual = a.usual {
                            APSeparator(afterFace: false)
                            ChatKeyValue(key: "Usual month", value: Format.whole(usual))
                        }
                    }
                    .padding(.top, 10)
                }
                if !rows.isEmpty {
                    APCard {
                        ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                            if i > 0 { APSeparator() }
                            NavigationLink(value: PearlChatView.Route.transaction(t.id)) {
                                APPaymentRow(name: t.name, line: Format.short(t.date),
                                             money: t.inflow ? .into(t.shownAmount) : .out(t.shownAmount))
                                    .accessibilityHint("Opens it")
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.top, 10)
                }
            }
            .chatPage()
        }
    }
}

// MARK: - PC-07 · PC-10

/// G7-TellMore 1: "Sorted 7. 2 left for later." and the row back to Needs a look.
private struct ChatSorted: View {
    let said: String?
    let sorted: Int
    let left: Int
    let seeThem: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let said = said { ChatYou(text: said) }
                ChatLine(text: ChatWords.sortedTitle(sorted: sorted, left: left))
                if let row = ChatWords.sortedBody(left: left) {
                    Button(action: seeThem) {
                        HStack(spacing: 12) {
                            ChatIcon(symbol: "cart")
                            Text(row).font(Nacre.body).foregroundColor(Pearl.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(ChatWords.seeThe(left))
                                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                                .foregroundColor(Pearl.link)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 64)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .apCard()
                    .padding(.top, 12)
                    .accessibilityElement(children: .combine)
                    .accessibilityHint("Opens Needs a look")
                }
            }
            .chatPage()
        }
    }
}

/// G7-TellMore 4: "Pearl couldn't match that. …" and Tell it differently.
private struct ChatNothing: View {
    let said: String?
    let line: String
    let again: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let said = said { ChatYou(text: said) }
                ChatLine(text: [ChatWords.couldntMatch, line].filter { !$0.isEmpty }.joined(separator: " "))
                Button("Tell it differently", action: again)
                    .buttonStyle(APSecondaryButtonStyle())
                    .padding(.top, 12)
            }
            .chatPage()
        }
    }
}

// MARK: - PC-11 · couldn't answer

/// G7-Unavailable 1 (PC-11, from AI-15): where Apple Intelligence can't run
/// (A+: the tab stays and the bar keeps five), or if it stops while open.
private struct ChatUnavailable: View {
    let onSearch: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            ChatIcon(symbol: "sparkles")
            Text("Pearl chat needs Apple Intelligence")
                .font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            Text("It runs on this iPhone only, and needs a newer one.")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Button("Search instead", action: onSearch)
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.top, 18)
        }
        .padding(.horizontal, 36).padding(.top, 120)
    }
}

/// G7-Unavailable 2: her bubble, "Pearl couldn't answer that. Try again.", Try again.
private struct ChatFailed: View {
    let said: String
    let busy: Bool
    let retry: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                ChatYou(text: said)
                ChatErrorLine(text: ChatWords.failed)
                Button("Try again", action: retry)
                    .buttonStyle(APSecondaryButtonStyle())
                    .disabled(busy)
                    .padding(.top, 12)
            }
            .chatPage()
        }
    }
}

// MARK: - PC-12 · PC-13

/// G7-Confirm 1: "Here's a plan from your last 3 months…", the plan's card,
/// Set it · Not now. Nothing changes until she sets it.
private struct ChatPlanAsk: View {
    @ObservedObject var engine: ChatEngine
    let said: String
    let plan: PlanProposal

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if !said.isEmpty { ChatYou(text: said) }
                ChatLine(text: ChatWords.planLead(months: plan.months ?? 3))
                ChatPlanCard(plan: plan)
                if let error = engine.error { ChatErrorLine(text: error) }
                ChatPlanButtons(engine: engine, plan: plan)
            }
            .chatPage()
        }
    }
}

/// PC-12's card: "Make a Dining out plan of $220 a month?" over "Usual $286".
private struct ChatPlanCard: View {
    let plan: PlanProposal

    var body: some View {
        let category = plan.category ?? ""
        let amount = plan.amount ?? 0
        return ChatIconCard(symbol: CategorySheet.symbol(for: category),
                            title: ChatWords.planQuestion(category, amount),
                            sub: ChatWords.planSub(usual: plan.usual ?? amount))
    }
}

/// G7-Confirm 3: Not now. The plan she was shown, then "Okay, nothing changed."
private struct ChatNoChange: View {
    let said: String?
    let plan: PlanProposal?

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let said = said, !said.isEmpty { ChatYou(text: said) }
                if let plan = plan {
                    ChatLine(text: ChatWords.planLead(months: plan.months ?? 3))
                    ChatPlanCard(plan: plan)
                }
                ChatLine(text: ChatWords.nothingChanged, top: plan == nil ? 14 : 18)
            }
            .chatPage()
        }
    }
}

/// G7-Confirm 2 and 4: "Done. …", what was made and the way there. The
/// toast with Undo is the app's (ChatToast, ChatCards.swift).
private struct ChatDone: View {
    let said: String?
    let notes: [DoneNote]
    let open: (DoneLink) -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let said = said, !said.isEmpty { ChatYou(text: said) }
                ForEach(notes) { note in
                    ChatLine(text: note.line)
                    ChatDoneCard(note: note, open: open)
                }
            }
            .chatPage()
        }
    }
}

/// A plan's card and link, a trip's row and where it lives, a rule's card and link.
private struct ChatDoneCard: View {
    let note: DoneNote
    let open: (DoneLink) -> Void

    /// "See it in Your plan" stays hidden while Your plan is parked.
    static func linkShown(_ link: DoneLink) -> Bool {
        if case .plan = link { return YourPlanGate.shown }
        return true
    }

    var body: some View {
        VStack(spacing: 0) {
            if note.kind == .trip {
                Button { if let l = note.link { open(l) } } label: {
                    HStack(spacing: 12) {
                        Text(face)
                            .font(.custom("Figtree-Medium", size: 14))
                            .foregroundColor(Pearl.ink)
                            .frame(width: 40, height: 40)
                            .background(Circle().fill(APlus.face))
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(note.title).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            if let sub = note.sub {
                                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if let amount = note.amount {
                            // A trip's total is a total: no minus (note 1329:69536).
                            Text(amount).font(Nacre.headline).foregroundColor(Pearl.moneyOut)
                                .monospacedDigit().pearlAmountFit().fixedSize()
                        }
                        ChatChevron()
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .apCard()
                .padding(.top, 12)
                .accessibilityElement(children: .combine)
                .accessibilityHint("Opens the trip")
                if let n = note.note { ChatNote(text: n) }
            } else {
                ChatIconCard(symbol: note.kind == .plan ? "fork.knife" : "sparkles", title: note.title, sub: note.sub)
                if let label = note.linkLabel, let link = note.link, Self.linkShown(link) {
                    ChatQuietLink(title: label) { open(link) }.padding(.top, 8)
                }
            }
        }
    }

    /// "MO" for Montréal: two letters for a trip.
    private var face: String {
        let name = note.face ?? note.title
        let words = name.split { !$0.isLetter }
        if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        return APFace.initials(name)
    }
}

// MARK: - The composer

/// "Message Pearl" (dictation is the keyboard's mic). A+ (REDESIGN-03, -09;
/// G7-Chat): a capsule well with the 32 pt send arrow, off while empty and
/// rose with words. It sits just above the keyboard while she types (the
/// keyboard's safe area lifts it), and over the tab bar otherwise. The start
/// has "On this iPhone only" over it; while Pearl works it out it's at 45%.
private struct ChatComposer: View {
    @Binding var text: String
    var composing: FocusState<Bool>.Binding
    let onDevice: Bool
    let off: Bool
    let send: () -> Void

    /// Send is off until there are words.
    private var canSend: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !off }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if onDevice {
                Text(ChatWords.onDevice.uppercased())
                    .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 4)
            }
            HStack(spacing: 8) {
                TextField("", text: $text, prompt: Text(ChatWords.placeholder).foregroundColor(Pearl.muted))
                    .font(Nacre.body).foregroundColor(Pearl.ink)
                    .tint(Pearl.action)
                    .focused(composing)
                    .submitLabel(.send)
                    .onSubmit(send)
                    .accessibilityLabel(ChatWords.placeholder)
                    .accessibilityIdentifier("chat-composer")
                Button(action: send) {
                    Image(systemName: "arrow.up").font(.system(size: 15, weight: .bold))
                        .foregroundColor(canSend ? Pearl.onAction : Pearl.muted)
                        .frame(width: 32, height: 32)
                        .background(Circle().fill(canSend ? Pearl.action : APlus.trackSoft))
                        .frame(width: 44, height: 44)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .padding(.vertical, -6).padding(.trailing, -6)
                .disabled(!canSend)
                .accessibilityLabel("Send")
                .accessibilityIdentifier("chat-send")
            }
            .padding(.leading, 16).padding(.trailing, 6)
            .frame(minHeight: 44)
            .wellStyle(focused: composing.wrappedValue, capsule: true)
        }
        .opacity(off ? 0.45 : 1)
        .disabled(off)
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
    }
}

/// PC-07, PC-10, PC-11 before A+, and Your plan's YP-06, PaidBackFind's
/// empty: the Empty state. Icon in a blush bubble, a Fraunces title, one
/// line (or none), a text action. (The chat itself uses G7's screens now.)
struct EmptyStateBlock: View {
    let title: String
    let line: String?
    let action: String?
    let act: () -> Void

    init(title: String, line: String?, action: String?, act: @escaping () -> Void) {
        self.title = title
        self.line = line
        self.action = action
        self.act = act
    }

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "magnifyingglass").font(.system(size: 20, weight: .medium))
                .foregroundColor(Pearl.action)
                .frame(width: 56, height: 56)
                .background(Circle().fill(Pearl.bubble))
                .accessibilityHidden(true)
            VStack(spacing: 8) {
                Text(title).font(Pearl.heading(18, relativeTo: .title3)).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                if let line = line {
                    Text(line).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.muted)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let action = action {
                Button(action, action: act)
                    .font(Nacre.textButton).foregroundColor(Pearl.link)
                    .frame(minWidth: 240, minHeight: 44)
                    .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16).padding(.vertical, 32)
    }
}

/// The chat's reads through the app's APIClient: GET, and POST only to the
/// server's read-only /api/chat/*. Nothing else.
struct APIChatReading: ChatReading {
    let api: APIClient

    func get<T: Decodable>(_ path: String) async throws -> T {
        precondition(path.hasPrefix("api/chat"), "The chat reads only its own endpoints")
        return try await api.get(path)
    }

    func read<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        precondition(path.hasPrefix("api/chat/"), "The chat reads only its own endpoints")
        return try await api.post(path, body)
    }
}

/// The executor's writes (ChatExecutor, on her tap only).
struct APIChatWriting: ChatWriting {
    let api: APIClient

    func post<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        try await api.post(path, body)
    }

    func put<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        try await api.put(path, body)
    }

    func delete<T: Decodable>(_ path: String, query: [String: String]) async throws -> T {
        try await api.delete(path, query: query)
    }
}
