import Foundation

// What the Pearl server sends, as the iPhone app reads it. Field names follow
// the server's JSON (snake_case); anything the app can do without is
// optional, so a new field on the server never breaks the app.

// MARK: - Signing in

struct AuthStatus: Decodable {
    let signedIn: Bool
    let required: Bool?
    let user: PearlUser?
    /// Where "Contact support" writes to (A-10).
    let contact: String?

    enum CodingKeys: String, CodingKey {
        case signedIn = "signed_in", required, user, contact
    }
}

struct PearlUser: Decodable, Equatable {
    let id: Int?
    let username: String?
    let email: String?
    let firstName: String?
    let onboarding: Onboarding?
    /// Passkeys saved for her (from the sign-in status).
    var passkeys: Int? = nil

    struct Onboarding: Decodable, Equatable {
        let done: Bool?
        let step: String?
    }

    enum CodingKeys: String, CodingKey {
        case id, username, email, onboarding, passkeys
        case firstName = "first_name"
    }

    var name: String { firstName ?? "" }
}

/// GET /api/profile: the counts on Profile's rows (P-01).
struct ProfileSummary: Decodable {
    let accounts: Int?
    let needsYou: Int?
    let rules: Int?

    enum CodingKeys: String, CodingKey {
        case accounts, rules
        case needsYou = "needs_you"
    }
}

/// The answer to a sign-in: signed in, or a code sent to her email first
/// (THL-114, on a device that isn't trusted yet).
struct SignInReply: Decodable {
    let signedIn: Bool?
    let user: PearlUser?
    let codeNeeded: Bool?
    let sentTo: String?
    let resendIn: Int?
    let created: Bool?

    enum CodingKeys: String, CodingKey {
        case user, created
        case signedIn = "signed_in"
        case codeNeeded = "code_needed"
        case sentTo = "sent_to"
        case resendIn = "resend_in"
    }
}

struct CodeSent: Decodable {
    let sentTo: String?
    let resendIn: Int?

    enum CodingKeys: String, CodingKey {
        case sentTo = "sent_to", resendIn = "resend_in"
    }
}

/// The three password rules and the strength meter (THL-114).
struct PasswordRules: Decodable, Equatable {
    var length: Bool
    var common: Bool
    var email: Bool
    var more: Int
    var ok: Bool
    var segments: Int
    var label: String
}

// MARK: - Linking a bank (O-06 to O-09)

struct LinkToken: Decodable {
    let linkToken: String

    enum CodingKeys: String, CodingKey { case linkToken = "link_token" }
}

struct LinkedItem: Decodable {
    let itemId: String?
    let institution: String?
    let syncError: String?

    enum CodingKeys: String, CodingKey {
        case institution
        case itemId = "item_id"
        case syncError = "sync_error"
    }
}

struct AccountsOverview: Decodable {
    let linked: [Account]
    /// Accounts added by hand: what a purchase added by hand was paid with.
    var added: [Account]? = nil
    /// Banks to sign in to again, or cut off (THL-120).
    var needsYou: Int? = nil

    enum CodingKeys: String, CodingKey {
        case linked, added
        case needsYou = "needs_you"
    }

    struct Account: Decodable, Identifiable, Hashable {
        let id: String
        let name: String
        let mask: String?
        let institution: String?
        let kind: String?
        let balance: Double?
        let owing: Bool?
        let joint: Bool?
        let jointShare: Double?
        let jointPeople: [String]?
        let historyFrom: String?
        let transactions: Int?
        let itemId: String?
        /// "up_to_date", "sign_in", "disconnected", "retrying"…
        let status: String?
        let updatedAt: String?
        /// "plaid", or "hand" for a balance she added (AM-05).
        var source: String? = nil
        /// Counted toward Allowance and her totals (AM-02, AM-03).
        var counted: Bool? = nil
        var anchor: Bool? = nil
        var canAnchor: Bool? = nil
        var nickname: String? = nil
        var disconnectedOn: String? = nil

