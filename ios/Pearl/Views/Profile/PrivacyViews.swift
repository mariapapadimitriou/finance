import SwiftUI
import UIKit
import UserNotifications

// Privacy and notifications (Pearl iOS Handoff File, Pearl app page, THL-117
// and THL-139): CN-04 Privacy and consent, CN-05 Turn off AI sorting?, N-01
// Turn on notifications and N-02 Notifications.

private let cardRadius: CGFloat = 22

/// A line icon in a rose-washed circle: 34pt in a row, 72pt over N-01.
private struct RoseBubble: View {
    let symbol: String
    var size: CGFloat = 34

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size / 2, weight: .regular))
            .foregroundColor(Pearl.action)
            .frame(width: size, height: size)
            .background(Circle().fill(Nacre.roseWash))
            .accessibilityHidden(true)
    }
}

/// "NEEDED FOR PEARL": the caption over a card.
private struct CardCaption: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.caption1)
            .foregroundColor(Pearl.ink)
            .padding(.leading, 16).padding(.top, 4)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The page's Fraunces title and the line under it.
private struct PageTitle: View {
    let title: String
    let line: String

    var body: some View {
        Text(title).font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
            .accessibilityAddTraits(.isHeader)
        Text(line).font(Nacre.footnote).foregroundColor(Pearl.ink)
    }
}

/// One row: an optional icon, a title, a line under it, and what sits at the end.
private struct PrivacyRow<Trailing: View>: View {
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
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            trailing()
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 50)
        .contentShape(Rectangle())
    }
}

/// A row with a switch. VoiceOver reads the switch, with the line as its hint.
private struct SwitchRow: View {
    var symbol: String? = nil
    let title: String
    var sub: String? = nil
    var hint: String? = nil
    let isOn: Bool
    var disabled = false
    let changed: (Bool) -> Void

    var body: some View {
        PrivacyRow(symbol: symbol, title: title, sub: sub) {
            Toggle(title, isOn: Binding(get: { isOn }, set: changed))
                .labelsHidden()
                .tint(Pearl.action)
                .disabled(disabled)
                .accessibilityHint(hint ?? sub ?? "")
        }
    }
}

