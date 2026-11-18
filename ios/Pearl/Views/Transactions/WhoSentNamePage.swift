import SwiftUI

/// T-14 Who sent this? (THL-232) before PB-30, for money no one owes her
/// that Pearl can't put a name to (2026-11-18, after #380): the same
/// question as Needs a look asks it (AnswerSheet's `.sender` step), with a
/// name typed or one of the RECENT people, then Continue. The name is who
/// PB-30's OTHER PURCHASES are split with; nothing is saved here, so the
/// payback keeps one save and one Undo. No "Use your bank's name instead"
/// or Skip: those answer the Needs a look question, and this is a step in
/// Paid back.
@MainActor
struct WhoSentNamePage: View {
    let api: APIClient
    /// The money's face: "E-Transfer", "+$30.00", its day.
    let name: String
    let amount: String
    let date: String
    let onPick: (String) -> Void
    let onClose: () -> Void

    @State private var text = ""
    @State private var choice: String?
    @State private var recent: [String] = []

    private var typed: String { text.trimmingCharacters(in: .whitespaces) }

    private var shown: [String] {
        recent.filter { typed.isEmpty || $0.localizedCaseInsensitiveContains(typed) }
    }

    private var picked: String? { choice ?? (typed.isEmpty ? nil : typed) }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Who sent this?") { onClose() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: name, amount: amount, tone: Pearl.moneyIn, sub: Format.short(date))
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
                        TextField("", text: $text, prompt: Text("Name").foregroundColor(Pearl.muted))
                            .font(Nacre.body).autocorrectionDisabled()
                            .textInputAutocapitalization(.words)
                            .accessibilityLabel("Name")
                            .onChange(of: text) { value in if !value.isEmpty { choice = nil } }
                    }
                    .padding(.horizontal, 14).frame(height: 44)
                    .background(Capsule().fill(Pearl.ink.opacity(0.08)))
                    if !shown.isEmpty {
                        Text("RECENT").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16)
                        GlassCard {
                            ForEach(Array(shown.enumerated()), id: \.element) { i, n in
                                if i > 0 { RowSeparator() }
                                row(n)
                            }
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            Button("Continue") { if let n = picked { onPick(n) } }
                .buttonStyle(NacreButtonStyle())
                .disabled(picked == nil)
                .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await load() }
    }

    private func row(_ n: String) -> some View {
        Button {
            choice = n
            text = ""
        } label: {
            HStack(spacing: 12) {
                Text(n).font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                if choice == n {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(choice == n ? .isSelected : [])
    }

    /// GET /api/people/recent: the people she's split with, newest first.
    private func load() async {
        struct Past: Decodable { let name: String }
        struct Reply: Decodable { let people: [Lenient<Past>] }
        let r: Reply? = try? await api.get("api/people/recent")
        recent = (r?.people ?? []).compactMap { $0.value?.name }
    }
}