        enum CodingKeys: String, CodingKey {
            case id, name, mask, institution, kind, balance, owing, joint, transactions, status
            case source, counted, anchor, nickname
            case updatedAt = "updated_at"
            case canAnchor = "can_anchor"
            case disconnectedOn = "disconnected_on"
            case jointShare = "joint_share"
            case jointPeople = "joint_people"
            case historyFrom = "history_from"
            case itemId = "item_id"
        }

        var isCard: Bool { kind == "card" || kind == "loan" }
        /// Signed out at the bank, or cut off: only signing in again fixes it.
        var needsReconnect: Bool { status == "sign_in" || status == "disconnected" }
        /// "TD Visa ••9021".
        var label: String { (mask ?? "").isEmpty ? name : "\(name) ••\(mask!)" }
        var isHand: Bool { source == "hand" }
    }
}

/// PUT /api/accounts/<id>/settings: the account afterwards, and the
/// Allowance it leaves (AM-03's "Allowance is now $738.58").
struct AccountSaved: Decodable {
    let account: AccountsOverview.Account?
    let safeToSpend: Double?

    enum CodingKeys: String, CodingKey {
        case account
        case safeToSpend = "safe_to_spend"
    }
}

// MARK: - Pay and bills (O-10)

struct IncomeBills: Decodable {
    let pays: [Pay]
    let candidates: [Candidate]
    let bills: [Bill]
    /// O-10f, O-10g: a regular deposit setup asks about before it can be pay.
    let asks: [Ask]?

    struct Ask: Decodable, Identifiable, Hashable {
        /// "joint" (Whose pay?) or "etransfer" (What is it?).
        let kind: String
        let key: String
        let payer: String
        let name: String
        let amount: Double
        let cadence: String
        let txn: String
        let people: [String]?
        let share: Double?
        let person: String?
        var id: String { key }
    }

    struct Pay: Decodable, Identifiable, Hashable {
        let id: String
        let name: String
        let amount: Double
        let cadence: String
        let next: String?
        let payer: String?
    }

    /// A deposit that looks like pay, not yet answered.
    struct Candidate: Decodable, Identifiable, Hashable {
        let payer: String
        let name: String
        let amount: Double
        let cadence: String
        let next: String?
        var id: String { payer }
    }

    struct Bill: Decodable, Identifiable, Hashable {
        let key: String
        let name: String
        let amount: Double
        let varies: Bool?
        let cadence: String
        let next: String?
        let day: Int?
        let category: String?
        let ticked: Bool?
        let source: String?
        /// Someone's share that comes off it (O-10g).
        let shared: Shared?
        var id: String { key }

        struct Shared: Decodable, Hashable {
            let person: String?
            let amount: Double
        }
    }
}

// MARK: - Your Allowance (O-11)

/// GET /api/home, as the end of onboarding reads it.
struct AllowanceHome: Decodable {
    let month: String
    let reviewCount: Int?
    let safeToSpend: Allowance?

    enum CodingKeys: String, CodingKey {
        case month
        case reviewCount = "review_count"
        case safeToSpend = "safe_to_spend"
    }
}

struct Allowance: Decodable {
    let state: String?
    let amount: Double?
    let shown: Double?
    let daysLeft: Int?
    let month: String?
    let nextPay: String?
    let overBy: Double?
    let estimate: Bool?
    /// O-11d: history starts this day, partway through the month, so the
    /// Allowance is for the rest of it.
    let from: String?

