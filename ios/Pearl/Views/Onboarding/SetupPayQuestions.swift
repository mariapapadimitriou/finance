import SwiftUI

// What setup asks about a regular deposit before it can be pay: whose pay
// it is on a joint account (O-10f), and what someone's regular e-Transfers
// are (O-10g). Each answers for the deposit's sender and hands back the
// whole check.

/// O-10f Whose pay is this? — Me, one of the people on the account, or both
/// of them (her share counts); or it isn't regular pay at all.
@MainActor
struct WhosePaySheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let ask: IncomeBills.Ask
    let saved: (IncomeBills) -> Void

    @State private var choice: String?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Whose pay is this?") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: ask.name, amount: "+" + Format.whole(ask.amount), tone: Pearl.moneyIn,
                                   sub: "\(cadence(ask.cadence).lowercased()) · joint account")
                    GlassCard {
                        ForEach(Array(options.enumerated()), id: \.element.id) { i, o in
                            if i > 0 { RowSeparator() }
                            choiceRow(o.label, detail: o.detail, on: choice == o.id) { choice = o.id }
                        }
                    }
                    if let error = error { Hint(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(choice == nil || busy)
                .padding(.horizontal, 16).padding(.top, 6)
            Button("This isn’t regular pay") { Task { await notPay() } }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(busy)
                .padding(.bottom, 4)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    private var options: [(id: String, label: String, detail: String?)] {
        let people = ask.people ?? []
        let share = Int((ask.share ?? 50).rounded())
        return [("me", "Me", nil)]
            + (people.isEmpty ? [("them", "Someone else", nil)] : people.map { ("them:" + $0, $0, nil) })
            + [("both", "Both of us", "Your share · \(share)%")]
    }

    private func save() async {
        guard let choice = choice else { return }
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["remember": true]
        if choice.hasPrefix("them:") {
            body["who"] = "them"
            body["person"] = String(choice.dropFirst(5))
        } else {
            body["who"] = choice
        }
        do {
            let _: OK = try await app.api.put("api/transactions/\(ask.txn)/joint-from", body)
            let reply: IncomeBills = try await app.api.get("api/income-bills")
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
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
/// her back, or something else.
@MainActor
struct WhatIsItSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let ask: IncomeBills.Ask
    /// The bills it could be a share of.
    let bills: [IncomeBills.Bill]
    let saved: (IncomeBills) -> Void

    @State private var choice: String?
    @State private var bill: String?
    @State private var busy = false
    @State private var error: String?

    private var who: String { ask.person ?? "Their" }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "What is it?") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: ask.name, amount: Format.whole(ask.amount), tone: Pearl.ink,
                                   sub: cadence(ask.cadence).lowercased())
                    GlassCard {
                        choiceRow("\(who)’s share of a bill", detail: nil, on: choice == "share") { choice = "share" }
                        RowSeparator()
                        choiceRow("Paying me back", detail: nil, on: choice == "payback") { choice = "payback" }
                        RowSeparator()
                        choiceRow("Something else", detail: nil, on: choice == "else") { choice = "else" }
                    }
                    if choice == "share" {
                        Text("WHICH BILL?").font(Nacre.caption2).tracking(0.6).padding(.leading, 16).padding(.top, 4)
                        if bills.isEmpty {
                            Text("Add the bill first, then come back to this.")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                        } else {
                            GlassCard {
                                ForEach(Array(likelyBills.enumerated()), id: \.element.id) { i, b in
                                    if i > 0 { RowSeparator() }
                                    choiceRow(b.name, detail: "\(cadence(b.cadence)) · \(Format.amount(b.amount))",
                                              on: bill == b.key) { bill = b.key }
                                }
                            }
                            if let b = bills.first(where: { $0.key == bill }) {
                                Text("Your \(b.name) counts \(Format.amount(max(b.amount - ask.amount, 0))) for you.")
                                    .font(Nacre.footnote).padding(.horizontal, 16)
                            }
                        }
                    }
                    if choice == "else" {
                        Text("Pearl will ask about each one in Needs a look.")
                            .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                    }
                    if let error = error { Hint(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(choice == nil || (choice == "share" && bill == nil) || busy)
                .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
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

    private func save() async {
        guard let choice = choice else { return }
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["payer": ask.payer, "answer": choice]
        if let bill = bill, choice == "share" { body["bill"] = bill }
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/etransfer", body)
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
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
