import Foundation

/// TEST-36 (S-03e, G2-Amounts): switching how to split starts the new method
/// from the split as it stands, so $60.00 each with Sam stays $60.00 and
/// $60.00 on Amounts ("60.00"), 50% and 50% on %, 1 and 1 on Shares.
/// tests/test_split_carry.py checks it with swiftc.
enum SplitCarry {
    /// The new method's typed values, from each row's share in cents (in row
    /// order). `me` is her row when she's in it: on Amounts it stays empty so
    /// it gives way (S-03rg), on % it takes what's left of 100.
    static func values(_ rows: [(key: String, cents: Int)], to mode: String, me: String?) -> [String: String] {
        let total = rows.map(\.cents).reduce(0, +)
        guard total > 0, rows.allSatisfy({ $0.cents >= 0 }) else { return [:] }
        var out: [String: String] = [:]
        switch mode {
        case "amount":
            // Cents always, as every amount well shows them (TEST-48): "60.00".
            for r in rows where r.key != me { out[r.key] = String(format: "%.2f", Double(r.cents) / 100) }
        case "percent":
            let pct = { (c: Int) in (Double(c) * 10000 / Double(total)).rounded() / 100 }
            for r in rows where r.key != me { out[r.key] = plain(pct(r.cents)) }
            if let me = me, rows.contains(where: { $0.key == me }) {
                let others = rows.filter { $0.key != me }.map { pct($0.cents) }.reduce(0, +)
                out[me] = plain(max(0, (100 - others) * 100).rounded() / 100)
            }
        case "shares":
            for (k, n) in shares(rows) { out[k] = plain(n) }
        default:
            return [:]
        }
        return out
    }

    /// Whole shares when the split has a small ratio (2 and 1); otherwise
    /// each row against the smallest, to two places ($100.01 is 1 and 1).
    private static func shares(_ rows: [(key: String, cents: Int)]) -> [(String, Double)] {
        let some = rows.map(\.cents).filter { $0 > 0 }
        guard let least = some.min() else { return [] }
        let g = some.reduce(0) { gcd($0, $1) }
        if let most = some.max(), most / g <= 20 {
            return rows.map { ($0.key, Double($0.cents / g)) }
        }
        return rows.map { ($0.key, (Double($0.cents) / Double(least) * 100).rounded() / 100) }
    }

    private static func gcd(_ a: Int, _ b: Int) -> Int { b == 0 ? a : gcd(b, a % b) }

    /// 60 → "60", 33.33 → "33.33" (the same as SplitSheet.plain).
    static func plain(_ x: Double) -> String {
        x.rounded() == x ? String(Int(x)) : String(format: "%.2f", x)
    }
}
