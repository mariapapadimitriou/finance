import SwiftUI

/// Add to your bills? (T-32): a purchase as a bill, with how often it
/// repeats, her share, the next payment and its category. Pearl starts with
/// what it knows (a bill it found for the merchant, a split's share).
@MainActor
struct AddToBillsSheet: View {
    let t: Transaction
    let api: APIClient
    let categories: [CategoryList.Category]
    /// The category she just chose, when she came from Change category.
    var category: String? = nil
    let onAdded: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var cadence = "monthly"
    @State private var share = 100
    @State private var next = Date()
    @State private var pickingDay = false
    @State private var chosenCategory = ""
    @State private var pickingCategory = false
    @State private var loaded = false
    @State private var busy = false
    @State private var error: String?

    private struct Suggestion: Decodable {
        let cadence: String
        let next: String
        let share: Int
        let category: String
    }

    private static let cadences: [(key: String, name: String)] = [
        ("weekly", "Every week"), ("biweekly", "Every 2 weeks"), ("monthly", "Every month"),
        ("bimonthly", "Every 2 months"), ("quarterly", "Every 3 months"),
        ("semiannual", "Every 6 months"), ("annual", "Every year"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Add to your bills?") { dismiss() }
            ScrollView {
                VStack(spacing: 12) {
                    QuestionHeader(name: t.merchant, amount: Format.money(t), tone: t.tone, sub: nil)
                    GlassCard {
                        Menu {
                            Picker("", selection: $cadence) {
                                ForEach(Self.cadences, id: \.key) { c in Text(c.name).tag(c.key) }
                            }
                        } label: { rowLabel("Repeats", cadenceName) }
                        .buttonStyle(.plain)
                        RowSeparator()
                        Menu {
                            Picker("", selection: $share) {
                                ForEach(shares, id: \.self) { s in Text("\(s)%").tag(s) }
                            }
                        } label: { rowLabel("Your share", "\(share)%") }
                        .buttonStyle(.plain)
                        RowSeparator()
                        Button { pickingDay.toggle() } label: {
                            rowLabel("Next payment", "Around \(Format.short(Format.isoDay(next)))")
                        }
                        .buttonStyle(.plain)
                        if pickingDay {
                            DatePicker("", selection: $next, in: Date()..., displayedComponents: .date)
                                .datePickerStyle(.graphical).tint(Pearl.action)
                                .padding(.horizontal, 8)
                                .onChange(of: next) { _ in pickingDay = false }
                        }
                        RowSeparator()
                        Button { pickingCategory = true } label: {
                            rowLabel("Category", chosenCategory.isEmpty ? "Choose" : chosenCategory)
                        }
                        .buttonStyle(.plain)
                    }
                    if share < 100 {
                        Text("Your bills count \(Format.amount(billAmount)) of it.")
                            .font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button("Add to bills") { Task { await add() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(!loaded || busy || chosenCategory.isEmpty)
                .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .task { await load() }
        .sheet(isPresented: $pickingCategory) {
            CategorySheet(name: t.merchant, amount: Format.money(t), tone: t.tone, categories: categories,
                          current: chosenCategory, spendingOnly: true) { name, _ in
                chosenCategory = name
                pickingCategory = false
            }
        }
    }

    private var cadenceName: String {
        Self.cadences.first { $0.key == cadence }?.name ?? "Every month"
    }

    /// The usual shares, and hers when a split makes it something else.
    private var shares: [Int] {
        var out = [100, 75, 50, 25]
        if !out.contains(share) { out.append(share) }
        return out.sorted(by: >)
    }

    /// The whole charge, not just her share: the bill is the charge.
    private var billAmount: Double {
        ((t.fullAmount ?? t.amount) * Double(share) / 100 * 100).rounded() / 100
    }

    private func rowLabel(_ title: String, _ value: String) -> some View {
        HStack(spacing: 8) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer()
            Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 50).contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private func load() async {
        do {
            let s: Suggestion = try await api.get("api/transactions/\(t.id)/bill")
            cadence = s.cadence
            share = s.share
            next = Format.localDay(s.next) ?? Date()
            chosenCategory = category ?? s.category
            loaded = true
            self.error = nil
        } catch is CancellationError {
            // The sheet redrew and asked again; that answer fills it in.
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func add() async {
        busy = true
        defer { busy = false }
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(t.id)/bill", [
                "cadence": cadence, "next": Format.isoDay(next), "share": share, "category": chosenCategory,
            ])
            onAdded(reply.title ?? "Added to your bills.")
        } catch {
            self.error = error.localizedDescription
        }
    }
}
