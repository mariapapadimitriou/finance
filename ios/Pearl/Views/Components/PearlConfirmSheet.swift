import SwiftUI

/// TEST-06 (Figma section 16 `1227:18934`, build note `1231:21488`; product
/// owner 2026-11-10): one Pearl sheet for every confirmation that used to be
/// a stock alert or action sheet. A Sheet header (overline, Fraunces title,
/// optional face), the body words, then what the frame adds: a field, a
/// callout, WHAT GOES / WHAT STAYS rows, or option rows. The Primary button
/// names the action; the secondary, ✕ and a swipe down all keep things as
/// they are. No red: a destructive action is the Primary button too.
///
/// Loading: the Primary button reads "Removing…" and the sheet can't be
/// swiped away. A failure keeps the sheet up with a champagne Banner
/// ("Couldn’t … Nothing changed. Try again.") and the Primary reads "Try
/// again" (S-08rc/rd, T-03x2, SO-06b).
struct PearlConfirmSheet: View {
    /// A text field on the sheet (T-77c's Why?, AM-09n's Nickname, SO-06's
    /// Type "reset"): its label, prompt and words under it. `needs` says
    /// what has to be typed before the Primary turns on.
    struct Field {
        let label: String
        var prompt: String = ""
        var note: String? = nil
        var needs: Needs = .anything
        var identifier: String? = nil

        enum Needs: Equatable {
            /// Anything but spaces (T-77c, AM-09n, AM-14n).
            case anything
            /// These exact words, any case (SO-06: "reset").
            case words(String)
            /// Nothing: optional.
            case nothing
        }

        func allows(_ text: String) -> Bool {
            let typed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            switch needs {
            case .anything: return !typed.isEmpty
            case .words(let w): return typed.lowercased() == w.lowercased()
            case .nothing: return true
            }
        }
    }

    /// A row in WHAT GOES / WHAT STAYS (SO-06).
    struct Line: Hashable {
        let title: String
        let sub: String
    }

    var face: String? = nil
    let overline: String
    let title: String
    var sub: String? = nil
    var message: String? = nil
    var field: Field? = nil
    @Binding var text: String
    var goes: [Line] = []
    var stays: [Line] = []
    let primary: String
    var busyLabel: String? = nil
    var secondary: String = "Cancel"
    /// "Couldn’t delete Corner Store. Nothing changed. Try again."
    var failure: String = "Something went wrong. Nothing changed. Try again."
    let onClose: () -> Void
    /// Does the thing. Throwing keeps the sheet up with the Banner; a
    /// `SplitMenuError` puts the server's own words on it.
    let run: () async throws -> Void

    @State private var busy = false
    @State private var failed: String?
    @FocusState private var typing: Bool

    init(face: String? = nil, overline: String, title: String, sub: String? = nil, message: String? = nil,
         field: Field? = nil, text: Binding<String> = .constant(""), goes: [Line] = [], stays: [Line] = [],
         primary: String, busyLabel: String? = nil, secondary: String = "Cancel",
         failure: String = "Something went wrong. Nothing changed. Try again.",
         onClose: @escaping () -> Void, run: @escaping () async throws -> Void) {
        self.face = face
        self.overline = overline
        self.title = title
        self.sub = sub
        self.message = message
        self.field = field
        self._text = text
        self.goes = goes
        self.stays = stays
        self.primary = primary
        self.busyLabel = busyLabel
        self.secondary = secondary
        self.failure = failure
        self.onClose = onClose
        self.run = run
    }

    private var ready: Bool { field.map { $0.allows(text) } ?? true }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: face, overline: overline, title: title, sub: sub, close: onClose)
                .disabled(busy)
            if let message = message {
                Text(message).font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !goes.isEmpty { lines("What goes", goes) }
            if !stays.isEmpty { lines("What stays", stays) }
            if let field = field { fieldView(field) }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : primary, busy: busy, busyLabel: busyLabel,
                              secondary: secondary,
                              onPrimary: { Task { await go() } }, onSecondary: onClose)
                .disabled(!ready)
        }
        .onAppear {
            if field != nil {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { typing = true }
            }
        }
    }

    private func lines(_ heading: String, _ rows: [Line]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            PearlSectionLabel(text: heading)
            PearlOptionCard {
                ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                    if i > 0 { PearlDivider() }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                        Text(row.sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 12)
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }

    private func fieldView(_ field: Field) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(field.label).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
            TextField("", text: $text, prompt: Text(field.prompt).foregroundColor(Pearl.muted))
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .focused($typing)
                .submitLabel(.done)
                .onSubmit { if ready { Task { await go() } } }
                .padding(.horizontal, 14).frame(minHeight: 50)
                .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.card))
                .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
                    .strokeBorder(typing ? Pearl.action : Pearl.border, lineWidth: typing ? 1.5 : 1))
                .accessibilityLabel(field.label)
                .accessibilityIdentifier(field.identifier ?? field.label)
                .disabled(busy)
            if let note = field.note {
                Text(note).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func go() async {
        guard ready, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = failure
        }
    }
}

/// T-49b: a sheet of Option rows (Change / Remove), each acting at once.
struct PearlOptionsSheet: View {
    struct Option: Identifiable {
        let symbol: String
        let title: String
        let sub: String
        let action: () -> Void
        var id: String { title }
    }

    let overline: String
    let title: String
    var sub: String? = nil
    let options: [Option]
    let onClose: () -> Void

    var body: some View {
        PearlSheet {
            PearlSheetHeader(overline: overline, title: title, sub: sub, close: onClose)
            PearlOptionCard {
                ForEach(Array(options.enumerated()), id: \.element.id) { i, o in
                    if i > 0 { PearlDivider() }
                    PearlOptionRow(symbol: o.symbol, title: o.title, sub: o.sub, action: o.action)
                }
            }
        }
    }
}
