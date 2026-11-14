# AI in Pearl, on the device: feasibility and architecture plan

engBOT, 2026-11-14. This is a plan only; nothing in it is built. The product owner's decisions of 2026-11-14 set the uses, the auto-sort rule, and the decision that all of Pearl's data may go to the on-device model. designBOT is designing the screens in parallel.

A compile-only spike is on `spike/ai-foundation-models` (8844c1e), not for merge. It is described in section 1.6.

---

## 1. What Apple's Foundation Models framework gives us here

Sources on this Mac:
- **Toolchain:** Xcode 26.6 (17F113), iOS SDK 26.5.
- **Interface:** `iPhoneOS26.5.sdk/System/Library/Frameworks/FoundationModels.framework/Modules/FoundationModels.swiftmodule/arm64e-apple-ios.swiftinterface` (1,501 lines). Its doc comments are in the `.swiftdoc` next to it.
- **Pearl's deployment target:** iOS 16.0 (`ios/Pearl.xcodeproj`, `make_project.py`).

### 1.1 Availability
- Every API is `@available(iOS 26.0, macOS 26.0, visionOS 26.0, *)`, and `@available(tvOS, unavailable)` / `@available(watchOS, unavailable)`. Some newer APIs are iOS 26.4 or later:
  - the `tokenCount(for:)` family;
  - `@Generable(…, representNilExplicitlyInGeneratedContent:)`.
- `SystemLanguageModel.default.availability` is `.available` or `.unavailable(reason)`, and `isAvailable` is a shortcut. The reasons are:
  - `.deviceNotEligible`: "The device does not support Apple Intelligence."
  - `.appleIntelligenceNotEnabled`: "Apple Intelligence is not enabled on the system."
  - `.modelNotReady`: the swiftdoc says "The model isn't ready because it's downloading or because…" (other system reasons).

  Pearl has to check this every time, and fall back (section 2.6).
- **Devices:** the SDK only says "The device must support Apple Intelligence" and "Apple Intelligence must be turned on in Settings". Which iPhones qualify isn't in the SDK. From Apple's public list it's the iPhone 15 Pro and later. **Check the product owner's iPhone in Settings › Apple Intelligence & Siri.**
- **Languages:** `supportedLanguages: Set<Locale.Language>` lists them, and a prompt in an unsupported language or locale throws `.unsupportedLanguageOrLocale`. English (Canada) needs a check on the device.
- **Use cases:** `SystemLanguageModel(useCase: .general | .contentTagging, guardrails:)`. `.contentTagging` is the tuned mode for tagging and classifying, a candidate for sorting.
- **Adapters:** `SystemLanguageModel.Adapter` loads custom adapters. That's out of scope.

### 1.2 Guided generation (`@Generable`)
- `@Generable(description:)` on a struct or enum, plus `@Guide(description:, …)` on its properties.
- Built-in guides:
  - strings: `.anyOf([...])`, `.constant`, `.pattern(Regex)`;
  - numbers (Int, Float, Double, Decimal): `.minimum`, `.maximum`, `.range`;
  - arrays: count guides.
- `String`, `Int`, `Float`, `Double`, `Bool` and `Array` are `Generable`.
- `session.respond(to:generating:includeSchemaInPrompt:options:)` returns a typed `Response<T>` and **constrains decoding to the schema**. The model can't invent a category outside `.anyOf`, and a confidence outside `0...100` can't come back. This is the main safety rail for auto-sort.
- `streamResponse` gives `PartiallyGenerated` snapshots, which suit Ask Pearl.

### 1.3 Tool calling
`protocol Tool<Arguments, Output>: Sendable`:
- It has `name`, `description` and `parameters` (a `GenerationSchema`, generated from a `@Generable Arguments`).
- Its body is `@concurrent func call(arguments:) async throws -> Output`, where `Output` is `PromptRepresentable`, for example a `String` or `GeneratedContent`.
- Tools are passed to `LanguageModelSession(model:tools:instructions:)`. The model decides when to call them, and the calls and outputs are logged in the session's `Transcript` (`.toolCalls`, `.toolOutput`).
- A Tool can call Pearl's API. That's the "ask Pearl for detail" path.