    enum CodingKeys: String, CodingKey {
        case state, amount, shown, month, estimate, from
        case daysLeft = "days_left"
        case nextPay = "next_pay"
        case overBy = "over_by"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func opt<T: Decodable>(_ type: T.Type, _ k: CodingKeys) -> T? { (try? c.decodeIfPresent(type, forKey: k)) ?? nil }
        state = opt(String.self, .state)
        amount = opt(Double.self, .amount)
        shown = opt(Double.self, .shown)
        daysLeft = opt(Int.self, .daysLeft)
        month = opt(String.self, .month)
        nextPay = opt(String.self, .nextPay)
        overBy = opt(Double.self, .overBy)
        // The server says which kind of estimate ("rough", "usual",
        // "cautious") or null; any of them is an estimate.
        estimate = opt(Bool.self, .estimate) ?? opt(String.self, .estimate).map { !$0.isEmpty }
        from = opt(String.self, .from)
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
    /// Who owes her for splits, and the rows behind it ("Owed to you").
    let owedIds: [String]
    /// "Sam and Dad · 2 · $106.06": who, for how many purchases, and how much.
    let owedNames: [String]
    let owedCount: Int
    let owedTotal: Double
    /// Every tag she has used, for the filter.
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case transactions, total, owed, tags
        case monthTotals = "month_totals"
    }

    private struct Owed: Decodable {
        let ids: [String]?
        let names: [String]?
        let count: Int?
        let total: Double?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        transactions = try c.decode([Lenient<Transaction>].self, forKey: .transactions).compactMap { $0.value }
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? transactions.count
        monthTotals = try? c.decodeIfPresent(Totals.self, forKey: .monthTotals)
        let owed = (try? c.decodeIfPresent(Owed.self, forKey: .owed)) ?? nil
        owedIds = owed?.ids ?? []
        owedNames = owed?.names ?? []
        owedCount = owed?.count ?? owedIds.count
        owedTotal = owed?.total ?? 0
        tags = ((try? c.decodeIfPresent([String].self, forKey: .tags)) ?? nil) ?? []
    }

    struct Totals: Decodable, Hashable {
        let income: Double?
        let spent: Double?
        let count: Int?
    }
}

/// One transaction as the list (THL-122) and its detail describe it.
struct Transaction: Decodable, Identifiable, Hashable {
    let id: String
    let date: String
    private let merchantName: String?
    let description: String?
    /// Always positive; `inflow` says which way it went. A split's is her share.
    let amount: Double
    let inflow: Bool
    let category: String?
    let account: String?
    let accountId: String?
    let note: String?
    let pending: Bool
    let excluded: String
    let countsToward: String?
    /// "spending", "income" or "none".
    let counts: String
    let chip: Chip?
    /// Pearl's guess at the category, waiting for her yes (a dashed chip).
    let suggested: Bool
    let myNote: String
    let split: Bool
    let fullAmount: Double?
    let refundOf: Linked?
    let refundedBy: [Linked]
    let repays: String?
    let oneOff: Bool
    let canOneOff: Bool
    let tags: [String]
    let kind: String?
    let group: String?
    let categorySource: String?
    let joint: String
    let jointPeople: [String]
    /// Whose money in a joint deposit is: "me", "them", "both", or "" while
    /// it's asked; which of the people; and the account's share (T-33, T-40).
    let jointFrom: String
    let jointPerson: String?
    let jointShare: Double?
    let manual: Bool
    let recurring: String?

    // Only on GET /api/transactions/<id>.
    /// Money in: what kind of income ("salary"), and her regular pay from
    /// this payer, when it is one (THL-198).
    let incomeType: String?
    let regularPay: RegularPay?
    /// A purchase split with people (THL-291): your part and each of theirs.
    let splitting: Splitting?
    /// A deposit split into parts, or a part of one.
    let parts: [DepositPart]
    let partOf: PartOf?
    let leftToSort: Bool
    let oneOffLine: OneOffLine?
    let repaidBy: [Brief]
    let transfer: Transfer?
    let repaysCharge: Brief?

    struct Chip: Decodable, Hashable {
        let label: String?
        let suggested: Bool?
    }

    /// A refund and the purchase it came off, either way round.
    struct Linked: Decodable, Hashable {
        let id: String
        let merchant: String
        let date: String
        let amount: Double
    }

    /// Another transaction, briefly: a payback, or the charge one repays.
    struct Brief: Decodable, Hashable {
        let id: String
        let date: String
        let merchant: String?
        let description: String?
        let amount: Double
        let accountName: String?
        let person: String?
        /// The part of it that paid this back, when that's less than all.
        let paid: Double?

