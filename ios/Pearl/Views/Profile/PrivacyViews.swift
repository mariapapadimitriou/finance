import SwiftUI
import UIKit
import UserNotifications

// Privacy and notifications (Pearl iOS Handoff File, Pearl app page, THL-117
// and THL-139): CN-04 Privacy and consent, CN-05 Turn off AI sorting?, CN-06
// Ask Pearl's switch and Turn off Ask Pearl? (THL-308, AI2-Switch), N-01
// Turn on notifications and N-02 Notifications. THL-309 (Pearl redesign
// canvas, Pearl page, AI Phase 4): CN-07 Off · Rules · Smart in the row
// (AI4-Setting, option A), CN-08 Turn on Smart? (AI4-Consent) and CN-09
// stepping down (AI4-StepDown).

let cardRadius: CGFloat = 22

/// A line icon on the action wash (A+ `.icon`, 36).
private struct RoseBubble: View {
    let symbol: String
    var size: CGFloat = 36

    var body: some View {
        IconBubble(symbol: symbol, size: size)
    }
}

/// "NEEDED FOR PEARL": A+ `.label` over a card.
struct CardCaption: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        APSectionLabel(text: text).padding(.top, 12)
    }
}

/// The page's 34 pt title and its `muted` lead line.
struct PageTitle: View {
    let title: String
    let line: String?

    var body: some View {
        ProfileHeading(title: title, intro: line)
    }
}

/// One A+ row: an optional icon, a title over its line, what sits at the end.
struct PrivacyRow<Trailing: View>: View {
    var symbol: String? = nil
    let title: String
    var sub: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            if let symbol = symbol { RoseBubble(symbol: symbol) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            trailing()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
    }
}

/// A row with a switch. VoiceOver reads the switch, with the line as its hint.
struct SwitchRow: View {
    var symbol: String? = nil
    let title: String
    var sub: String? = nil
    var hint: String? = nil
    let isOn: Bool
    var disabled = false
    let changed: (Bool) -> Void

    var body: some View {
        PrivacyRow(symbol: symbol, title: title, sub: sub) {
            // TEST-39 (G5-Notifications, N-02): the row says the title once.
            // The A+ switch (APToggleStyle) draws its label whatever
            // .labelsHidden() says, so the switch has none on screen; the
            // title is its VoiceOver label.
            Toggle(isOn: Binding(get: { isOn }, set: changed)) { EmptyView() }
                .fixedSize()
                .tint(Pearl.action)
                .disabled(disabled)
                .accessibilityLabel(title)
                .accessibilityHint(hint ?? sub ?? "")
        }
        .opacity(disabled ? 0.45 : 1)
    }
}

struct RowChevron: View {
    var body: some View { APChevron() }
}

// MARK: - CN-04 Privacy and consent, CN-05 Turn off AI sorting?

