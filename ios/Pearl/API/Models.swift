import Foundation

// What the Pearl server sends, as the iPhone app reads it. Field names follow
// the server's JSON (snake_case); anything the app can do without is
// optional, so a new field on the server never breaks the app.

// MARK: - Signing in

struct AuthStatus: Decodable {
    let signedIn: Bool
    let required: Bool?
    let user: PearlUser?

    enum CodingKeys: String, CodingKey {
        case signedIn = "signed_in", required, user
    }
}

struct PearlUser: Decodable, Equatable {
    let id: Int?
    let username: String?
    let email: String?
    let firstName: String?
    let onboarding: Onboarding?

    struct Onboarding: Decodable, Equatable {
        let done: Bool?
    }

    enum CodingKeys: String, CodingKey {
        case id, username, email, onboarding
        case firstName = "first_name"
    }

    var name: String { firstName ?? username ?? "" }
}

/// The answer to a sign-in: signed in, or waiting to confirm this device.
struct SignInReply: Decodable {
    let signedIn: Bool?
    let user: PearlUser?
    let confirmDevice: Bool?
    let choices: DeviceChoices?

    enum CodingKeys: String, CodingKey {
        case user, choices
        case signedIn = "signed_in"
        case confirmDevice = "confirm_device"
    }
}

struct DeviceChoices: Decodable {
    let approve: Approver?
    let recovery: Bool?

    struct Approver: Decodable {
        let label: String?
    }
}

struct CodeSent: Decodable {
    let sentTo: String?
    let resendIn: Int?

    enum CodingKeys: String, CodingKey {
        case sentTo = "sent_to", resendIn = "resend_in"
    }
}

/// Polling "Approve on another device".
struct DeviceStatus: Decodable {
    let signedIn: Bool?
    let state: String?
    let user: PearlUser?

    enum CodingKeys: String, CodingKey {
        case signedIn = "signed_in", state, user
    }
}

// MARK: - Home

struct Home: Decodable {
    let today: String?
    let month: String
    let reviewCount: Int
    let snapshot: Snapshot?
    let safeToSpend: SafeToSpend?
    let connections: [Connection]?

    enum CodingKeys: String, CodingKey {
        case today, month, snapshot, connections
        case reviewCount = "review_count"
        case safeToSpend = "safe_to_spend"
    }

    struct Snapshot: Decodable {
        let rows: [Row]
        let daysInMonth: Int?
        let day: Int?

        enum CodingKeys: String, CodingKey {
            case rows, day
            case daysInMonth = "days_in_month"
        }

        struct Row: Decodable, Identifiable {
            let key: String
            let label: String?
            let lens: String?
            let spent: Double?
            let usual: Double?
            let usualByToday: Double?
            let received: Double?
            let expected: Double?
            let saved: Double?
            let nextPay: String?

            var id: String { key }

            enum CodingKeys: String, CodingKey {
                case key, label, lens, spent, usual, received, expected, saved
                case usualByToday = "usual_by_today"
                case nextPay = "next_pay"
            }
        }
    }

    struct SafeToSpend: Decodable {
        let state: String?
        let amount: Double?
        let perDay: Double?
        let daysLeft: Int?
        let nextPay: String?
        let overBy: Double?

        enum CodingKeys: String, CodingKey {
            case state, amount
            case perDay = "per_day"
            case daysLeft = "days_left"
            case nextPay = "next_pay"
            case overBy = "over_by"
        }
    }

    struct Connection: Decodable {
        let institution: String?
        let state: String?
    }
}

/// "Set Pearl up again", after Start over.
struct SetupAgain: Decodable {
    let active: Bool
    let left: Int
    let steps: [Step]

    struct Step: Decodable, Identifiable {
        let key: String
        let title: String
        let sub: String
        let done: Bool
        var id: String { key }
    }
}

// MARK: - Transactions

struct TransactionList: Decodable {
    let transactions: [Transaction]
    let total: Int
    let monthTotals: Totals?

