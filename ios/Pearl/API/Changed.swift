import Foundation

/// What a write changed (perf rehaul, 2026-11-19; finance/changed.py).
///
/// Every transaction-shaped POST/PUT/PATCH/DELETE answers with this on top
/// of its usual fields: the ledger's new version and ETag, the rows it
/// touched exactly as api/transactions/list describes them (so a list can
/// swap them in place), the ids of rows that no longer exist, the
/// Allowance as Home shows it, and how many rows Needs a look has. A
/// screen that applies it needn't ask for itself again.
struct Changed: Decodable {
    let version: Int
    let etag: String?
    let rows: [Transaction]
    let removed: [String]
    let allowance: Allowance?
    let reviewCount: Int?

    enum CodingKeys: String, CodingKey {
        case version, etag, rows, removed, allowance
        case reviewCount = "review_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(Int.self, forKey: .version)
        etag = (try? c.decodeIfPresent(String.self, forKey: .etag)) ?? nil
        rows = ((try? c.decodeIfPresent([Lenient<Transaction>].self, forKey: .rows)) ?? nil)?
            .compactMap { $0.value } ?? []
        removed = ((try? c.decodeIfPresent([String].self, forKey: .removed)) ?? nil) ?? []
        allowance = (try? c.decodeIfPresent(Allowance.self, forKey: .allowance)) ?? nil
        reviewCount = (try? c.decodeIfPresent(Int.self, forKey: .reviewCount)) ?? nil
    }

    /// The ledger version in an ETag, `W/"42-2026-11-20"` → 42.
    static func version(inETag tag: String) -> Int? {
        var s = Substring(tag)
        if s.hasPrefix("W/") { s = s.dropFirst(2) }
        s = s.trimmingCharacters(in: CharacterSet(charactersIn: "\""))[...]
        guard let dash = s.firstIndex(of: "-") else { return Int(s) }
        return Int(s[..<dash])
    }
}

/// A write's answer read two ways: its own fields as `Body`, and the
/// `changed` envelope beside them. For call sites whose reply type is a
/// one-off struct; MarkReply, QuickSortStep and CategoryChange carry
/// `changed` themselves.
struct WriteReply<Body: Decodable>: Decodable {
    let body: Body
    let changed: Changed?

    private enum Keys: String, CodingKey { case changed }

    init(from decoder: Decoder) throws {
        body = try Body(from: decoder)
        let c = try? decoder.container(keyedBy: Keys.self)
        changed = (try? c?.decodeIfPresent(Changed.self, forKey: .changed)) ?? nil
    }
}

/// Just the envelope, for the outbox to apply whatever the reply was.
struct ChangedOnly: Decodable {
    let changed: Changed?
}

extension Array where Element == Transaction {
    /// The rows a write touched, swapped in by id; the rows it removed,
    /// gone. Rows the list didn't have aren't added (their place depends on
    /// the list's order and filters; the next ETag check brings them).
    /// Returns whether anything here changed.
    @discardableResult
    mutating func merge(_ changed: Changed) -> Bool {
        var touched = false
        if !changed.removed.isEmpty {
            let gone = Set(changed.removed)
            let before = count
            removeAll { gone.contains($0.id) }
            touched = count != before
        }
        guard !changed.rows.isEmpty else { return touched }
        let fresh = Dictionary(changed.rows.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        for i in indices {
            if let row = fresh[self[i].id], row != self[i] {
                self[i] = row
                touched = true
            }
        }
        return touched
    }
}