/// What's been agreed to, each with its date. Reading linked accounts is
/// managed in Accounts. Working out the numbers is withdrawn by deleting the
/// account, from Your data. The optional ones change on tap and the server
/// logs each change with its time.
@MainActor
struct ConsentView: View {
    @EnvironmentObject private var app: AppModel
    /// Your data's way home, after Start over.
    let goHome: () -> Void
    @State private var privacy: Privacy?
    @State private var doc: PearlDoc?
    @State private var askingAIOff = false
    /// CN-06: Turn off Ask Pearl? asks first, on a Pearl sheet.
    @State private var askingAskOff = false
    @State private var busy: String?
    @State private var error: String?
    /// CN-08: Turn on Smart?, the first time she picks Smart.
    @State private var askingSmart = false
    /// CN-09: what Off goes back to with Undo, and the line after Smart → Rules.
    @State private var steppedDown = false
    @State private var toast: PearlToast.Model?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                PageTitle(title: "Privacy and consent", line: "Change your mind any time.")
                if let privacy = privacy {
                    content(privacy)
                } else if let error = error {
                    APErrorLine(text: error)
                } else {
                    APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }.padding(.top, 12)
                }
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .docSheet($doc)
        .sheet(isPresented: $askingAIOff) {
            // CN-09 (AI4-StepDown 3): Smart or Rules → Off asks first, on the
            // reworded Pearl sheet. Her patterns stay.
            let was = mode
            PearlConfirmSheet(overline: "Pearl sorts for you", title: "Stop Pearl sorting for you?",
                              message: SortingWords.offSheet(patterns),
                              primary: "Turn off", busyLabel: "Turning off…", secondary: "Keep it on",
                              failure: "Couldn’t turn it off. Nothing changed. Try again.",
                              onClose: { askingAIOff = false }) {
                privacy = try await putSorting("off")
                askingAIOff = false
                steppedDown = false
                say("Pearl stopped sorting for you.") { await undoSorting(to: was) }
            }
        }
        .sheet(isPresented: $askingSmart) {
            // CN-08 (AI4-Consent): asked once. "Like Ask Pearl, …" when she
            // already uses it. Not now, ✕ or a swipe keep what she had.
            let was = mode
            PearlConfirmSheet(overline: "Pearl sorts for you", title: "Turn on Smart?",
                              message: SortingWords.consent(likeAsk: isOn("ai_ask")),
                              primary: "Turn on Smart", busyLabel: "Turning on…", secondary: "Not now",
                              failure: "Couldn’t turn it on. Nothing changed. Try again.",
                              onClose: { askingSmart = false }) {
                privacy = try await putSorting("smart", consent: true)
                askingSmart = false
                steppedDown = false
                say("Smart is on.") { await undoSorting(to: was) }
            }
        }
        .overlay(alignment: .bottom) {
            if let toast = toast {
                PearlToast(model: toast) { if self.toast == toast { withAnimation { self.toast = nil } } }
                    .padding(.bottom, 12)
                    .id(toast.id)
            }
        }
        .sheet(isPresented: $askingAskOff) {
            // CN-06 (AI2-Switch 3, 4): a Pearl sheet. A failed turn-off says
            // so and leaves the switch on.
            PearlConfirmSheet(overline: "Ask Pearl", title: "Turn off Ask Pearl?",
                              message: "Pearl stops sending your questions to Claude. Your sorting and rules stay.",
                              primary: "Turn off", busyLabel: "Turning off\u{2026}", secondary: "Keep it on",
                              failure: "Couldn\u{2019}t turn it off. Nothing changed. Try again.",
                              onClose: { askingAskOff = false }) {
                privacy = try await app.api.put("api/privacy/consents", ["key": "ai_ask", "value": false])
                askingAskOff = false
            }
        }
    }

    @ViewBuilder
    private func content(_ privacy: Privacy) -> some View {
        CardCaption("Needed for Pearl")
        APCard {
            NavigationLink { AccountsView() } label: {
                PrivacyRow(symbol: "building.columns", title: "Reading your accounts",
                           sub: agreed("read_data")) { RowChevron() }
            }
            .buttonStyle(.plain)
            APSeparator(afterFace: false)
            NavigationLink { YourDataView(goHome: goHome) } label: {
                PrivacyRow(symbol: "chart.line.uptrend.xyaxis", title: "Working out your numbers",
                           sub: agreed("insights")) { RowChevron() }
            }
            .buttonStyle(.plain)
            .accessibilityHint("Opens Your data. To withdraw this, you delete your account.")
        }

        CardCaption("Your choice")
        APCard {
            // CN-06 (THL-308, AI2-Switch 1): Ask Pearl, above Pearl sorts for
            // you, with the privacy line under it. On is instant; off asks first.
            SwitchRow(symbol: "bubble.left", title: "Ask Pearl",
                      sub: "Uses Claude, by Anthropic. Never your account numbers or bank logins.",
                      isOn: isOn("ai_ask"), disabled: busy == "ai_ask") { on in
                if on { Task { await change("ai_ask", to: true) } } else { askingAskOff = true }
            }
            .accessibilityIdentifier("privacy-ask-pearl")
            APSeparator(afterFace: false)
            // CN-07 (THL-309, AI4-Setting option A): Off · Rules · Smart in
            // the row, one tap, and one line under it that follows the choice.
            SortingRow(mode: mode, line: SortingWords.line(mode, patterns: patterns, steppedDown: steppedDown),
                       disabled: busy == "sorting") { choose($0) }
                .accessibilityIdentifier("privacy-sorting")
            APSeparator(afterFace: false)
            SwitchRow(symbol: "envelope", title: "Tips and news by email",
                      isOn: isOn("tips"), disabled: busy == "tips") { on in
                Task { await change("tips", to: on) }
            }
            APSeparator(afterFace: false)
            SwitchRow(symbol: "chart.bar", title: "Help improve Pearl", sub: "Anonymous usage only",
                      isOn: isOn("analytics"), disabled: busy == "analytics") { on in
                Task { await change("analytics", to: on) }
            }
        }
        if let error = error { APErrorLine(text: error) }

        CardCaption("Your rights")
        APCard {
            if let contact = privacy.contact, !contact.isEmpty, let mail = URL(string: "mailto:\(contact)") {
                Link(destination: mail) {
                    PrivacyRow(symbol: "eye", title: "See or correct what we hold") { RowChevron() }
                }
                .buttonStyle(.plain)
                .accessibilityHint("Writes to our privacy officer, who replies within 30 days")
                APSeparator(afterFace: false)
            }
            Button { doc = .privacy } label: {
                PrivacyRow(symbol: "doc.text", title: "Privacy policy") { RowChevron() }
            }
            .buttonStyle(.plain)
        }
    }

    private func isOn(_ key: String) -> Bool { privacy?.consents?[key]?.value == true }

    // MARK: CN-07 / CN-08 / CN-09

    /// Off · Rules · Smart, from the server; the old switch maps across.
    private var mode: String { privacy?.sorting?.mode ?? (isOn("ai_sort") ? "rules" : "off") }
    private var patterns: Int { privacy?.sorting?.patterns ?? 0 }

    /// One tap. Smart the first time asks (CN-08); Off asks (CN-09); the
    /// rest is at once, with a toast and Undo where the boards draw one.
    private func choose(_ pick: String) {
        guard pick != mode, busy == nil else { return }
        switch pick {
        case "off":
            askingAIOff = true
        case "smart" where privacy?.sorting?.asked != true:
            askingSmart = true
        default:
            let was = mode
            Task {
                guard await setSorting(pick) else { return }
                steppedDown = was == "smart" && pick == "rules"
                if steppedDown {
                    say("Back to Rules.") { await undoSorting(to: was) }
                } else if pick == "smart" {
                    say("Smart is on.") { await undoSorting(to: was) }
                }
            }
        }
    }

    /// Shows the choice straight away, then takes the server's record of it.
    private func setSorting(_ pick: String) async -> Bool {
        let before = privacy
        privacy?.sorting?.mode = pick
        busy = "sorting"
        error = nil
        defer { busy = nil }
        do {
            privacy = try await putSorting(pick)
            return true
        } catch {
            privacy = before
            self.error = app.handle(error)
            return false
        }
    }

    private func putSorting(_ pick: String, consent: Bool = false) async throws -> Privacy {
        try await app.api.put("api/privacy/sorting", ["mode": pick, "consent": consent])
    }

    private func undoSorting(to was: String) async {
        steppedDown = false
        _ = await setSorting(was)
    }

    private func say(_ text: String, undo: @escaping () async -> Void) {
        withAnimation {
            toast = PearlToast.Model(text: text, action: "Undo", run: {
                withAnimation { toast = nil }
                Task { await undo() }
            })
        }
    }

    /// "Agreed Oct 2, 2026", or "Not agreed".
    private func agreed(_ key: String) -> String {
        guard let consent = privacy?.consents?[key], consent.value == true else { return "Not agreed" }
        return consent.at.map { "Agreed \(Format.agreedDay($0))" } ?? "Agreed"
    }

    private func load() async {
        do {
            privacy = try await app.api.get("api/privacy")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Shows the change straight away, then takes the server's record of it.
    private func change(_ key: String, to value: Bool) async {
        let before = privacy
        privacy?.consents?[key] = Privacy.Consent(value: value, at: nil)
        busy = key
        error = nil
        defer { busy = nil }
        do {
            privacy = try await app.api.put("api/privacy/consents", ["key": key, "value": value])
        } catch {
            privacy = before
            self.error = app.handle(error)
        }
    }
}

// MARK: - CN-07 Pearl sorts for you

/// CN-07's words (AI4-Setting, AI4-Consent, AI4-StepDown), exactly as drawn.
enum SortingWords {
    static func line(_ mode: String, patterns n: Int, steppedDown: Bool) -> String {
        switch mode {
        case "off":
            return n > 0 ? "Nothing sorts by itself. \(yours(n)) stay for when you turn it back on."
                : "Nothing sorts by itself."
        case "smart":
            return "Rules, plus Claude for reasons and harder cases."
        default:
            if steppedDown && n > 0 {
                return n == 1 ? "Your pattern keeps sorting. Only its reason goes back to plain."
                    : "Your \(n) patterns keep sorting. Only their reasons go back to plain."
            }
            return "Sorts the ways you said yes to."
        }
    }

    static func offSheet(_ n: Int) -> String {
        n > 0 ? "New ones wait for you in Quick sort. \(yours(n)) stay, ready if you turn it back on."
            : "New ones wait for you in Quick sort."
    }

    /// CN-08, with the correction to THL-309 AC 3: shop names only.
    static func consent(likeAsk: Bool) -> String {
        (likeAsk ? "Like Ask Pearl, Smart uses Claude, by Anthropic."
            : "Smart uses Claude, by Anthropic, for reasons and harder cases.")
            + " It sees shop names only, never amounts, dates, people, account numbers or bank logins."
            + " You still say yes first."
    }

    private static func yours(_ n: Int) -> String { n == 1 ? "Your pattern will" : "Your \(n) patterns" }
}

/// kit `.row.noface.sortrow`: the icon, "Pearl sorts for you" over the
/// three-part `.seg` (Off · Rules · Smart) and one muted line that changes
/// with the choice (role status, so VoiceOver reads the change).
struct SortingRow: View {
    let mode: String
    let line: String
    var disabled = false
    let pick: (String) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            IconBubble(symbol: "sparkles", size: 36)
            VStack(alignment: .leading, spacing: 8) {
                Text("Pearl sorts for you").font(Nacre.body).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                APSegmented(options: [("off", "Off"), ("rules", "Rules"), ("smart", "Smart")],
                            selection: Binding(get: { mode }, set: { if let v = $0 { pick(v) } }))
                    .disabled(disabled)
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.updatesFrequently)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .onChange(of: line) { new in UIAccessibility.post(notification: .announcement, argument: new) }
    }
}