    enum CodingKeys: String, CodingKey {
        case transactions, total
        case monthTotals = "month_totals"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        transactions = try c.decode([Lenient<Transaction>].self, forKey: .transactions).compactMap { $0.value }
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? transactions.count
        monthTotals = try? c.decodeIfPresent(Totals.self, forKey: .monthTotals)
    }

    struct Totals: Decodable {
        let income: Double?
        let spent: Double?
        let count: Int?
    }
}

struct Transaction: Decodable, Identifiable, Hashable {
    let id: String
    let date: String
    private let merchantName: String?
    let description: String?
    /// Always positive; `inflow` says which way it went.
    let amount: Double
    let inflow: Bool
    let category: String?
    let account: String?
    let note: String?
    let pending: Bool?
    let excluded: String?
    let countsToward: String?
    let chip: Chip?
    let myNote: String?

    struct Chip: Decodable, Hashable {
        let label: String?
        let suggested: Bool?
    }

    enum CodingKeys: String, CodingKey {
        case id, date, description, amount, inflow, category, account, note, pending, excluded, chip
        case merchantName = "merchant"
        case countsToward = "counts_toward"
        case myNote = "my_note"
    }

    /// The name to show: the merchant, else the bank's description.
    var merchant: String {
        if let name = merchantName, !name.isEmpty { return name }
        if let text = description, !text.isEmpty { return text }
        return "Transaction"
    }

    static func == (a: Transaction, b: Transaction) -> Bool { a.id == b.id && a.category == b.category }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct Summary: Decodable {
    let months: [String]?
    let latestMonth: String?

    enum CodingKeys: String, CodingKey {
        case months
        case latestMonth = "latest_month"
    }
}

struct CategoryList: Decodable {
    let categories: [Category]

    struct Category: Decodable, Identifiable, Hashable {
        let name: String
        let group: String?
        let hidden: Bool?
        var id: String { name }
    }
}

struct CategoryChange: Decodable {
    let category: String?
}

// MARK: - Needs a look

/// One transaction as Needs a look describes it. Unlike the list, the amount
/// is signed: money in is negative.
struct BriefTransaction: Decodable, Hashable {
    let id: String
    let date: String
    let merchant: String?
    let description: String?
    let amount: Double
    let accountName: String?
    let category: String?
    /// Set on an unsorted transfer she skipped.
    let skipped: Bool?

    enum CodingKeys: String, CodingKey {
        case id, date, merchant, description, amount, category, skipped
        case accountName = "account_name"
    }

    var inflow: Bool { amount < 0 }
    var name: String { (merchant?.isEmpty == false ? merchant : description) ?? "Transaction" }
}

struct Review: Decodable {
    let count: Int
    let open: Int?
    let unsureCategory: [Item]
    let moneyIn: [Item]
    let incomeType: [Item]
    let jointIn: [Item]
    let whoSent: [Item]
    let duplicate: [Item]
    let recurringTransfer: [Item]
    let unsorted: Unsorted?
    let kinds: [String: String]?

    enum CodingKeys: String, CodingKey {
        case count, open, unsorted, kinds, duplicate
        case unsureCategory = "unsure_category"
        case moneyIn = "money_in"
        case incomeType = "income_type"
        case jointIn = "joint_in"
        case whoSent = "who_sent"
        case recurringTransfer = "recurring_transfer"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        count = try c.decodeIfPresent(Int.self, forKey: .count) ?? 0
        open = try c.decodeIfPresent(Int.self, forKey: .open)
        unsorted = try? c.decodeIfPresent(Unsorted.self, forKey: .unsorted)
        kinds = try? c.decodeIfPresent([String: String].self, forKey: .kinds)
        func items(_ key: CodingKeys) -> [Item] {
            (try? c.decodeIfPresent([Lenient<Item>].self, forKey: key))?.compactMap { $0.value } ?? []
        }
        unsureCategory = items(.unsureCategory)
        moneyIn = items(.moneyIn)
        incomeType = items(.incomeType)
        jointIn = items(.jointIn)
        whoSent = items(.whoSent)
        duplicate = items(.duplicate)
        recurringTransfer = items(.recurringTransfer)
    }