        enum CodingKeys: String, CodingKey {
            case id, date, merchant, description, amount, person, paid
            case accountName = "account_name"
        }

        var name: String { person ?? merchant ?? description ?? "Transaction" }
    }

    struct Splitting: Decodable, Hashable {
        let mode: String?
        let you: Double
        let people: [Person]

        struct Person: Decodable, Hashable, Identifiable {
            let name: String
            let amount: Double
            let paid: Double
            let owes: Double
            let paidOn: String?
            let cash: Double?
            let cashIds: [Int]?
            let letGo: LetGo?
            var id: String { name }

            struct LetGo: Decodable, Hashable { let was: Double; let day: String }

            enum CodingKeys: String, CodingKey {
                case name, amount, paid, owes, cash
                case paidOn = "paid_on"
                case cashIds = "cash_ids"
                case letGo = "let_go"
            }
        }
    }

    struct PartOf: Decodable, Hashable {
        let id: String
        let amount: Double
        let date: String
        let parts: [DepositPart]
    }

    struct RegularPay: Decodable, Hashable {
        let cadence: String?
        let next: String?
    }

    struct OneOffLine: Decodable, Hashable {
        let since: String?
        let line: String
    }

    /// The other end of a transfer between her accounts.
    struct Transfer: Decodable, Hashable {
        let from: String
        let to: String
        let otherId: String?
        let otherDate: String?

        enum CodingKeys: String, CodingKey {
            case from, to
            case otherId = "other_id"
            case otherDate = "other_date"
        }
    }

    enum CodingKeys: String, CodingKey {
        case id, date, description, amount, inflow, category, account, note, pending, excluded, chip
        case counts, suggested, split, repays, tags, kind, group, joint, manual, recurring, transfer
        case merchantName = "merchant"
        case accountId = "account_id"
        case countsToward = "counts_toward"
        case myNote = "my_note"
        case fullAmount = "full_amount"
        case refundOf = "refund_of"
        case refundedBy = "refunded_by"
        case oneOff = "one_off"
        case canOneOff = "can_one_off"
        case categorySource = "category_source"
        case jointPeople = "joint_people"
        case jointFrom = "joint_from"
        case jointPerson = "joint_person"
        case jointShare = "joint_share"
        case jointSplit = "joint_split"
        case oneOffLine = "one_off_line"
        case incomeType = "income_type"
        case regularPay = "regular_pay"
        case splitting, parts
        case partOf = "part_of"
        case leftToSort = "left_to_sort"
        case repaidBy = "repaid_by"
        case repaysCharge = "repays_charge"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // The row's identity must be there; everything else has a default,
        // so one odd field never drops a row from the list.
        func opt<T: Decodable>(_ type: T.Type, _ key: CodingKeys) -> T? {
            (try? c.decodeIfPresent(type, forKey: key)) ?? nil
        }
        id = try c.decode(String.self, forKey: .id)
        date = try c.decode(String.self, forKey: .date)
        amount = try c.decode(Double.self, forKey: .amount)
        merchantName = opt(String.self, .merchantName)
        description = opt(String.self, .description)
        inflow = opt(Bool.self, .inflow) ?? false
        category = opt(String.self, .category)
        account = opt(String.self, .account)
        accountId = opt(String.self, .accountId)
        note = opt(String.self, .note)
        pending = opt(Bool.self, .pending) ?? false
        excluded = opt(String.self, .excluded) ?? ""
        countsToward = opt(String.self, .countsToward)
        counts = opt(String.self, .counts) ?? "spending"
        chip = opt(Chip.self, .chip)
        suggested = opt(Bool.self, .suggested) ?? (chip?.suggested ?? false)
        myNote = opt(String.self, .myNote) ?? ""
        split = opt(Bool.self, .split) ?? false
        fullAmount = opt(Double.self, .fullAmount)
        refundOf = opt(Linked.self, .refundOf)
        refundedBy = opt([Linked].self, .refundedBy) ?? []
        repays = opt(String.self, .repays)
        oneOff = opt(Bool.self, .oneOff) ?? false
        canOneOff = opt(Bool.self, .canOneOff) ?? false
        tags = opt([String].self, .tags) ?? []
        kind = opt(String.self, .kind)
        group = opt(String.self, .group)
        categorySource = opt(String.self, .categorySource)
        joint = opt(String.self, .joint) ?? ""
        jointPeople = opt([String].self, .jointPeople) ?? []
        jointFrom = opt(String.self, .jointFrom) ?? ""
        jointPerson = opt(String.self, .jointPerson).flatMap { $0.isEmpty ? nil : $0 }
        jointShare = opt(Double.self, .jointSplit) ?? opt(Double.self, .jointShare)
        manual = opt(Bool.self, .manual) ?? false
        recurring = opt(String.self, .recurring)
        oneOffLine = opt(OneOffLine.self, .oneOffLine)
        incomeType = opt(String.self, .incomeType)
        regularPay = opt(RegularPay.self, .regularPay)
        splitting = opt(Splitting.self, .splitting)
        parts = opt([DepositPart].self, .parts) ?? []
        partOf = opt(PartOf.self, .partOf)
        leftToSort = opt(Bool.self, .leftToSort) ?? false
        repaidBy = opt([Brief].self, .repaidBy) ?? []
        transfer = opt(Transfer.self, .transfer)
        repaysCharge = opt(Brief.self, .repaysCharge)
    }

