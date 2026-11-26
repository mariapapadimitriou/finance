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
    /// Recovery codes she has left (SEC-08).
    var recoveryCodes: Int? = nil

    struct Onboarding: Decodable, Equatable {
        let done: Bool?
        let step: String?
    }

    enum CodingKeys: String, CodingKey {
        case id, username, email, onboarding, passkeys
        case recoveryCodes = "recovery_codes"
        case firstName = "first_name"
    }

    var name: String { firstName ?? "" }
}

/// GET /api/profile: the counts on Profile's rows (P-01).
struct ProfileSummary: Decodable {
    let accounts: Int?
    let needsYou: Int?
    let rules: Int?
    /// Recurring transfers she confirmed (THL-295).
    var recurring: Int? = nil

    enum CodingKeys: String, CodingKey {
        case accounts, rules, recurring
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
    /// A-11: the sign-in waits until this iPhone is confirmed.
    var confirmDevice: Bool? = nil
    var choices: DeviceChoices? = nil

    enum CodingKeys: String, CodingKey {
        case user, created, choices
        case confirmDevice = "confirm_device"
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
        /// Your accounts v2 (1415:87857): the server's short name
        /// (finance/account_names.py), the bank on its own, and the name
        /// without the bank, for the grouped row's list.
        var shortName: String? = nil
        var shortBank: String? = nil
        var shortProduct: String? = nil

        enum CodingKeys: String, CodingKey {
            case id, name, mask, institution, kind, balance, owing, joint, transactions, status
            case source, counted, anchor, nickname
            case shortName = "short_name"
            case shortBank = "short_bank"
            case shortProduct = "short_product"
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
    /// When she confirmed her income and her bills; nil until she has
    /// (IB-02: what Pearl found is only its suggestion until then).
    var checked: Checked? = nil
    /// Her own amount a month, and Pearl's estimate (IB-03).
    var expected: Expected? = nil
    var totals: Totals? = nil
    /// "Are your e-Transfers to M. Papas your rent?"
    var rentQuestion: RentQuestion? = nil
    /// What a bill's removal took away, for Undo.
    var removed: Removed? = nil
    /// YP-09's Your plan card.
    var yourPlan: PlanCard? = nil

    enum CodingKeys: String, CodingKey {
        case pays, candidates, bills, asks, checked, expected, totals, removed
        case rentQuestion = "rent_question"
        case yourPlan = "your_plan"
    }

    /// YP-09: none yet (no rows), not in use, or in use with its total a month.
    struct PlanCard: Decodable, Hashable {
        let rows: Int
        let inUse: Bool
        let total: Double

        enum CodingKeys: String, CodingKey {
            case rows, total
            case inUse = "in_use"
        }
    }

    struct Checked: Decodable, Hashable {
        let income: String?
        let bills: String?
    }

    struct Expected: Decodable, Hashable {
        let amount: Double?
        let varies: Bool?
        let estimate: Double?
    }

    struct Totals: Decodable, Hashable {
        let income: Double?
        let bills: Double?
    }

    struct RentQuestion: Decodable, Hashable, Identifiable {
        let key: String
        let recipient: String?
        let amount: Double
        let day: Int?
        var id: String { key }
    }

    struct Removed: Decodable, Hashable {
        let key: String
        let name: String
        let amount: Double
        let cadence: String
        let next: String?
        let varies: Bool?
    }

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
        /// O-10b: the account it lands in, and whether it changes each time.
        var account: String? = nil
        var varies: Bool? = nil
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
        /// O-10a: the whole bill, and her percent of it (nil is all of it).
        var full: Double? = nil
        var share: Int? = nil
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
    /// H-00r v2 / T-01r (n-home-gauge, n-cf-meter): the month's Allowance
    /// before spending, what's spent of it (paid bills count as bills), and
    /// "ok", "close" or "over" (80% and 100% of it). Left is `shown`.
    var total: Double? = nil
    var spent: Double? = nil
    var zone: String? = nil
    /// "$69 a day" for `daysLeft`; nil when over.
    var perDay: Double? = nil
    /// How it adds up: the server's rows (income, bills, spent, saved,
    /// plan, from_last_month) and the part of spent that paid bills.
    var rows: [Row] = []
    var billsPaid: Double? = nil

    struct Row: Decodable {
        let key: String
        let amount: Double
    }

    enum CodingKeys: String, CodingKey {
        case state, amount, shown, month, estimate, from, spent, zone, rows
        case daysLeft = "days_left"
        case nextPay = "next_pay"
        case overBy = "over_by"
        case total = "allowance"
        case perDay = "per_day"
        case billsPaid = "bills_paid"
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
        total = opt(Double.self, .total)
        spent = opt(Double.self, .spent)
        zone = opt(String.self, .zone)
        perDay = opt(Double.self, .perDay)
        rows = (opt([Lenient<Row>].self, .rows) ?? []).compactMap { $0.value }
        billsPaid = opt(Double.self, .billsPaid)
    }
}

// MARK: - Home

struct Home: Decodable {
    let today: String?
    let month: String
    let reviewCount: Int
    /// How many Pearl sorted without asking, shown so it isn't silent.
    var pearlSorted: Int? = nil
    /// REDESIGN-18: her answers plus what Pearl sorted, over the same window
    /// as `reviewCount`; the streak's "sorted".
    var sorted: Int? = nil
    /// AI-01: how many Pearl sorted from her own answers in the last 7 days.
    var patternWeek: Int? = nil
    /// A month with a third paycheque: a note, nothing to do.
    var paychequeNote: Review.PayMonth? = nil
    let snapshot: Snapshot?
    let safeToSpend: Allowance?
    let connections: [Connection]?

    enum CodingKeys: String, CodingKey {
        case today, month, snapshot, connections, sorted
        case reviewCount = "review_count"
        case pearlSorted = "pearl_sorted"
        case patternWeek = "pattern_week"
        case paychequeNote = "paycheque_note"
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

    /// A bank connection, worst first: "needs_sign_in", "disconnected",
    /// "bank_down" (H-01).
    struct Connection: Decodable, Identifiable {
        let itemId: String?
        let institution: String?
        let state: String?
        let lastSynced: String?
        let cardsOnly: Bool?
        var id: String { itemId ?? institution ?? "" }

        enum CodingKeys: String, CodingKey {
            case institution, state
            case itemId = "item_id"
            case lastSynced = "last_synced"
            case cardsOnly = "cards_only"
        }
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
    /// Arrivals merged into a transfer line in `transactions` (2026-11-15),
    /// shown only when a filter keeps them and not their line (TransferEnds).
    let merged: [Transaction]
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
        case transactions, total, owed, tags, merged
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
        merged = ((try? c.decodeIfPresent([Lenient<Transaction>].self, forKey: .merged)) ?? nil)?
            .compactMap { $0.value } ?? []
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
        /// T-01r: what was put away this month (month totals only).
        let saved: Double?
        /// T-01r3 (TEST-05): this month's pay still to come, until it's in.
        var pay: Pay? = nil

        struct Pay: Decodable, Hashable {
            let toCome: Double
            let expected: String?
            enum CodingKeys: String, CodingKey {
                case toCome = "to_come"
                case expected
            }
        }
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
    /// Settable (perf rehaul, 2026-11-19) so a screen can show a change
    /// the moment she makes it, before the server's row replaces this one.
    var category: String?
    let account: String?
    let accountId: String?
    let note: String?
    let pending: Bool
    let excluded: String
    let countsToward: String?
    /// "spending", "income" or "none".
    let counts: String
    var chip: Chip?
    /// TC-A (THL-122): a Transfer that pays off a card, which reads as an
    /// amount; a move between her own accounts reads "⇄ $500.00"
    /// (`movedBetweenAccounts`).
    var cardPayment = false
    /// The tap audit (P8): money in that can never be pay (a card payment,
    /// anything onto a card), so More offers no "This is my regular pay".
    var neverPay = false
    /// What the Always switch needs, from the list (2026-11-08), so the page
    /// shows it as it opens.
    var rule: RuleFacts? = nil
    /// Always on income (2026-11-08): the payer, if one can be named, and
    /// whether their deposits always count as this kind.
    var incomeRule: IncomeRule? = nil
    struct IncomeRule: Decodable, Hashable {
        let payer: String?
        let on: Bool?
    }
    struct RuleFacts: Decodable, Hashable {
        let learnable: Bool?
        let mixed: Bool?
        let hasRule: Bool?
        /// "common": the name is one every transfer shares, so no rule.
        var why: String? = nil
        enum CodingKeys: String, CodingKey { case learnable, mixed, why; case hasRule = "has_rule" }
    }
    /// Pearl's guess at the category, waiting for her yes (a dashed chip).
    var suggested: Bool
    let myNote: String
    let split: Bool
    let fullAmount: Double?
    @Boxed var refundOf: Linked?
    let refundedBy: [Linked]
    let repays: String?
    /// PQ-03p: the payback question the review asks about this deposit, on
    /// the row itself (2026-11-20), so the page opens on it. `paybackKnown`
    /// says the server answered at all (null means "no question").
    let paybackQuestion: PaybackQuestion?
    let paybackKnown: Bool
    let oneOff: Bool
    let canOneOff: Bool
    /// The piggy bank that paid for it, in whole or part.
    var bankId: Int? = nil
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
    /// The bank's spelling of the merchant, which a rename is keyed on (T-80).
    let bankMerchant: String?
    /// Her share was set on this charge (T-76).
    let shareSet: Bool
    /// The joint account's fixed share, when it splits every purchase (AM-08).
    let accountShare: Double?
    /// JOINT-B (S-01jr, T-06jr): her part of a joint purchase before any
    /// split ("Split your $50.00 with friends"); nil off a joint account.
    var jointPart: Double? = nil
    /// SPLIT-C: "unknown" for Not sure yet, or how it's split; nil unsplit.
    var splitMode: String? = nil
    let manual: Bool
    let recurring: String?
    /// The rule behind `recurring` (2026-11-24), only on GET /api/transactions/<id>.
    struct RecurringRule: Decodable, Equatable {
        let id: String
        /// "Every month, around the 1st".
        let when: String
        let category: String
        let count: Int
        let first: String?
    }
    var recurringRule: RecurringRule? = nil

