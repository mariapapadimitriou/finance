import SwiftUI

// P6b / P6c (TP-P6-Setup, THL-127, THL-45, THL-114, THL-119, THL-120,
// THL-198; the tap audit, 2026-11-26, approved by the product owner):
// set-up asks one question, "Is this your pay?", about the pay Pearl found,
// with the bills it found one level down. Card payments are never offered
// as pay (the server's `never_pay`). When there is no found pay, or a
// deposit needs her (whose pay, what is it), O-10 Your pay and bills is
// shown instead, as before.

/// P6b: one found pay, Yes or No; the bills Pearl found behind one row.
@MainActor
struct SetupPayView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [SetupRoute]
    @State private var data: IncomeBills?
    /// Her ticks on P6c, kept here so Yes / No saves them.
    @State private var ticked: [String: Bool] = [:]
    @State private var seeingBills = false
    @State private var busy = false
    @State private var error: String?
    @State private var loaded = false

    private var pay: IncomeBills.Candidate? { data?.candidates.first }

    /// O-10 is still the page when there is nothing to ask in one line.
    private var oneQuestion: Bool {
        guard let data = data else { return true }
        return pay != nil && (data.asks ?? []).isEmpty
    }

    var body: some View {
        if loaded && !oneQuestion {
            PayAndBillsView(path: $path)
        } else {
            question
        }
    }

    private var question: some View {
        OnbScreen(part: 3, partName: "Your money") {
            OnbTitle(title: "Is this your pay?")
            if let pay = pay {
                VStack(spacing: 4) {
                    CFRing(name: pay.name, size: 56)
                    Text(pay.name).font(Nacre.body).foregroundColor(Pearl.ink).padding(.top, 8)
                    Text("+" + Format.whole(pay.amount))
                        .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle))
                        .foregroundColor(Pearl.moneyIn).monospacedDigit().pearlAmountFit()
                    Text([cadence(pay.cadence), pay.account].compactMap { $0 }.joined(separator: " \u{00B7} "))
                        .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 16).padding(.vertical, 22)
                .apCard()
                .padding(.top, 10)
                .accessibilityElement(children: .combine)
            } else if error == nil {
                APCard { APSkeletonRow() }.padding(.top, 10)
            }
            if let data = data, !data.bills.isEmpty {
                APCard {
                    Button { seeingBills = true } label: {
                        CFRowLabel(symbol: "calendar", title: SetupPayView.found(data.bills.count),
                                   sub: "\(Format.whole(monthly)) a month \u{00B7} \(countedWords)", trailing: .chevron)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("setup-bills")
                }
                .padding(.top, 2)
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Yes, it\u{2019}s my pay", busy: busy, enabled: pay != nil,
                       identifier: "setup-pay-yes") { Task { await answer("yes") } }
            Button("No") { Task { await answer("no") } }
                .buttonStyle(APSecondaryButtonStyle())
                .disabled(busy || pay == nil)
                .accessibilityIdentifier("setup-pay-no")
        }
        .navigationDestination(isPresented: $seeingBills) {
            SetupBillsView(bills: data?.bills ?? [], ticked: $ticked)
        }
        .task { await load() }
    }

    /// "Pearl found 16 bills".
    static func found(_ n: Int) -> String { n == 1 ? "Pearl found 1 bill" : "Pearl found \(n) bills" }

    private func on(_ b: IncomeBills.Bill) -> Bool { ticked[b.key] ?? b.ticked ?? true }

    private var monthly: Double {
        (data?.bills ?? []).filter(on).reduce(0) { $0 + PayBillsWords.monthly($1.amount, cadence: $1.cadence) }
    }

    /// "all counted", "14 counted".
    private var countedWords: String {
        let bills = data?.bills ?? []
        let n = bills.filter(on).count
        return n == bills.count ? "all counted" : "\(n) counted"
    }

    private func load() async {
        do {
            data = try await app.api.get("api/income-bills")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
        loaded = true
    }

    /// Yes: it's her pay. No: Pearl asks about the next one it found, or
    /// carries on with its estimate and asks on Home when a pay lands (P12a).
    /// Either way the bills are saved as she ticked them.
    private func answer(_ word: String) async {
        guard let pay = pay else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": pay.payer, "answer": word])
            if word == "no", reply.candidates.first != nil {
                withAnimation(.easeInOut(duration: 0.25)) { data = reply }
                return
            }
            var answers: [String: Bool] = [:]
            for bill in reply.bills { answers[bill.key] = on(bill) }
            let _: IncomeBills = try await app.api.put("api/income-bills/bills", ["ticked": answers])
            app.changed()
            path.append(.saving)
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// P6c: the bills Pearl found, one level down (O-10's list, unchanged):
/// all counted, she unticks what isn't hers.
struct SetupBillsView: View {
    let bills: [IncomeBills.Bill]
    @Binding var ticked: [String: Bool]
    @Environment(\.dismiss) private var dismiss

    private func on(_ b: IncomeBills.Bill) -> Bool { ticked[b.key] ?? b.ticked ?? true }

    private var monthly: Double {
        bills.filter(on).reduce(0) { $0 + PayBillsWords.monthly($1.amount, cadence: $1.cadence) }
    }

    var body: some View {
        OnbScreen {
            OnbTitle(title: bills.count == 1 ? "1 bill" : "\(bills.count) bills",
                     line: "\(Format.whole(monthly)) a month. Untick any that aren\u{2019}t yours.")
            APCard {
                ForEach(Array(bills.enumerated()), id: \.element.id) { i, bill in
                    if i > 0 { APSeparator() }
                    BillLine(bill: bill, on: on(bill), toggle: { ticked[bill.key] = !on(bill) }, edit: {
                        ticked[bill.key] = !on(bill)
                    })
                }
            }
            .padding(.top, 2)
        } actions: {
            OnbPrimary(title: "Done", identifier: "setup-bills-done") { dismiss() }
        }
    }
}
