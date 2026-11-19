import SwiftUI
import UIKit

// Profile › Your data (THL-116, THL-214, THL-234; Pearl iOS Handoff File,
// Pearl app page): D-01 and D-02 here, D-03 to D-05 below, and Start over in
// StartOverView.swift.

// MARK: - The look these screens share

/// A line icon from the handoff file on the A+ 36 pt circle: action wash,
/// danger for Delete, money-in for a ready download.
struct DataIcon: View {
    let image: String
    var size: CGFloat = 36
    var tone: Color = Pearl.action

    var body: some View {
        Image(image)
            .resizable()
            .renderingMode(.template)
            .foregroundColor(tone)
            .frame(width: size / 2, height: size / 2)
            .frame(width: size, height: size)
            .background(Circle().fill(wash))
            .accessibilityHidden(true)
    }

    private var wash: Color {
        if tone == Pearl.danger { return ProfileTone.dangerWash }
        if tone == Pearl.moneyIn { return ProfileTone.goodWash }
        return ProfileTone.actionWash
    }
}

/// The A+ row: an icon, a title over its line, a chevron if it opens something.
struct DataRow: View {
    let icon: String
    let title: String
    var sub: String? = nil
    var tone: Color = Pearl.ink
    var chevron = false
    var busy = false
    var iconTone: Color? = nil

    var body: some View {
        HStack(spacing: 12) {
            DataIcon(image: icon, tone: iconTone ?? (tone == Pearl.danger ? Pearl.danger : Pearl.action))
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(tone)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .multilineTextAlignment(.leading)
            if busy {
                ProgressView()
            } else if chevron {
                APChevron()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// "Your data / It's yours.": the 34 pt title and its `muted` line.
struct DataHeading: View {
    let title: String
    let line: String?

    var body: some View {
        ProfileHeading(title: title, intro: line)
    }
}

/// "RIGHT AWAY": the A+ label over a card.
struct DataCaption: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        APSectionLabel(text: text).padding(.top, 12)
    }
}

/// A card of rows, its corners as these screens draw them.
struct DataCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        APCard(content: content)
    }
}

/// A sheet's surface (D-04, SO-03): the A+ sheet, as every other one.
struct BandedSheetBackground: View {
    var body: some View { SheetBackground() }
}

// MARK: - D-01 Your data, D-02 the download ready

@MainActor
struct YourDataView: View {
    @EnvironmentObject private var app: AppModel
    /// After Start over: back out of Profile's pages, to Home.
    let goHome: () -> Void
    /// Opened from Delete your account's "Download a copy first" (Sign-in
    /// and security): start getting the copy ready straight away.
    var prepareOnOpen = false

    @State private var summary: ExportSummary?
    @State private var prepared = false
    @State private var preparing = false
    @State private var downloading = false
    @State private var file: SharedFile?
    @State private var folder: URL?
    @State private var error: String?
    @State private var showStartOver = false

    private struct ExportSummary: Decodable {
        let accounts: Int?
        let transactions: Int?
        let bytes: Int?
    }