    // Only on GET /api/transactions/<id>.
    /// Money in: what kind of income ("salary"), and her regular pay from
    /// this payer, when it is one (THL-198).
    let incomeType: String?
    @Boxed var regularPay: RegularPay?
    /// A purchase split with people (THL-291): your part and each of theirs.
    @Boxed var splitting: Splitting?
    /// A deposit split into parts, or a part of one.
    let parts: [DepositPart]
    @Boxed var partOf: PartOf?
    let leftToSort: Bool
    @Boxed var oneOffLine: OneOffLine?
    let repaidBy: [Brief]
    @Boxed var transfer: Transfer?
    /// Link transfers (2026-11-22): the other legs she linked this row with
    /// as one movement of money; empty when she didn't.
    var links: [Brief] = []
    /// The transfer line this arrival was merged into (2026-11-15): sent
    /// apart, in TransactionList.merged, for a filter that keeps only this
    /// end (TransferEnds).
    var mergedInto: String? = nil
    @Boxed var repaysCharge: Brief?
    /// Paybacks 2 (TP-04), boxed so Transaction stays small.
    @Boxed var jointPayback: JointPayback?
    /// TR-05 / TR-06: the trip it's in ("Shopping · Trip to Montréal"),
    /// boxed so Transaction stays small (Boxed.swift).
    @Boxed var trip: TripRef?
    /// RC-01, RC-02 (ROWCOST-01): what a split purchase costs her now and
    /// the parts its line names, as the server works them out
    /// (finance/txlist.py `cost_now`); boxed so Transaction stays small.
    @Boxed var cost: Cost?

    /// RC-01 / RC-02: `amount` is already the cost now; these are for the
    /// line under it and the RC-03 count-up of what's back.
    struct Cost: Decodable, Hashable {
        let now: Double
        let whole: Double
        let back: Double
        let toCome: Double
        let work: Double
        let ways: Int
        /// Her share as split, before any share she let go ("your share
        /// $30.00", RC-02); nil on Not sure yet.
        var share: Double? = nil
        let unsure: Bool
        /// The row's: "$127.50 split · $30.00 back · $57.50 to come".
        let line: String
        /// The page's: "$150.00 split 5 ways · $40.00 back · $50.00 to come".
        let header: String
        enum CodingKeys: String, CodingKey {
            case now, whole, back, work, ways, share, unsure, line, header
            case toCome = "to_come"
        }
    }

    /// A trip, as a row names it (finance/api.py `_with_trip`).
    struct TripRef: Decodable, Hashable {
        let id: String
        let name: String
        let start: String
        let end: String
        /// TR-06: how many transactions are in it ("Mar 4–9 · 23 transactions").
        var count: Int? = nil
    }

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
        /// TEST-31 Money back (T-41m): a refund of her share of it, and how much.
        var share: Bool? = nil
        var paid: Double? = nil
        /// On the purchase's REFUNDED BY row: its S-05o and Unlink refund? (SPLIT-25).
        @Boxed var link: LinkInfo? = nil
    }

    /// SPLIT-25 (THL-291): one payment that paid back this purchase, as
    /// S-05o's options and the Unlink? sheet (S-34s, S-34k) say it. The
    /// server words it, so the line always says what Unlink does.
    struct LinkInfo: Decodable, Hashable, Identifiable {
        let id: String
        /// The money in to unlink (`DELETE …/paybacks/<inflow>` or `…/refund`),
        /// or the cash or app payment (`DELETE …/split/cash/<cash_id>`).
        let inflow: String?
        let cashId: Int?
        /// What it put toward this purchase.
        let amount: Double
        let date: String
        /// bank, part, cash, app, reimbursement or refund.
        let kind: String
        /// "e-Transfer", "cash", "PayPal payment": "Unlink the $10.00 cash…".
        let noun: String
        /// S-05o: "Jo paid back $30.00" over "Part of $60.00 · also paid back Pizza Nova".
        let dialog: String
        let message: String
        /// "View the e-Transfer", "View the deposit", "View the refund"; none for cash.
        let view: Target?
        let sheet: Sheet
        /// S-05t's toast, when the server knows it before unlinking.
        let toast: String?
        /// The whole payment, the other purchases it paid back, and the
        /// deposit that holds it (REFRESH-02's payment cards on S-40).
        var whole: Double? = nil
        var others: [String]? = nil
        var deposit: Deposit? = nil
        /// PB-42 (Paybacks & undo): who it's credited to, every other purchase
        /// the same payment still pays back ("Pai Northern Thai stays paid"),
        /// their share of this purchase, and what of the payment is still free.
        var person: String? = nil
        var stays: [String]? = nil
        var share: Double? = nil
        var free: Double? = nil
        /// "e-Transfer": the whole payment's word, also for a part of it.
        var word: String? = nil

        struct Target: Decodable, Hashable { let id: String; let label: String }
        struct Deposit: Decodable, Hashable { let id: String; let amount: Double; let date: String }
        struct Sheet: Decodable, Hashable {
            let title: String
            let name: String
            /// Whose initials the sheet shows: "JO", "LO" for a Loblaws refund.
            let face: String
            let sub: String
            /// S-34s: "This $60.00 also paid back Pizza Nova. Unlink only Loblaws’ $30.00?"
            let ask: String?
            let line: String
            let button: String
            /// REFRESH-02 (S-34sr, S-34kr): "Unlink Sam’s e-Transfer?" (or the ask),
            /// the payment card, "Unlink $30.00" / "Keep linked", the footnote.
            var heading: String? = nil
            var overline: String? = nil
            var card: Card? = nil
            var confirm: String? = nil
            var keep: String? = nil
            var note: String? = nil

            struct Card: Decodable, Hashable { let label: String; let amount: Double }
        }

        enum CodingKeys: String, CodingKey {
            case id, inflow, amount, date, kind, noun, dialog, message, view, sheet, toast, whole, others, deposit
            case person, stays, share, free, word
            case cashId = "cash_id"
        }
    }

    /// PB-41o (REFRESH-18): a payment over the share it paid: what paid the
    /// share, the extra, and whether it's still a question.
    struct OverPayment: Decodable, Hashable {
        let charge: String
        let name: String
        let share: Double
        let back: Double
        let extra: Double
        let state: String
        let line: String?
        /// What's still a question of it, S-11e2's line, and "e-Transfer" or "payment".
        var asked: Double? = nil
        var note: String? = nil
        var word: String? = nil

        var asks: Bool { state == "ask" }
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
        /// The purchase's split, when it was split (2026-11-08).
        @Boxed var split: Splitting? = nil
        /// On the purchase's PAID BACK row: its S-05o and Unlink? (SPLIT-25).
        @Boxed var link: LinkInfo? = nil
        /// T-41w: how the deposit was answered: "reimbursement" for Work
        /// paying me back; nil for a friend paying her back.
        var kind: String? = nil
        /// PB-41o (REFRESH-18): what of it is over the share it paid.
        @Boxed var over: OverPayment? = nil

        enum CodingKeys: String, CodingKey {
            case id, date, merchant, description, amount, person, paid, split, link, kind, over
            case accountName = "account_name"
        }