### 1.4 Context window and token limits
- `SystemLanguageModel.contextSize` is back-deployed to 26.0 and inlines to **4096 tokens**. The doc says: "The context size represents the total number of tokens that can be used in a single session". That covers instructions, the prompt, tool definitions and outputs, the schema and the response together.
- Going over throws `GenerationError.exceededContextWindowSize`.
- `GenerationOptions(sampling:temperature:maximumResponseTokens:)` exists. `sampling: .greedy` gives repeatable answers, which sorting needs.
- **What this means:** a transaction line costs about 25–40 tokens, so one call can carry roughly 40–60 rows next to the instructions and schema. A month of about 150 rows is 3–5 calls. The ledger (about 1,000 demo rows) can never go in whole, so Python must summarise first. `tokenCount(for:)` (iOS 26.4+) lets us size batches exactly.

### 1.5 Errors to handle
`GenerationError` has these cases:
- `exceededContextWindowSize`
- `guardrailViolation`
- `unsupportedLanguageOrLocale`
- `rateLimited`
- `concurrentRequests`
- `refusal`
- decoding failures

Finance text can trip the guardrails, for example merchant names. Every call needs a "no answer, leave it to Quick sort" path.

### 1.6 The spike (`spike/ai-foundation-models`, 8844c1e, not for merge)
`ios/Pearl/AI/PearlModelSpike.swift` contains:
- a `@Generable SortGuessSpike` (id, an answer guided by `.anyOf`, confidence `.range(0...100)`, reason);
- a `Tool` (`merchantHistory`);
- the availability reasons mapped to plain words;
- one `LanguageModelSession.respond(to:generating:options: .greedy)` call.

It sits behind `#if canImport(FoundationModels)` and `@available(iOS 26.0, *)`.

What it showed:
- It **builds** for the simulator SDK and for `generic/platform=iOS` (`CODE_SIGNING_ALLOWED=NO`).
- `otool -l` shows FoundationModels as **`LC_LOAD_WEAK_DYLIB`**, so the iOS 16 deployment target stays safe: the app still launches on iOS 16–25. There's no need to raise the target.
- It's never called and was never run, and no simulator was used. Apple Intelligence can't run in our simulator setup anyway, so the model can only be tested on the product owner's iPhone.

---

## 2. Architecture

Your proposal holds in outline. I'd change two things:
- **The model should rank and explain, not decide alone.** Confidence for auto-sort should come mostly from Pearl's own evidence (section 2.3). A small model's self-reported "confidence" isn't calibrated.
- **Most "pattern sorting" doesn't need the model at all.** The sister's deposits are a sender-and-account pattern that Python can find exactly. The model earns its place on fuzzy cases, explanations and questions in words.

```
 Server (Python, hosted)                    iPhone (Swift, iOS 26+)
 ─────────────────────────                  ─────────────────────────────────────
 pattern features & aggregates  ──GET──▶    PearlAI (wrapper; availability check)
  recurring series, merchant                 ├─ Sorter: batches of ≤ ~50 rows,
  history, joint sender/account              │   @Generable answers (anyOf the
  patterns, usual month & drift,             │   answers Pearl allows), greedy
  duplicates, card balances                  ├─ Explainer: one-line reasons
 candidate rows with their evidence          ├─ Ask Pearl: session + Tools
 auto-sort endpoint ◀──POST── decisions      │   (merchant, month, subscriptions,
  (records who/why, returns Undo)            │    card, search) → Pearl's API
 "Pearl sorted these" + Undo                 └─ Fallback: today's rules only
```

### 2.1 Python computes, and the model reads
Much of what we need already exists:

