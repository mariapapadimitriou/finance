import SwiftUI
import UIKit

// Profile › Your data (THL-116, THL-214, THL-234; Pearl iOS Handoff File,
// Pearl app page): D-01 and D-02 here, D-03 to D-05 below, and Start over in
// StartOverView.swift.

// MARK: - The look these screens share

/// A line icon from the handoff file in a rose-tinted circle.
struct TintedIcon: View {
    let image: String
    var size: CGFloat = 34

    var body: some View {
        Image(image)
            .resizable()
            .renderingMode(.template)
            .foregroundColor(Pearl.action)
            .frame(width: size / 2, height: size / 2)
            .frame(width: size, height: size)
            .background(Circle().fill(Pearl.action.opacity(0.1)))
            .accessibilityHidden(true)
    }
}

/// An icon, a title, a line under it, and a chevron if it opens something.
struct DataRow: View {
    let icon: String
    let title: String
    var sub: String? = nil
    var tone: Color = Pearl.ink
    var chevron = false
    var busy = false

    var body: some View {
        HStack(spacing: 12) {
            TintedIcon(image: icon)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(tone)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .multilineTextAlignment(.leading)
            if busy {
                ProgressView()
            } else if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// "Your data / It's yours.": the title and its one line.
struct DataHeading: View {
    let title: String
    let line: String

    var body: some View {
        Text(title).font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
        Text(line).font(Nacre.footnote).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// "RIGHT AWAY": the label over a card.
struct DataCaption: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased()).font(Nacre.caption).foregroundColor(Pearl.ink)
            .padding(.leading, 16).padding(.top, 4)
            .accessibilityAddTraits(.isHeader)
    }
}

/// A card of rows, its corners as these screens draw them.
struct DataCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        GlassCard(radius: 22, content: content)
    }
}

/// A sheet's nacre band along the top, fading into the sheet (D-04, SO-03).
struct BandedSheetBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        if scheme == .dark {
            SheetBackground()
        } else {
            ZStack(alignment: .top) {
                Color(hex: 0xFFFBFD)
                LinearGradient(colors: [Color(hex: 0xFFD6E0).opacity(0.9), Color(hex: 0xE3D4FF).opacity(0.7),
                                        Color(hex: 0xCFF3EE).opacity(0.5)],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(height: 120)
                LinearGradient(colors: [Color(hex: 0xFFFBFD).opacity(0), Color(hex: 0xFFFBFD)],
                               startPoint: .top, endPoint: .bottom)
                    .frame(height: 120)
            }
            .ignoresSafeArea()
        }
    }
}

// MARK: - D-01 Your data, D-02 the download ready

@MainActor
struct YourDataView: View {
    @EnvironmentObject private var app: AppModel
    /// After Start over: back out of Profile's pages, to Home.
    let goHome: () -> Void