        var name: String { person ?? merchant ?? description ?? "Transaction" }
    }

    struct Splitting: Decodable, Hashable {
        let mode: String?
        let you: Double
        let people: [Person]
        /// SPLIT-22b (S-05u, THL-181): paybacks linked here that Pearl
        /// credited to no one, newest first. Each asks "Who sent this?".
        var uncredited: [Uncredited]? = nil
        /// JOINT-B: what was split (her part of a joint purchase, or all of it).
        var base: Double? = nil
        /// SPLIT-C (S-04u): what a Not sure yet split still costs her, and
        /// what's come back so far.
        var still: Double? = nil
        var paid: Double? = nil
        /// SPLIT-C (S-46c): the day she said That's everything.
        var closedAt: String? = nil
        /// JOINT-B (S-04j): who else is on the joint account, and their part.
        var joint: Joint? = nil
        /// TEST-18 (THL-303): she's in it ("I had some too"); nil is yes.
        var me: Bool? = nil
        /// TEST-31 (S-04w, S-04w2, S-40w): her own share, reimbursed by work.
        var mine: Mine? = nil

        /// SPLIT-C: Not sure yet, with no amounts.
        var unsure: Bool { mode == "unknown" }
        /// TEST-18: she's in it.
        var withMe: Bool { me ?? true }

        struct Joint: Decodable, Hashable {
            let label: String
            let people: [String]
            let share: Double?
            let part: Double
            let theirs: Double
        }

        enum CodingKeys: String, CodingKey {
            case mode, you, people, uncredited, base, still, paid, joint, me, mine
            case closedAt = "closed_at"
        }

        /// TEST-31: "✓ Reimbursed by Northwind · Nov 14", or "Reimbursed
        /// $45.00 of $60.00 · $15.00 stays yours" (S-04w2), with what
        /// reimbursed it for S-40w's REIMBURSED BY.
        struct Mine: Decodable, Hashable {
            let amount: Double
            let reimbursed: Double
            let on: String?
            let stays: Double
            var links: [LinkInfo]? = nil
            /// TEST-31 Money back (S-04m): "refund" when a shop refund covered
            /// it ("✓ Refunded"), else "reimbursement" (work).
            var kind: String? = nil
            var refunded: Bool { kind == "refund" }
            /// Reimbursed in full.
            var full: Bool { stays < 0.005 }
        }

        /// "$30.00 from an e-Transfer" over "Nov 16 · no name · paid back Loblaws".
        struct Uncredited: Decodable, Hashable, Identifiable {
            let id: String
            /// What it put toward this purchase.
            let amount: Double
            let date: String
            /// The name the bank put on it, if any.
            let sender: String?
            /// "e-Transfer" or "payment".
            let word: String
            /// The deposit's own name, for its initials ("Interac e-Transfer").
            let name: String?
            let paidBack: [String]

            enum CodingKeys: String, CodingKey {
                case id, amount, date, sender, word, name
                case paidBack = "paid_back"
            }
        }

        struct Person: Decodable, Hashable, Identifiable {
            let name: String
            let amount: Double
            let paid: Double
            let owes: Double
            let paidOn: String?
            let cash: Double?
            let cashIds: [Int]?
            let letGo: LetGo?
            /// Paid back through another app (SPLIT-11), apart from cash.
            var app: Double? = nil
            /// Paid more than their share (S-03e): she owes them this.
            var over: Double? = nil
            /// Their % or shares, so Edit split opens the way it was saved (S-03e).
            var weight: Double? = nil
            /// The app she named for their newest app payment (SPLIT-14, S-06 v3).
            var appName: String? = nil
            /// Each cash or app payment once, as recorded (SPLIT-15).
            var payments: [Payment]? = nil
            /// Paybacks of theirs that also paid back other purchases (SPLIT-16).
            var shared: [Shared]? = nil
            /// Every payment that paid them back here, each with its S-05o
            /// options and Unlink? sheet (SPLIT-25, S-05v).
            var links: [LinkInfo]? = nil
            /// TEST-18b (S-48e): what of their money she called a gift.
            var gift: Double? = nil
            var id: String { name }

            /// REFRESH-18: what they paid over, until she has said what it is.
            var extra: Extra? = nil

            struct LetGo: Decodable, Hashable {
                let was: Double
                let day: String
                /// REFRESH-18 (S-04s): a small difference Pearl settled itself.
                var auto: Bool? = nil
            }

            /// What they paid over their share (finance/over_under.py): "ask"
            /// (the chip), "small" (a quiet line), "owe", or "said" once it
            /// has all gone somewhere.
            struct Extra: Decodable, Hashable {
                let state: String
                /// What's still a question, or the small one.
                let amount: Double
                /// What she owes back.
                let owe: Double
                /// "You owe $15.00 back", "$10.00 gift · $5.00 for Pizza Nova".
                let line: String?
                /// S-11e2: "$10.00 was a gift.".
                var note: String? = nil
                /// What of it has gone somewhere (a gift, sent back, another share).
                var moved: Double? = nil

                var asks: Bool { state == "ask" && amount >= 0.005 }
                var small: Bool { state == "small" }
            }

            /// She undid a small let go here, so Pearl doesn't settle it again.
            var hers: Bool? = nil

            /// The cutoff for a difference that settles itself (SMALL_MAX,
            /// SMALL_SHARE in finance/over_under.py; both must hold), to say
            /// it before she confirms. The server decides.
            static func small(_ difference: Double, of share: Double) -> Bool {
                let d = Int((difference * 100).rounded()), s = Int((share * 100).rounded())
                return d > 0 && d <= 200 && d * 10 <= s
            }

            /// What of their share she let go, now.
            var letGoLeft: Double { max(0, (((letGo?.was ?? amount) - amount) * 100).rounded() / 100) }
            /// Paid back in full, or settled with a small difference (S-04s).
            var settledInFull: Bool { owes < 0.005 && paid >= 0.005 && (letGo == nil || letGo?.auto == true) }

            /// "$250.00 cash · Nov 3", and "$200.00 deposited Nov 12 · $50.00 still cash".
            struct Payment: Decodable, Hashable {
                let amount: Double
                let day: String
                let via: String?
                let app: String?
                let deposited: Double
                let depositedOn: String?
                let still: Double
                /// SPLIT-19 (S-11c): the whole payment, when its extra went
                /// elsewhere too, and what of it she gave back.
                var whole: Double? = nil
                var givenBack: Double? = nil
                /// SPLIT-19 (S-11c, Paying me back): every purchase it paid
                /// back, this payment's own first, when it paid more than one.
                var paidBack: [String]? = nil

                enum CodingKeys: String, CodingKey {
                    case amount, day, via, app, deposited, still, whole
                    case depositedOn = "deposited_on"
                    case givenBack = "given_back"
                    case paidBack = "paid_back"
                }
            }

            /// "Her $60.00 e-Transfer also paid back Costco" (S-03f, SPLIT-16).
            struct Shared: Decodable, Hashable {
                let whole: Double
                let here: Double
                let others: [String]
                let word: String
            }

            /// Their share before any let go: what Edit split shows (S-03e).
            var share: Double { letGo?.was ?? amount }

            enum CodingKeys: String, CodingKey {
                case name, amount, paid, owes, cash, app, over, weight, payments, shared, links, gift, extra, hers
                case appName = "app_name"
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
        /// Paybacks 2 (TP-01): on money in from a joint account into one
        /// only hers, who else is on it ("Mom paid me back").
        var joint: JointFrom? = nil
        /// TP-05: between two accounts only hers, so no Paid back.
        var mineOnly: Bool? = nil
        /// A chain (2026-11-22): the accounts the money passed through on
        /// its way from `from` to `to`, and every leg's id.
        var via: [String]? = nil
        var legs: [String]? = nil

        struct JointFrom: Decodable, Hashable {
            let people: [String]
            /// "Joint ··1123".
            let account: String
        }

        enum CodingKeys: String, CodingKey {
            case from, to, joint, via, legs
            case otherId = "other_id"
            case otherDate = "other_date"
            case mineOnly = "mine_only"
        }
    }

    /// Paybacks 2 (TP-04): money in that a joint account's other owner paid
    /// her back with; the money out of the joint account is theirs.
    struct JointPayback: Decodable, Hashable {
        let person: String
        /// The joint money out, "Joint ··1123", and "Chequing ··4417".
        let outId: String
        let account: String
        let into: String

        enum CodingKeys: String, CodingKey {
            case person, account, into
            case outId = "out_id"
        }
    }