    /// The name to show: the merchant, else the bank's description.
    var merchant: String {
        if let name = merchantName, !name.isEmpty { return name }
        if let text = description, !text.isEmpty { return text }
        return "Transaction"
    }

    /// The category the row shows: Pearl's chip, else the stored one.
    var label: String { chip?.label ?? category ?? "Other" }

    /// Needs a look asking a question ("Not sorted yet", "Whose?"), not
    /// Pearl guessing at a category.
    var asks: Bool { suggested && ["Not sorted yet", "Possible duplicate", "Whose?"].contains(label) }

    /// Left out, a transfer, a repayment: shown, but not counted.
    var notCounted: Bool { !excluded.isEmpty || counts == "none" }

    static func == (a: Transaction, b: Transaction) -> Bool { a.id == b.id && a.category == b.category }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// One part of a deposit (THL-291): a payback, a gift, money from her own
/// accounts…, and the purchase it pays back.
struct DepositPart: Decodable, Hashable, Identifiable {
    let id: String
    let kind: String
    let amount: Double
    let person: String?
    let incomeKind: String?
    let category: String?
    let charge: Charge?
    let sorted: Bool?

    struct Charge: Decodable, Hashable {
        let id: String
        let merchant: String
        let date: String
        let amount: Double
        let category: String?
    }

    enum CodingKeys: String, CodingKey {
        case id, kind, amount, person, category, charge, sorted
        case incomeKind = "income_kind"
    }

    /// "Payback · Flight to Athens", "Gift", "Dad overpaid".
    var label: String {
        switch kind {
        case "payback": return "Payback" + (charge.map { " · \($0.merchant)" } ?? "")
        case "refund": return "Refund" + (charge.map { " · \($0.merchant)" } ?? "")
        case "gift": return "Gift"
        case "income": return "Income"
        case "moved": return "From my own accounts"
        case "savings": return "Out of savings"
        case "cash": return "Cash you were paid"
        case "overpaid": return "\(person ?? "They") overpaid"
        case "category": return category ?? "Other"
        default: return "Left to sort"
        }
    }
}

/// GET /api/owed (S-14).
struct OwedOverview: Decodable {
    let total: Double
    let people: Int
    let owesYou: [Row]
    let youOwe: [Row]
    let paidBack: [Back]

    struct Row: Decodable, Hashable, Identifiable {
        let name: String
        let total: Double
        let items: [Item]
        var id: String { name }

        struct Item: Decodable, Hashable {
            let merchant: String?
            let date: String
            let owes: Double?
            let amount: Double?
        }
    }