private struct RowChevron: View {
    var body: some View {
        Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
            .foregroundColor(Pearl.muted)
            .accessibilityHidden(true)
    }
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
    @State private var busy: String?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                PageTitle(title: "Privacy and consent", line: "Change your mind any time.")
                if let privacy = privacy {
                    content(privacy)
                } else if let error = error {
                    Hint(text: error).padding(.horizontal, 16)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 16)
                }
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .docSheet($doc)
        .sheet(isPresented: $askingAIOff) {
            // CN-05r (TEST-06): a Pearl sheet, not a stock alert.
            PearlConfirmSheet(overline: "Sort with AI", title: "Turn off AI sorting?",
                              message: "Pearl will use your bank’s categories and your rules. You can turn it back on any time.",
                              primary: "Turn off", busyLabel: "Turning off…", secondary: "Keep it on",
                              failure: "Couldn’t turn it off. Nothing changed. Try again.",
                              onClose: { askingAIOff = false }) {
                privacy = try await app.api.put("api/privacy/consents", ["key": "ai_sort", "value": false])
                askingAIOff = false
            }
        }
    }

    @ViewBuilder
    private func content(_ privacy: Privacy) -> some View {
        CardCaption("Needed for Pearl")
        GlassCard(radius: cardRadius) {
            NavigationLink { AccountsView() } label: {
                PrivacyRow(symbol: "building.columns", title: "Reading your accounts",
                           sub: agreed("read_data")) { RowChevron() }
            }
            .buttonStyle(.plain)
            RowSeparator()
            NavigationLink { YourDataView(goHome: goHome) } label: {
                PrivacyRow(symbol: "chart.line.uptrend.xyaxis", title: "Working out your numbers",
                           sub: agreed("insights")) { RowChevron() }
            }
            .buttonStyle(.plain)
            .accessibilityHint("Opens Your data. To withdraw this, you delete your account.")
        }

        CardCaption("Your choice")
        GlassCard(radius: cardRadius) {
            SwitchRow(symbol: "sparkle", title: "Sort with AI", sub: "Merchant, amount and date only",
                      isOn: isOn("ai_sort"), disabled: busy == "ai_sort") { on in
                if on { Task { await change("ai_sort", to: true) } } else { askingAIOff = true }
            }
            RowSeparator()
            SwitchRow(symbol: "bell", title: "Tips and news by email",
                      isOn: isOn("tips"), disabled: busy == "tips") { on in
                Task { await change("tips", to: on) }
            }
            RowSeparator()
            SwitchRow(symbol: "heart", title: "Help improve Pearl", sub: "Anonymous usage only",
                      isOn: isOn("analytics"), disabled: busy == "analytics") { on in
                Task { await change("analytics", to: on) }
            }
        }
        if let error = error {
            Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
        }

        CardCaption("Your rights")
        GlassCard(radius: cardRadius) {
            if let contact = privacy.contact, !contact.isEmpty, let mail = URL(string: "mailto:\(contact)") {
                Link(destination: mail) {
                    PrivacyRow(title: "See or correct what we hold") { RowChevron() }
                }
                .buttonStyle(.plain)
                .accessibilityHint("Writes to our privacy officer, who replies within 30 days")
                RowSeparator()
            }
            Button { doc = .privacy } label: {
                PrivacyRow(title: "Privacy policy") {
                    // The design's "v1.0" isn't true yet: the policy is a draft.
                    Text("Draft").font(Nacre.body).foregroundColor(Pearl.muted)
                    RowChevron()
                }
            }
            .buttonStyle(.plain)
        }
    }

    private func isOn(_ key: String) -> Bool { privacy?.consents?[key]?.value == true }

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

    private let moments = [
        Moment(id: "payday", symbol: "calendar", title: "Payday", sub: "When your pay lands"),
        Moment(id: "weekly", symbol: "chart.line.uptrend.xyaxis", title: "Weekly check-in", sub: "Sundays at 10 am"),
        Moment(id: "progress", symbol: "star", title: "Progress", sub: "When your Anchor grows"),
        Moment(id: "milestones", symbol: "sparkle", title: "Milestones", sub: "When a new step opens"),
        Moment(id: "bank", symbol: "building.columns", title: "Bank needs you", sub: "When a bank needs you"),
    ]

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                PageTitle(title: "Notifications", line: "At most 3 a week.")
                if let prefs = settings?.prefs {
                    content(prefs)
                } else if let error = error {
                    Hint(text: error).padding(.horizontal, 16)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 16)
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
        CardCaption("What you get")
        GlassCard(radius: cardRadius) {
            ForEach(Array(moments.enumerated()), id: \.element.id) { i, moment in
                if i > 0 { RowSeparator() }
                SwitchRow(symbol: moment.symbol, title: moment.title, sub: moment.sub,
                          isOn: prefs.types[moment.id]?.phone == true) { on in
                    Task { await setMoment(moment.id, on: on) }
                }
            }
        }
        if permission == .denied { blockedNote }
        if let error = error {
            Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
        }

        CardCaption("Quiet hours")
        GlassCard(radius: cardRadius) {
            quietRow("From", prefs.quiet.from) { value in
                Task { await save(["quiet": ["from": value]]) { $0.quiet.from = value } }
            }
            RowSeparator()
            quietRow("To", prefs.quiet.to) { value in
                Task { await save(["quiet": ["to": value]]) { $0.quiet.to = value } }
            }
        }

        CardCaption("Lock screen")
        GlassCard(radius: cardRadius) {
            SwitchRow(title: "Show amounts",
                      hint: "Off: “Your pay arrived.” On: “Your pay of $2,140 arrived.”",
                      isOn: prefs.lockAmounts) { on in
                Task { await save(["lock_amounts": on]) { $0.lockAmounts = on } }
            }
        }
    }

    /// The switches can't reach her lock screen while iOS is blocking them, so say so.
    private var blockedNote: some View {
        VStack(alignment: .leading, spacing: 4) {
            ProfileNote("Notifications are off for Pearl in iPhone Settings.")
            if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
                Link("Open Settings", destination: url)
                    .font(Nacre.footnote)
                    .foregroundColor(Pearl.action)
                    .padding(.horizontal, 16)
            }
        }
    }

    /// "From   9:00 pm  ›", opening every half hour.
    private func quietRow(_ label: String, _ value: String, chosen: @escaping (String) -> Void) -> some View {
        Menu {
            Picker(label, selection: Binding(get: { value }, set: chosen)) {
                ForEach(QuietTime.all, id: \.self) { time in
                    Text(QuietTime.words(time)).tag(time)
                }
            }
        } label: {
            HStack(spacing: 10) {
                Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(QuietTime.words(value)).font(Nacre.body).foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                RowChevron()
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 50)
            .contentShape(Rectangle())
        }
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

    var body: some View {
        NacreScreen {
            VStack(spacing: 12) {
                VStack(spacing: 10) {
                    RoseBubble(symbol: "bell", size: 72)
                    Text("Want a heads-up?").font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
                        .multilineTextAlignment(.center)
                        .accessibilityAddTraits(.isHeader)
                    Text("Only at the right moments.").font(Nacre.footnote).foregroundColor(Pearl.ink)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 4)

                GlassCard(radius: cardRadius) {
                    moment("calendar", "Payday", "A nudge to set something aside")
                    RowSeparator()
                    moment("chart.line.uptrend.xyaxis", "Weekly check-in", "Your week in one minute")
                    RowSeparator()
                    moment("star", "Progress", "When your Anchor grows")
                    RowSeparator()
                    moment("building.columns", "Bank needs you", "When a bank asks you to sign in")
                }

                Text("Never about overspending. Quiet from \(QuietTime.short(quiet.from)) to \(QuietTime.short(quiet.to)).")
                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 28)
        } actions: {
            BottomActions {
                Button("Turn on notifications") { Task { await turnOn() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy)
            } secondary: {
                Button("Not now") { Task { await answer("not_now") } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .disabled(busy)
            }
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