    enum CodingKeys: String, CodingKey {
        case id, date, description, amount, inflow, category, account, note, pending, excluded, chip
        case counts, suggested, split, repays, tags, kind, group, joint, manual, recurring, transfer, rule, links
        case incomeRule = "income_rule"
        case recurringRule = "recurring_rule"
        case cardPayment = "card_payment"
        case neverPay = "never_pay"
        case merchantName = "merchant"
        case accountId = "account_id"
        case countsToward = "counts_toward"
        case myNote = "my_note"
        case fullAmount = "full_amount"
        case refundOf = "refund_of"
        case refundedBy = "refunded_by"
        case oneOff = "one_off"
        case canOneOff = "can_one_off"
        case bankId = "bank_id"
        case categorySource = "category_source"
        case jointPeople = "joint_people"
        case jointFrom = "joint_from"
        case jointPerson = "joint_person"
        case jointShare = "joint_share"
        case jointSplit = "joint_split"
        case bankMerchant = "bank_merchant"
        case shareSet = "share_set"
        case jointPart = "joint_part"
        case splitMode = "split_mode"
        case oneOffLine = "one_off_line"
        case incomeType = "income_type"
        case regularPay = "regular_pay"
        case splitting, parts
        case partOf = "part_of"
        case leftToSort = "left_to_sort"
        case repaidBy = "repaid_by"
        case repaysCharge = "repays_charge"
        case mergedInto = "merged_into"
        case trip, cost
        case jointPayback = "joint_payback"
        case paybackQuestion = "payback_question"
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
        cardPayment = opt(Bool.self, .cardPayment) ?? false
        neverPay = opt(Bool.self, .neverPay) ?? false
        rule = opt(RuleFacts.self, .rule)
        incomeRule = opt(IncomeRule.self, .incomeRule)
        suggested = opt(Bool.self, .suggested) ?? (chip?.suggested ?? false)
        myNote = opt(String.self, .myNote) ?? ""
        split = opt(Bool.self, .split) ?? false
        fullAmount = opt(Double.self, .fullAmount)
        refundOf = opt(Linked.self, .refundOf)
        refundedBy = opt([Linked].self, .refundedBy) ?? []
        repays = opt(String.self, .repays)
        paybackQuestion = opt(PaybackQuestion.self, .paybackQuestion)
        paybackKnown = c.contains(.paybackQuestion)
        oneOff = opt(Bool.self, .oneOff) ?? false
        canOneOff = opt(Bool.self, .canOneOff) ?? false
        bankId = opt(Int.self, .bankId)
        tags = opt([String].self, .tags) ?? []
        kind = opt(String.self, .kind)
        group = opt(String.self, .group)
        categorySource = opt(String.self, .categorySource)
        joint = opt(String.self, .joint) ?? ""
        jointPeople = opt([String].self, .jointPeople) ?? []
        jointFrom = opt(String.self, .jointFrom) ?? ""
        jointPerson = opt(String.self, .jointPerson).flatMap { $0.isEmpty ? nil : $0 }
        jointShare = opt(Double.self, .jointSplit) ?? opt(Double.self, .jointShare)
        bankMerchant = opt(String.self, .bankMerchant)
        shareSet = opt(Bool.self, .shareSet) ?? false
        accountShare = opt(Double.self, .jointShare)
        jointPart = opt(Double.self, .jointPart)
        splitMode = opt(String.self, .splitMode)
        manual = opt(Bool.self, .manual) ?? false
        recurring = opt(String.self, .recurring)
        recurringRule = opt(RecurringRule.self, .recurringRule)
        oneOffLine = opt(OneOffLine.self, .oneOffLine)
        incomeType = opt(String.self, .incomeType)
        regularPay = opt(RegularPay.self, .regularPay)
        splitting = opt(Splitting.self, .splitting)
        parts = opt([DepositPart].self, .parts) ?? []
        partOf = opt(PartOf.self, .partOf)
        leftToSort = opt(Bool.self, .leftToSort) ?? false
        repaidBy = opt([Brief].self, .repaidBy) ?? []
        transfer = opt(Transfer.self, .transfer)
        links = opt([Brief].self, .links) ?? []
        repaysCharge = opt(Brief.self, .repaysCharge)
        mergedInto = opt(String.self, .mergedInto)
        trip = opt(TripRef.self, .trip)
        cost = opt(Cost.self, .cost)
        jointPayback = opt(JointPayback.self, .jointPayback)
    }

    /// The name to show: the merchant, else the bank's description.
    var merchant: String {
        if let name = merchantName, !name.isEmpty { return name }
        if let text = description, !text.isEmpty { return text }
        return "Transaction"
    }

    /// The category the row shows: Pearl's chip, else the stored one.
    var label: String { chip?.label ?? category ?? "Other" }

    /// The row as it will read once the server has sorted it as `name`
    /// (perf rehaul, 2026-11-19): shown at once, replaced by the server's
    /// own row when the write's `changed` comes back.
    func sorted(as name: String) -> Transaction {
        var t = self
        t.category = name
        t.chip = Chip(label: name, suggested: false)
        t.suggested = false
        return t
    }

    /// The row with Pearl's guess taken as right: the same chip, no longer dashed.
    func guessConfirmed() -> Transaction {
        var t = self
        let name = label
        t.category = name
        t.chip = Chip(label: name, suggested: false)
        t.suggested = false
        return t
    }

    /// Needs a look asking a question ("Not sorted yet", "Whose?"), not
    /// Pearl guessing at a category.
    var asks: Bool { suggested && ["Not sorted yet", "Possible duplicate", "Whose?"].contains(label) }

    /// Left out, a transfer, a repayment: shown, but not counted.
    var notCounted: Bool { !excluded.isEmpty || counts == "none" }

    /// TC-A (THL-122, THL-123, Figma 1368:8300): money moved between her own
    /// accounts, into or out of savings included. It didn't leave her, so it
    /// reads "⇄ $500.00" in grey with no sign. A card payment is money moved
    /// between her accounts too, and its page says so, so it has ⇄ as well
    /// (product owner, 2026-11-26; was a plain amount). A row left out and
    /// joint money that isn't hers don't count either: grey, no ⇄.
    var movedBetweenAccounts: Bool {
        excluded.isEmpty && counts == "none"
            && ["Transfer", "Saved"].contains(chip?.label ?? "")
    }

    /// TC-A: where it went, for VoiceOver's "Moved $500.00 to Tangerine
    /// Savings": the other end when the server joined the two, else this
    /// account for an arrival, else the payee.
    var movedTo: String {
        if let to = transfer?.to, !to.isEmpty { return to }
        if inflow, let account = account, !account.isEmpty { return account }
        return merchant
    }

    /// Everything a row shows. SwiftUI skips redrawing a row that compares
    /// equal, so comparing less leaves old answers on the list: a Yes keeps the
    /// category and changes only the chip (the critics' stale rows, 2026-11-06).
    ///
    /// Stack (2026-11-16): written as one expression, this had a 31,584-byte
    /// frame in the Debug device build, near the 32 KB that crashed the
    /// product owner's iPhone (#340, #364): Debug gives every field read its
    /// own stack slot, and `a.splitting`, `a.trip` and `a.cost` copied whole
    /// values out of their boxes. The same fields are now compared a few at a
    /// time in helpers that are never inlined, so each has a small frame of
    /// its own, and the boxed ones compare as boxes (Boxed.==): the same box
    /// is equal without unboxing, else their contents are compared, as before.
    /// No field was dropped: there's no revision field from the server that
    /// changes whenever these do, so `id` alone would miss a reload's edits.
    /// `id` goes first, so two different transactions stop there.
    static func == (a: Transaction, b: Transaction) -> Bool {
        a.id == b.id && sameChip(a, b) && sameMoney(a, b) && sameAnswers(a, b) && sameSplit(a, b)
    }

    @inline(never)
    private static func sameChip(_ a: Transaction, _ b: Transaction) -> Bool {
        a.category == b.category && a.suggested == b.suggested && a.chip == b.chip
            && a.merchant == b.merchant
    }

    @inline(never)
    private static func sameMoney(_ a: Transaction, _ b: Transaction) -> Bool {
        a.amount == b.amount && a.fullAmount == b.fullAmount && a.note == b.note && a.counts == b.counts
            && a.excluded == b.excluded && a.cardPayment == b.cardPayment && a.pending == b.pending
    }

    @inline(never)
    private static func sameAnswers(_ a: Transaction, _ b: Transaction) -> Bool {
        a.oneOff == b.oneOff && a.tags == b.tags && a.jointFrom == b.jointFrom && a.bankId == b.bankId
            && sameLinks(a, b)
    }