    struct Back: Decodable, Hashable {
        let name: String?
        let merchant: String?
        let date: String
        let amount: Double
        let cash: Bool?
    }

    enum CodingKeys: String, CodingKey {
        case total, people
        case owesYou = "owes_you"
        case youOwe = "you_owe"
        case paidBack = "paid_back"
    }
}

/// What turning one-off on or off answers (U-02's toast).
struct OneOffReply: Decodable {
    let oneOff: Bool
    let title: String?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case title, detail
        case oneOff = "one_off"
    }
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
    let accountId: String?
    let category: String?
    /// Set on an unsorted transfer she skipped.
    let skipped: Bool?
    /// A payback candidate Pearl thinks most likely.
    let likely: Bool?

    enum CodingKeys: String, CodingKey {
        case id, date, merchant, description, amount, category, skipped, likely
        case accountName = "account_name"
        case accountId = "account_id"
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
        /// A joint account's name and the people on it ("Who put this in?").
        let label: String?
        let people: [String]?
        /// Purchases money in could pay back, likeliest first.
        let candidates: [BriefTransaction]?
        /// A recurring transfer's pattern ("every month, around the 10th").
        let series: Series?
        /// A joint account's share, for "Both of us · Your share 50%" (T-33).
        let share: Double?
        /// The part of a deposit left to sort (THL-291): the whole deposit
        /// and how much of it is sorted.
        let rest: Rest?

        var id: String { key }

        struct Rest: Decodable, Hashable {
            let whole: Double
            let sorted: Double
        }

        enum CodingKeys: String, CodingKey {
            case key, txn, reason, skipped, from, guess, label, people, candidates, series, rest, share
            case guessLabel = "guess_label"
        }

        init(key: String, txn: BriefTransaction, skipped: Bool?, label: String? = nil,
             people: [String]? = nil, share: Double? = nil) {
            self.key = key
            self.txn = txn
            self.skipped = skipped
            self.label = label
            self.people = people
            self.share = share
            reason = nil; from = nil; guessLabel = nil; guess = nil
            candidates = nil; series = nil; rest = nil
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            func opt<T: Decodable>(_ type: T.Type, _ k: CodingKeys) -> T? { (try? c.decodeIfPresent(type, forKey: k)) ?? nil }
            key = try c.decode(String.self, forKey: .key)
            txn = try c.decode(BriefTransaction.self, forKey: .txn)
            reason = opt(String.self, .reason)
            skipped = opt(Bool.self, .skipped)
            from = opt(String.self, .from)
            guessLabel = opt(String.self, .guessLabel)
            guess = opt(Guess.self, .guess)
            label = opt(String.self, .label)
            people = opt([String].self, .people)
            candidates = (opt([Lenient<BriefTransaction>].self, .candidates))?.compactMap { $0.value }
            series = opt(Series.self, .series)
            rest = opt(Rest.self, .rest)
            share = opt(Double.self, .share)
        }

        static func == (a: Item, b: Item) -> Bool { a.key == b.key }
        func hash(into hasher: inout Hasher) { hasher.combine(key) }
    }

    struct Series: Decodable, Hashable {
        let when: String?
        let count: Int?
        let to: String?
    }

    /// Pearl's guess: a category name for "unsure", an income kind, or an
    /// object ({"action": "payback", "charge": …}) for money in.
    enum Guess: Decodable, Hashable {
        case text(String)
        case action(String, charge: BriefTransaction?)

        init(from decoder: Decoder) throws {
            let single = try decoder.singleValueContainer()
            if let s = try? single.decode(String.self) {
                self = .text(s)
                return
            }
            struct Action: Decodable { let action: String?; let charge: BriefTransaction? }
            let a = try single.decode(Action.self)
            self = .action(a.action ?? "", charge: a.charge)
        }

        var text: String? { if case .text(let s) = self { return s } else { return nil } }
        var action: String? { if case .action(let a, _) = self { return a } else { return nil } }
        var charge: BriefTransaction? { if case .action(_, let c) = self { return c } else { return nil } }
    }
}

