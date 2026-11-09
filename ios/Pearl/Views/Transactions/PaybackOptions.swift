import SwiftUI

// SPLIT-25 (THL-291): a payment's options from the purchase it paid back
// (S-05o) and its Unlink? sheet (S-34s / S-34k).
//
// Presentation to be replaced by custom design, see design refresh: the
// product owner asked for custom Pearl pages and sheets (and a ••• menu on
// each person's row) instead of stock iOS dialogs, and designBOT is drawing
// them. Everything the screens do lives in the server's `LinkInfo` and in
// these two views, so swapping the look touches only this file.

/// S-05o: "Jo paid back $30.00", where the money came from, then View,
/// Unlink… and Cancel. Not a stock iOS dialog (product owner,
/// 2026-11-09). `actions` run after the sheet has gone, so the next sheet
/// can open.
struct PaybackOptionsSheet: View {
    struct Action: Identifiable {
        let id = UUID()
        let title: String
        var destructive = false
        let run: () -> Void
    }

    let title: String
    let message: String?
    let actions: [Action]
    /// Closes the sheet; `then` runs once it's gone.
    let onClose: (_ then: (() -> Void)?) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                SheetTitle(title: title) { onClose(nil) }
                if let message = message, !message.isEmpty {
                    Text(message).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16)
                }
                GlassCard {
                    ForEach(Array(actions.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator(inset: 16) }
                        Button { onClose(a.run) } label: {
                            HStack {
                                Text(a.title).font(Nacre.body)
                                    .foregroundColor(a.destructive ? Pearl.action : Pearl.ink)
                                Spacer()
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(Pearl.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
                Button("Cancel") { onClose(nil) }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Pearl.card))
                    .buttonStyle(.plain)
                    .padding(.horizontal, 16)
            }
            .padding(.bottom, 16)
        }
        .background(SheetBackground())
        .presentationDetents([.medium, .large])
    }
}

// MARK: - Unlink? from the purchase (SPLIT-25, THL-291)

/// S-34s / S-34k: Unlink? for one payment, from the purchase it paid back.
/// The server words the sheet (`LinkInfo.sheet`), so its line says what
/// Unlink does for that kind of payback. Unlink shows a spinner and the
/// sheet stays open until the server answers (S-34s); a failure keeps
/// everything as it was and says so (S-34s error).
@MainActor
struct UnlinkLinkSheet: View {
    let link: Transaction.LinkInfo
    /// The purchase it's unlinked from.
    let charge: String
    let api: APIClient
    let onCancel: () -> Void
    /// S-05t: the toast's title and its Undo.
    let onDone: (String, JSONValue?) -> Void
    @State private var busy = false
    @State private var failed = false

    private struct Reply: Decodable {
        let title: String?
        let undo: JSONValue?
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                SheetTitle(title: link.sheet.title) { onCancel() }
                HStack(spacing: 12) {
                    Initials(name: link.sheet.face, size: 48)
                        .overlay(Circle().strokeBorder(
                            AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose],
                                            center: .center), lineWidth: 1.2))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(link.sheet.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(link.sheet.sub).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
                .padding(.horizontal, 16)
                VStack(spacing: 12) {
                    if let ask = link.sheet.ask {
                        Text(ask)
                    }
                    Text(link.sheet.line)
                    if failed {
                        // S-34s error: color/text/caution, announced by VoiceOver.
                        Text("Couldn’t unlink that. Nothing changed. Try again.")
                            .foregroundColor(Pearl.caution)
                    }
                }
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
                HStack(spacing: 10) {
                    Button(failed ? "Try again" : link.sheet.button) { Task { await unlink() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                    Button("Keep linked", action: onCancel)
                        .font(Nacre.headline).foregroundColor(Pearl.ink)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(Capsule().fill(Pearl.card))
                        .buttonStyle(.plain)
                }
                .disabled(busy)
                .padding(.horizontal, 16)
            }
            .padding(.bottom, 16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        // It grows with the text for Dynamic Type and never cuts it off.
        .presentationDetents(link.sheet.ask == nil ? [.height(320), .large] : [.height(400), .large])
        .interactiveDismissDisabled(busy)
    }

    private func unlink() async {
        busy = true
        defer { busy = false }
        do {
            let reply: Reply
            switch link.kind {
            case "refund":
                reply = try await api.delete("api/transactions/\(link.inflow ?? link.id)/refund")
            case "cash", "app":
                reply = try await api.delete("api/transactions/\(charge)/split/cash/\(link.cashId ?? 0)")
            default:
                reply = try await api.delete("api/transactions/\(charge)/paybacks/\(link.inflow ?? link.id)")
            }
            failed = false
            onDone(reply.title ?? link.toast ?? "Unlinked", reply.undo)
        } catch {
            failed = true
            UIAccessibility.post(notification: .announcement, argument: "Couldn’t unlink that. Nothing changed. Try again.")
        }
    }
}