    /// What it's linked to (Paybacks 2): a reload that only links or unlinks
    /// it, or changes who paid, redraws the page. The arrays compare by
    /// their buffers first and the boxed ones as boxes (Boxed.==), so no
    /// link is copied out of its box onto this frame.
    @inline(never)
    private static func sameLinks(_ a: Transaction, _ b: Transaction) -> Bool {
        a.refundedBy == b.refundedBy && a.repaidBy == b.repaidBy && a._refundOf == b._refundOf
            && a._repaysCharge == b._repaysCharge && a._transfer == b._transfer
            && a._jointPayback == b._jointPayback
    }

    @inline(never)
    private static func sameSplit(_ a: Transaction, _ b: Transaction) -> Bool {
        // TEST-19 (round 2): the page holds its Transaction in @State,
        // and SwiftUI skips a redraw when the new value compares equal.
        // A split saved, closed or paid back changes only these.
        a.split == b.split && a._splitting == b._splitting
            // TR-05: made into a trip, renamed, or taken out of one.
            && a._trip == b._trip
            // RC-03: a payback changes what's back and to come.
            && a._cost == b._cost
    }
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
    /// The cash records a cash part holds, to save it again (S-10e).
    var cashIds: [Int]? = nil
    /// PB-41: the person's share of the purchase a payback part pays back.
    var share: Double? = nil
    /// PB-41s (REFRESH-18): a few cents over several shares; counts for nothing.
    var small: Bool? = nil
    /// PB-41o: what of it is over the share.
    var over: Transaction.OverPayment? = nil
    /// What they owe again once it's unlinked, when that isn't `amount`.
    var again: Double? = nil

    struct Charge: Decodable, Hashable {
        let id: String
        let merchant: String
        let date: String
        let amount: Double
        let category: String?
    }

    enum CodingKeys: String, CodingKey {
        case id, kind, amount, person, category, charge, sorted, share, small, over, again
        case incomeKind = "income_kind"
        case cashIds = "cash_ids"
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
        // S-11 v2 (SPLIT-04).
        case "reimbursement": return "Paid back · work" + (charge.map { " · \($0.merchant)" } ?? "")
        case "loan": return "Lent me this"
        case "lent_back": return "Money I lent, back"
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
            /// The split purchase, to count splits (H-00n).
            var chargeId: String? = nil

            enum CodingKeys: String, CodingKey {
                case merchant, date, owes, amount
                case chargeId = "charge_id"
            }
        }
    }

    struct Back: Decodable, Hashable {
        let name: String?
        let merchant: String?
        let date: String
        let amount: Double
        let cash: Bool?
        /// Through another app, and which (SPLIT-14).
        var app: Bool? = nil
        var appName: String? = nil
        /// SPLIT-15: how much of a cash payment a deposit holds, and when.
        var deposited: Double? = nil
        var depositedOn: String? = nil
        var still: Double? = nil
        /// SPLIT-19: one payment that paid back several purchases, named.
        var paidBack: [String]? = nil

        enum CodingKeys: String, CodingKey {
            case name, merchant, date, amount, cash, app, deposited, still
            case appName = "app_name"
            case depositedOn = "deposited_on"
            case paidBack = "paid_back"
        }
    }

    /// SPLIT-C (S-14u): Not sure yet splits, never in the total.
    var notSettled: [NotSettled]? = nil

    struct NotSettled: Decodable, Hashable, Identifiable {
        let chargeId: String
        let merchant: String
        let date: String
        let people: [String]
        let paid: Double
        let still: Double
        /// Who has paid something so far (H-00u0).
        var paidBy: [String]? = nil
        /// TEST-18 (S-14u4): she's in it.
        var me: Bool? = nil
        var id: String { chargeId }

        enum CodingKeys: String, CodingKey {
            case merchant, date, people, paid, still, me
            case chargeId = "charge_id"
            case paidBy = "paid_by"
        }
    }

    enum CodingKeys: String, CodingKey {
        case total, people
        case owesYou = "owes_you"
        case youOwe = "you_owe"
        case paidBack = "paid_back"
        case notSettled = "not_settled"
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
        /// G1-WhatWasThis-r: how often she has used it (her four likeliest lead).
        var uses: Int? = nil
        var id: String { name }
    }
}

struct CategoryChange: Decodable {
    let category: String?
    /// What Undo sends back (T-38b).
    var undo: JSONValue? = nil
    /// What the write changed (perf rehaul, 2026-11-19).
    var changed: Changed? = nil
}

// MARK: - Categories and rules

/// GET /api/rules: her saved rules, Fixed or Variable by category, her names
/// for merchants, her tags, and the categories she hid.
struct RulesBook: Decodable {
    let rules: [Rule]
    /// What she chose: category → "fixed" or "variable".
    let kinds: [String: String]?
    /// What Pearl would say on its own, the same way.
    let pearlKinds: [String: String]?
    let names: [MerchantName]?
    let tags: [TagTotal]?
    let hidden: [String]?

    enum CodingKeys: String, CodingKey {
        case rules, kinds, names, tags, hidden
        case pearlKinds = "pearl_kinds"
    }

    struct Rule: Decodable, Identifiable, Hashable {
        /// "merchant:loblaws", "destination:…", "recurring:…", "pay:…", "exclusion:3".
        let id: String
        let kind: String
        let name: String
        let category: String?
        let reason: String?
        let matched: Int?

        /// Files things under a category she can change. Pay is always income,
        /// and a leave-out rule has no category.
        var isSorting: Bool { kind != "pay" && kind != "exclusion" }

        /// "Always Groceries".
        var words: String {
            switch kind {
            case "exclusion": return "Always left out"
            case "pay": return "Always your regular pay"
            default: return "Always \(category ?? "Other")"
            }
        }

        /// What the rule does, in a sentence (pay and leave-out rules).
        var does: String {
            if kind == "pay" {
                return "Every deposit from \(name) counts as your regular pay: income, and part of your monthly income."
            }
            let why = reason.map { $0.isEmpty ? "" : ": \($0)" } ?? ""
            let now: String
            switch matched ?? 0 {
            case 0: now = "It catches new ones as they come in."
            case 1: now = "It leaves out 1 transaction now."
            case let n: now = "It leaves out \(n) transactions now."
            }
            return "Always left out\(why). \(now)"
        }

        /// What removing it does.
        var removing: String {
            kind == "pay"
                ? "Removing it keeps the ones already sorted as your pay. The next deposit from them is asked about again."
                : "Removing it puts what it left out back into your spending."
        }
    }

    struct MerchantName: Decodable, Identifiable, Hashable {
        /// The bank's spelling.
        let merchant: String
        let key: String
        /// Her name for it.
        let name: String
        var id: String { key }
    }

    struct TagTotal: Decodable, Identifiable, Hashable {
        let tag: String
        let count: Int
        let spent: Double
        var id: String { tag }
    }
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
    /// An unsorted transfer: where it went ("••4567", a payee).
    var to: String? = nil
    /// Whether a rule for this name could match the right rows.
    var learnable: Bool? = nil
    /// A merchant she has sorted into more than one category (T-97).
    var mixed: Bool? = nil
    /// Money going out that the evidence asks about in its own words.
    var pair: Review.Pair? = nil
    /// What counts as hers, when she shared it or a piggy bank paid part.
    var myAmount: Double? = nil
    /// TEST-31 T-09w: her share of a split purchase as its own match
    /// (`share`, what's `left` of it), and who else it was split with.
    var share: Bool? = nil
    var left: Double? = nil
    var whole: Double? = nil
    var splitWith: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case id, date, merchant, description, amount, category, skipped, likely, to, learnable, mixed, pair
        case share, left, whole
        case splitWith = "split_with"
        case myAmount = "my_amount"
        case accountName = "account_name"
        case accountId = "account_id"
    }

    var inflow: Bool { amount < 0 }
    var name: String { (merchant?.isEmpty == false ? merchant : description) ?? "Transaction" }
    /// The amount to show: hers, the same as the transaction's own page.
    var shownAmount: Double { myAmount ?? abs(amount) }
    /// "Your share of $131.40", when that's less than the whole.
    var shareNote: String? {
        !inflow && abs(amount) - shownAmount > 0.005 ? "Your share of \(Format.amount(abs(amount)))" : nil
    }
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
    /// "Is TD Savings where you save?", "Still paid by Acme?".
    let checks: [Item]
    /// T-74: months that held a third paycheque. No transaction to sort;
    /// "Got it" dismisses one.
    let threePayMonth: [PayMonth]
    /// AI-18: patterns Pearl asks about once, before it sorts any (Quick sort).
    var patternAsks: [PatternAsk] = []
    /// TR-01: likely trips Pearl asks about, one card each (Quick sort).
    var tripAsks: [TripAsk] = []
    /// Answers given today, and rows Pearl sorted without asking.
    var sortedToday: Int = 0
    var pearlSorted: Int = 0
    /// REDESIGN-18: her own answers over the same window as `pearlSorted`
    /// (Home's `sorted` is this plus `pearlSorted`).
    var youSorted: Int = 0
    let unsorted: Unsorted?
    let kinds: [String: String]?

