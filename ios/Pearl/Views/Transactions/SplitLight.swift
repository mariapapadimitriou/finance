import ContactsUI
import SwiftUI

// P11 · Lighter split (TP-P11-Split, fewer taps, approved by the product
// owner 2026-11-26; THL-289, THL-291, THL-181, THL-303, THL-165): one sheet,
// "Split $75.48". People she has split with before are chips; Evenly is
// already done; "I'm paying a share"; Other ways one level down; Add someone
// new where typing always works and Contacts asks nothing until "Choose from
// Contacts" (the iOS contact picker needs no permission: the agreed
// exception to Pearl sheets). The sheet itself is SplitSheet's `light`
// layout (SplitFlow.swift); these are its parts.

/// P11a: a person as a chip, rose when they're in the split; "+ Add" last.
struct SplitPersonChip: View {
    let name: String
    var on = false
    var add = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(add ? "+" : APFace.initials(name))
                    .font(.custom("Figtree-Medium", size: 12, relativeTo: .caption))
                    .foregroundColor(on ? Pearl.onAction : Pearl.ink)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(on ? Color.white.opacity(0.22) : Pearl.ink.opacity(0.08)))
                Text(add ? "Add" : name)
                    .font(Nacre.body).foregroundColor(on ? Pearl.onAction : (add ? Pearl.link : Pearl.ink))
                    .lineLimit(1)
            }
            .padding(.leading, 6).padding(.trailing, 14).frame(minHeight: 44)
            .background(Capsule().fill(on ? Pearl.action : Pearl.card))
            .overlay(Capsule().strokeBorder(on ? Color.clear : Pearl.ink.opacity(0.12), lineWidth: 1))
            .contentShape(Capsule())
            .animation(.easeOut(duration: 0.15), value: on)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(add ? "Add someone new" : name)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// P11c: Other ways, one level down. Each opens today's screen (S-03).
struct SplitOtherWaysSheet: View {
    let onPick: (String) -> Void
    let onBack: () -> Void
    let onClose: () -> Void

    private static let ways: [(mode: String, title: String, sub: String, symbol: String)] = [
        ("amount", "Amounts", "Type what each person owes", "dollarsign.circle"),
        ("percent", "Percent", "Like 60% and 40%", "percent"),
        ("shares", "Shares", "Like 2 for Sam, 1 for you", "person.2"),
        ("unknown", "Not sure yet", "Add amounts when you know", "calendar"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitleBar(title: "Other ways", back: onBack, close: onClose)
            ScrollView {
                APCard {
                    ForEach(Array(Self.ways.enumerated()), id: \.element.mode) { i, w in
                        if i > 0 { APSeparator(afterFace: false) }
                        Button { onPick(w.mode) } label: {
                            CFRowLabel(symbol: w.symbol, title: w.title, sub: w.sub)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("split-way-\(w.mode)")
                    }
                }
                .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 16)
            }
        }
        .background(APSheetSurface())
        .fitsContent()
        .presentationDragIndicator(.visible)
    }
}

/// P11d: Add someone new. The field is focused and looks typeable; Add
/// "Jo" always works; people from past splits that match; Choose from
/// Contacts opens the system picker, which asks for nothing.
struct AddSomeoneNewSheet: View {
    /// People she has split with before, to match what she types.
    let known: [String]
    /// Already on this split.
    let already: [String]
    /// Refused names (a joint account's holders) and why.
    var refuse: (String) -> String? = { _ in nil }
    let onAdd: (String) -> Void
    let onBack: () -> Void
    let onClose: () -> Void

    @State private var typed = ""
    @State private var picking = false
    @FocusState private var focused: Bool

    private var name: String { typed.trimmingCharacters(in: .whitespaces) }
    private var matches: [String] {
        guard !name.isEmpty else { return [] }
        return known.filter { $0.localizedCaseInsensitiveContains(name) && !already.contains($0)
            && $0.caseInsensitiveCompare(name) != .orderedSame }
    }

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitleBar(title: "Add someone new", back: onBack, close: onClose)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("", text: $typed, prompt: Text("Type a name").foregroundColor(Pearl.muted))
                        .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                        .textInputAutocapitalization(.words).autocorrectionDisabled()
                        .focused($focused)
                        .submitLabel(.done).onSubmit(add)
                        .padding(.horizontal, 14).frame(minHeight: 48)
                        .wellStyle(focused: focused)
                        .accessibilityIdentifier("split-add-name")
                    if let why = refuse(name), !name.isEmpty { APErrorLine(text: why) }
                    if !name.isEmpty || !matches.isEmpty {
                        APCard {
                            if !name.isEmpty {
                                Button(action: add) {
                                    HStack(spacing: 12) {
                                        Text("+").font(.system(size: 20, weight: .medium)).foregroundColor(Pearl.action)
                                            .frame(width: 36, height: 36)
                                        Text("Add “\(name)”").font(Nacre.body).foregroundColor(Pearl.link)
                                        Spacer(minLength: 0)
                                    }
                                    .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .disabled(refuse(name) != nil)
                            }
                            ForEach(Array(matches.enumerated()), id: \.element) { i, n in
                                if i > 0 || !name.isEmpty { APSeparator() }
                                Button { onAdd(n) } label: {
                                    APPersonRow(face: n, name: n, line: "From a past split", lineTone: Pearl.muted) { EmptyView() }
                                        .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    APCard {
                        Button { focused = false; picking = true } label: {
                            CFRowLabel(symbol: "person.crop.circle.badge.plus", title: "Choose from Contacts")
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("split-contacts")
                    }
                }
                .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 16)
            }
        }
        .background(APSheetSurface())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { focused = true } }
        .sheet(isPresented: $picking) {
            ContactPicker { picked in
                picking = false
                if let picked = picked, refuse(picked) == nil { onAdd(picked) }
            }
            .ignoresSafeArea()
        }
    }

    private func add() {
        guard !name.isEmpty, refuse(name) == nil else { return }
        onAdd(name)
    }
}

/// CNContactPickerViewController: the system's own contact list. It runs
/// out of process and hands back only the contact she taps, so Pearl needs
/// no Contacts permission and no alert is shown (product owner's call, P11).
struct ContactPicker: UIViewControllerRepresentable {
    let onDone: (String?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onDone: onDone) }

    func makeUIViewController(context: Context) -> CNContactPickerViewController {
        let picker = CNContactPickerViewController()
        picker.delegate = context.coordinator
        picker.displayedPropertyKeys = [CNContactGivenNameKey, CNContactFamilyNameKey]
        return picker
    }

    func updateUIViewController(_ controller: CNContactPickerViewController, context: Context) {}

    final class Coordinator: NSObject, CNContactPickerDelegate {
        let onDone: (String?) -> Void
        init(onDone: @escaping (String?) -> Void) { self.onDone = onDone }

        func contactPicker(_ picker: CNContactPickerViewController, didSelect contact: CNContact) {
            onDone(Self.name(of: contact))
        }

        func contactPickerDidCancel(_ picker: CNContactPickerViewController) { onDone(nil) }

        static func name(of c: CNContact) -> String? {
            var name = "\(c.givenName) \(c.familyName)".trimmingCharacters(in: .whitespaces)
            if name.isEmpty { name = c.nickname.trimmingCharacters(in: .whitespaces) }
            if name.isEmpty { name = c.organizationName.trimmingCharacters(in: .whitespaces) }
            return name.isEmpty ? nil : name
        }
    }
}