    /// The .zip, somewhere the share sheet can hand it on from.
    private struct SharedFile: Identifiable {
        let id = UUID()
        let url: URL
    }

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                DataHeading(title: "Your data", line: "It\u{2019}s yours.")
                if preparing {
                    DataCard {
                        DataRow(icon: "DataDownload", title: "Getting your copy ready\u{2026}", busy: true)
                    }
                    .padding(.top, 6)
                } else if let summary = summary {
                    ready(summary).padding(.top, 6)
                }
                DataCard {
                    Button { Task { await prepare() } } label: {
                        DataRow(icon: "DataDownload", title: "Download a copy", sub: "A spreadsheet of everything",
                                chevron: true)
                    }
                    .buttonStyle(.plain)
                    .disabled(preparing)
                    APSeparator()
                    Button { showStartOver = true } label: {
                        DataRow(icon: "DataStartOver", title: "Start over",
                                sub: "Your banks stay. Sorting starts fresh.", chevron: true)
                    }
                    .buttonStyle(.plain)
                    // Delete your account moved to Sign-in and security (G5-Data, G5-Security).
                }
                .padding(.top, 6)
                if let error = error, summary == nil { APErrorLine(text: error) }
            }
        }
        .toolbar(.hidden, for: .tabBar)
        .navigationDestination(isPresented: $showStartOver) {
            StartOverView(goHome: goHome, downloadFirst: { downloadFirst { showStartOver = false } })
        }
        .task {
            guard prepareOnOpen, !prepared else { return }
            prepared = true
            await prepare()
        }
        .sheet(item: $file, onDismiss: removeFile) { file in
            ShareSheet(url: file.url).ignoresSafeArea()
        }
    }

    /// D-02 (G5-Data): "Your download is ready", then the button that saves
    /// it; if it couldn't save, the reason and Try again.
    @ViewBuilder private func ready(_ summary: ExportSummary) -> some View {
        DataCard {
            DataRow(icon: "DataDownload", title: "Your download is ready", sub: counts(summary), iconTone: Pearl.moneyIn)
        }
        if let error = error { APErrorLine(text: error) }
        Button(error != nil ? "Try again" : (sizeWords(summary).map { "Download .zip \u{00B7} \($0)" } ?? "Download .zip")) {
            Task { await download() }
        }
        .buttonStyle(APPrimaryButtonStyle(busy: downloading))
        .disabled(downloading)
    }

    /// "6 accounts · 1,306 transactions".
    private func counts(_ summary: ExportSummary) -> String {
        let accounts = summary.accounts ?? 0
        let transactions = summary.transactions ?? 0
        return "\(accounts.formatted()) account\(accounts == 1 ? "" : "s") · "
            + "\(transactions.formatted()) transaction\(transactions == 1 ? "" : "s")"
    }

    /// "84 KB", "1.2 MB". Never "0 KB".
    private func sizeWords(_ summary: ExportSummary) -> String? {
        guard let bytes = summary.bytes, bytes > 0 else { return nil }
        if bytes < 1_048_576 { return "\(max(1, Int((Double(bytes) / 1024).rounded()))) KB" }
        return String(format: "%.1f MB", Double(bytes) / 1_048_576)
    }

    /// "Download a copy first", from D-03 or SO-02: back here, getting it ready.
    private func downloadFirst(back: () -> Void) {
        back()
        Task { await prepare() }
    }

    private func prepare() async {
        guard !preparing else { return }
        preparing = true
        defer { preparing = false }
        do {
            summary = try await app.api.get("api/data/export")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func download() async {
        downloading = true
        defer { downloading = false }
        do {
            let data = try await app.api.download("api/data/export.zip")
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let url = folder.appendingPathComponent("pearl-data.zip")
            self.folder = folder
            try data.write(to: url, options: [.atomic, .completeFileProtection])
            error = nil
            file = SharedFile(url: url)
        } catch let problem where problem is APIError || problem is CancellationError {
            error = app.handle(problem)
        } catch {
            self.error = "Pearl couldn’t save the download. Try again."
        }
    }

    /// Her whole history shouldn't stay in temporary files once it's handed on.
    private func removeFile() {
        guard let folder = folder else { return }
        try? FileManager.default.removeItem(at: folder)
        self.folder = nil
    }
}

/// The system share sheet, for saving the .zip to Files or sending it on.
private struct ShareSheet: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

// MARK: - D-03 Delete your account?

@MainActor
struct DeleteAccountView: View {
    @EnvironmentObject private var app: AppModel
    let downloadFirst: () -> Void

    @State private var options: DeleteOptions?
    @State private var confirming = false
    @State private var opening = false
    @State private var error: String?
    /// The account is gone: D-05 shows once the sheet has closed.
    @State private var deleted: DeleteAccountSheet.Deleted?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 8) {
                DataHeading(title: "Delete your account?", line: nil)
                DataCaption("Right away")
                DataCard {
                    APBullet(text: "Your banks are disconnected")
                    APSeparator(afterFace: false)
                    APBullet(text: "You\u{2019}re signed out everywhere")
                }
                DataCaption("Within 30 days")
                DataCard {
                    APBullet(text: "Everything else is deleted", sub: "Including backups")
                }
                DataCaption("What we keep")
                DataCard {
                    APBullet(text: "A record your account existed", sub: "The law asks us to")
                }
                if let error = error { APErrorLine(text: error).padding(.top, 4) }
            }
        } bottom: {
            Button("Continue") { Task { await open() } }
                .buttonStyle(APPrimaryButtonStyle(busy: opening))
                .disabled(opening)
            Button("Download a copy first", action: downloadFirst)
                .buttonStyle(APQuietTextStyle())
        }
        .toolbar(.hidden, for: .tabBar)
        .sheet(isPresented: $confirming, onDismiss: finish) {
            if let options = options {
                DeleteAccountSheet(options: options) { done in
                    deleted = done
                    confirming = false
                }
                .background(BandedSheetBackground())
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
            }
        }
    }

    /// Nothing is deleted yet: this only asks how she can confirm it's her.
    private func open() async {
        opening = true
        defer { opening = false }
        do {
            let reply: DeleteOptions = try await app.api.get("api/account/delete")
            guard !reply.usable.isEmpty else {
                error = "There’s no way to confirm it’s you on this iPhone. Contact us and we’ll help."
                return
            }
            options = reply
            error = nil
            confirming = true
        } catch {
            self.error = app.handle(error)
        }
    }

    private func finish() {
        if let deleted = deleted { app.accountDeleted(sentTo: deleted.sentTo) }
    }
}

/// How she can confirm it's her (GET /api/account/delete).
struct DeleteOptions: Decodable {
    let methods: [String]

    /// The server also takes a passkey, but the iPhone can't offer one until
    /// the app has its associated domain (see SettingsViews.swift). Face ID
    /// alone proves nothing to the server, so D-04's Face ID state waits too.
    var usable: [String] { ["code", "password"].filter(methods.contains) }
}

