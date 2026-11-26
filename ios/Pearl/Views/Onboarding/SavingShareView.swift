import SwiftUI

/// O-10s "How much do you want to save?" (THL-127, THL-119): a share of
/// each paycheque, 5%, 10%, 15%, 20% or her own, and what it comes to each
/// paycheque and each month. Kept as her savings rate (PUT
/// /api/income-bills/saving); she can change it any time.
@MainActor
struct SavingShareView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [SetupRoute]
    @State private var pct: Double = 15
    @State private var custom = false
    @State private var customText = ""
    @State private var monthlyIncome: Double = 0
    @State private var pay: IncomeBills.Pay?
    @State private var busy = false
    @State private var error: String?

    private static let shares: [Double] = [5, 10, 15, 20]

    var body: some View {
        // G6-Saving O-10s: part 3, the share big, the chips, what it comes to;
        // Other puts her share in a well instead. P6d (TP-P6-Setup, TP-Words):
        // "each pay" and "Other" (were "each paycheque" and "Custom").
        OnbScreen(part: 3, partName: "Your money") {
            OnbTitle(title: "How much do you want to save?", line: "A share of each pay. Change it anytime.")
            if !custom {
                VStack(spacing: 0) {
                    Text("\(Int(pct))%").font(.custom("Fraunces-SemiBold", size: 56, relativeTo: .largeTitle))
                        .tracking(-1).foregroundColor(Pearl.ink)
                    Text("of your pay").font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 16)
                .accessibilityElement(children: .combine)
            }
            chips.padding(.top, custom ? 6 : 4)
            if custom {
                ShareWell(text: $customText).padding(.top, 6)
                    .onChange(of: customText) { v in
                        if let n = Double(v.replacingOccurrences(of: "%", with: "")), (0...50).contains(n) { pct = n }
                    }
                ProfileNote(customNote)
            } else {
                APCard {
                    if let pay = pay {
                        APKeyValueRow(key: "Each pay", value: Format.whole(pay.amount * pct / 100))
                        APSeparator(afterFace: false)
                    }
                    APKeyValueRow(key: "Each month", value: "\u{2248} " + Format.whole(monthlyIncome * pct / 100))
                }
                .padding(.top, 8)
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Continue", busy: busy) { Task { await save() } }
        }
        .task { await load() }
    }

    private var chips: some View {
        HStack(spacing: 8) {
            ForEach(Self.shares, id: \.self) { s in
                chip("\(Int(s))%", on: !custom && pct == s) { custom = false; pct = s }
            }
            chip("Other", on: custom) { custom = true; customText = "\(Int(pct))" }
        }
        .frame(maxWidth: .infinity)
    }

    /// "$258 each paycheque · ≈ $559 a month".
    private var customNote: String {
        let month = "\u{2248} " + Format.whole(monthlyIncome * pct / 100) + " a month"
        guard let pay = pay else { return month }
        return Format.whole(pay.amount * pct / 100) + " each pay \u{00B7} " + month
    }

    /// `.chip`: 34 high on `chip`; the one picked is `action`.
    private func chip(_ label: String, on: Bool, _ tap: @escaping () -> Void) -> some View {
        Button(action: tap) {
            Text(label).font(Nacre.subheadline).foregroundColor(on ? Pearl.onAction : Pearl.ink)
                .padding(.horizontal, 14).frame(height: 34)
                .background(Capsule().fill(on ? Pearl.action : APlus.chip))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private struct Saving: Decodable { let pct: Double? }

    private func load() async {
        if let data: IncomeBills = try? await app.api.get("api/income-bills") {
            monthlyIncome = data.totals?.income ?? 0
            pay = data.pays.first
        }
        if let s: Saving = try? await app.api.get("api/income-bills/saving"), let p = s.pct {
            pct = p
            custom = !Self.shares.contains(p)
            if custom { customText = "\(Int(p))" }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let _: Saving = try await app.api.put("api/income-bills/saving", ["pct": pct])
            path.append(.allowance)
        } catch {
            self.error = app.handle(error)
        }
    }
}