    struct PayMonth: Decodable, Identifiable, Hashable {
        let key: String
        /// "2026-10".
        let month: String
        let paycheque: Double?
        let monthly: Double?
        let reason: String?
        let skipped: Bool?
        var id: String { key }
    }

    enum CodingKeys: String, CodingKey {
        case count, open, unsorted, kinds, duplicate
        case unsureCategory = "unsure_category"
        case moneyIn = "money_in"
        case incomeType = "income_type"
        case jointIn = "joint_in"
        case whoSent = "who_sent"
        case recurringTransfer = "recurring_transfer"
        case checks
        case threePayMonth = "three_pay_month"
        case sortedToday = "sorted_today"
        case pearlSorted = "pearl_sorted"
        case youSorted = "you_sorted"
        case patternAsks = "pattern_asks"
        case tripAsks = "trip_asks"
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
        checks = items(.checks)
        sortedToday = (try? c.decodeIfPresent(Int.self, forKey: .sortedToday)) ?? 0
        pearlSorted = (try? c.decodeIfPresent(Int.self, forKey: .pearlSorted)) ?? 0
        youSorted = (try? c.decodeIfPresent(Int.self, forKey: .youSorted)) ?? 0
        patternAsks = (try? c.decodeIfPresent([Lenient<PatternAsk>].self, forKey: .patternAsks))?
            .compactMap { $0.value } ?? []
        tripAsks = (try? c.decodeIfPresent([Lenient<TripAsk>].self, forKey: .tripAsks))?
            .compactMap { $0.value } ?? []
        threePayMonth = (try? c.decodeIfPresent([Lenient<PayMonth>].self, forKey: .threePayMonth))?
            .compactMap { $0.value } ?? []
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
        /// T-15: the other copy of a possible duplicate.
        var twin: BriefTransaction? = nil
        /// S-21u (SPLIT-22b, THL-181): a payback already linked that Pearl
        /// credited to no one. Its "Who sent this?" opens S-35c.
        var credit: Credit? = nil
        /// S-21x (SPLIT-23 (1), THL-181): a payback linked to a purchase
        /// nobody still owed on, so the whole amount is extra. Its "What was
        /// this?" opens S-11x.
        var extra: Extra? = nil
        /// AI-07: why Pearl won't sort this one by itself.
        var unsure: Unsure? = nil
        /// PQ-03 (Payback question, note 1419:89986): "Is mPg paying you
        /// back?" in the server's words, with the likely purchases as tiles.
        /// Boxed so Item stays small (Boxed.swift; stack check).
        @Boxed var payback: PaybackQuestion? = nil

        /// S-21o (REFRESH-18): a payment over someone's share. Its "What’s
        /// the extra?" opens S-11e.
        @Boxed var over: Over? = nil
        /// S-21p, S-21g: the share it could be paying back.
        @Boxed var split: SplitMatch? = nil

        struct Over: Decodable, Hashable {
            let charge: String
            let merchant: String
            let name: String
            let amount: Double
            /// "e-Transfer" or "payment"; what they paid and their share.
            var word: String? = nil
            var share: Double? = nil
            var note: String? = nil
        }

        struct SplitMatch: Decodable, Hashable {
            let merchant: String
            let name: String
            let owes: Double
            /// A share she let the rest of go of.
            var letGo: Bool? = nil
            /// A Not sure yet split: no amount anyone owes.
            var unknown: Bool? = nil
            enum CodingKeys: String, CodingKey { case merchant, name, owes, unknown; case letGo = "let_go" }
        }

        struct Extra: Decodable, Hashable {
            /// Every purchase it was linked to: "extra on Loblaws".
            let paidBack: [String]
            /// Who has paid back on them: "Sam and Priya have both paid you back".
            let people: [String]
            /// The extra: the whole deposit on S-21x, the part on S-21xm.
            let amount: Double
            /// S-21xm (THL-301, SPLIT-24): the whole deposit, when only part of it is extra.
            var whole: Double? = nil
            /// S-11xm: the purchases it still pays back, with who: "Jo paid
            /// back $30.00 of this for Pizza Nova."
            let credited: [Credited]?
            enum CodingKeys: String, CodingKey { case paidBack = "paid_back"; case people, amount, whole, credited }

            struct Credited: Decodable, Hashable {
                let person: String
                let merchant: String
                let amount: Double
            }

            /// Only part of the deposit is extra (S-21xm / S-11xm).
            var isPart: Bool { !(credited ?? []).isEmpty }
        }

        /// AI-07 (designBOT, 2026-11-15): the first case that applies.
        struct Unsure: Decodable, Hashable {
            let `case`: String
            var k: Int? = nil
            let n: Int
            var category: String? = nil
            var name: String? = nil

            /// Line 1, in ink.
            var line: String {
                let k = self.k ?? 0
                switch `case` {
                case "category":
                    return "Pearl’s not sure: \(k) of your last \(n) here \(k == 1 ? "was" : "were") \(category ?? "something else")."
                case "split": return "Pearl’s not sure: you split \(k) of your last \(n) here."
                case "person":
                    let who = name ?? "them"
                    let whose = who.lowercased().hasSuffix("s") ? "\(who)’" : "\(who)’s"
                    return "Pearl’s not sure: \(k) of the last \(n) from \(who) were \(whose) share."
                default: return "Pearl’s not sure: you’ve sorted only \(n) here so far."
                }
            }
        }

        struct Credit: Decodable, Hashable {
            /// Every purchase it paid back: "paid back Loblaws".
            let paidBack: [String]
            enum CodingKeys: String, CodingKey { case paidBack = "paid_back" }
        }

        var id: String { key }

        /// The merchant's other open guesses: the rule waits until these are answered.
        var siblings: [BriefTransaction] = []
        /// A question the evidence asks. Yes answers this row alone.
        var pair: Pair? = nil

        struct Rest: Decodable, Hashable {
            let whole: Double
            let sorted: Double
        }

        enum CodingKeys: String, CodingKey {
            case key, txn, reason, skipped, from, guess, label, people, candidates, series, rest, share, twin
            case siblings, pair, credit, extra, unsure, payback, over, split
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
            twin = opt(BriefTransaction.self, .twin)
            siblings = opt([Lenient<BriefTransaction>].self, .siblings)?.compactMap { $0.value } ?? []
            pair = opt(Pair.self, .pair)
            credit = opt(Credit.self, .credit)
            extra = opt(Extra.self, .extra)
            over = opt(Over.self, .over)
            split = opt(SplitMatch.self, .split)
            unsure = opt(Unsure.self, .unsure)
            payback = opt(PaybackQuestion.self, .payback)
        }

        static func == (a: Item, b: Item) -> Bool {
            a.key == b.key && a.txn == b.txn && a.pair == b.pair && a.guess == b.guess && a.skipped == b.skipped
        }
        func hash(into hasher: inout Hasher) { hasher.combine(key) }
    }

    /// Pearl says what it knows first (finance/pairs.py): a question the
    /// evidence asks. Yes answers this row alone.
    struct Pair: Decodable, Hashable {
        let question: String
        let evidence: String
        let line: String
        let other: String
    }

    struct Series: Decodable, Hashable {
        let when: String?
        let count: Int?
        let to: String?
        /// RQ-01 (POLISH-01): "monthly", "biweekly", "weekly" or "payday".
        var cadence: String? = nil
        var amount: Double? = nil
        /// Each payment's day, oldest first, for the rhythm.
        var dates: [String]? = nil
        var first: String? = nil
        /// When the next one is due on the schedule.
        var next: String? = nil
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
    /// A question about her plan, not a category: Yes or No (finance/checks.py).
    case check
}

struct Ask: Identifiable, Hashable {
    let kind: Question
    let item: Review.Item

    /// T-06a: a transfer to one of her savings accounts, by its last digits.
    func savedTo(_ accounts: [AccountsOverview.Account]) -> String? {
        guard kind == .transfer, let to = item.txn.to, to.contains("••") else { return nil }
        let digits = to.filter(\.isNumber)
        return accounts.first { a in
            ["savings", "investment"].contains(a.kind ?? "") && !(a.mask ?? "").isEmpty && digits.hasSuffix(a.mask!)
        }?.name
    }
    var id: String { item.key }
    var t: BriefTransaction { item.txn }
    var skipped: Bool { item.skipped == true }