    struct Unsorted: Decodable {
        let transfers: [BriefTransaction]?
    }

    struct Item: Decodable, Identifiable, Hashable {
        let key: String
        let txn: BriefTransaction
        let reason: String?
        let skipped: Bool?
        let from: String?
        let guessLabel: String?
        let guess: Guess?

        var id: String { key }

        enum CodingKeys: String, CodingKey {
            case key, txn, reason, skipped, from, guess
            case guessLabel = "guess_label"
        }

        static func == (a: Item, b: Item) -> Bool { a.key == b.key }
        func hash(into hasher: inout Hasher) { hasher.combine(key) }
    }

    /// Pearl's guess: a category name for "unsure", an income kind, or an
    /// object ({"action": "own"}) for money in.
    enum Guess: Decodable {
        case text(String)
        case action(String)

        init(from decoder: Decoder) throws {
            let single = try decoder.singleValueContainer()
            if let s = try? single.decode(String.self) {
                self = .text(s)
                return
            }
            struct Action: Decodable { let action: String? }
            let a = try single.decode(Action.self)
            self = .action(a.action ?? "")
        }

        var text: String? { if case .text(let s) = self { return s } else { return nil } }
    }
}

/// What Needs a look asks about, in the order it asks.
enum ReviewKind: String {
    case category, moneyIn, incomeType, transfer, other
}

struct ReviewEntry: Identifiable, Hashable {
    let kind: ReviewKind
    let item: Review.Item
    var id: String { item.key }
    var question: String {
        switch kind {
        case .category: return "What was this?"
        case .moneyIn: return "Is this income?"
        case .incomeType: return item.guessLabel == "Bonus / irregular" ? "Is this a bonus?" : "What kind of income?"
        case .transfer: return "Where did it go?"
        case .other: return "Needs a look"
        }
    }
}

extension Review {
    /// Every open question the app can show, the kinds it answers first.
    var entries: [ReviewEntry] {
        let open: (Item) -> Bool = { $0.skipped != true }
        var out: [ReviewEntry] = unsureCategory.filter(open).map { ReviewEntry(kind: .category, item: $0) }
        out += moneyIn.filter(open).map { ReviewEntry(kind: .moneyIn, item: $0) }
        out += incomeType.filter(open).map { ReviewEntry(kind: .incomeType, item: $0) }
        let transfers: [BriefTransaction] = (unsorted?.transfers ?? []).filter { $0.skipped != true }
        out += transfers.map { t in
            ReviewEntry(kind: .transfer, item: Item(key: "u:" + t.id, txn: t, reason: nil, skipped: nil,
                                                    from: nil, guessLabel: nil, guess: nil))
        }
        let others: [Item] = jointIn + whoSent + duplicate + recurringTransfer
        out += others.filter(open).map { ReviewEntry(kind: .other, item: $0) }
        return out
    }

    /// Open questions the app has no card for at all (months with a third
    /// paycheque): answered on the web.
    var webOnly: Int {
        max(0, (open ?? count) - entries.count)
    }
}

/// The answer to sorting one transaction: what changed, and how to undo it.
struct MarkReply: Decodable {
    let title: String?
    let detail: String?
    let undo: JSONValue?
}

// MARK: - Helpers

/// Decodes what it can and drops an element it can't, so one odd item never
/// empties a whole list.
struct Lenient<T: Decodable>: Decodable {
    let value: T?
    init(from decoder: Decoder) throws {
        value = try? T(from: decoder)
    }
}

/// Any JSON, kept as it came, to send back unchanged (an Undo payload).
indirect enum JSONValue: Codable, Hashable {
    case string(String), number(Double), bool(Bool), null
    case array([JSONValue]), object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .null: try c.encodeNil()
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    /// As Foundation objects, for a JSON request body.
    var any: Any {
        switch self {
        case .string(let s): return s
        case .number(let n): return n
        case .bool(let b): return b
        case .null: return NSNull()
        case .array(let a): return a.map { $0.any }
        case .object(let o): return o.mapValues { $0.any }
        }
    }
}
