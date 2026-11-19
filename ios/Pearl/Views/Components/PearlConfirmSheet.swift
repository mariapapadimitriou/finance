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
/// swiped away. A failure keeps the sheet up with the error line
/// ("Couldn’t … Nothing changed. Try again.") and the Primary reads "Try
/// again" (S-08rc/rd, T-03x2, SO-06b).
///
/// A+ (G1-PConfirm, T-77c / T-03x): the title centred with ✕ (kit `.shead`),
/// the message in ink 17, then the Primary and the Secondary. No overline
/// and no face (less text); `overline` and `face` are kept so callers
/// read as before. The failure is kit `.errline` (ⓘ in `danger`).
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
        /// T-77c (rethought): the field waits behind this quiet link ("Add
        /// a reason") and shows once she taps it. Use with `.nothing`.
        var reveal: String? = nil

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
    @State private var revealed = false
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

    /// The field shows: always, or once "Add a reason" is tapped (or she
    /// typed one and the sheet came back).
    private var showsField: Bool {
        guard let field = field else { return false }
        return field.reveal == nil || revealed || !text.isEmpty
    }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: title, close: onClose)
                .disabled(busy)
            if let sub = sub {
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                    .padding(.top, -10)
            }
            if let message = message {
                Text(message).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
            if !goes.isEmpty { lines("What goes", goes) }
            if !stays.isEmpty { lines("What stays", stays) }
            if let field = field {
                if showsField {
                    fieldView(field)
                } else if let reveal = field.reveal {
                    Button(reveal) {
                        revealed = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { typing = true }
                    }
                    .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.link)
                    .frame(maxWidth: .infinity, minHeight: 44)
                }
            }
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : primary, busy: busy, busyLabel: busyLabel,
                              secondary: secondary,
                              onPrimary: { Task { await go() } }, onSecondary: onClose)
                .disabled(!ready)
        }
        .onAppear {
            if field != nil && showsField {
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

    /// REDESIGN-09: a visible well, its label above it.
    private func fieldView(_ field: Field) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(field.label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            TextField("", text: $text, prompt: Text(field.prompt).foregroundColor(Pearl.muted))
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .tint(Pearl.action)
                .focused($typing)
                .submitLabel(.done)
                .onSubmit { if ready { Task { await go() } } }
                .padding(.horizontal, 14).frame(minHeight: 44)
                .wellStyle(focused: typing)
                .accessibilityLabel(field.label)
                .accessibilityIdentifier(field.identifier ?? field.label)
                .disabled(busy)
            if let note = field.note {
                Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
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

/// T-49b (G1-Days): a sheet of option rows (Change / Remove), each acting
/// at once. A+: the heading centred with ✕, the who (an icon, the title in
/// Fraunces 22, its line), then one card of rows; a destructive row is red
/// with its icon on the danger wash and no chevron.
struct PearlOptionsSheet: View {
    struct Option: Identifiable {
        let symbol: String
        let title: String
        let sub: String
        var destructive = false
        let action: () -> Void
        var id: String { title }
    }

    /// The centred heading ("Montreal trip"); the overline in the old look.
    let overline: String
    let title: String
    var sub: String? = nil
    var symbol: String = "calendar"
    let options: [Option]
    let onClose: () -> Void

    var body: some View {
        APSheet {
            APSheetHeader(heading: overline, symbol: symbol, title: title, sub: sub, close: onClose)
            APOptionCard {
                ForEach(Array(options.enumerated()), id: \.element.id) { i, o in
                    if i > 0 { APSeparator() }
                    if o.destructive {
                        PearlDestructiveRow(symbol: o.symbol, title: o.title, sub: o.sub, action: o.action)
                    } else {
                        APOptionRow(symbol: o.symbol, title: o.title, sub: o.sub, action: o.action)
                    }
                }
            }
        }
    }
}

/// A red entry row (house rules: red for destructive entry rows): the icon
/// on the danger wash, the title in `danger`, its line muted, no chevron.
struct PearlDestructiveRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                APIcon(symbol: symbol, tone: Pearl.danger, wash: Pearl.danger.opacity(0.12))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.danger)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(.isButton)
    }
}
