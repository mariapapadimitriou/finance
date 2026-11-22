import SwiftUI

/// Link transfers (product owner, 2026-11-22): $200 moved from one account
/// to a second and on into a joint one; Pearl paired two legs and left one
/// on its own, with no way to say they were one movement of money. The
/// sheet lists what could be another leg, the same amount within a week on
/// any account, to tick one or several; Link saves them as one link
/// (PUT …/links) with one Undo. On a linked row the same sheet shows its
/// legs ticked, and Unlink.
@MainActor
struct LinkTransfersSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let t: Transaction
    let api: APIClient
    let onDone: (MarkReply) -> Void

    struct Leg: Decodable, Identifiable, Hashable {
        let id: String
        let date: String
        let merchant: String?
        let amount: Double
        let accountName: String?
        let linked: Bool?
        let elsewhere: Bool?

        enum CodingKeys: String, CodingKey {
            case id, date, merchant, amount, linked, elsewhere
            case accountName = "account_name"
        }
    }

    private struct Reply: Decodable {
        let rows: [Leg]
        let days: Int?
    }

    @State private var legs: [Leg]?
    @State private var picked: Set<String> = []
    @State private var busy = false
    @State private var error: String?

    /// The legs already in its link.
    private var already: Set<String> { Set((legs ?? []).filter { $0.linked == true }.map(\.id)) }
    private var linkedNow: Bool { !already.isEmpty || !t.links.isEmpty }

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitleBar(title: linkedNow ? "Linked transfers" : "Link transfers") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    APQuestionWho(name: t.merchant, amount: Format.amount(t.amount), tone: Pearl.moved,
                                  sub: [t.account, Format.short(t.date)].compactMap { $0 }.joined(separator: " \u{00B7} "))
                    Text("Tick the other legs of this move. Linked, they count as one transfer: not spending, not income.")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                    if let legs = legs {
                        if legs.isEmpty {
                            APCard {
                                Text("Nothing else for \(Format.amount(t.amount)) within a week.")
                                    .font(Nacre.body).foregroundColor(Pearl.muted)
                                    .padding(.horizontal, 16).frame(minHeight: 64)
                            }
                        } else {
                            APSheetLabel(text: "Same amount, within a week")
                            APCard {
                                ForEach(Array(legs.enumerated()), id: \.element.id) { i, leg in
                                    if i > 0 { APSeparator(afterFace: false) }
                                    row(leg)
                                }
                            }
                        }
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
                    }
                    if let error = error { APErrorLine(text: error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            VStack(spacing: 8) {
                Button(linkedNow ? "Save" : "Link") { Task { await save(picked) } }
                    .buttonStyle(APPrimaryButtonStyle())
                    .disabled(busy || picked.isEmpty || picked == already)
                if linkedNow {
                    Button("Unlink") { Task { await save([]) } }
                        .buttonStyle(APSecondaryButtonStyle())
                        .disabled(busy)
                }
            }
            .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
        }
        .background(APSheetSurface())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await load() }
    }

    private func row(_ leg: Leg) -> some View {
        let on = picked.contains(leg.id)
        return Button {
            if on { picked.remove(leg.id) } else { picked.insert(leg.id) }
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(leg.merchant ?? "Transfer").font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text([leg.accountName, Format.short(leg.date), leg.elsewhere == true ? "in another link" : nil]
                            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " \u{00B7} "))
                        .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                }
                Spacer(minLength: 8)
                Text((leg.amount < 0 ? "+" : "") + Format.amount(abs(leg.amount)))
                    .font(Nacre.body).foregroundColor(leg.amount < 0 ? Pearl.moneyIn : Pearl.ink)
                APTickBox(on: on)
            }
            .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func load() async {
        do {
            let reply: Reply = try await api.get("api/transactions/\(t.id)/link-candidates")
            legs = reply.rows
            picked = Set(reply.rows.filter { $0.linked == true }.map(\.id))
        } catch {
            legs = []
            self.error = app.handle(error)
        }
    }

    /// PUT …/links with the legs ticked (none unlinks); the page shows the
    /// toast, with the server's Undo.
    private func save(_ ids: Set<String>) async {
        busy = true
        defer { busy = false }
        do {
            let reply: MarkReply = try await api.put("api/transactions/\(t.id)/links", ["ids": Array(ids)])
            onDone(reply)
        } catch {
            self.error = app.handle(error)
        }
    }
}