// MARK: - N-02 Notifications

/// Which moments, quiet hours, and amounts on the lock screen, saved on tap.
/// The switches are the phone channel; a moment's email choice stays as it is.
@MainActor
struct NotificationsView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var settings: NotificationSettings?
    @State private var permission: UNAuthorizationStatus?
    @State private var latestSave = 0
    @State private var error: String?

    private struct Moment: Identifiable {
        let id: String
        let symbol: String
        let title: String
        let sub: String
    }

    /// G5-Notifications: Progress and Milestones are hidden while Save and
    /// Wins are parked (A+, 2026-11-18); the server keeps their settings.
    private let moments = [
        Moment(id: "payday", symbol: "calendar", title: "Payday", sub: "When your pay lands"),
        Moment(id: "weekly", symbol: "chart.line.uptrend.xyaxis", title: "Weekly check-in", sub: "Sundays at 10 am"),
        Moment(id: "bank", symbol: "building.columns", title: "Bank needs you", sub: "When a bank needs you"),
    ]

    /// "From" or "To" while she picks a time on the Pearl sheet.
    @State private var picking: String?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                PageTitle(title: "Notifications", line: "At most 3 a week.")
                if let prefs = settings?.prefs {
                    content(prefs)
                } else if let error = error {
                    APErrorLine(text: error)
                } else {
                    APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }.padding(.top, 12)
                }
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .task { await readPermission() }
        // Back from iPhone Settings, the answer may have changed.
        .onChange(of: scenePhase) { phase in
            if phase == .active { Task { await readPermission() } }
        }
    }

    @ViewBuilder
    private func content(_ prefs: NotificationSettings.Prefs) -> some View {
        if permission == .denied { blockedBanner.padding(.top, 8) }
        CardCaption("What you get")
        APCard {
            ForEach(Array(moments.enumerated()), id: \.element.id) { i, moment in
                if i > 0 { APSeparator(afterFace: false) }
                SwitchRow(title: moment.title, sub: moment.sub,
                          isOn: prefs.types[moment.id]?.phone == true,
                          disabled: permission == .denied) { on in
                    Task { await setMoment(moment.id, on: on) }
                }
            }
        }
        if let error = error { APErrorLine(text: error) }

        CardCaption("Quiet hours")
        APCard {
            quietRow("From", prefs.quiet.from) { picking = "from" }
            APSeparator(afterFace: false)
            quietRow("To", prefs.quiet.to) { picking = "to" }
        }

        CardCaption("Lock screen")
        APCard {
            SwitchRow(title: "Show amounts", sub: "\u{201C}Your pay of $2,140 arrived.\u{201D}",
                      hint: "Off: \u{201C}Your pay arrived.\u{201D} On: \u{201C}Your pay of $2,140 arrived.\u{201D}",
                      isOn: prefs.lockAmounts, disabled: permission == .denied) { on in
                Task { await save(["lock_amounts": on]) { $0.lockAmounts = on } }
            }
        }
    }

    /// G5-Notifications: off in iPhone Settings, so the banner says so.
    private var blockedBanner: some View {
        APBanner(symbol: "bell", text: "Notifications are off for Pearl in iPhone Settings.", action: "Open Settings") {
            if let url = URL(string: UIApplication.openNotificationSettingsURLString) { UIApplication.shared.open(url) }
        }
    }

    /// "From   9:00 pm": the time in `link`; it opens the Pearl sheet.
    private func quietRow(_ label: String, _ value: String, open: @escaping () -> Void) -> some View {
        Button(action: open) {
            APKeyValueRow(key: label, value: QuietTime.words(value), link: true)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Quiet hours \(label.lowercased())")
        .accessibilityValue(QuietTime.words(value))
    }

    private func readPermission() async {
        permission = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    private func load() async {
        do {
            settings = try await app.api.get("api/notifications")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Turning a moment on is when iOS first needs to be asked, if it hasn't been.
    private func setMoment(_ key: String, on: Bool) async {
        async let saved: Void = save(["types": [key: ["phone": on]]]) { $0.types[key]?.phone = on }
        if on && permission == .notDetermined {
            _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            await readPermission()
        }
        await saved
    }

    /// Shows the change straight away. Only the newest save's reply is drawn,
    /// so a slow reply can't undo a later tap; a failed one reloads what's saved.
    private func save(_ body: [String: Any], apply: (inout NotificationSettings.Prefs) -> Void) async {
        if var prefs = settings?.prefs {
            apply(&prefs)
            settings?.prefs = prefs
        }
        error = nil
        latestSave += 1
        let this = latestSave
        do {
            let reply: NotificationSettings = try await app.api.put("api/notifications", body)
            if this == latestSave { settings = reply }
        } catch {
            let message = app.handle(error)
            await load()
            self.error = message
        }
    }
}

private struct PickingTime: Identifiable { let id: String }

/// Quiet hours' time, on a Pearl sheet (no stock menu): every half hour,
/// the one in use picked; a tap picks at once.
private struct QuietTimeSheet: View {
    let title: String
    let value: String
    let pick: (String) -> Void
    let close: () -> Void

    var body: some View {
        PearlSheet {
            APSheetTitle(title: title, close: close)
            ScrollViewReader { proxy in
                APCard {
                    ForEach(Array(QuietTime.all.enumerated()), id: \.element) { i, time in
                        if i > 0 { APSeparator(afterFace: false) }
                        APChoiceRow(title: QuietTime.words(time), selected: time == value) { pick(time) }
                            .id(time)
                    }
                }
                .onAppear { proxy.scrollTo(value, anchor: .center) }
            }
        }
    }
}

/// Quiet hours as the server keeps them ("21:00") and as they're said.
enum QuietTime {
    /// Every half hour of the day.
    static let all: [String] = (0..<48).map { String(format: "%02d:%02d", $0 / 2, $0 % 2 * 30) }

    private static func parts(_ time: String) -> (hour: Int, minute: Int, day: String)? {
        let bits = time.split(separator: ":").compactMap { Int($0) }
        guard bits.count == 2 else { return nil }
        return (bits[0] % 12 == 0 ? 12 : bits[0] % 12, bits[1], bits[0] < 12 ? "am" : "pm")
    }

    /// "9:00 pm".
    static func words(_ time: String) -> String {
        guard let t = parts(time) else { return time }
        return String(format: "%d:%02d %@", t.hour, t.minute, t.day)
    }

    /// "9 pm", or "9:30 pm" when it isn't on the hour.
    static func short(_ time: String) -> String {
        guard let t = parts(time) else { return time }
        return t.minute == 0 ? "\(t.hour) \(t.day)" : words(time)
    }
}

// MARK: - N-01 Turn on notifications

/// Over Home, once the Allowance has a number and before iOS has been asked
/// (HomeView). "Turn on notifications" brings up the system's own question.
@MainActor
struct TurnOnNotificationsView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let quiet: NotificationSettings.Quiet
    @State private var busy = false

    /// G5-Notifications N-01 "Want a heads-up?": three moments (Progress is
    /// hidden while Save is parked), then Turn on and Not now.
    var body: some View {
        NacreScreen {
            VStack(alignment: .leading, spacing: 12) {
                Text("Want a heads-up?").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity)
                    .accessibilityAddTraits(.isHeader)
                ProfileNote("Only at the right moments. Never about overspending.", centred: true)
                APCard {
                    moment("calendar", "Payday", "A nudge to set something aside")
                    APSeparator()
                    moment("chart.line.uptrend.xyaxis", "Weekly check-in", "Your week in one minute")
                    APSeparator()
                    moment("building.columns", "Bank needs you", "When a bank asks you to sign in")
                }
                .padding(.top, 2)
                ProfileNote("Quiet from \(QuietTime.short(quiet.from)) to \(QuietTime.short(quiet.to)).", centred: true)
            }
            .padding(.top, 20)
        } actions: {
            VStack(spacing: 12) {
                Button("Turn on notifications") { Task { await turnOn() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
                Button("Not now") { Task { await answer("not_now") } }
                    .buttonStyle(APSecondaryButtonStyle())
                    .disabled(busy)
            }
            .padding(.horizontal, 16).padding(.bottom, 8)
        }
    }

    private func moment(_ symbol: String, _ title: String, _ sub: String) -> some View {
        PrivacyRow(symbol: symbol, title: title, sub: sub) { EmptyView() }
            .accessibilityElement(children: .combine)
    }

    private func turnOn() async {
        busy = true
        let granted = (try? await UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        await answer(granted ? "on" : "not_now")
    }

    /// The answer is only a record of having asked, so a failed save never
    /// holds up Home.
    private func answer(_ word: String) async {
        busy = true
        let _: NotificationSettings? = try? await app.api.post("api/notifications/prompt", ["answer": word])
        dismiss()
    }
}