    @State private var summary: ExportSummary?
    @State private var preparing = false
    @State private var downloading = false
    @State private var file: SharedFile?
    @State private var folder: URL?
    @State private var error: String?
    @State private var showStartOver = false
    @State private var showDelete = false

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
                DataHeading(title: "Your data", line: "It’s yours.")
                if let summary = summary { ready(summary) }
                DataCard {
                    Button { Task { await prepare() } } label: {
                        DataRow(icon: "DataDownload", title: "Download a copy", sub: "A spreadsheet of everything",
                                chevron: true, busy: preparing)
                    }
                    .buttonStyle(.plain)
                    .disabled(preparing)
                    RowSeparator()
                    Button { showStartOver = true } label: {
                        DataRow(icon: "DataStartOver", title: "Start over",
                                sub: "Sort everything again from scratch", chevron: true)
                    }
                    .buttonStyle(.plain)
                    RowSeparator()
                    Button { showDelete = true } label: {
                        DataRow(icon: "DataTrash", title: "Delete your account", tone: Pearl.moneyOut, chevron: true)
                    }
                    .buttonStyle(.plain)
                }
                if let error = error { Hint(text: error).padding(.horizontal, 16) }
            }
        }
        .toolbar(.hidden, for: .tabBar)
        .navigationDestination(isPresented: $showStartOver) {
            StartOverView(goHome: goHome, downloadFirst: { downloadFirst { showStartOver = false } })
        }
        .navigationDestination(isPresented: $showDelete) {
            DeleteAccountView(downloadFirst: { downloadFirst { showDelete = false } })
        }
        .sheet(item: $file, onDismiss: removeFile) { file in
            ShareSheet(url: file.url).ignoresSafeArea()
        }
    }

    /// D-02: "Your download is ready", and the button that saves it.
    private func ready(_ summary: ExportSummary) -> some View {
        DataCard {
            VStack(spacing: 4) {
                DataRow(icon: "DataDownload", title: "Your download is ready", sub: counts(summary))
                Button(sizeWords(summary).map { "Download .zip · \($0)" } ?? "Download .zip") {
                    Task { await download() }
                }
                .buttonStyle(NacreButtonStyle(busy: downloading))
                .disabled(downloading)
                .padding(.horizontal, 16)
            }
            .padding(.bottom, 14)
        }
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
            VStack(alignment: .leading, spacing: 12) {
                DataHeading(title: "Delete your account?", line: "Here’s what happens.")
                DataCaption("Right away")
                DataCard {
                    DataRow(icon: "DataUnplug", title: "Your banks are disconnected")
                    RowSeparator()
                    DataRow(icon: "DataSignOut", title: "You’re signed out everywhere")
                }
                DataCaption("Within 30 days")
                DataCard {
                    DataRow(icon: "DataTrash", title: "Everything else is deleted", sub: "Including backups")
                }
                DataCaption("What we keep")
                DataCard {
                    DataRow(icon: "DataShield", title: "A record your account existed", sub: "The law asks us to")
                }
                if let error = error { Hint(text: error).padding(.horizontal, 16) }
            }
        } bottom: {
            Button("Continue") { Task { await open() } }
                .buttonStyle(NacreButtonStyle(busy: opening))
                .disabled(opening)
            Button("Download a copy first", action: downloadFirst)
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
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

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Confirm it’s you") { dismiss() }
            ScrollView {
                VStack(spacing: 10) {
                    Image(systemName: method == "password" ? "key" : "envelope")
                        .font(.system(size: 26))
                        .foregroundColor(Pearl.action)
                        .frame(width: 64, height: 64)
                        .background(Circle().fill(Pearl.action.opacity(0.1)))
                        .accessibilityHidden(true)
                        .padding(.top, 6)
                    Text(line).font(Nacre.body).foregroundColor(Pearl.ink)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.bottom, 6)
                    if method == "code" {
                        CodeBoxes(code: $code, failed: failed).fixedSize()
                    } else if method == "password" {
                        DataCard {
                            FieldRow(label: "Password", text: $password, kind: .secure, content: .password)
                        }
                    }
                    if let error = error { Hint(text: error).padding(.top, 4) }
                    // Never on the sixth digit: deleting always takes this press.
                    Button("Delete my account") { Task { await remove() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                        .disabled(!ready || busy)
                        .padding(.top, 6)
                    if method == "code" {
                        Button("Send a new code") { Task { await sendCode() } }
                            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                            .disabled(busy)
                    }
                    if let other = other {
                        Button(other == "code" ? "Use an email code instead" : "Use your password instead") {
                            choose(other)
                        }
                        .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                        .disabled(busy)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .interactiveDismissDisabled(busy)
        .onAppear { if method.isEmpty, let first = options.usable.first { choose(first) } }
        .onChange(of: code) { _ in failed = false }
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
                .buttonStyle(NacreButtonStyle())
        }
    }
}

/// The open shell, a title and a line, with buttons along the bottom
/// (D-05, SO-04, SO-05).
struct DataResult<Extra: View, Actions: View>: View {
    let title: String
    let line: String
    @ViewBuilder var extra: () -> Extra
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            VStack(spacing: 10) {
                Image("LogoMark").resizable().frame(width: 160, height: 133.333)
                    .accessibilityHidden(true)
                Text(title).font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                Text(line).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
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