| Need | Already in Pearl | New |
|---|---|---|
| Recurring payments and subscriptions | `finance/insights/recurring.py` (cadence clustering), `recurring_transfers.py`, `recurring_api.py` | "forgotten": not used or reviewed in N months, a price rise |
| Duplicates | `duplicates.py` (THL-165) | — |
| Usual month and drift | `usual_month.py`, `growth_insights.py` (vs usual) | a per-merchant drift series |
| Budget and cash flow | `spend_plan.py`, `safe_to_spend.py`, `income_bills.py` | a forward plan (bills and pay dates) |
| Who a joint deposit belongs to | `joint.py` (joint deposit rules by account and name) | "sender X → hers, N of N times" evidence |
| Merchant history | `categorize.py` overrides, `review.mixed_merchants`, `quick_sort` | per-merchant answer counts and the last answer |
| What Pearl sorted without asking | `sorted_log.pearl_rows` (each with a reason) and `review["pearl_sorted"]` | AI sorts recorded with confidence and model |

The model must never add up money. Totals, counts and dates come from Python. The model gets them as facts and may only quote them.

### 2.2 What goes to the model
Only compact summaries, each kept under about 2,500 tokens so the schema and answer still fit:
- **For sorting:** per row, the id, date, amount, account, merchant and the bank's label, plus its **evidence**:
  - how she answered this merchant before (counts per answer);
  - its recurring series, if any;
  - the joint account and sender pattern;
  - the rule Pearl would apply.
- **For Ask Pearl:** a one-screen digest (this month vs usual, top merchants, subscriptions, cards). Tools fetch the rest on demand.

### 2.3 Auto-sort with Undo
Each candidate gets an **evidence score** from Python. Examples:
- the same sender into the same joint account, answered "hers" 6 times out of 6;
- the merchant answered Groceries 9 times out of 9;
- an exact recurring series she already confirmed.

The model then picks the answer from an `.anyOf` list of the answers Pearl allows, with a reason. **Auto-sort only when both hold:**
1. The evidence score is at or above the threshold (start strict, for example ≥ 5 prior answers, all the same).
2. The model's answer equals what the evidence says.

Anything else goes to Quick sort as **Yes or Skip** (the house rule: one card per transaction, never grouped). The model's answer becomes the card's guess, with its reason as the line.

Every auto-sort is written through a new endpoint, recorded as `sorted_by = "pearl_ai"` with the answer, evidence, model reason, confidence, model version and time:
- It appears under the existing **"Pearl sorted"** list (`sorted_log.pearl_rows`), so "Pearl sorted these" reuses that surface.
- It has one **Undo** per row and an Undo for the batch, through the existing `undo_payload` / `undo_marks` machinery.