    /// T-93o (replaces T-93n): Pearl's best for a category is Other. It's a
    /// guess like any other, Yes or Skip; Yes sorts this one as Other and
    /// never saves "always for <merchant>" (a rule would file every one there).
    var guessesOther: Bool {
        kind == .category && item.pair == nil && (item.guess?.text ?? t.category ?? "Other") == "Other"
    }

    /// A guess Pearl can be told yes to (T-90, T-92): a category, "Saved to",
    /// or a question the evidence asks.
    func isGuess(_ accounts: [AccountsOverview.Account]) -> Bool {
        kind == .category || savedTo(accounts) != nil || item.pair != nil || incomeGuess != nil
    }

    /// A guess opens T-96, a full page; the rest of a deposit and any other
    /// question open a sheet.
    func opensPage(_ accounts: [AccountsOverview.Account]) -> Bool {
        item.rest == nil && item.pair == nil && incomeGuess == nil && isGuess(accounts)
    }

    /// "Other income": the kind Pearl would call this money, when it asks.
    var incomeGuess: String? {
        guard kind == .incomeType, item.guess?.text != nil else { return nil }
        return item.guessLabel
    }

    /// Why Pearl is asking, under the question, where the reason helps.
    var evidence: String? {
        if let pair = item.pair { return pair.evidence }
        if incomeGuess != nil || item.guess?.action == "unknown" { return item.reason }
        return nil
    }

    /// "Dining out", or T-66's "Saved to TD Savings".
    func guessLabel(_ accounts: [AccountsOverview.Account]) -> String {
        if let to = savedTo(accounts) { return "Saved to \(to)" }
        if let income = incomeGuess { return income }
        return item.guess?.text ?? t.category ?? "Other"
    }

    /// A rule needs a name it can match, and never files everything under Other.
    private func canRule(_ accounts: [AccountsOverview.Account]) -> Bool {
        guard t.learnable != false, !guessesOther else { return false }
        return savedTo(accounts) != nil || (t.category ?? "Other") != "Other"
    }

    /// Sorted into different categories before: Yes says so, and saves no rule (T-97).
    func varies(_ accounts: [AccountsOverview.Account]) -> Bool {
        t.mixed == true && savedTo(accounts) == nil && canRule(accounts)
    }

    /// Whether Yes saves the rule. Each row is its own answer, so the rule
    /// waits for the merchant's last open row: by then her answers have either
    /// agreed, or they disagreed and the merchant varies.
    func savesRule(_ accounts: [AccountsOverview.Account]) -> Bool {
        // A bank transfer out starts with Always off (product owner,
        // 2026-11-25): OT-01 asks about the older ones instead of moving them.
        if kind == .transfer && !t.inflow && savedTo(accounts) == nil { return false }
        return canRule(accounts) && !varies(accounts) && item.siblings.isEmpty
    }

    /// Yes: this row, and the rule when `newOnes` says so. Every merchant gets
    /// a Yes; one card is one transaction.
    func yesAnswer(_ accounts: [AccountsOverview.Account], newOnes: Bool? = nil) -> ReviewAnswer {
        if kind == .check { return .check(item.key, yes: true) }
        if item.pair != nil { return .pair(t.id) }
        if incomeGuess != nil, let kind = item.guess?.text { return .incomeType(t.id, kind: kind) }
        let rule = newOnes ?? savesRule(accounts)
        if savedTo(accounts) != nil { return .mark(t.id, ["case": "saved", "remember": rule]) }
        if rule && canRule(accounts) {
            return .always(t.id, label: guessLabel(accounts))
        }
        return varies(accounts) ? .varies(t.id, name: t.name) : .confirm(t.id)
    }

    /// Whether the page offers the Always switch at all.
    func canSaveRule(_ accounts: [AccountsOverview.Account]) -> Bool { item.pair == nil && canRule(accounts) }

    /// The line above the buttons: what Yes will do, before it's done.
    func yesLine(_ accounts: [AccountsOverview.Account]) -> String {
        if let pair = item.pair { return pair.line }
        if let income = incomeGuess { return "Yes counts it as \(income)." }
        // T-93o (1284:103): Other is just this one, and the card is the way out.
        if guessesOther { return "Yes sorts this one as Other." }
        if varies(accounts) { return "Yes sorts just this one. \(t.name) varies, so no rule." }
        return savesRule(accounts) ? "Yes sorts this, and always for \(t.name)." : "Yes sorts just this one."
    }

    /// "Dining?", "Saved or spent?", "Whose?"…
    var chip: String {
        if let pair = item.pair { return pair.question }
        switch kind {
        // T-93o: Other is a guess like any other, "Other?".
        case .category: return "\(item.guess?.text ?? t.category ?? "Other")?"
        case .transfer: return "Saved or spent?"
        case .moneyIn:
            // S-21x: the extra on a paid-back purchase.
            if item.extra != nil { return "What was this?" }
            // S-21o (REFRESH-18).
            if item.over != nil { return "What’s the extra?" }
            if item.rest != nil { return "\(Format.amount(t.amount)) left to sort" }
            if item.guess?.action == "refund" { return "Whose refund?" }
            // A payment network isn't a person: never "Is Interac paying you back?".
            return t.learnable == false ? "Someone sent you \(Format.amount(t.amount))" : "What was this?"
        case .incomeType: return incomeGuess.map { "\($0)?" } ?? "What kind of income?"
        case .joint: return "Whose?"
        case .whoSent: return "Who sent this?"
        case .duplicate: return "Same purchase?"
        case .recurring: return "Recurring?"
        case .check: return item.pair?.question ?? "Is this right?"
        }
    }
}

extension Review {
    /// Every question, oldest kinds first, skipped ones included (they say so).
    var asks: [Ask] {
        var out = unsureCategory.map { Ask(kind: .category, item: $0) }
        out += (unsorted?.transfers ?? []).map { t in
            var item = Item(key: "u:" + t.id, txn: t, skipped: t.skipped)
            item.pair = t.pair
            return Ask(kind: .transfer, item: item)
        }
        out += moneyIn.map { Ask(kind: .moneyIn, item: $0) }
        out += incomeType.map { Ask(kind: .incomeType, item: $0) }
        out += jointIn.map { Ask(kind: .joint, item: $0) }
        out += whoSent.map { Ask(kind: .whoSent, item: $0) }
        out += duplicate.map { Ask(kind: .duplicate, item: $0) }
        out += recurringTransfer.map { Ask(kind: .recurring, item: $0) }
        out += checks.map { Ask(kind: .check, item: $0) }
        return out
    }
}

/// A pattern Pearl asks about first (AI-18): one Quick sort card for it.
struct PatternAsk: Decodable, Identifiable, Hashable {
    let id: String
    let kind: String
    let merchant: String?
    let answer: String
    let label: String
    let count: Int
    let need: Int
    var account: String? = nil
    var joint: String? = nil
    var rhythm: String? = nil
    /// The usual (median) amount.
    var amount: Double? = nil
    /// AI-18b: the smallest and largest, and whether every one is within $1.
    var low: Double? = nil
    var high: Double? = nil
    var sameAmount: Bool? = nil
    /// AI-18: every joint deposit was an e-Transfer.
    var etransfers: Bool? = nil

    enum CodingKeys: String, CodingKey {
        case id, kind, merchant, answer, label, count, need, account, joint, rhythm, amount, low, high, etransfers
        case sameAmount = "same_amount"
    }

    var isJoint: Bool { kind == "joint" }
    var name: String { merchant ?? answer }
    var firstName: String { answer.split(separator: " ").first.map(String.init) ?? answer }

