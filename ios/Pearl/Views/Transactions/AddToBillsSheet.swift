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
    /// T-106 (G1-TxPage): Repeats and Your share open Pearl sheets, not stock menus.
    @State private var picking: Pick?
    @State private var loaded = false
    @State private var busy = false
    @State private var error: String?

    private enum Pick: String, Identifiable {
        case cadence, share
        var id: String { rawValue }
    }

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
            CFSheetTitle(title: "Add to your bills?") { dismiss() }
            ScrollView {
                VStack(spacing: 12) {
                    // T-106 (G1-TxPage): "Rogers · −$95.00 · every month".
                    APQuestionWho(name: t.merchant, amount: Format.money(t), tone: t.tone,
                                  sub: cadenceName.lowercased())
                    APCard {
                        Button { picking = .cadence } label: { rowLabel("Repeats", cadenceName) }
                            .buttonStyle(.plain)
                        APSeparator(afterFace: false)
                        Button { picking = .share } label: { rowLabel("Your share", "\(share)%") }
                            .buttonStyle(.plain)
                        APSeparator(afterFace: false)
                        // G0-DateSheet DP-02: the Pearl date sheet, today onward.
                        Button { pickingDay = true } label: {
                            rowLabel("Next payment", "Around \(Format.short(Format.isoDay(next)))")
                        }
                        .buttonStyle(.plain)
                        APSeparator(afterFace: false)
                        Button { pickingCategory = true } label: {
                            rowLabel("Category", chosenCategory.isEmpty ? "Choose" : chosenCategory,
                                     choose: chosenCategory.isEmpty)
                        }
                        .buttonStyle(.plain)
                    }
                    if share < 100 {
                        Text("Your bills count \(Format.amount(billAmount)) of it.")
                            .font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16)
                    }
                    if let error = error { APErrorLine(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button("Add to bills") { Task { await add() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(!loaded || busy || chosenCategory.isEmpty)
                .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .cfSheet()
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .task { await load() }
        .pearlDateSheet(isPresented: $pickingDay, title: "When is it due next?", selection: $next,
                        range: .todayOnward)
        .sheet(item: $picking) { which in
            switch which {
            case .cadence:
                CFRadioSheet(title: "Repeats", options: Self.cadences.map { ($0.key, $0.name) }, chosen: cadence) {
                    cadence = $0
                    picking = nil
                }
            case .share:
                CFRadioSheet(title: "Your share", options: shares.map { (String($0), "\($0)%") },
                             chosen: String(share)) {
                    share = Int($0) ?? share
                    picking = nil
                }
            }
        }
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

    /// kit `.kv`; "Choose" in `link` until there's an answer (T-106s).
    private func rowLabel(_ title: String, _ value: String, chevron: Bool = true, choose: Bool = false) -> some View {
        HStack(spacing: 8) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer()
            Text(value).font(Nacre.body).foregroundColor(choose ? Pearl.link : Pearl.muted).lineLimit(1)
            if chevron { CFChevron() }
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
