import SwiftUI

/// Pearl chat (note 1340:8893, THL-117, THL-139, THL-213, THL-254), the
/// Pearl tab since A+ (REDESIGN-02, -03; AP-Chat): a full tab screen with the
/// tab bar showing. The conversation stays across tab switches; "New chat"
/// asks first on a Pearl sheet, then clears it. One exchange at a time:
///
/// PC-03 (1338:7879 / 1338:8040)  start: Start with…, "Message Pearl", "On this iPhone only" (TEXT-01)
/// PC-04 (1338:8200 / 1338:8355)  an answer: her words, a summary, the totals, the rows (each opens its page)
/// PC-05/06/08/09                 the cards (ChatCards.swift)
/// PC-07 (1338:8755 / 1338:8875)  "Sorted 7. 2 left for later." · See the 2
/// PC-10 (1338:9238 / 1338:9356)  nothing matched · Tell it differently
/// PC-11 (1338:9474 / 1338:9587)  unavailable · Search instead (the tab stays; the bar keeps 5)
/// PC-12 (1344:8893 / 1344:9043)  a plan to set: Set it · Not now
/// PC-13 (1344:9178 / 1344:9285)  "Done. Dining out plan set to $220 a month." · See it in Your plan
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

    init(api: APIClient, describe: @escaping (Error) -> String, onSearch: @escaping () -> Void) {
        _engine = StateObject(wrappedValue: ChatEngine(
            brain: PearlIntelligence.brain(plans: Features.chatPlans), reader: ChatReader(APIChatReading(api: api)),
            executor: ChatExecutor(writer: APIChatWriting(api: api)), allowsPlans: Features.chatPlans,
            describe: describe))
        self.onSearch = onSearch
    }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                bar
                content.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                if available { composer }
            }
            .nacreScreen()
            .navigationBarHidden(true)
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .transaction(let id): TransactionByID(id: id, categories: app.categories)
                case .needsALook: ReviewView()
                case .trip(let id): TripPage(id: id)
                case .rules: CategoriesRulesView()
                case .plan: YourPlanView()
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
            // G7 (REDESIGN-14): asks first, on a Pearl sheet.
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

    private var largeTitle: Bool {
        if !available { return true }
        switch engine.screen {
        case .start, .sorted, .nothing: return true
        default: return false
        }
    }

    /// AP-Chat: "Pearl" as a large title on PC-03, PC-07, PC-10 and PC-11;
    /// over an exchange, "Pearl" inline and centred with New chat on the
    /// right. No Close: it's a tab.
    private var bar: some View {
        VStack(alignment: .leading, spacing: 0) {
            if largeTitle {
                Text("Pearl").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
            } else {
                ZStack {
                    Text("Pearl").font(Nacre.headline).foregroundColor(Pearl.ink)
                        .accessibilityAddTraits(.isHeader)
                    HStack {
                        Spacer()
                        Button("New chat") { askingNewChat = true }
                            .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                            .foregroundColor(Pearl.link)
                            .buttonStyle(.plain)
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                            .accessibilityHint("Asks first. What you told Pearl here is forgotten.")
                            .accessibilityIdentifier("chat-new")
                    }
                }
                .frame(height: 44)
                .padding(.horizontal, 16)
            }
        }
        .padding(.top, 6)
    }

    // MARK: The screens

    @ViewBuilder private var content: some View {
        if !available {
            unavailable
        } else {
            switch engine.screen {
            case .start: start
            case .thinking(let said): thinking(said)
            case .reply(let said, let text, let answer, let rows): reply(said, text, answer, rows)
            case .cards(let deck): ChatDeckView(engine: engine, deck: deck)
            case .sorted(let sorted, let left): sortedScreen(sorted, left)
            case .nothing(let line): nothingMatched(line)
            case .plan(let said, let p): planScreen(said, p)
            case .done(let said, let notes): doneScreen(said, notes)
            case .noChange(let said): noChange(said)
            }
        }
    }

    /// PC-03: four starters in Option rows.
    private var start: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("START WITH")
                    .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 16).padding(.top, 64)
                GlassCard(radius: 20) {
                    starter("sparkles", "Tell Pearl what you did", nil, .tell)
                    RowSeparator(inset: 0).padding(.horizontal, 16)
                    starter("bag", "Ask about my spending", "A short answer, with the transactions behind it", .ask)
                    RowSeparator(inset: 0).padding(.horizontal, 16)
                    starter("tv", "Find subscriptions", nil, .subscriptions)
                    RowSeparator(inset: 0).padding(.horizontal, 16)
                    starter("airplane", "Was this a trip?", nil, .trips)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func starter(_ symbol: String, _ title: String, _ sub: String?, _ mode: ChatMode) -> some View {
        Button { Task { await engine.pick(mode) } } label: {
            HStack(spacing: 12) {
                Image(systemName: symbol).font(.system(size: 18)).foregroundColor(Pearl.action)
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(Pearl.bubble))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Pearl.ink)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("chat-starter-\(mode.rawValue)")
    }

    private func thinking(_ said: String) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            words(ChatWords.quote(said))
            ProgressView().frame(maxWidth: .infinity)
                .accessibilityLabel("Pearl is working it out")
        }
        .padding(.horizontal, 20).padding(.top, 14)
    }

    /// PC-04.
    private func reply(_ said: String?, _ text: String, _ answer: SpendingAnswer?,
                       _ rows: [BriefTransaction]) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    if let said = said { words(ChatWords.quote(said)) }
                    words(text)
                }
                .padding(.horizontal, 4)
                if let a = answer, let total = a.total {
                    // The totals card: "Dining, October $286" and "Usual month $214".
                    GlassCard(radius: 22) {
                        HStack(alignment: .top, spacing: 12) {
                            stat(a.title ?? "", Format.whole(total))
                            if let usual = a.usual { stat("Usual month", Format.whole(usual)) }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 14)
                    }
                }
                if !rows.isEmpty {
                    GlassCard(radius: 22) {
                        ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                            if i > 0 { RowSeparator(inset: 68) }
                            NavigationLink(value: Route.transaction(t.id)) { ChatRow(t: t) }
                                .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
            Text(value).font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    /// PC-07.
    private func sortedScreen(_ sorted: Int, _ left: Int) -> some View {
        EmptyStateBlock(title: ChatWords.sortedTitle(sorted: sorted, left: left),
                        line: ChatWords.sortedBody(left: left),
                        action: left > 0 ? ChatWords.seeThe(left) : nil) {
            path.append(.needsALook)
        }
    }

    /// PC-10: Tell it differently puts her back in the composer.
    private func nothingMatched(_ line: String) -> some View {
        EmptyStateBlock(title: "Pearl couldn\u{2019}t match that", line: line, action: "Tell it differently") {
            engine.restart()
            engine.mode = .tell
            composing = true
        }
    }

    /// PC-11 (from AI-15): the Pearl tab where Apple Intelligence can't run
    /// (A+: the tab stays and the bar keeps five), or if it stops while open.
    private var unavailable: some View {
        EmptyStateBlock(title: "Pearl chat needs Apple Intelligence",
                        line: "Pearl chat needs a newer iPhone.",
                        action: "Search instead", act: onSearch)
    }

    /// PC-12: nothing changes until she sets it.
    private func planScreen(_ said: String, _ p: PlanProposal) -> some View {
        let category = p.category ?? ""
        let amount = p.amount ?? 0
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    if !said.isEmpty { words(ChatWords.youSaid(said)) }
                    words(ChatWords.planLead(months: p.months ?? 3))
                }
                .padding(.horizontal, 4)
                callout(symbol: CategorySheet.symbol(for: category), title: ChatWords.planQuestion(category, amount),
                        line: ChatWords.planSub(usual: p.usual ?? amount))
                if let error = engine.error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                }
                ChatPlanButtons(engine: engine, plan: p)
                .padding(.top, 38)
            }
            .padding(.horizontal, 16).padding(.top, 14)
        }
    }

    /// PC-13, and a trip or pattern she said Yes to: "Done. …", where it
    /// lives now, and the way there. The only undo: change it where it lives.
    private func doneScreen(_ said: String?, _ notes: [DoneNote]) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let said = said, !said.isEmpty { words(ChatWords.youSaid(said)).padding(.horizontal, 4) }
                ForEach(notes) { note in
                    VStack(alignment: .leading, spacing: 12) {
                        words(note.line).padding(.horizontal, 4)
                        callout(symbol: symbol(note.link), title: note.title, line: note.place)
                        if let route = route(note.link), let label = note.linkLabel {
                            Button(label) { path.append(route) }
                                .font(Nacre.textButton).foregroundColor(Pearl.link)
                                .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(.horizontal, 16).padding(.top, 14)
        }
    }

    /// "Okay, nothing changed." after Not now.
    private func noChange(_ said: String?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let said = said, !said.isEmpty { words(ChatWords.youSaid(said)) }
            words(ChatWords.nothingChanged)
        }
        .padding(.horizontal, 20).padding(.top, 14)
    }

    private func symbol(_ link: DoneLink?) -> String {
        switch link {
        case .trip?: return "airplane"
        case .rules?: return "sparkles"
        case .plan?, nil: return "fork.knife"
        }
    }

    /// Where a confirmation lives. PC-13's "See it in Your plan" opens Your
    /// plan, which shows YP-03 while the plan is in use and YP-01 otherwise.
    private func route(_ link: DoneLink?) -> Route? {
        switch link {
        case .trip(let id)?: return .trip(id)
        case .rules?: return .rules
        case .plan?: return .plan
        case nil: return nil
        }
    }

    /// PC-12's preview card and PC-13's done card (the Callout).
    private func callout(symbol: String, title: String, line: String?) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).font(.system(size: 18)).foregroundColor(Pearl.action)
                .frame(width: 24, height: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let line = line {
                    Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 17).padding(.vertical, 13)
        .pearlCard(radius: 20)
        .accessibilityElement(children: .combine)
    }

    /// Her words and Pearl's short lines: Footnote, muted (PC-04, PC-12).
    private func words(_ s: String) -> some View {
        Text(s).font(Nacre.footnote).foregroundColor(Pearl.muted)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: The composer

    /// "Message Pearl" (dictation is the keyboard's mic). A+ (REDESIGN-03,
    /// -09): a well with the send up-arrow, off while empty and rose with
    /// words, just above the keyboard. PC-03 has the on-device line over it.
    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if case .start = engine.screen {
                Text(ChatWords.onDevice.uppercased())
                    .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 4)
            }
            HStack(spacing: 4) {
                TextField("", text: $text, prompt: Text(ChatWords.placeholder).foregroundColor(Pearl.muted))
                    .font(Nacre.body).foregroundColor(Pearl.ink)
                    .tint(Pearl.action)
                    .focused($composing)
                    .submitLabel(.send)
                    .onSubmit(send)
                    .accessibilityLabel(ChatWords.placeholder)
                    .accessibilityIdentifier("chat-composer")
                Button(action: send) {
                    Image(systemName: "arrow.up").font(.system(size: 14, weight: .bold))
                        .foregroundColor(canSend ? Pearl.onAction : Pearl.muted)
                        .frame(width: 28, height: 28)
                        .background(Circle().fill(canSend ? Pearl.action : APlus.trackSoft))
                        .frame(width: 44, height: 44)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(!canSend)
                .accessibilityLabel("Send")
                .accessibilityIdentifier("chat-send")
            }
            .padding(.leading, 14).padding(.trailing, 0)
            .frame(minHeight: 44)
            .wellStyle(focused: composing, capsule: true)
        }
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
    }

    /// Send is off until there are words.
    private var canSend: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    private func send() {
        guard canSend else { return }
        let said = text
        text = ""
        composing = false
        Task { await engine.send(said) }
    }
}

/// PC-07, PC-10, PC-11 and Your plan's YP-06: the Empty state. Icon in a
/// blush bubble, a Fraunces title, one line (or none), a text action.
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

/// PC-04's rows: who, "Dining · Oct 24", how much. Each opens its page.
private struct ChatRow: View {
    let t: BriefTransaction

    var body: some View {
        HStack(spacing: 12) {
            Initials(name: t.name)
            VStack(alignment: .leading, spacing: 2) {
                Text(t.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text([t.category, Format.short(t.date)].compactMap { $0 }.filter { !$0.isEmpty }
                        .joined(separator: " \u{00B7} "))
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(t.shownAmount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(t.inflow ? Pearl.moneyIn : Pearl.moneyOut)
                .lineLimit(1).fixedSize()
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens it")
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
}