    /// AI-18: "e-Transfers from Ana Ruiz" only when every one was; else
    /// "Deposits from Ana Ruiz". AI-18b: "Purchases at Farm Boy".
    var who: String {
        isJoint ? "\(etransfers == true ? "e-Transfers" : "Deposits") from \(name)" : "Purchases at \(name)"
    }
    /// AI-18b: the amounts vary by more than $1, so the card shows their range.
    var varies: Bool {
        guard sameAmount != true, let low = low, let high = high else { return false }
        return high - low > 1
    }
    /// "$400.00", or AI-18b's "$12–$48" (whole dollars).
    var shownAmount: String? {
        if varies, let low = low, let high = high { return Format.whole(low) + "\u{2013}" + Format.whole(high) }
        return amount.map(Format.amount)
    }
    /// "Each one · into Joint · every 2 weeks"; AI-18b "Usually $27 · about every week".
    var each: String {
        if varies {
            return ([amount.map { "Usually \(Format.whole($0))" }, rhythm] as [String?])
                .compactMap { $0 }.joined(separator: " · ")
        }
        return (["Each one", isJoint ? "into \(joint ?? account ?? "the joint account")" : nil,
                 rhythm.map { $0.replacingOccurrences(of: "about ", with: "") }] as [String?])
            .compactMap { $0 }.joined(separator: " · ")
    }
    /// "Always Ana's share?", AI-18b "Always Groceries?".
    var question: String { "Always \(label)?" }
    /// "Last 8: Ana's share." (TEXT-01); AI-18b "Last 5 at Farm Boy:
    /// Groceries."
    var because: String {
        isJoint ? "Last \(count): \(label)." : "Last \(count) at \(name): \(label)."
    }
    /// "Sort new ones the same way?" (TEXT-01).
    var yesSkip: String { "Sort new ones the same way?" }
    /// AI-18y's toast names it as AI-06 does (LearnedRule.title): "Ana's
    /// deposits", "Farm Boy".
    var title: String {
        guard isJoint else { return name }
        return (firstName.lowercased().hasSuffix("s") ? "\(firstName)\u{2019}" : "\(firstName)\u{2019}s") + " deposits"
    }
}

/// An amount in one billing currency. Pearl converts nothing, so a trip
/// across currencies has one of these for each (finance/trips.py).
struct MoneyTotal: Decodable, Hashable {
    let currency: String
    let amount: Double
}

extension Array where Element == MoneyTotal {
    /// "$1,284.60"; with more than one currency "$1,240 CAD + $310 USD" (TR-02m).
    var shown: String { Format.totals(map { ($0.currency, $0.amount) }) }
    var mixed: Bool { count > 1 }
}

/// TR-01: a likely trip Pearl asks about, from GET /api/review's `trip_asks`.
struct TripAsk: Decodable, Identifiable, Hashable {
    /// "2026-03-04:2026-03-09".
    let id: String
    let key: String
    let ids: [String]
    let start: String
    let end: String
    let days: Int
    var place: String? = nil
    var flight: Bool? = nil
    var hotel: Bool? = nil
    var fees: Bool? = nil
    /// "Trip to Montréal", or "" with no place.
    var name: String? = nil
    let count: Int
    let totals: [MoneyTotal]
    var monthNames: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case id, key, ids, start, end, days, place, flight, hotel, fees, name, count, totals
        case monthNames = "month_names"
    }

    /// "Mar 4–9 · 23 transactions".
    var line: String { "\(Format.span(start, end)) · \(count) transaction\(count == 1 ? "" : "s")" }

    /// TR-01's caption: "A flight, a hotel, 5 days in Montréal." With no
    /// place it ends "5 days away." (note 1329:69536, Wording; TEXT-01).
    var story: String {
        let lead = [flight == true ? "a flight" : nil, hotel == true ? "a hotel" : nil].compactMap { $0 }
        let stay = "\(days) day\(days == 1 ? "" : "s")" + (place.map { " in \($0)" } ?? " away")
        let text = lead.isEmpty ? stay : lead.joined(separator: ", ") + ", " + stay
        return text.prefix(1).uppercased() + text.dropFirst() + "."
    }

    /// "March", "March and April".
    var months: String { Format.andList(monthNames ?? [Format.monthName(String(start.prefix(7)))]) }
}

/// A trip (finance/trips.py `summary`): its name, rows, dates, totals per
/// currency, the months its rows count in, and its categories (TR-02–TR-04).
struct Trip: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let ids: [String]
    let start: String
    let end: String
    var place: String? = nil
    /// "pearl" (she said yes to TR-01) or "you" (Select › Make a trip).
    var by: String? = nil
    var day: String? = nil
    let count: Int
    let totals: [MoneyTotal]
    var monthNames: [String]? = nil
    var categories: [Category]? = nil

    struct Category: Decodable, Hashable {
        let category: String
        let count: Int
        /// Currency → what the category came to in it (TR-03); Pearl converts nothing.
        var totals: [String: Double]? = nil

        /// The biggest first, as the trip's own totals.
        var money: [MoneyTotal] {
            (totals ?? [:]).map { MoneyTotal(currency: $0.key, amount: $0.value) }
                .sorted { (abs($0.amount), $1.currency) > (abs($1.amount), $0.currency) }
        }
    }

    enum CodingKeys: String, CodingKey {
        case id, name, ids, start, end, place, by, day, count, totals, categories
        case monthNames = "month_names"
    }

    /// "Mar 4–9 · 23 transactions".
    var line: String { "\(Format.span(start, end)) · \(count) transaction\(count == 1 ? "" : "s")" }
    /// "March", "March and April".
    var months: String { Format.andList(monthNames ?? [Format.monthName(String(start.prefix(7)))]) }

    /// TR-09, TR-13: "The 23 stay as they are" (TEXT-01); one row reads
    /// "The transaction stays as it is" (note 1329:69536, Wording).
    static func stayLine(_ n: Int) -> String {
        n == 1 ? "The transaction stays as it is" : "The \(n) stay as they are"
    }
}

/// A row in Sorted today or Pearl sorted: who, how much, and why it's sorted.
struct SortedRow: Decodable, Identifiable {
    let id: String
    let date: String
    let merchant: String?
    let amount: Double
    let line: String
    let undo: JSONValue?
    /// AI-02: a row Pearl sorted from her own answers; it opens AI-03.
    var record: String? = nil
    /// AI-02: "rules" for a row something she set sorted (FROM YOUR RULES),
    /// "unchecked" for the rest (NOT CHECKED BY YOU).
    var group: String? = nil
}

/// The answer to sorting one transaction: what changed, and how to undo it.
/// PQ-03 (Payback question, note 1419:89986; finance/payback_question.py).
/// GET /api/review's `payback` on a money-in question, and
/// GET /api/transactions/<id>/payback-question's `question`.
struct PaybackQuestion: Decodable, Hashable {
    /// The sender as the bank named them ("mPg"), or as she did.
    let who: String
    /// She named them, or it isn't an e-Transfer: no "Name them".
    let named: Bool
    let tiles: [Tile]
    /// PQ-03b: a part payment stays on the split.
    let part: Bool
    let card: Card

    struct Tile: Decodable, Hashable, Identifiable {
        let charge: String
        let merchant: String
        let amount: Double
        let date: String
        let category: String
        let card: String
        /// "split" (they're on it), "memo" (their message names it) or "share".
        let kind: String
        /// "Añejo · $61.57", "Añejo · mPg’s share" (LT-03).
        let title: String
        /// The reason, in the tile (LT-03): "about a third · 2 days before",
        /// "$20.00 of mPg’s $30.79 · $10.79 still to come", "“tacos”".
        let compare: String
        /// PQ-03c: "mPg paid back $20.00 for Añejo".
        let toast: String
        /// PQ-03b: who on the split it's theirs ("Anastasia"), sent with the
        /// answer so it credits them however the bank wrote the sender.
        var person: String? = nil
        /// Pearl's guess: the first tile only, drawn dashed.
        var guess: Bool? = nil
        var id: String { charge }

        /// "Oct 31 · about a third · 2 days before" (LT-03); a split's tile
        /// says only how it compares (PQ-03b).
        var line: String {
            let parts = kind == "split" ? [compare] : [Format.short(date), compare]
            return parts.filter { !$0.isEmpty }.joined(separator: " · ")
        }
    }

    struct Card: Decodable, Hashable {
        /// "Paying you back for Añejo?".
        let title: String
        /// "Pearl’s guess · about a third" (TEXT-01).
        let line: String
    }
}

struct MarkReply: Decodable {
    let title: String?
    let detail: String?
    let undo: JSONValue?
    /// TEST-31 S-11w: more than her share came in; what's extra, asked next.
    var extra: ShareExtra? = nil
    /// What the write changed (perf rehaul, 2026-11-19).
    var changed: Changed? = nil
    /// OT-01: how many of the older ones moved.
    var moved: Int? = nil

    struct ShareExtra: Decodable, Hashable {
        let amount: Double
        let whole: Double
        let share: Double
        let charge: String
        let merchant: String
        /// S-11m: on a refund, who still owes on the split, in its order.
        var people: [Owing]? = nil

        struct Owing: Decodable, Hashable {
            let name: String
            let owes: Double
        }
    }
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

/// A-11: how this iPhone can be confirmed: approved on her other device,
/// or with a recovery code.
struct DeviceChoices: Decodable, Hashable {
    let approve: Approve?
    let recovery: Bool?

    struct Approve: Decodable, Hashable {
        let label: String?
        /// Seconds since 1970.
        let usedAt: Double?
        enum CodingKeys: String, CodingKey {
            case label
            case usedAt = "used_at"
        }
    }
}

/// SEC-10: another device asking to sign in as her.
struct Approval: Decodable, Identifiable, Hashable {
    let id: Int
    let label: String?
    let near: String?
    let account: Account?

    struct Account: Decodable, Hashable {
        let name: String?
        let email: String?
    }
}