### 2.4 Tools for Ask Pearl
Each Tool is read-only and returns a short string or `GeneratedContent`:
- `merchantHistory(merchant)`
- `month(month)` (totals vs usual)
- `subscriptions()`
- `drift(category|merchant)`
- `cards()` (balance, utilisation, due date)
- `search(text)` (≤ 10 rows)
- `plan()` (this month's Allowance and bills to come)

No Tool can write. Answers stream into an Ask Pearl sheet, which designBOT is drawing.

### 2.5 Where it runs
- **Only while the app is open.** The model runs on the iPhone and the server can't call it.
  - Auto-sort runs after sync, when Cash flow or Home opens.
  - Ask Pearl runs when she asks.
- A `BGProcessingTask` could try overnight. Whether the model is available in the background isn't stated in the SDK, so the plan doesn't depend on it.
- The web never auto-sorts, and Pearl on the web isn't changed.

### 2.6 Fallback
If `availability` isn't `.available`, or a call throws, Pearl does exactly what it does today: the rules, Needs a look and Quick sort. Two extras:
- **Python-only pattern sorting:** the evidence score with **no** model step. This can ship before the model and works on any iPhone, if the product owner wants that (open question 2).
- **Saying why:** a one-line reason in Profile ("Apple Intelligence is off"), from the spike's mapping.

---

## 3. Server work
- **`GET /api/ai/candidates?limit=`:** the rows waiting to be sorted, each with its evidence block (2.2), in batches sized for 4,096 tokens.
- **`GET /api/ai/digest?month=`:** the Ask Pearl digest, under about 1,500 tokens.
- **Read endpoints for the Tools:** many already exist (transactions list and search, recurring, usual month, Home). We add what's missing: per-merchant history, drift and cards.
- **`POST /api/ai/sorted`:** a batch of `{txn_id, answer, evidence, reason, confidence, model}`.
  - It applies each answer through the same code as a person's answer (`marks.apply`, `quick_sort.step`), so totals, rules and joint handling stay one implementation.
  - It returns per-row Undo plus a batch Undo.
  - It **never saves a rule** ("always for …"). Only she does that.
- **Recording:** a `txn_ai_sorts` table (or `sorted_log` rows with `source = "pearl_ai"`) holding the audit trail. Undo removes the answer and marks the row so it isn't auto-sorted again.
- **Settings:** AI on or off, and the threshold. The product owner can change both.
- **pytest:** the evidence scoring, the endpoints, Undo, and "never twice after Undo".

---

## 4. Phases (pattern sorting first)
1. **P1: pattern sorting.**
   - Python evidence scores for joint deposits (the sister), merchants and recurring series.
   - The candidates and sorted endpoints, and the "Pearl sorted these" summary with Undo.
   - Then the on-device model as the second check and the source of reasons; unsure rows go to Quick sort as Yes or Skip.
   - P1a (Python only) can ship on its own.
2. **P2: subscriptions, recurring and duplicates.** Surface the existing Python results, add "forgotten" and price-rise checks, and let the model write the one-line explanations.
3. **P3: drift, merchant check and credit cards.** Drift series, a merchant's page summary, card utilisation and due dates.
4. **P4: Ask Pearl.** A streaming session with the Tools in 2.4.
5. **P5: budget and cash flow plan.** The model proposes; she accepts. It never changes the Allowance by itself.

Each phase needs designBOT's frames and the product owner's pick, as usual.

---

## 5. Risks
- **Device eligibility.** If her iPhone can't run Apple Intelligence, everything except P1a is unavailable. Check this first.
- **Small-model quality on finance.** Treat the model as a ranker and explainer behind Python evidence, never as the only judge of an auto-sort.
- **Confidence isn't calibrated.** The threshold leans on evidence counts. Watch Undo rates after launch and tighten if needed.
- **4,096-token context.** Batching and summaries are mandatory, and Ask Pearl must use Tools rather than long prompts.
- **Guardrails and refusals** on merchant names or money questions. These need graceful "couldn't answer" paths.
- **No simulator testing.** UI checks need a fake `PearlAI` behind a protocol. Real checks only happen on her iPhone, by hand.
- **Silent changes to her numbers.** Every auto-sort must be visible in "Pearl sorted these" and undoable. It must never save rules or touch splits, joint shares or the Allowance by itself.
- **Speed and battery.** About 3–5 calls per month of rows. Run once per sync, prewarm the session (`prewarm(promptPrefix:)`), and never on every screen.
- **The model changes with iOS updates.** Record the model version with each sort.

## 6. Open questions for the product owner
1. Which answers may Pearl auto-sort?
   - categories only;
   - also "hers / theirs" on joint deposits (the sister);
   - also transfers and savings.
2. Should P1a (Python patterns only, no Apple Intelligence) ship first, so it works on any iPhone?
3. How strict should the start be? I propose at least 5 earlier answers, all the same, plus the model agreeing. Should there be a daily cap on auto-sorts?
4. Should past months be auto-sorted too, or only new transactions from now on?
5. After Undo, should Pearl never auto-sort that row again, or that merchant?
6. Ask Pearl: facts about her own money only, or also suggestions ("you could cancel …")?
7. Credit cards: what does "track use" mean: balance, utilisation, due dates, interest, or spending per card?
8. Budget and cash flow: may the model change the Allowance or plan, or only propose for her to accept?
9. An on/off switch in Profile, and a short line saying data never leaves the iPhone for this?