// MARK: - D-04 Confirm it's you

@MainActor
struct DeleteAccountSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let options: DeleteOptions
    let done: (Deleted) -> Void

    @State private var method = ""
    @State private var code = ""
    @State private var password = ""
    @State private var sentTo: String?
    @State private var failed = false
    @State private var busy = false
    @State private var error: String?

    struct Deleted: Decodable {
        let sentTo: String?
        enum CodingKeys: String, CodingKey { case sentTo = "confirmation_sent_to" }
    }

    private struct Sent: Decodable {
        let sentTo: String?
        enum CodingKeys: String, CodingKey { case sentTo = "sent_to" }
    }

    private var ready: Bool { method == "code" ? code.count == 6 : !password.isEmpty }

    /// G5-Delete D-04: the six code wells (or the password well), then
    /// Delete my account, the rose Primary, greyed until it's ready.
    var body: some View {
        VStack(spacing: 0) {
            APSheetTitle(title: "Confirm it\u{2019}s you") { dismiss() }
                .padding(.horizontal, 16).padding(.top, 14)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(line).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if method == "code" {
                        ProfileCodeWells(code: $code, failed: failed)
                        if failed {
                            Text("That code didn\u{2019}t work. Try again or send a new one.")
                                .font(Nacre.footnote).foregroundColor(Pearl.danger)
                                .frame(maxWidth: .infinity)
                        }
                    } else if method == "password" {
                        SecureWell(label: "Password", text: $password, content: .password)
                    }
                    if let error = error, !failed { APErrorLine(text: error) }
                }
                .padding(.horizontal, 16).padding(.top, 8)
                .padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 0) {
                // Never on the sixth digit: deleting always takes this press.
                Button("Delete my account") { Task { await remove() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy, busyLabel: "Deleting\u{2026}"))
                    .disabled(!ready || busy)
                    .padding(.bottom, 4)
                if method == "code" {
                    Button("Send a new code") { Task { await sendCode() } }
                        .buttonStyle(APQuietTextStyle())
                        .disabled(busy)
                }
                if let other = other {
                    Button(other == "code" ? "Use an email code instead" : "Use your password instead") {
                        choose(other)
                    }
                    .buttonStyle(APQuietTextStyle())
                    .disabled(busy)
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .interactiveDismissDisabled(busy)
        .onAppear { if method.isEmpty, let first = options.usable.first { choose(first) } }
        .onChange(of: code) { c in if !c.isEmpty { failed = false } }
    }

    private var line: String {
        if method == "password" { return "Enter your password. This can’t be undone." }
        guard let sentTo = sentTo else { return "Sending a 6-digit code to your email." }
        return "We sent a 6-digit code to \(sentTo). This can’t be undone."
    }

    /// The other way to confirm, when there is one.
    private var other: String? { options.usable.first { $0 != method } }

    private func choose(_ next: String) {
        method = next
        error = nil
        if next == "code" { Task { await sendCode() } }
    }

    private func sendCode() async {
        error = nil
        do {
            let reply: Sent = try await app.api.post("api/account/delete/code")
            sentTo = reply.sentTo
            code = ""
        } catch {
            self.error = app.handle(error)
        }
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        error = nil
        do {
            let proof: [String: Any] = method == "code" ? ["method": "code", "code": code]
                : ["method": "password", "password": password]
            done(try await app.api.post("api/account/delete", proof))
        } catch {
            failed = true
            code = ""
            password = ""
            self.error = app.handle(error)
        }
    }
}

// MARK: - D-05 Your account is deleted

/// Full screen, outside the tabs: she's signed out by the time it shows.
@MainActor
struct AccountDeletedView: View {
    @EnvironmentObject private var app: AppModel
    let sentTo: String?

    var body: some View {
        DataResult(title: "Your account is deleted",
                   line: sentTo.map { "We’ve sent a confirmation to \($0)." }
                       ?? "We’ve disconnected your banks and signed you out.") {
            EmptyView()
        } actions: {
            Button("Close") { app.phase = .signedOut }
                .buttonStyle(APPrimaryButtonStyle())
        }
    }
}

/// The open shell, a title and a line, with buttons along the bottom
/// (D-05, SO-04, SO-05).
struct DataResult<Extra: View, Actions: View>: View {
    let title: String
    let line: String
    /// The pearl over the title; off when a list needs the room (SO-04b).
    var showsArt = true
    @ViewBuilder var extra: () -> Extra
    @ViewBuilder var actions: () -> Actions

    /// G5-StartOver SO-04, G5-Delete D-05: the mark, the 34 pt title and a
    /// `muted` line, centred; the buttons along the bottom.
    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            VStack(spacing: 8) {
                if showsArt {
                    APMark(width: 170).padding(.bottom, 28)
                }
                Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                Text(line).font(Nacre.body).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
                extra()
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
            Spacer(minLength: 0)
            VStack(spacing: 4, content: actions)
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
        }
        .nacreScreen()
    }
}
