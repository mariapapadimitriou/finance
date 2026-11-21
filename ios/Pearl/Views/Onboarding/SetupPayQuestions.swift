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
        // G6-PayBills O-10f: who, then each answer as a radio row that
        // answers at once, and one short note. No Save.
        VStack(spacing: 0) {
            APSheetTitle(title: "Whose pay is this?") { dismiss() }
                .padding(.horizontal, 16).padding(.top, 14)
                .sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    APWho(face: ask.name, name: ask.name,
                          line: "+" + Format.amount(ask.amount) + " " + every + " \u{00B7} joint", lineTone: Pearl.moneyIn)
                        .padding(.top, 8)
                    ProfileSection("It\u{2019}s\u{2026}")
                    APCard {
                        APChoiceRow(title: "Me", sub: "Counts as your pay", selected: false) { answer("me") }
                        if people.isEmpty {
                            APSeparator(afterFace: false)
                            APChoiceRow(title: "Someone else", sub: "Not in your numbers", selected: false) { answer("them") }
                        } else {
                            ForEach(people, id: \.self) { person in
                                APSeparator(afterFace: false)
                                APChoiceRow(title: person, sub: "Not in your numbers", selected: false) {
                                    answer("them", person: person)
                                }
                            }
                        }
                        APSeparator(afterFace: false)
                        APChoiceRow(title: people.count > 1 ? "Everyone" : "Both of us", sub: "Your \(share)% counts",
                                    selected: false) { answer("both") }
                        APSeparator(afterFace: false)
                        APChoiceRow(title: "This isn\u{2019}t regular pay", sub: "Ask me about each deposit",
                                    selected: false) { Task { await notPay() } }
                    }
                    .disabled(busy)
                    if let error = error { APErrorLine(text: error) }
                    ProfileNote("Pearl remembers this for \(ask.name).")
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
                .sheetPart()
            }
        }
        .background(SheetBackground())
        .fitsContent()
        .task { deposits = try? await app.api.get("api/transactions/\(ask.txn)/paydays") }
    }

    /// "every 2 weeks".
    private var every: String {
        AnswerSheet.every(deposits?.cadence) ?? cadence(ask.cadence).lowercased()
    }

    private var people: [String] { ask.people ?? [] }
    private var share: Int { Int((ask.share ?? 50).rounded()) }

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
            APSheetTitle(title: "What is it?") { dismiss() }
                .padding(.horizontal, 16).padding(.top, 14)
                .sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    // G6-PayEdit O-10g: money in is green with "+"; the answers are radio rows.
                    QuestionHeader(name: ask.name, amount: "+" + Format.whole(ask.amount), tone: Pearl.moneyIn,
                                   sub: cadence(ask.cadence).lowercased())
                    APCard {
                        APChoiceRow(title: "\(who)’s share of a bill", selected: choice == "share") { choice = "share" }
                        APSeparator(afterFace: false)
                        APChoiceRow(title: "Paid back", selected: choice == "payback") { save("payback") }
                        APSeparator(afterFace: false)
                        APChoiceRow(title: "Something else", sub: "Pearl asks about each one in Needs a look",
                                    selected: choice == "else") { save("else") }
                    }
                    .disabled(busy)
                    if choice == "share" {
                        ProfileSection("Which bill?")
                        if bills.isEmpty {
                            Text("Add the bill first, then come back to this.")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                        } else {
                            APCard {
                                ForEach(Array(likelyBills.enumerated()), id: \.element.id) { i, b in
                                    if i > 0 { APSeparator(afterFace: false) }
                                    APChoiceRow(title: b.name,
                                                sub: "\(Format.amount(b.amount)) \u{00B7} \(Format.amount(max(b.amount - ask.amount, 0))) counts for you",
                                                selected: false) { save("share", bill: b.key) }
                                }
                            }
                            .disabled(busy)
                        }
                    }
                    if let error = error { APErrorLine(text: error) }
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

