import SwiftUI

/// T-20 Add a tag: one or more of her tags, or a new one, on every row she
/// picked in Cash flow.
struct BulkTagSheet: View {
    let title: String
    let amount: String
    let tone: Color
    let count: Int
    /// Her tags, to tick.
    let known: [String]
    let onAdd: ([String]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var typed = ""
    @State private var chosen: [String] = []

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Add a tag") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                        TextField("", text: $typed, prompt: Text("New tag").foregroundColor(Pearl.muted))
                            .font(Nacre.body).autocorrectionDisabled().textInputAutocapitalization(.never)
                            .submitLabel(.done).onSubmit(addTyped)
                        if !clean(typed).isEmpty {
                            Button("Add", action: addTyped).font(Nacre.textButton).foregroundColor(Pearl.link)
                        }
                    }
                    .padding(.horizontal, 14).frame(height: 44)
                    .background(Capsule().fill(Pearl.ink.opacity(0.08)))
                    let tags = shownTags
                    if !tags.isEmpty {
                        Text("YOUR TAGS").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16)
                        GlassCard {
                            ForEach(Array(tags.enumerated()), id: \.element) { i, tag in
                                if i > 0 { RowSeparator(inset: 52) }
                                Button { toggle(tag) } label: {
                                    HStack(spacing: 12) {
                                        Image(systemName: chosen.contains(tag) ? "checkmark.circle.fill" : "circle")
                                            .font(.system(size: 22))
                                            .foregroundColor(chosen.contains(tag) ? Pearl.action : Pearl.muted)
                                        Text(tag).font(Nacre.body).foregroundColor(Pearl.ink)
                                        Spacer()
                                    }
                                    .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityAddTraits(chosen.contains(tag) ? .isSelected : [])
                            }
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            Button(chosen.count > 1 ? "Add \(chosen.count) tags" : "Add tag") {
                addTyped()
                onAdd(chosen)
            }
            .buttonStyle(NacreButtonStyle())
            .disabled(chosen.isEmpty && clean(typed).isEmpty)
            .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    /// "3  3 transactions  −$89.00".
    private var header: some View {
        HStack(spacing: 12) {
            Initials(name: "\(count)", size: 48)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(1)
                Text(amount).font(Nacre.subheadline).foregroundColor(tone)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }

    /// Her tags and any new ones, narrowed by what she's typing.
    private var shownTags: [String] {
        var all = known
        for tag in chosen where !all.contains(tag) { all.insert(tag, at: 0) }
        let q = clean(typed)
        return q.isEmpty ? all : all.filter { $0.localizedCaseInsensitiveContains(q) }
    }

    private func clean(_ s: String) -> String { s.trimmingCharacters(in: .whitespaces) }

    private func addTyped() {
        let tag = clean(typed).replacingOccurrences(of: "#", with: "")
        guard !tag.isEmpty else { return }
        if !chosen.contains(tag) { chosen.append(tag) }
        typed = ""
    }

    private func toggle(_ tag: String) {
        if let i = chosen.firstIndex(of: tag) { chosen.remove(at: i) } else { chosen.append(tag) }
    }
}
