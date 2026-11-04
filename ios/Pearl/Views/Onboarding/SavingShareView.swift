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
        NacreScreen {
            ShellProgress(part: 3, name: "Your money")
            Text("How much do you want to save?").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text("A share of each paycheque. Change it anytime.").font(Nacre.body)
            VStack(spacing: 2) {
                Text("\(Int(pct))%").font(.custom("Fraunces-SemiBold", size: 64, relativeTo: .largeTitle))
                    .foregroundColor(Pearl.ink)
                Text("of your pay").font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .accessibilityElement(children: .combine)
            HStack(spacing: 8) {
                ForEach(Self.shares, id: \.self) { s in
                    chip("\(Int(s))%", on: !custom && pct == s) { custom = false; pct = s }
                }
                chip("Custom", on: custom) { custom = true; customText = "\(Int(pct))" }
            }
            .frame(maxWidth: .infinity)
            if custom {
                FieldRow(label: "Your share", text: $customText, prompt: "12%")
                    .keyboardType(.numberPad)
                    .sheetCard()
                    .onChange(of: customText) { v in
                        if let n = Double(v.replacingOccurrences(of: "%", with: "")), (0...50).contains(n) { pct = n }
                    }
            }
            GlassCard {
                if let pay = pay {
                    row("Each paycheque", sub: cadence(pay.cadence), value: pay.amount * pct / 100, exact: true)
                    RowSeparator()
                }
                row("Each month", sub: nil, value: monthlyIncome * pct / 100, exact: false)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Continue") { Task { await save() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy)
            }
        }
        .task { await load() }
    }

    private func chip(_ label: String, on: Bool, _ tap: @escaping () -> Void) -> some View {
        Button(action: tap) {
            Text(label).font(Nacre.footnote).foregroundColor(on ? .white : Pearl.ink)
                .padding(.horizontal, 14).frame(height: 34)
                .background(Capsule().fill(on ? Pearl.action : Nacre.glass))
                .overlay(Capsule().strokeBorder(on ? Pearl.action : Nacre.glassEdge, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func row(_ title: String, sub: String?, value: Double, exact: Bool) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                if let sub = sub { Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted) }
            }
            Spacer()
            Text((exact ? "" : "≈ ") + Format.whole(value)).font(Nacre.headline).foregroundColor(Pearl.moneyIn)
        }
        .padding(.horizontal, 16).frame(minHeight: 56)
        .accessibilityElement(children: .combine)
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
