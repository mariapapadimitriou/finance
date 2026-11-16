import SwiftUI

// What setup asks about a regular deposit before it can be pay: whose pay
// it is on a joint account (O-10f), and what someone's regular e-Transfers
// are (O-10g). Each answers for the deposit's sender and hands back the
// whole check.

/// O-10f Whose pay is this? — PQ-01 (POLISH-01, 1393:83919 / 1393:84293;
/// THL-305, THL-232): the paydays shown and why Pearl asks, then Me, each
/// person on the account and Both of us as tiles that answer at once (with a
/// toast and Undo), and "This isn't regular pay" as a row. No Save.
@MainActor
struct WhosePaySheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let ask: IncomeBills.Ask
    let saved: (IncomeBills) -> Void

    @State private var deposits: AnswerSheet.Deposits?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Whose pay is this?") { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    QuestionHeader(name: ask.name, amount: "+" + Format.amount(ask.amount), tone: Pearl.moneyIn,
                                   sub: "Joint")
                    QuestionCaption(text: "Why Pearl is asking")
                    WhyCard(sentence: sentence, dates: deposits?.dates ?? [], amount: ask.amount,
                            footer: "It’s a joint account, so Pearl needs to know whose it is.")
                    QuestionCaption(text: "It’s…")
                    AnswerGrid(columns: 3) {
                        AnswerTile(title: "Me", line: "Counts as your pay", symbol: "briefcase") { answer("me") }
                        if people.isEmpty {
                            AnswerTile(title: "Someone else", line: "Not in your numbers",
                                       symbol: "person.crop.circle.badge.xmark") { answer("them") }
                        } else {
                            ForEach(people, id: \.self) { person in
                                AnswerTile(title: person, line: "Not in your numbers",
                                           symbol: "person.crop.circle.badge.xmark") { answer("them", person: person) }
                            }
                        }
                        AnswerTile(title: "Both of us", line: "Your \(share)% counts", symbol: "person.2") { answer("both") }
                    }
                    .disabled(busy)
                    AnswerRow(symbol: "person.crop.circle.badge.xmark", title: "This isn’t regular pay",
                              line: "Ask me about each deposit") { Task { await notPay() } }
                        .disabled(busy)
                    if let error = error { Hint(text: error) }
                    QuestionFooter(text: "Pearl remembers this for every deposit from \(ask.name).")
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
        }
        .background(SheetBackground())
        .fitsContent()
        .task { deposits = try? await app.api.get("api/transactions/\(ask.txn)/paydays") }
    }

    private var people: [String] { ask.people ?? [] }
    private var share: Int { Int((ask.share ?? 50).rounded()) }

    /// "Maple Co has paid $1,980.00 into your joint account every 2 weeks since September."
    private var sentence: String {
        let money = Format.amount(ask.amount)
        let since = deposits?.first.map { " since \(AnswerSheet.sinceMonth($0))" } ?? ""
        let every = AnswerSheet.every(deposits?.cadence) ?? cadence(ask.cadence).lowercased()
        return "\(ask.name) has paid \(money) into your joint account \(every)\(since)."
    }

    /// A tile answers for every deposit from them, then the toast with Undo.
    private func answer(_ who: String, person: String? = nil) {
        busy = true
        Task {
            defer { busy = false }
            do {
                let reply = try await ReviewAnswer.joint(ask.txn, who: who, person: person, remember: true).send(app.api)
                let check: IncomeBills = try await app.api.get("api/income-bills")
                saved(check)
                dismiss()
                app.say(reply.title ?? "Sorted.", undo: reply.undo.map { payload in {
                    guard let body = payload.any as? [String: Any] else { return }
                    let _: OK = try await app.api.post("api/transactions/undo", body)
                } })
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private func notPay() async {
        busy = true
        defer { busy = false }
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": ask.payer, "answer": "no"])
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// O-10g What is it? — their share of a bill (which comes off it), paying
/// her back, or something else. POLISH-01 audit 8: a tap answers, as on
/// PQ-01; their share of a bill answers once she taps the bill. No Save.
@MainActor
struct WhatIsItSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let ask: IncomeBills.Ask
    /// The bills it could be a share of.
    let bills: [IncomeBills.Bill]
    let saved: (IncomeBills) -> Void

    @State private var choice: String?
    @State private var busy = false
    @State private var error: String?

    private var who: String { ask.person ?? "Their" }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "What is it?") { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: ask.name, amount: Format.whole(ask.amount), tone: Pearl.ink,
                                   sub: cadence(ask.cadence).lowercased())
                    GlassCard {
                        choiceRow("\(who)’s share of a bill", detail: nil, on: choice == "share") { choice = "share" }
                        RowSeparator()
                        choiceRow("Paid back", detail: nil, on: choice == "payback") { save("payback") }
                        RowSeparator()
                        choiceRow("Something else", detail: "Pearl will ask about each one in Needs a look.",
                                  on: choice == "else") { save("else") }
                    }
                    .disabled(busy)
                    if choice == "share" {
                        Text("WHICH BILL?").font(Nacre.caption2).tracking(0.6).padding(.leading, 16).padding(.top, 4)
                        if bills.isEmpty {
                            Text("Add the bill first, then come back to this.")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                        } else {
                            GlassCard {
                                ForEach(Array(likelyBills.enumerated()), id: \.element.id) { i, b in
                                    if i > 0 { RowSeparator() }
                                    choiceRow(b.name, detail: "\(cadence(b.cadence)) · \(Format.amount(b.amount)) · counts \(Format.amount(max(b.amount - ask.amount, 0))) for you",
                                              on: false) { save("share", bill: b.key) }
                                }
                            }
                            .disabled(busy)
                        }
                    }
                    if let error = error { Hint(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
        }
        .background(SheetBackground())
        .fitsContent()
    }

/// Rent first, then the bills their e-Transfer could be part of (bigger
    /// than it), biggest first, then the rest.
    private var likelyBills: [IncomeBills.Bill] {
        bills.sorted { a, b in
            func rank(_ x: IncomeBills.Bill) -> Int {
                if x.category == "Rent & Housing" || x.name.lowercased().contains("rent") { return 0 }
                return x.amount > ask.amount ? 1 : 2
            }
            return rank(a) != rank(b) ? rank(a) < rank(b) : a.amount > b.amount
        }
    }

    private func save(_ answer: String, bill: String? = nil) {
        choice = answer
        busy = true
        var body: [String: Any] = ["payer": ask.payer, "answer": answer]
        if let bill = bill { body["bill"] = bill }
        Task {
            defer { busy = false }
            do {
                let reply: IncomeBills = try await app.api.post("api/income-bills/etransfer", body)
                saved(reply)
                dismiss()
            } catch {
                self.error = app.handle(error)
            }
        }
    }
}

/// One answer: its words, a line under them, and a tick when chosen.
private func choiceRow(_ label: String, detail: String?, on: Bool, _ tap: @escaping () -> Void) -> some View {
    Button(action: tap) {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
                if let detail = detail {
                    Text(detail).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
            }
            Spacer(minLength: 8)
            if on {
                Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 4)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(on ? .isSelected : [])
}