/// What Needs a look asks about (T-10), each row's dashed chip naming it.
enum Question: Hashable {
    case category, transfer, moneyIn, incomeType, joint, whoSent, duplicate, recurring
}

struct Ask: Identifiable, Hashable {
    let kind: Question
    let item: Review.Item
    var id: String { item.key }
    var t: BriefTransaction { item.txn }
    var skipped: Bool { item.skipped == true }

    /// "Dining?", "Saved or spent?", "Whose?"…
    var chip: String {
        switch kind {
        case .category: return "\(item.guess?.text ?? t.category ?? "Other")?"
        case .transfer: return "Saved or spent?"
        case .moneyIn: return item.rest != nil ? "\(Format.amount(t.amount)) left to sort" : "What was this?"
        case .incomeType: return "What kind of income?"
        case .joint: return "Whose?"
        case .whoSent: return "Who sent this?"
        case .duplicate: return "Same purchase?"
        case .recurring: return "Recurring?"
        }
    }
}

extension Review {
    /// Every question, oldest kinds first, skipped ones included (they say so).
    var asks: [Ask] {
        var out = unsureCategory.map { Ask(kind: .category, item: $0) }
        out += (unsorted?.transfers ?? []).map { t in
            Ask(kind: .transfer, item: Item(key: "u:" + t.id, txn: t, skipped: t.skipped))
        }
        out += moneyIn.map { Ask(kind: .moneyIn, item: $0) }
        out += incomeType.map { Ask(kind: .incomeType, item: $0) }
        out += jointIn.map { Ask(kind: .joint, item: $0) }
        out += whoSent.map { Ask(kind: .whoSent, item: $0) }
        out += duplicate.map { Ask(kind: .duplicate, item: $0) }
        out += recurringTransfer.map { Ask(kind: .recurring, item: $0) }
        return out
    }

    /// Open questions the app has no row for (months with a third
    /// paycheque): answered on the web.
    var webOnly: Int {
        max(0, (open ?? count) - asks.filter { !$0.skipped }.count)
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

// MARK: - Notifications (N-01, N-02)

/// GET and PUT /api/notifications.
struct NotificationSettings: Decodable {
    var prefs: Prefs

    struct Prefs: Decodable {
        var types: [String: Channels]
        var quiet: Quiet
        var lockAmounts: Bool
        let prompt: Prompt?

        enum CodingKeys: String, CodingKey {
            case types, quiet, prompt
            case lockAmounts = "lock_amounts"
        }
    }

    struct Channels: Decodable {
        var phone: Bool
        var email: Bool
    }

    /// "21:00" to "08:00".
    struct Quiet: Decodable, Identifiable {
        var from: String
        var to: String
        var id: String { "\(from)-\(to)" }
    }

    /// N-01's answer: "on", "not_now", or none yet.
    struct Prompt: Decodable {
        let answer: String?
    }
}

// MARK: - How we protect you (P-03)

/// GET /api/privacy: the banks Pearl reads, and who to write to.
struct Privacy: Decodable {
    let connections: [Connection]
    let contact: String?
    /// CN-04: "read_data", "insights", "ai_sort", "tips", "analytics"…
    var consents: [String: Consent]?

    struct Consent: Decodable {
        let value: Bool?
        /// When it was given, in seconds. Usage data, on by default, has none.
        let at: Double?

        init(value: Bool?, at: Double?) {
            self.value = value
            self.at = at
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            value = (try? c.decodeIfPresent(Bool.self, forKey: .value)) ?? nil
            at = (try? c.decodeIfPresent(Double.self, forKey: .at)) ?? nil
        }

        private enum CodingKeys: String, CodingKey { case value, at }
    }

    struct Connection: Decodable, Identifiable {
        let itemId: String
        let institution: String
        let accounts: Int?
        let lastSynced: String?
        let state: String?
        var id: String { itemId }

        enum CodingKeys: String, CodingKey {
            case institution, accounts, state
            case itemId = "item_id"
            case lastSynced = "last_synced"
        }
    }
}
