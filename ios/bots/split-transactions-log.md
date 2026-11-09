# designBOT ↔ engBOT · Splitting transactions

The shared log for the two bots (`.claude/agents/designBOT.md`,
`.claude/agents/engBOT.md`). Entries are only ever appended.

- **Figma:** iOS handoff file `ohcxhB9hV25H6nANVw3lq4`, page "Pearl app"
- **Jira:** thalloapp.atlassian.net, project THL (splitting: THL-291, THL-278, THL-124, THL-42, THL-181, THL-199, THL-260, THL-264)
- **Code:** `ios/Pearl/Views/Transactions/SplitFlow.swift`, `PartsFlow.swift`

## How the bots talk

1. **engBOT** reads Jira, the Figma frames and the code, then logs each functional problem as `SPLIT-NN` to designBOT.
2. **designBOT** replies to each issue, redesigns on the Pearl app page, and gives the node IDs (or disagrees, citing Jira).
3. **engBOT** checks the new frames and marks each issue `Accepted` or `Still blocked`.
4. The **product owner** picks which redesigns to build. engBOT builds them, comments on the Jira ticket and moves it to Testing.

## Issue tracker

| ID | Title | Severity | Jira | Status |
|----|-------|----------|------|--------|
| SPLIT-01 | Save before the split adds up: Jira and S-03b block it, the app allows it | Major | THL-291 | Decided (b′) 2026-11-09 · Built — PR #315, THL-291 in Testing |
| SPLIT-02 | Edit split after someone has paid, or removing someone who paid | Major | THL-291, THL-181 | Built — PR #315, THL-291/THL-181 in Testing |
| SPLIT-03 | S-33 Edit on a deposit in parts has no edit state and can't save | Major | THL-291, THL-289 | Built — PR #315, THL-291/THL-289 in Testing |
| SPLIT-04 | "What's the other $172?" is drawn three ways and leaves out Jira's kinds | Major | THL-291 | Built (S-11 v2, and S-11k for Other income, SPLIT-18) — PR #315, THL-291 in Testing |
| SPLIT-05 | S-22 / S-11 use Income/Not income tabs and Continue, against the sorting rules | Minor | THL-291, THL-254 | Decided (b) 2026-11-09 · Built (S-11 v2); S-22 v2 matches since round 8 (SPLIT-17) |
| SPLIT-06 | Split from Quick sort: held for the card (T-96) or saved at once (THL-278)? | Major | THL-278, THL-254 | Decided (a) 2026-11-09 · Built (T-98s) — PR #315, THL-278 in Testing |
| SPLIT-07 | S-23/S-24 split and link aren't one save; leaving halfway keeps the split | Major | THL-260, THL-264 | Built — PR #315, THL-260/THL-264 in Testing |
| SPLIT-08 | Splitting a purchase on a joint account: offered, then refused by the server | Major | THL-291, THL-282 | Built — PR #315, THL-282 in Testing |
| SPLIT-09 | S-12 Check and save doesn't show the effect on Allowance | Major | THL-289, THL-291 | Built — PR #315, THL-289/THL-291 in Testing |
| SPLIT-10 | Odd cents and uneven percents: no frame, and the preview disagrees with what's saved | Minor | THL-291 | Built — PR #315, THL-291 in Testing |
| SPLIT-11 | Cash or Another app for more than they owe, and cash only partly deposited | Minor | THL-291 | Built — PR #315 (round 9: "Next: the extra" opens S-11c, SPLIT-19), THL-291 in Testing |
| SPLIT-12 | Code is ahead of Figma: split screens with no frame, or that differ from it | Minor | THL-291 | Built — PR #315 (T-09r title; income list replaced by S-11 v2 tiles) |
| SPLIT-13 | Owed to you from a Home nudge: in Jira, no frame | Minor | THL-291 | Built — PR #315, THL-291 in Testing |
| SPLIT-14 | Another app has no field for which app | Minor | THL-291, THL-289 | Built — PR #315, THL-291 in Testing |
| SPLIT-15 | A partly deposited cash payment is listed twice | Minor | THL-291 | Built — PR #315, THL-291 in Testing |
| SPLIT-16 | Removing a person unlinks her whole payback, from other purchases too | Major | THL-291, THL-181, THL-289 | Built — PR #315, THL-291/THL-181 in Testing |
| SPLIT-17 | S-22 v2 brings back Split into parts (reverses aa07127) and turns Always off | Minor | THL-291, THL-254 | Accepted (round 9): Split into parts removed, aa07127 stands; Always on by default. S-22 v2 995:37522 / 1008:41353. App already matched; no code change |
| SPLIT-18 | Other income's follow-up (Interest, Government, Tax refund) has no frame | Minor | THL-291 | Accepted and built (round 9) — PR #315 (8176985): S-11k 1017:103 / 1017:419, T-08k 1017:715 / 1017:1013. THL-291 in Testing; THL-254 commented |
| SPLIT-19 | S-06 v2's extra has nowhere to go for cash or an app | Major | THL-291 | Accepted and built (round 9) — PR #315 (8176985): S-11c 1017:1309 / 1017:1607. THL-291 in Testing. List line "paid back Loblaws and Pizza Nova" not built yet |

## Conversation

### [engBOT] 2026-11-09 10:20 · round 1 start
I compared the split flows against Jira, Figma and the code. This round is an audit only: no code, Jira or Figma changes.
- **Jira:** THL-291 (build story, acceptance criteria), THL-289 (design brief, flows 1–7), THL-278, THL-124, THL-42, THL-181, THL-199, THL-260, THL-264, plus the `text ~ "split"` search (THL-282, THL-290, THL-298 and others, read by summary). All of them are in Testing.
- **Figma (Pearl app, section 536:14142 "Cash flow · Splits & paybacks · THL-289"):** S-02 536:14143, S-03 536:14362, S-03b 536:14538, S-04 536:14717, S-05 536:14816, S-06 536:14899, S-07 536:15089, S-08 536:15170, S-09 538:14642, S-10 538:14937, S-11 538:15192, S-11n 877:38651, S-12 538:15479, S-13 538:15730, S-14 538:15997, S-15 542:16060, S-16 542:16196, S-17 542:16329, S-18 542:16482, S-19 542:16623, S-20 542:17369, S-21 543:16404, S-22 543:16592, S-23 543:16831, S-24 543:17060, S-25 543:17196, S-26 543:17422, S-27 543:17648, S-28 543:19294, S-29 545:18508, S-30 545:18815, S-32 545:19014, S-33 545:19240, S-34 545:19355, S-35 545:19575, S-36 545:19799, S-36b 545:20089. Each has a dark twin. There is no S-01 or S-31. Related frames: T-39 523:14239, T-73 764:34004, T-96 893:35507 (note 972:36148), T-98 972:35460, T-99 972:35522.
- **Code:** `SplitFlow.swift`, `PartsFlow.swift`, `TransactionDetailView.swift` (Options, split card, parts, unlink), `AnswerSheet.swift`, `QuickSortView.swift`, `ReviewView.swift`. Server: `finance/api.py` (PUT/DELETE split, paybacks), `finance/parts_api.py`, `finance/parts.py`, `finance/splits.py`.
- **Churn:** at least 10 of the last 40 commits on main change how splitting works without a Figma update. They are 6aba3e5 (split with several people), c40006c (each person's choices moved into a tap), 452aaab (swipe to remove, save before it adds up, edit any time), c58e973 (Add someone goes straight to How to split), 549654c, afb83ee, aa07127 (Who paid you back? lists every share, no Split into parts on money in), 8edd375 and 2b9863c. Several of these are decisions dated 2026-11-08/09 in code comments that the frames don't show. That gap is behind SPLIT-01, SPLIT-12 and others below.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-01 · Save before the split adds up
**Severity:** Major
**Jira:** THL-291: "$85 split as You $30 / Priya $30 / Sam $20 blocks Save with "$5.00 left to assign"", and in Rules: "Save only when shares add up exactly." and ""I had some too" off = user's share $0."   **Figma:** S-03b 536:14538 (Save disabled, "$4.12 left to assign")   **Code:** `ios/Pearl/Views/Transactions/SplitFlow.swift:476-477` (Save is disabled only when `gapCents < 0`), `:438-446` ("$x isn’t anyone’s yet · it stays yours"); `finance/splits.py:103-106` ("Less is fine (2026-11-08)").
**Problem:** The app and server now let you save a split that doesn't add up, and the rest silently becomes your share (commit 452aaab). That goes against both the AC and S-03b. It also breaks the "I had some too" switch. Example: $84.12 Loblaws, "I had some too" off, Amounts, Sam $40.00. Save is enabled, and your share becomes $44.12 even though you said you had none of it.
**Ask:** Decide which rule stands. (a) Keep S-03b and the AC (Save blocked until it adds up), or (b) redraw S-03b for "save now, the rest stays yours" and get THL-291's AC changed. If (b), say what happens to the rest when "I had some too" is off: block, ask, or something else.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-02 · Edit split after someone has paid, or removing someone who paid
**Severity:** Major
**Jira:** THL-181: "For each person, "Paid back" and "Owes" add up to their share and agree with the repayments linked." THL-289 flow 7: "unlink or edit from either side".   **Figma:** S-05 536:14816 ("Edit split · You and Sam · evenly", but no frame for where it goes); S-19 542:16623 / S-20 542:17369 (someone part-paid or let go)   **Code:** `SplitFlow.swift:39-58` (opening it again turns % and Shares into Amounts), `:294-301` and `:324` (swipe to remove anyone, with no check); `finance/splits.py:211-233` (a payback whose person isn't in the split counts for "the first who still owes").
**Problem:** Edit split goes back into S-02/S-03 as if nobody had paid. Three cases go wrong:
1. Remove Priya, who paid $28.04 by e-Transfer. Her payback no longer matches a name, so the server credits it to Sam, and Sam shows as paid back.
2. Lower someone's share below what they've already paid. The extra disappears: Owes is $0 and the overpayment isn't recorded anywhere (it isn't "they overpaid").
3. Edit a split where someone was let go (S-20). Their let-go amount is overwritten.
Opening it again also loses the % or Shares the split was made with.
**Ask:** Draw Edit split for a split where people have paid or been let go:
- Can a person with a payback or cash be removed? If so, does it ask to unlink their payback first ("Priya paid $28.04 — unlink it?")?
- What happens when a share drops below what was paid?
- Does the split open in the mode it was saved in?

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-03 · S-33 Edit on a deposit in parts has no edit state and can't save
**Severity:** Major
**Jira:** THL-291: "Unlinking any part from either side restores both sides"; THL-289 flow 7: "unlink or edit from either side".   **Figma:** S-33 545:19240 (Options › Edit "Change amounts or purchases"), S-34 545:19355   **Code:** `TransactionDetailView.swift:1030-1036` (Edit opens `PartsSheet` from scratch); `PartsFlow.swift:652-673` (it loads only what's owed now, so the shares this deposit already paid are gone from the list); `finance/parts.py:137-138` ("This deposit is already in parts. Unlink them first.").
**Problem:** S-33's Edit has no frame for where it goes. As built, it opens an empty "Sort the $600". The purchases this deposit pays back no longer show as owed, so they can't be picked again, and Save fails with "already in parts". Edit is a dead end. The S-33 frame also lists only Flight $428 and Loblaws $64 under PAYS BACK for a "Payback + gift" $600. The $108 gift row is missing, so the parts shown don't add up to the deposit.
**Ask:** Either draw Edit (S-10/S-27 opened with the current parts filled in and removable, the purchases they pay still listed, and Save replacing them), or drop Edit and keep Unlink as the only way. Add the gift row to S-33 so the parts add up to $600.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-04 · "What's the other $172?" is drawn three ways and leaves out Jira's kinds
**Severity:** Major
**Jira:** THL-291 Rules: "Each part has an amount and a kind: payback …, gift …, income (any of the 7 kinds), between my accounts, savings, refund (linked to a purchase), any category, or "they overpaid"". AC: "The same $172 can be split into two parts (e.g. $100 gift + $72 they overpaid), and "they overpaid" shows $72 under You owe."   **Figma:** S-11 538:15192 (Income tab: 7 income tiles), S-11n 877:38651 (Not income tab: Paid back, Refund, My own money, Loan, Not mine), S-36b 545:20089 (a list: A gift / Pays back something else / Sam overpaid / Money I earned), S-27 543:17648   **Code:** `PartsFlow.swift:393-407` (a list: gift, payback, overpaid, income, moved, refund), `:451` (6 income kinds).
**Problem:**
- The same question has three designs: income tiles, not-income tiles, and a list.
- For an ordinary rest (not an "extra"), the tiles have no "They overpaid", "Savings" or "a spending category". So the AC's "$100 gift + $72 they overpaid" can't be reached in S-11/S-11n. Only S-36b has "overpaid", and that's only for an extra.
- S-11n offers Loan and Not mine for part of a deposit, which Jira doesn't list. What does "Not mine" mean for $72 of Dad's $600?
- The code follows none of these exactly.
**Ask:** One design for "What's the other $x?" (plain rest and extra), covering Jira's list (including they overpaid, savings and a category) or saying which kinds are dropped and why. Say what Loan and Not mine do as a part, or remove them.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-05 · S-22 / S-11 use Income/Not income tabs and Continue, against the sorting rules
**Severity:** Minor
**Jira:** THL-291 ("income (any of the 7 kinds)"); the product owner's sorting rules (2026-11-07): tiles answer at once, "with no tabs, Save or Continue"; income tiles are "My pay, Bonus, A gift, Other income"; every answer lives on the one What was this? page (Outcome table 349:9375).   **Figma:** S-22 543:16592 (tabs + Continue), S-11 538:15192 / S-11n 877:38651 (tabs + Review, 7 income tiles)   **Code:** `AnswerSheet.swift:470-474` (Paid back on the shared page opens `PartsSheet`), `PartsFlow.swift:453-469`.
**Problem:** The split frames still use the older tabs-and-Continue pattern and seven income tiles. The shared What was this? page has since moved to tiles that answer at once, with four income tiles. If I build S-22 and S-11 as drawn, the app gets a second What was this? page that behaves differently.
**Ask:** Redraw S-22 and S-11/S-11n on the current What was this? page (tiles answer at once, four income tiles), or say why splits are an exception. Jira's "7 kinds" and the four-tile rule also need to be reconciled.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-06 · Split from Quick sort: held for the card (T-96) or saved at once (THL-278)?
**Severity:** Major
**Jira:** THL-278: ""Who was it with?" is the card's next step … Save shows the Sorted card with Next. The category is settled, so the transaction leaves Needs a look. Undo restores the split, the share and the category."   **Figma:** T-96 893:35507 and note 972:36148: "tapping a card opens its page with no Yes. Category, piggy bank, split, Exclude, Always and Regular bill are held for the card."; T-98 972:35460 (only shows a held category, "YOUR CHOICE")   **Code:** `TransactionDetailView.swift:430-434` and `AnswerSheet.swift:176-181` both save the split at once through `SplitFlow.swift:500` (`PUT api/transactions/<id>/split`). Nothing is held.
**Problem:** The two sources disagree. T-96 says a split is held until Yes on the card; THL-278 says it saves and shows the Sorted card. No frame shows a Quick sort card asking about a held split, e.g. "Split with Sam · your share $42.06 — Yes?". As built, a split from a Quick sort card's page saves straight away, skipping the card.
**Ask:** Decide held or immediate for a split from Quick sort. If held, draw the T-98 card state for a split (what it says, what Yes and Skip do). If immediate, update the T-96 note.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-07 · S-23/S-24 split and link aren't one save; leaving halfway keeps the split
**Severity:** Major
**Jira:** THL-260: "Picking an unmarked purchase marks it … and links the payback in the same save" and "One Undo reverses both the mark and the link."   **Figma:** S-23 543:16831 → S-24 543:17060 ("Dad’s share", "Split and link") → S-10/S-12   **Code:** `PartsFlow.swift:153-157` and `:324-332` (Split and link saves the split at once, then adds the payback part only inside the sheet); `SplitFlow.swift:500`; `finance/parts_api.py:164` (the parts save's undo covers only the parts).
**Problem:** "Split and link" saves the Costco split right away. The link waits for the deposit's own Save two or three steps later. If she closes the sheet in between (X, swipe down) or the save fails, Costco stays split with "Dad owes you $106.20", and the $600 deposit is still unsorted. Undo on the Sorted card reverses the parts but not the split. Neither THL-260 rule holds.
**Ask:** Say what leaving the flow after S-24 does (discard the split? ask "Keep Costco split with Dad?"?). Make sure the Sorted card's Undo copy covers both the split and the link.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-08 · Splitting a purchase on a joint account: offered, then refused by the server
**Severity:** Major
**Jira:** THL-291 (no rule for joint accounts); THL-282 / THL-172: a joint charge is split with "Whose was it?".   **Figma:** S-02 536:14143 shows "Sam · Joint account" as a person to split with; there is no frame for a split on a joint-account purchase (joint section 812:32107 doesn't cover it either)   **Code:** `finance/api.py:459-460` ("On a joint account, say whose it was instead." → 400); `TransactionDetailView.swift:978-980` and `AnswerSheet.swift:244` (`canSplit` doesn't check the account, so Split with others is offered).
**Problem:** On a joint-account purchase, she can go through Who was it with? and How to split, then gets an error at Save. S-02 implies you'd split with your joint partner, but the server says to use "Whose was it?" instead. Splitting your own half of a joint purchase with a friend (e.g. a $90 dinner on the joint card, your $45 split with Priya) has no design at all.
**Ask:** For a joint-account purchase, decide whether to hide Split with others, show why it isn't available, or design a split of "your share". Say what the "Joint account" label on S-02 means.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-09 · S-12 Check and save doesn't show the effect on Allowance
**Severity:** Major
**Jira:** THL-289 flow 4: "A review step shows the equation and how safe-to-spend changes, then Save." THL-291 AC: "choosing Gift raises safe to spend by $172 and shows the Gift income kind; the flight's Travel spend drops by $428." (Allowance, per the house rule.)   **Figma:** S-12 538:15479 (two rows only: Payback · Flight to Athens $428.00, Gift +$172.00)   **Code:** `PartsFlow.swift:488-524` (an undesigned "Leftover this month · Was $x" row).
**Problem:** S-12 has no effect line, so I can't show what Jira asks for. The code invented a "Leftover this month" row. It isn't designed, isn't called Allowance, and adds the $428 payback to November's leftover even though the flight it pays back is from Sep 28.
**Ask:** Draw the effect on S-12, named Allowance, and say which month each part lands in. A payback for an earlier month's purchase: does it lower that month's Travel or this month's? The gift goes to the deposit's month.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-10 · Odd cents and uneven percents: no frame, and the preview disagrees with what's saved
**Severity:** Minor
**Jira:** THL-291: "Evenly (odd cent to the user)"; AC: "Evenly gives $28.34 / $28.33 / $28.33 with the extra cent on the user."   **Figma:** S-03 536:14362 ($42.06 × 2) and S-18 542:16482 ($28.04 × 3) both divide exactly; S-15 542:16060 shows only 50/50   **Code:** `SplitFlow.swift:394-400` and `:402-415` (all odd cents go to the first row); `finance/splits.py:126-128` (with you left out, one cent each to the first people); `SplitFlow.swift:438-442`.
**Problem:**
- No frame shows an odd cent, and Jira doesn't say who gets it when "I had some too" is off.
- The app and server then disagree: $10.03 among 4 people without you previews as $2.53 / $2.50 / $2.50 / $2.50 but saves as $2.51 / $2.51 / $2.51 / $2.50.
- In %, thirds (33.33 × 3) leave "0.01% isn’t anyone’s yet", which reads as an error.
**Ask:**
- Draw an Evenly frame with an odd cent (e.g. the AC's $85 three ways).
- State the rule when you're not included.
- Say how % handles thirds: round the last person, or allow 33.34.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-11 · Cash or Another app for more than they owe, and cash only partly deposited
**Severity:** Minor
**Jira:** THL-291 Cash in hand: "A later cash deposit asks "Is this cash you were already paid?" and links recorded cash as Moving money (never counted twice)"; THL-289 flow 5: "Bank deposit / e-Transfer (find it), Cash in hand, Another app."   **Figma:** S-06 536:14899 (Amount is editable), S-13 538:15730, S-36 545:19799 (extra, bank only)   **Code:** `SplitFlow.swift:904-910` (Cash and Another app both post to `split/cash`); `finance/parts_api.py:104-118` (no limit against what's owed); `PartsFlow.swift:591-596` (the cash part is capped at the deposit, but every ticked cash record is attached).
**Problem:**
- Sam owes $42.06 and she marks $60 cash. Sam shows paid, and the $17.94 extra vanishes; S-36's "Sam sent extra" exists only for bank deposits.
- "Another app" has no defined outcome. Built as cash, a PayPal payment shows "Cash" on S-05 and is offered later in "Is this cash you were paid?".
- She marked $250 cash and deposits $200. S-13 doesn't say what happens to the $50 that wasn't deposited.
**Ask:** Draw or state:
- cash or app paid above what's owed (reuse S-36's extra?);
- how Another app is labelled and whether it's ever matched to a deposit;
- cash only partly deposited.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-12 · Code is ahead of Figma: split screens with no frame, or that differ from it
**Severity:** Minor
**Jira:** THL-291: "Light and dark match the frames". House rule: don't build screens with no Figma design.   **Figma:** S-04 536:14717 (Mark paid back / Remind Sam / Let it go as rows), S-17 542:16329, S-20 542:17369   **Code:** `SplitFlow.swift:534-570` (choices in a dialog when you tap the person, c40006c); `:955-995` (swipe to remove, 452aaab); `:96-107` (Add someone ticks several people, "ADDING", 6aba3e5); `PartsFlow.swift:179` ("What did it refund?" step), `:453-469` ("What kind of income?" list); `SplitFlow.swift:560-561` ("Undo let it go" in the dialog, vs the S-20 toast).
**Problem:** These are already in the app with no frame, or differ from the frame. I can't tell whether they're accepted, and a later "match the frames" pass would undo them.
**Ask:** For each one, update the frame (light and dark) or tell me to revert to the frame.

### [engBOT → designBOT] 2026-11-09 10:20 · SPLIT-13 · Owed to you from a Home nudge: in Jira, no frame
**Severity:** Minor
**Jira:** THL-291 Owed to you: "Opened from the Moving money breakdown and the Home owes-you nudge."   **Figma:** S-14 538:15997; Home H-00 752:33773 has no owes-you nudge   **Code:** `TransactionsView.swift:600-608` and `SplitFlow.swift:571` (the only ways in); `HomeView.swift` has none.
**Problem:** The Home way into Owed to you is required by Jira but isn't drawn, so it isn't built.
**Ask:** Draw the Home owes-you nudge (when it shows, what it says, where it goes), or get it dropped from THL-291.

### [designBOT] 2026-11-09 14:30 · round 2 start
I replied to all 13 issues. The new frames are on Pearl app in section 536:14142. They sit in a new column to the right of S-11n (x ≥ 17581), under the header 994:36735. No old frame was changed. Each frame has a ticket tag (screen code and every Jira ticket) and a note under it that spells out the behaviour. **All of them are light only (no dark twins yet), and every one is Awaiting product owner.** Don't build any of them until the product owner picks. Three issues need the product owner to decide: SPLIT-01, SPLIT-05 and SPLIT-06. SPLIT-04 depends on SPLIT-05.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-01 · Save before the split adds up
**Status:** Needs product owner
**Jira:** THL-291, THL-289   **Figma:** S-03b v2 994:36736 (recommended option); option (a) is the existing S-03b 536:14538
THL-291 and S-03b block Save, but commit 452aaab allows it on purpose. I'm not picking a side; the product owner decides.
- **(a) Block Save until it adds up exactly.** This is THL-291 and S-03b as drawn. It's strict, and it makes her type every cent.
- **(b′) Recommended: the rest stays yours, but only when you're part of the split.** With "I had some too" on, Save is enabled and your row shows it before saving ("Your share $44.12 · $4.12 of it is the rest"). The status reads "$4.12 isn’t anyone’s yet · it stays yours" in ink, not red. "That’s $x too much" still blocks. With "I had some too" off there's no "you" to keep the rest, so S-03b stays as drawn: Save disabled and "$4.12 left to assign". That fixes the $44.12 bug in your example. The server has to block the not-included case as well.
If (b′) is picked, THL-291's "Save only when shares add up exactly" needs rewording.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-02 · Edit split after someone has paid
**Status:** Redesigned
**Jira:** THL-291, THL-181, THL-289 flow 7   **Figma:** S-03e 994:36904, S-03f 994:37078 · Awaiting product owner
- **S-03e (Edit split):** opens in the mode it was saved in, with the same numbers (not converted to Amounts). Each person with money against them shows it under their name: "Paid $28.04", "Paid $20.00 cash · let go $8.04".
- **Share lowered below what was paid:** the field and caption turn red ("$8.04 more than this share"). Save stays enabled, and the difference becomes "they overpaid" under You owe (THL-291 kind). The status line says "you’ll owe her $8.04".
- **Let go:** stored as share − paid. Raising the share raises the let go; lowering it below what was paid turns it into overpaid. Nothing is overwritten.
- **S-03f (removing someone with a payback):** the swipe asks "Remove Priya?" with "Unlink and remove" or "Keep Priya". Unlinking sends the e-Transfer back to Needs a look. For cash or another app, the record is deleted with the person (same alert, different copy). Someone with only a let go is removed with no question.
- **Server:** a payback is never re-credited to "the first who still owes". `splits.py:211-233` has to stop doing that; a payback always belongs to its own person.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-03 · Edit on a deposit in parts
**Status:** Redesigned
**Jira:** THL-291, THL-289 flow 7   **Figma:** S-33 v2 995:36892, S-10e 995:37021 · Awaiting product owner
- **S-33 v2:** the caption is now PARTS and lists every part: Flight $428 + Loblaws $64 + "A gift · Income · Gift +$108.00" = $600. Edit's subtitle is "Change the parts or what they pay back".
- **Edit:** opens S-10e "Edit the $600" with the current parts filled in.
- **Removing a part:** swipe to remove. The amount goes back to Left to sort, and Sort the rest opens S-11 v2.
- **Paybacks already linked:** the purchases this deposit already pays back stay listed (ticked) in "What did this pay back?".
- **Saving:** Save changes replaces all parts in one save (the server should replace, not reject with "already in parts"). Cancel leaves everything as it was.
- Unlink (S-34) stays the way to undo everything.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-04 · One "What's the other $x?"
**Status:** Redesigned (depends on SPLIT-05)
**Jira:** THL-291 Rules and AC, THL-254   **Figma:** S-11 v2 995:37232 · Awaiting product owner
There's now one design for the rest and for an extra: the shared What was this? page (T-08), titled "What’s the other $172?" or "What’s the extra $17.94?". At the top is a "How much of it?" row (all $172 unless she types less). Tiles answer at once for that amount. If anything is left, the page comes back for the new rest; otherwise it goes to Check and save. "Sort the rest later" is under Options.
**How Jira's kinds map to tiles:**
- gift → A gift
- income → My pay, Bonus or Other income (Other income asks which kind)
- payback → Paying me back
- refund → Money back (opens T-09r)
- between my accounts → My own money
- savings → Out of savings
- any category → **Off a category** (new tile, opens the category list)
- they overpaid → **Dad overpaid** (new tile, shows under You owe)
**Kept and dropped:**
- Lent me this stays: a loan from the sender (THL-128).
- **Not mine is dropped for parts.** On money that landed in her account, a "not mine" part means "they overpaid / I'll pass it on", and Dad overpaid now covers that.
This page replaces S-11, S-11n, S-27's kind step, S-36b and the code's kinds list. The AC's "$100 gift + $72 they overpaid" is two passes: How much $100 → A gift, then $72 → Dad overpaid.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-05 · Tabs and Continue on S-22 / S-11
**Status:** Needs product owner
**Jira:** THL-291 ("7 kinds"), THL-254 and the sorting rules (tiles answer at once, four income tiles, one What was this? page)   **Figma:** S-22 v2 995:37522 and S-11 v2 995:37232 (the recommended option)
THL-291 says "income (any of the 7 kinds)" and S-22/S-11 use tabs and Continue. The product owner's later rules (2026-11-07) say four income tiles that answer at once.
- **(a) Splits are an exception.** Keep the tabs, Continue and 7 income tiles on S-22/S-11. That means a second What was this? page that behaves differently.
- **(b) Recommended: splits use the shared page.**
  - S-22 v2 is T-08 for Dad's $600: Paying me back opens S-09, Split into parts opens S-10. "Always for Dad" is off by default.
  - S-11 v2 as in SPLIT-04.
  - The 7 kinds still exist: My pay, Bonus and A gift are tiles, and Other income asks for the rest (interest, government, tax refund, other).
  - THL-291's "7 kinds" wording would change to "any income kind".

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-06 · Split from Quick sort: held or saved at once
**Status:** Needs product owner
**Jira:** THL-278, THL-254   **Figma:** T-98s 998:37418 (recommended option); T-96 893:35507, note 972:36148
- **(a) Recommended: held for the card, as the T-96 note says.**
  - Back on the card, YOUR CHOICE reads "Groceries, split with Sam?" with "Your share $42.06 · Sam owes you $42.06".
  - Yes saves the split and the category in one go and shows the Sorted card with Undo. That Undo restores the split, the share and the category (THL-278).
  - Skip drops the held split.
  - This keeps "nothing saves until Yes" true for everything on a card's page.
- **(b) Immediate, as built.** The split saves from the page. Then the T-96 note drops "split", and the card should come back already sorted.
I don't think THL-278 and T-96 really disagree about when Save happens: THL-278 describes splitting from the card itself.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-07 · Split and link as one save
**Status:** Redesigned
**Jira:** THL-260, THL-264, THL-291   **Figma:** S-24x 998:37484, S-12c 998:37605, S-12d 998:37799 · Awaiting product owner
- **Held, not saved:** "Split and link" (S-24) no longer saves. Dad's share of Costco is held with the deposit's parts.
- **S-12c (Check and save):** shows it as "Splits Costco · Dad’s share $106.20", with the note "Saving splits Costco with Dad and links this payback in one go. One Undo puts both back." One request.
- **S-24x (leaving halfway):** X, swipe down or Back after S-24 asks "Leave without saving?" with Keep sorting or Leave. Leave drops the held split and the link.
- **Failed save:** nothing is split or linked, and the sheet stays open with the error.
- **S-12d (after saving):** the toast reads "Costco split and $600 sorted · Undo". That Undo reverses the parts, the link and the Costco split. The server's parts undo needs to include the split.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-08 · Joint-account purchase
**Status:** Redesigned
**Jira:** THL-282, THL-172, THL-291   **Figma:** S-01j 998:37841, S-02 v2 998:38004 · Awaiting product owner
- **S-01j:** on a joint-account purchase, the Options row is **Whose was it?** ("Joint with Sam · yours, Sam’s or shared", the existing joint flow in 812:32107). Split with others is hidden, so `canSplit` should check the account. This matches the server's "say whose it was instead".
- **S-02 v2:** the "Joint account" label under Sam is gone. It suggested you split with your joint partner. People on S-02 are just names.
- **Not designed:** splitting your own half of a joint purchase with a friend. It needs a server change, so it's for the product owner to add if wanted.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-09 · Effect on Allowance in Check and save
**Status:** Redesigned
**Jira:** THL-289 flow 4, THL-291 AC   **Figma:** S-12 v2 999:37852 · Awaiting product owner
There's a new WHAT CHANGES card under the parts, named Allowance, with one row per month affected:
- **Payback:** lowers the purchase it pays back, in that purchase's month. Example: "Travel · September $856 → $428" (the payback row reads "Payback · Flight, Sep 28"). A payback is never income, so it doesn't raise this month's Allowance. If the purchase is from this month, the row reads "Travel · November …" and this month's Allowance changes.
- **Gift, income and overpaid:** land in the deposit's month: "Allowance · November +$172.00".
This replaces the code's "Leftover this month" row. The month rule follows THL-291's payback rule; if the product owner would rather the payback land in the month it arrives, only that row's label changes.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-10 · Odd cents and thirds
**Status:** Redesigned
**Jira:** THL-291 (Evenly, AC $85)   **Figma:** S-18 v2 999:38055, S-15 v2 999:38228 · Awaiting product owner
- **S-18 v2:** $85 three ways is $28.34 / $28.33 / $28.33, with "Includes the odd cent" under You.
- **Rule, for preview and save:** divide the total and round down. Leftover cents go to you when "I had some too" is on; otherwise one cent each from the top of the list ($10.03 four ways without you is $2.51 / $2.51 / $2.51 / $2.50, the same as the server). The app preview's "all odd cents to the first row" changes to match. Shares and Split the rest evenly use the same rule.
- **S-15 v2 (%):** % works in cents. A shortfall smaller than one cent per person is rounding, not a gap. So 33.33% × 3 shows "Adds up to $85.00 ✓", with dollars under each row and the odd cent placed by the same rule. "0.01% isn’t anyone’s yet" never shows, and 33.34 is still allowed. A real % gap follows whatever SPLIT-01 decides.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-11 · Cash or another app above what's owed, and cash partly deposited
**Status:** Redesigned
**Jira:** THL-291 Cash in hand, THL-289 flow 5   **Figma:** S-06 v2 999:38403, S-13 v2 999:38554 · Awaiting product owner
- **S-06 v2 (paid more than owed):** an amount above what's owed shows "That’s $17.94 more than Sam owes…", and the button becomes "Next: the extra $17.94". It opens the same What's the extra page as a bank deposit (S-11 v2), so it can become "Sam overpaid" (You owe Sam $17.94).
- **Another app:** recorded like cash, with no bank transaction. It's labelled with the app ("Paid back · PayPal Nov 13" on S-05) and is **never** offered in "Is this cash you were paid?". Moving money from the app to her bank later counts as her own money.
- **S-13 v2 (cash partly deposited):** a $200 deposit against $250 cash takes "$200.00 of $250.00". The other $50 stays as cash in hand: Priya is still paid back, and the $50 can match a later deposit. When several records are ticked, they fill from the top until the deposit is used up.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-12 · Code ahead of Figma
**Status:** Redesigned (most accepted as built, two flagged)
**Jira:** THL-291   **Figma:** S-04 v2 1001:38264, S-17 v2 1001:38361, S-03f 994:37078 · Awaiting product owner
- **Choices in a dialog when you tap a person (c40006c): accepted.** S-04 v2 shows the person rows, Edit split at the bottom of the card, and an action sheet: "Sam · Owes you $42.06" with Mark paid back, Remind Sam, Let it go and Cancel.
- **"Undo let it go" in the dialog: accepted.** The S-20 toast still shows right after Let it go.
- **Swipe to remove (452aaab): accepted.** It needs the guard in S-03f (SPLIT-02) for people who have paid.
- **Add someone ticks several people, with ADDING (6aba3e5, c58e973): accepted.** S-17 v2: ADDING shows typed names, contacts tick in place, the button reads "Add 2 people", and it goes straight to How to split.
- **"What kind of income?" list (6 kinds): flagged as wrong.** It's a second income picker; use S-11 v2's tiles (Other income asks the kind).
- **"What did it refund?" step: accepted with a title fix.** It should be the shared T-09r "What was this a refund for?", not a separately worded step.
- Dark twins of these frames aren't drawn yet.

### [designBOT → engBOT] 2026-11-09 14:30 · SPLIT-13 · Home owes-you nudge
**Status:** Redesigned
**Jira:** THL-291 Owed to you, THL-125   **Figma:** H-00n 1001:38563 · Awaiting product owner
- **Placement and copy:** a Home card under Needs a look, in the same style as the other Home cards: "Sam and Priya owe you $70.10, from 2 splits. The oldest is from Nov 1." followed by "See who owes you ›", which opens Owed to you (S-14).
- **When it shows:** someone owes her and the oldest share is at least 7 days old, so a split made today doesn't nag.
- **Names:** up to two, then "and N others".
- **When it goes:** it disappears when nothing is owed. There's no dismiss, like the Needs a look card.

### [engBOT] 2026-11-09 16:10 · round 3 start
I checked every Redesigned frame on Pearl app (section 536:14142, column under 994:36735) with get_screenshot on the node IDs designBOT gave; no page-wide metadata. The product owner said "run all rounds without stopping", so round 4 builds what's Accepted below, except SPLIT-04, which waits on SPLIT-05. SPLIT-01, SPLIT-05 and SPLIT-06 wait on the product owner, and I won't build them. Every new frame is light only. I'm building to the existing theme tokens, so dark mode follows them. The dark twins are still owed (THL-291 "Light and dark match the frames"), but they don't block functionality.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-01 · Waiting on product owner
No build. Save stays as it is now (allowed while short, blocked when too much) until the product owner picks (a) or (b′).

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-02 · Accepted
**Figma:** S-03e 994:36904, S-03f 994:37078
- S-03e works: it opens in the saved mode, and the money already paid sits under each name.
- A share lowered below what was paid turns red and becomes "they overpaid" under You owe. The numbers add up: You $36.08 + Sam $28.04 + Priya $20.00 = $84.12, with Priya paid $28.04, so she's $8.04 over.
- Let go = share − paid, with no overwrite.
- S-03f asks before a payer is removed. Unlinking puts the e-Transfer back in Needs a look.
- Server needs: store % / Shares weights, so a split reopens in its mode; never credit a stated payer's payback to someone else; on edit, unlink removed people's paybacks and delete their cash; keep let go as share − paid.
- I keep the 2026-10-24 rule only for a payback with no name at all. It has no "own person", so it still goes to whoever owes exactly that much.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-03 · Accepted
**Figma:** S-33 v2 995:36892, S-10e 995:37021
- The parts add up ($428 + $64 + $108 = $600). Edit opens with the current parts, Save changes replaces them in one save, and Cancel leaves everything as it was.
- One gap I'm filling with existing UI, not new UI: S-10e doesn't draw what shows after a part is swiped away. I'm using S-10's existing "Left to sort" row and "Sort the rest" button. Until SPLIT-04/05 is picked, Sort the rest goes to the kinds step that's built now, not S-11 v2.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-04 · Accepted (not built: depends on SPLIT-05)
**Figma:** S-11 v2 995:37232
- One page covers the rest and the extra. Every Jira kind has a tile, including Dad overpaid, Out of savings and Off a category. "How much of it?" makes the AC's $100 + $72 two passes. Dropping Not mine for parts makes sense.
- I'll build it when the product owner picks SPLIT-05 (b).

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-05 · Waiting on product owner
No build.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-06 · Waiting on product owner
No build. A split from a Quick sort card's page still saves at once.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-07 · Accepted
**Figma:** S-24x 998:37484, S-12c 998:37605, S-12d 998:37799
- The held split, one request, "Leave without saving?" and the toast whose Undo reverses parts, link and split all work.
- S-12c has no WHAT CHANGES card, and S-12 v2 (SPLIT-09) does. I'm treating S-12 v2's card as part of every Check and save, so S-12c gets it too. Please add it to the frame.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-08 · Accepted
**Figma:** S-01j 998:37841, S-02 v2 998:38004
- On a joint purchase, Split with others is hidden. Whose was it? moves into Options with "Joint with Sam · yours, Sam’s or shared".
- The "Joint account" label is gone from S-02. Splitting your own half isn't designed, so it isn't built.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-09 · Accepted
**Figma:** S-12 v2 999:37852
- WHAT CHANGES: "Allowance · November +$172.00" for gift, income and overpaid, plus a category row in the purchase's month ("Travel · September $856 → $428").
- The server works these out without saving, so the numbers match what Save will do.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-10 · Accepted
**Figma:** S-18 v2 999:38055, S-15 v2 999:38228
- One rule for preview and save. A shortfall under one cent per person is rounding. "Includes the odd cent" and "the odd cent is yours" go under You.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-11 · Accepted (built in part)
**Figma:** S-06 v2 999:38403, S-13 v2 999:38554
- Another app is recorded like cash, and is never offered in "Is this cash you were paid?".
- Cash partly deposited works: records fill from the top, and the remainder stays cash in hand.
- **Not built:** S-06 v2's "Next: the extra $17.94". It opens S-11 v2, which waits on SPLIT-04/05.
- **New gap:** S-06 v2 has no way to say which app, so "Paid back · PayPal Nov 13" can't be shown. Logged as SPLIT-14.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-12 · Accepted
**Figma:** S-04 v2 1001:38264, S-17 v2 1001:38361
- The as-built behaviours match the frames: a person's choices in an action sheet, Undo let it go in the dialog, ADDING / "Add 2 people", and swipe to remove. Swipe now has the S-03f guard.
- Building the refund title fix ("What was this a refund for?", T-09r).
- The "What kind of income?" list stays until S-11 v2 (SPLIT-04/05) replaces it. Swapping it for tiles now would be the second income picker designBOT wants gone.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-13 · Accepted
**Figma:** H-00n 1001:38563
- The card shows when the oldest open share is at least 7 days old. It names up to two people, then "and N others", and "See who owes you ›" opens Owed to you. It has no dismiss.

### [engBOT → designBOT] 2026-11-09 16:10 · SPLIT-14 · Another app has no field for which app
**Severity:** Minor
**Jira:** THL-289 flow 5 ("Another app"); designBOT's SPLIT-11 reply ("labelled with the app: Paid back · PayPal Nov 13")   **Figma:** S-06 v2 999:38403 (Another app ticked: only Amount and When)   **Code:** `ios/Pearl/Views/Transactions/SplitFlow.swift` MarkPaidSheet form
**Problem:** The label needs the app's name, but S-06 v2 never asks for it. Until it does, an app payment reads "Paid back · Nov 13" on S-05, the same as a bank payback, and no longer "Cash".
**Ask:** Add the app choice to S-06 for Another app (a picker of PayPal / Wise / Apple Cash / Other, or a typed name), or drop the app name from the label.

### [engBOT] 2026-11-09 17:40 · round 4 · build
Branch `feat/split-bot-round` from main. PR https://github.com/mariapapadimitriou/finance/pull/315 is open and not merged.
- **e0da5fa** (iOS: SplitFlow, PartsFlow, TransactionDetailView, AnswerSheet, HomeView, Models): SPLIT-02 S-03e/S-03f; SPLIT-03 S-33 v2/S-10e; SPLIT-07 S-24x/S-12c/S-12d; SPLIT-08 S-01j; SPLIT-09 S-12 v2 WHAT CHANGES; SPLIT-10 odd-cent rule; SPLIT-11 S-13 v2 and Another app; SPLIT-12 T-09r title; SPLIT-13 H-00n. No .swift files added, so no make_project.
- **572b6b6** (server):
  - splits.py: a stated payer is never re-credited; adds over / weight / app; edit unlinks removed people's paybacks and cash; let go = share − paid; the % rounding rule.
  - store.py: `weight` and `via` columns.
  - parts.py / parts_api.py / api.py: replace on save, `owing.linked`, `split` in the parts save with one Undo, `parts/preview`, partly deposited cash, app never in cash-matches.
- **Tests:**
  - `python3 -m pytest -q`: 1728 passed. The split files (test_splits, test_parts, test_paybacks, test_payback_many, test_split_round) give 68 passed.
  - New: tests/test_split_round.py (17 tests). test_splits.py exact-match checks gained the new keys.
- **iOS build:** `xcodebuild … -destination 'generic/platform=iOS Simulator' build` gave BUILD SUCCEEDED. Not run by hand in a simulator.
- **Behaviour to know:**
  - A partial deposit turns one cash record into two. They stay two after Unlink; the totals are unchanged.
  - A payback covering several purchases is fully unlinked if its person is removed from the purchase it paid first.
  - Swipe-down can't drop a held split: it's disabled while one is held, and X asks first.
- **Jira:** all six tickets were already in Testing, so I commented and moved none.
  - Comments on THL-291, THL-181, THL-260, THL-264, THL-282 and THL-289.
  - THL-291 stays in Testing with open issues: SPLIT-01, 04, 05, 06 and 14.
- **Not built:** SPLIT-01, 05 and 06 (product owner); SPLIT-04 (waits on SPLIT-05); S-06 v2's "Next: the extra" (needs S-11 v2); SPLIT-14 (designBOT).

### [designBOT] 2026-11-09 19:00 · round 5 start
This round covers SPLIT-14, the missing WHAT CHANGES card on S-12c, dark twins for every frame from round 2 and this round, and the two server side effects engBOT noted in round 4. Everything is on Pearl app in section 536:14142. The section is now 28460 × 2270 so the new rows fit. No old frame was redrawn.
- **Dark twins:** each light frame in the round-2 column now has a twin below it at y = 1340, named "<frame> · Dark". They're built the same way as the existing twins: the frame's explicit mode on the colour collection is switched from 2:1 to 2:2, so every bound colour flips. Raw paints are copied from the matching paints on the existing twins (S-06 Dark 536:16064 for the background, auras, scrim and sheet). The nacre band and band fade are removed from sheets, as on the old twins. A few hand-set paints had no existing twin to copy from (alert and action-sheet panels, T-98s card, H-00n links). Those use the dark sheet navy and light ink. Each twin has its own ticket tag under it, ending in "· Dark".
- **Not done:** nothing from the list is left out. I didn't draw new frames for the two server side effects (see the SPLIT-15/16 entry below); they're copy and behaviour on frames that already exist.

### [designBOT → engBOT] 2026-11-09 19:00 · SPLIT-14 · Another app: which app
**Status:** Redesigned
**Jira:** THL-291, THL-289 flow 5   **Figma:** S-06 v3 1004:38392 (app named, with apps she's used before), S-06 v3a 1004:38576 (first time); dark 1008:40584, 1008:40744
- **App row:** ticking Another app adds an **App** row at the top of the Amount / When card. Bank deposit and Cash in hand don't show it. The Another app choice's description now reads "Pearl won’t look for it in your bank", which is the SPLIT-11 rule.
- **A typed name, not a fixed list.** A curated list (PayPal / Venmo / Wise / Apple Cash…) depends on the region: Venmo and Apple Cash don't exist in Canada, where Pearl's users bank. It also goes stale, and it's a hard-coded list of brands, which is the thing the house rules keep out of the app. A plain text field covers every app, with no brand names hard-coded.
- **"Used before" chips:** under the card, as one-tap chips, are the app names she has typed before (her own data, newest first, up to 4). The second time is one tap. They're hidden when she hasn't named any yet (S-06 v3a).
- **Optional:** Mark paid back works with the App field blank. Placeholder: "Which app?". Blank falls back to "Paid back · Another app · Nov 13". The name is a label only, so it shouldn't block saving.
- **Label:** saved with the payback (the `via` column already added in 572b6b6 can hold it). S-05, S-04 v2 and Owed to you read "Paid back · PayPal · Nov 13". Trim the name, cap it at 30 characters, and match "paypal" and "PayPal" without regard to case for the chips. Like Cash, it's never offered in "Is this cash you were paid?".
- S-06 v3 supersedes the form part of S-06 v2. The "more than owed → Next: the extra" behaviour from S-06 v2 is unchanged and still waits on SPLIT-04/05.
This completes S-06 v2, which you already accepted, so I'm sending it straight to you. The product owner can still change it.

### [designBOT → engBOT] 2026-11-09 19:00 · SPLIT-07 / SPLIT-09 · WHAT CHANGES on S-12c
**Status:** Redesigned
**Jira:** THL-260, THL-289 flow 4, THL-291   **Figma:** S-12c 998:37605 (added: caption 1004:38752, card 1004:38754); dark 1007:39514
The card is the same as on S-12 v2, using S-12c's numbers:
- **Allowance · November +$493.80:** the gift lands in the deposit's month.
- **Shopping · October $212.40 → $106.20:** Dad's share comes off Costco's own month and category (Sat, Oct 11, Shopping). That's the same month rule as the payback row on S-12 v2.
The card sits between the parts and the "Saving splits Costco…" note, and the sheet grew to fit. The S-12c note says what was added.

### [designBOT → engBOT] 2026-11-09 19:00 · Dark twins · round-2 and round-5 frames
**Status:** Redesigned
**Jira:** THL-291 ("Light and dark match the frames")   **Figma (light → dark):**
- S-03b v2 994:36736 → 1008:40898
- S-03e 994:36904 → 1007:38831
- S-03f 994:37078 → 1007:38650
- S-33 v2 995:36892 → 1007:39004
- S-10e 995:37021 → 1007:39132
- S-11 v2 995:37232 → 1008:41065
- S-22 v2 995:37522 → 1008:41353
- T-98s 998:37418 → 1008:41634
- S-24x 998:37484 → 1007:39342
- S-12c 998:37605 → 1007:39514
- S-12d 998:37799 → 1007:39719
- S-01j 998:37841 → 1008:39146
- S-02 v2 998:38004 → 1008:39262
- S-12 v2 999:37852 → 1008:39446
- S-18 v2 999:38055 → 1008:39650
- S-15 v2 999:38228 → 1008:39822
- S-06 v2 999:38403 → 1007:38500
- S-13 v2 999:38554 → 1008:39996
- S-04 v2 1001:38264 → 1008:40213
- S-17 v2 1001:38361 → 1008:40304
- H-00n 1001:38563 → 1008:40494
- S-06 v3 1004:38392 → 1008:40584
- S-06 v3a 1004:38576 → 1008:40744
**Values you'll need in code, because they aren't tokens:**
- **Split-method segment, selected:** rgb(0.30, 0.33, 0.58), the same as the old S-03 Dark.
- **Alert and action-sheet panel:** rgb(0.16, 0.17, 0.36) at 97%, with no tinted header band.
- **Scrim behind an alert:** 55%, not 32%.
- **Hand-set positive green:** rgb(0.47, 0.85, 0.62).
Everything else is a bound token and follows the theme.

### [designBOT → engBOT] 2026-11-09 19:00 · Server side effects from round 4 · what she should see
**Status:** Redesigned (behaviour and copy; no new frames)
**Jira:** THL-291 (Cash in hand: "never counted twice"), THL-181 ("Paid back" and "Owes" agree with the repayments linked), THL-289 flow 7   **Figma:** S-13 v2 999:38554, S-03f 994:37078, S-05 536:14816
I'm logging these as **SPLIT-15** and **SPLIT-16** so they can be tracked. engBOT, please add them to the tracker.

**SPLIT-15 · A partly deposited cash payment is listed twice.** She should always see **one payment, as she recorded it**. The split into two records is bookkeeping and must not show.
- **"Paid back this month" / S-05 / Owed to you:** one row, "Priya · Cash · $250.00 · Nov 3". When part of it has been deposited, add a second line under it: "$200.00 deposited Nov 12 · $50.00 still cash". Totals count $250 once.
- **"Is this cash you were paid?" (S-13 v2):** the remainder shows as one row, "Priya · $50.00 left of $250.00 cash · Nov 3". It never shows as a separate $50 payment.
- **Unlink the deposit:** the two records join back into one $250 cash record. Nothing changes on screen except the "deposited" line going away.
- **For the server:** keep a shared origin id on both pieces, and group by it everywhere a payment is listed or counted. The cleaner alternative is one cash record with a `deposited` amount.

**SPLIT-16 · Removing a person unlinks her whole payback, from other purchases too.** Removing Priya from one split should only touch **that** split. A purchase she isn't being removed from must never change without being asked.
- **S-03f alert, when her payback also covers other purchases:** "Remove Priya? Her $60.00 e-Transfer also paid back Costco. Removing her here unlinks only the $28.04 for Loblaws; Costco stays paid back." The buttons don't change: "Unlink and remove" and "Keep Priya".
- **After removing:** Loblaws no longer lists Priya. Costco still shows "Priya · Paid back". The e-Transfer goes back to Needs a look with "$28.04 left to sort", not the whole $60. Opening it shows the Costco part still linked, and the $28.04 rest on the shared What was this? page.
- **Undo** (toast "Priya removed · Undo"): puts the $28.04 link back on Loblaws.
- **If her payback covers only this purchase:** S-03f stays as drawn, and the whole e-Transfer goes back to Needs a look.
- **For the server:** on edit, unlink only the parts of a payback that point at the purchase being edited. Don't drop the payback record.

### [engBOT] 2026-11-09 20:30 · round 6 start
Final round; the product owner said to run every round without stopping. I checked designBOT's round-5 frames with get_screenshot on the given node IDs only: S-06 v3 1004:38392, S-06 v3a 1004:38576, S-12c 998:37605, and four dark twins (S-03f Dark 1007:38650, S-04 v2 Dark 1008:40213, S-06 v3 Dark 1008:40584, S-12c Dark 1007:39514). I compared the twins with the app's dark tokens in `ios/Pearl/Theme/Theme.swift` and `Nacre.swift`. I added SPLIT-15 and SPLIT-16 to the tracker.

### [engBOT → designBOT] 2026-11-09 20:30 · SPLIT-14 · Accepted
**Figma:** S-06 v3 1004:38392, S-06 v3a 1004:38576; dark 1008:40584
- The App row shows only for Another app, at the top of the Amount / When card. It's optional, with the placeholder "Which app?".
- The chips are her own app names, newest first, up to 4. They're hidden the first time (v3a).
- Blank shows "Another app". The name is trimmed, capped at 30 characters, and matched without regard to case.
- A typed name, not a brand list, is right: nothing hard-coded, and nothing that's wrong for a region.
- S-06 v2's "Next: the extra" still waits on SPLIT-04/05, as you said.

### [engBOT → designBOT] 2026-11-09 20:30 · SPLIT-07 / SPLIT-09 · S-12c WHAT CHANGES · Accepted
**Figma:** S-12c 998:37605 (card 1004:38754); dark 1007:39514
The card matches what the app already shows on S-12c. Since round 4, the app has run Check and save's WHAT CHANGES through `parts/preview` with the held split, so you get "Allowance · November +$493.80" and "Shopping · October $212.40 → $106.20". No code change was needed.

### [engBOT → designBOT] 2026-11-09 20:30 · Dark twins · Accepted, with two notes
**Figma:** 1007:38650, 1008:40213, 1008:40584, 1007:39514 (spot-checked); the other 19 in your list were not opened.
- **Tokens match the app.** Bound colours flip to the same dark values the app uses: page #0B1030, card #151B44, ink #FBF8F6, muted #B4B1CC, action #FF8FB1, and rule #252C5E.
- **Split-method segment, selected (rgb 0.30, 0.33, 0.58):** the app had no value for this, so it's built. It's set on the split sheet only and reset when the sheet closes.
- **Note 1, alerts and action sheets:** S-03f's alert and S-04 v2's action sheet are the system `.alert` and `.confirmationDialog`, which iOS draws in its own dark material. The panel rgb(0.16, 0.17, 0.36) at 97% and the 55% scrim can't be applied without swapping in custom alert views, and that isn't designed. Not built. I suggest the twins say "system alert, iOS draws it", so a later "match the frames" pass doesn't flag them. This doesn't block anything.
- **Note 2, positive green:** the hand-set rgb(0.47, 0.85, 0.62) (#78D99E) differs from the token color/text/money-in dark #56D48F, which the app uses for every positive amount. I kept the token. Please bind those fills to money-in rather than hand-setting them. Not blocking.

### [engBOT → designBOT] 2026-11-09 20:30 · SPLIT-15 · Accepted
**Jira:** THL-291 Cash in hand ("never counted twice")   **Figma:** S-13 v2 999:38554, S-05 536:14816
- I followed your first option, a shared origin id, because it keeps the round-4 rule that a later deposit can take what's left.
- Every list groups pieces by that origin, and Unlink rejoins them into one record.

### [engBOT → designBOT] 2026-11-09 20:30 · SPLIT-16 · Accepted, one copy change
**Jira:** THL-181 ("Paid back" and "Owes" agree with the repayments linked), THL-289 flow 7   **Figma:** S-03f 994:37078
- **Behaviour:** built as written.
- **Copy change:** the alert says "Priya’s $60.00 e-Transfer also paid back Costco. Removing Priya here unlinks only the $28.04 for Loblaws; Costco stays paid back." It doesn't say "Her … her", because Pearl doesn't know anyone's pronouns.
- **Payment word:** "e-Transfer" appears only when the deposit reads as one (e-Transfer or Interac). Otherwise the alert says "payment".

### [engBOT] 2026-11-09 21:10 · round 6 · build
Branch `feat/split-bot-round` (PR #315, open, not merged).

**SPLIT-14 (S-06 v3 / v3a):**
- **Server:** the `txn_split_cash.app` column, migrated. `POST …/split/cash` takes `app`: optional, trimmed, up to 30 characters, and kept only for `via: "app"`. The toast reads "Sam paid $42.06 through PayPal." New `GET /api/split/apps` lists her names newest first, one per name whatever its case, up to 4. `people_status` gains `app_name`, and Owed to you's paid back gains `app_name`.
- **App:**
  - MarkPaidSheet has the App row, the Used before chips and the v3 / v3a footnotes. The Another app subtitle is now "Pearl won’t look for it in your bank".
  - S-05 reads "Paid back · PayPal · Nov 13", or "Paid back · Another app · Nov 13" when no app was named.
  - Owed to you's paid back says the app's name, or "Another app".

**SPLIT-15:**
- **Server:**
  - A `txn_split_cash.origin` column. A record cut in two by a partial deposit keeps its origin.
  - `splits.payments()` groups the pieces into one payment, with `deposited`, `deposited_on` and `still`. It's used by `people_status` (`payments`) and by Owed to you's paid back.
  - cash-matches marks a remainder with `of`, the whole payment.
  - Unlinking a deposit (`parts.undo`, which Save changes also runs) rejoins free pieces into one record.
- **App:** S-05 and Paid back this month show one row with "$200.00 deposited Nov 12 · $50.00 still cash" under it. S-13 shows "$50.00 left of $250.00 cash · Nov 3". Totals count $250 once, as before.

**SPLIT-16:**
- **Server, `_edit_split`:** a removed person's payback that also covers other purchases is unlinked, then saved again as parts of the deposit:
  - one payback part per remaining purchase, with the same person and amounts;
  - plus a rest, so the e-Transfer is "$28.04 left to sort from a $60.00 deposit." in Needs a look;
  - Costco stays paid back;
  - Undo (a new `unparts` mark, run first) puts the deposit back whole, then restores the Loblaws link, the other links and the split.
  - A payback that covers only this purchase goes back whole, as before.
  - `people_status` gains `shared` for the alert copy.
- **App:**
  - S-03f's alert copy, as above.
  - Saving an edit that removed someone who had paid shows "Priya removed" with Undo, using the server's undo.

**Dark:** the split-method segment colour, as above. Nothing else was missing from the app.

**Tests:**
- New in `tests/test_split_round.py`: TestWhichApp (4), TestCashOnePayment (3), TestRemoveOnlyHere (4).
- Two existing tests changed:
  - test_splits.py's exact-match dicts gained the new keys.
  - test_cash_partly_deposited_keeps_the_rest now expects one $100 remainder of $250 after Save changes, not two $50 records. That's the SPLIT-15 rule.
- **Results:**
  - `python3 -m pytest -q`: 1739 passed, 0 failed. The split files give 28 in test_split_round.py.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` files were added, so `make_project` wasn't needed.
- **Commit:** f067b04, "Splits round 6: which app, one cash payment, remove only here". 12 files; `git show --stat` checked. Pushed to `feat/split-bot-round`.
- **PR #315:** the body now covers SPLIT-14/15/16, the S-12c card, the dark segment, and the system-alert note. It's still open and not merged.
- **Jira:** comments on THL-291, THL-181 and THL-289. All three stay in Testing, and I moved no ticket.

### [product owner] 2026-11-09 · SPLIT-01/05/06 decided: designBOT's recommendations
- **SPLIT-01 → (b′):** saving short is allowed only when "I had some too" is on, and her row shows "Your share $44.12 · $4.12 of it is the rest" before saving. With it off, Save is blocked with "$x left to assign", in the app and on the server. Figma S-03b v2 994:36736.
- **SPLIT-05 → (b):** splits use the shared What was this? page: tiles answer at once, four income tiles, and Other income asks for the rest. Figma S-22 v2 995:37522, S-11 v2 995:37232.
- **SPLIT-06 → (a):** a split made from a Quick sort card's page is held for the card: "Groceries, split with Sam?". Yes saves the split and the category with one Undo, and Skip drops it. Figma T-98s 998:37418.
- THL-291's AC is reworded to match: "Save only when shares add up exactly" becomes the (b′) rule, and "7 kinds" becomes "any income kind".
- Then build what was waiting on these: SPLIT-04 (S-11 v2), the S-06 v2 "Next: the extra" path (SPLIT-11), and the PartsFlow income list (SPLIT-12).

### [engBOT] 2026-11-09 22:30 · round 7 start
I checked the decided frames with get_screenshot on their node IDs only: S-03b v2 994:36736, S-11 v2 995:37232, S-22 v2 995:37522 (plus get_metadata on that one frame), T-98s 998:37418 and S-06 v2 999:38403. I didn't fetch any page-wide metadata. designBOT is working on dark twins in Figma and won't write here this round, so I've logged three new issues for the next round (SPLIT-17, 18 and 19). In each case I built only the part that isn't blocked.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-01 · Accepted
**Figma:** S-03b v2 994:36736
- With "I had some too" on and the total short, Save is on. Her row reads "Your share $44.12 · $4.12 of it is the rest", and the status line reads "$4.12 isn’t anyone’s yet · it stays yours" in ink.
- With it off, Save is off, and the line reads "$4.12 left to assign" in red. For % it reads "10% left to assign".
- The server refuses the same case with the same words.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-04 / SPLIT-05 / SPLIT-12 · Accepted (built, except SPLIT-17 and SPLIT-18)
**Figma:** S-11 v2 995:37232, S-22 v2 995:37522
- **What's built:** S-11 v2 replaces the old kinds list and the "What kind of income?" list in PartsFlow. That covers both the rest and the extra.
- **How it works:** "How much of it?" is on top. It's all of what's left unless she types less. The tiles answer at once; if anything is still left, the page comes back for it, and otherwise she goes to Check and save. "Sort the rest later" is under Options.
- **What each tile saves as a part:**
  - My pay → income Salary
  - Bonus → income Bonus
  - A gift → Gift
  - Paying me back → S-09
  - Money back → T-09r
  - My own money → between my accounts
  - Out of savings → savings
  - Dad overpaid → they overpaid (You owe)
  - Off a category → the category list
- **New server part kinds:** Work paying me back (links the expense, as a whole deposit's reimbursement does), Lent me this (Borrowed) and Money I lent, back (Lent). Not mine isn't a part.
- **The AC's $100 + $72:** two passes, with a test.
- **S-22 v2:** the shared page already is S-22 v2, apart from the two things in SPLIT-17.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-06 · Accepted
**Figma:** T-98s 998:37418
- From a Quick sort card's page, "Split with others" holds the split instead of saving it.
- The card says YOUR CHOICE, "Groceries, split with Sam?" and "Your share $42.06 · Sam owes you $42.06". Under it: "Yes saves the split and Groceries, for this one." and "Skip forgets the split. Tap the card to change it."
- Yes sends one PUT …/split with the category, and the Sorted card's Undo puts back the split, her share and the category. Skip drops the held split.
- Picking another category on the page keeps the split and changes its category. Picking a different answer, such as Not mine, drops it.
- **Not changed:** a split made on What was this? when Quick sort opens it as a sheet rather than the card's page (AnswerSheet's Options, for asks that don't open a page). It still saves at once, because T-98s covers only the card's page.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-11 · Still blocked (extra path), see SPLIT-19
The S-06 v2 caption and "Next: the extra $17.94" aren't built. Cash or an app paying above what's owed is still recorded in full, so the extra shows as "Sam overpaid" under You owe, which is the one outcome S-06 v2 names.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-17 · S-22 v2 brings back "Split into parts" and turns Always off
**Severity:** Minor
**Jira:** THL-291 ("a money-in transaction can hold several parts"), THL-254   **Figma:** S-22 v2 995:37522 (OPTIONS › Split into parts 995:37628; Toggle row 995:37568, off)   **Code:** `ios/Pearl/Views/Review/AnswerSheet.swift` intoSheet; commit aa07127 (2026-11-09 08:11, "no Split into parts on money in")
**Problem:** S-22 v2 differs from the shared page as built in two ways.
1. **Split into parts.** S-22 v2 adds "Split into parts" under OPTIONS. Commit aa07127 removed that row from What was this? and from income's page that same morning, on purpose: Paying me back opens Who paid you back?, where she ticks every share it paid back. S-22 v2 was drawn later the same day, and the frame doesn't say it reverses that decision. Putting it back would give two ways into parts on one page.
2. **Always for Dad.** On S-22 v2 the switch is off, and the reply says it's off by default. On the shared page it's on by default for every deposit, which is what the Outcome table rule assumes for My own money and Not mine. Turning it off just for Dad's frame would change every deposit's default.
**Ask:** For (1), say whether Split into parts comes back under OPTIONS on money in, reversing aa07127, or remove it from S-22 v2. For (2), say whether Always starts off for every deposit or only in some cases (for example, an e-Transfer from a person), or draw it on. Until then I haven't built either one.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-18 · "Other income asks for the rest" has no frame
**Severity:** Minor
**Jira:** THL-291 Rules, now "income (any income kind)"   **Figma:** S-11 v2 995:37232 (Other income tile); designBOT's SPLIT-05 reply ("Other income asks for the rest (interest, government, tax refund, other)")   **Code:** `ios/Pearl/Views/Transactions/PartsFlow.swift` take(_:)
**Problem:** No frame shows the question Other income asks. On the shared page (T-08), Other income saves "Other" straight away. So as built, Other income makes an income part of kind Other, and a part can't be Interest, Government or Tax refund. The old "What kind of income?" list is gone, as SPLIT-12 asked.
**Ask:** Draw the follow-up Other income opens (tiles for Interest, Government, Tax refund and Other?), and say whether the shared T-08 page asks it too, so the two stay the same.

### [engBOT → designBOT] 2026-11-09 22:30 · SPLIT-19 · S-06 v2's extra has nowhere to go for cash or an app
**Severity:** Major
**Jira:** THL-291 Cash in hand ("never counted twice"); designBOT's SPLIT-11 reply ("It opens the same What's the extra page as a bank deposit (S-11 v2)")   **Figma:** S-06 v2 999:38403 ("Next: the extra $17.94"), S-11 v2 995:37232   **Code:** `finance/parts_api.py` split_cash; `finance/parts.py` apply
**Problem:** On S-11 v2, each tile turns part of a bank deposit into a part row. Cash in hand and Another app have no bank transaction, so there's nothing to split. Example: Sam owes $42.06 and pays $60.00 cash.
- "Sam overpaid" works today: the whole $60 is recorded, and $17.94 shows under You owe.
- Every other tile has no defined result. If she taps A gift, does Pearl add a $17.94 cash money-in row (Income · Gift) to her transactions? If she taps Paying me back, is $17.94 recorded as Sam's cash on another split?
- My own money, Out of savings, Money back, Work paying me back and Off a category make little sense for cash she's holding.
- If a later cash deposit includes the extra, Pearl has to know not to count it twice.
**Ask:** Say what each tile does with a cash or app extra, and where that money shows. A cash transaction row? Which account for an app? Or draw a shorter extra page for cash and apps, for example with Sam overpaid, Paying me back and A gift. Until then the extra path isn't built.

### [engBOT] 2026-11-09 22:40 · round 7 · build
Branch `feat/split-bot-round` (PR #315, open, not merged).
- **Server:**
  - `splits.validate`: with include_me off, a short split is "$x left to assign." (amounts) or "x% left to assign." (%).
  - `parts.py`: new kinds `reimbursement`, `loan` and `lent_back`.
    - A reimbursement links its expense and marks it as a reimbursement. Once it pays everything owed, it counts an expense that was waiting to be reimbursed again. Unlink leaves that expense out again (`was_excluded`).
  - `parts/preview`: a reimbursement lowers a category like a payback does, but a left-out expense is skipped.
- **App:**
  - **SplitFlow:** the (b′) Save rule and the words for it; "Your share $x · $y of it is the rest" under You. `onHold` now also passes her share.
  - **PartsFlow:** the S-11 v2 page (CaseGrid tiles, "How much of it?", Options › Sort the rest later), the `work` step ("What did this pay back?"), and Off a category through CategorySheet. The kinds list, the incomeKind step and "Split into another part" are gone.
  - **Quick sort:** the T-98s held split (`CardSplit` on `CardDraft`, and `ReviewAnswer.split`), the card's lines, Yes and Skip.
  - New part labels in Models and on the transaction page.
- **Tests:**
  - New in `tests/test_split_round.py`: TestShortOnlyWithYou (4), TestRestTiles (5) and TestHeldSplitFromQuickSort (1).
  - Changed: test_parts.py's `test_amounts_can_be_short_but_not_over`. A short split without her now expects "$55.00 left to assign."
- **Results:**
  - `python3 -m pytest -q`: 1749 passed, 0 failed.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` files were added, so `make_project` wasn't needed.
- **Commit:** 22bf661, "Splits round 7: save short only with you, S-11 v2 tiles for parts, held split on the Quick sort card". 11 files; `git show --stat` checked. Pushed to `feat/split-bot-round`; PR #315's body updated.
- **Jira:** THL-291's two approved AC lines were reworded (Split methods: the (b′) rule; parts: "income (any income kind)"). Nothing else in the description changed. I commented on THL-291 and THL-278. No ticket was moved; both stay in Testing.

### [designBOT → engBOT] 2026-11-09 21:40 · Dark twins · Notes 1 and 2
**Status:** Redesigned
**Jira:** THL-291, THL-181   **Figma:** 1008:41110, 1008:41398 (green); tags 1007:38830, 1007:39513, 1008:40303; layers 1007:38770, 1007:38769, 1007:39453, 1007:39452, 1008:40267, 1008:40266
- **Positive green:** the last two hand-set greens (S-11 v2 Dark "$600.00 · Nov 9", S-22 v2 Dark "+$600.00") are now bound to color/text/money-in. All 13 green fills across the 23 twins use the token; none are hand-set. The round-5 "hand-set positive green rgb(0.47, 0.85, 0.62)" value no longer applies. Keep the token. One thing to check: in the Figma library, money-in dark resolves to #6EDB94, not the #56D48F in code. The frames follow the token either way, but the library and Swift values should match. Needs product owner to say which is right.
- **Alerts and action sheets:** S-03f Dark, S-24x Dark (alert) and S-04 v2 Dark (action sheet) are now tagged "iOS system alert/action sheet — drawn by iOS, colours indicative", with ".alert" or ".confirmationDialog" and "don't set custom colours". Their layers are renamed to match. The round-5 panel colour rgb(0.16, 0.17, 0.36) at 97% and the 55% scrim are only an illustration, not values to build. Use the system dark material, as you did.
- **The other 19 dark twins:** I opened each one. I found no unflipped light colours, no unreadable text and no leftover nacre band. S-12d's neutral incoming amounts match the light frame (those rows aren't sorted yet). There's nothing to change in code.

### [product owner] 2026-11-09 · SPLIT-17: Split into parts stays removed on money in
Commit aa07127 stands. designBOT updates S-22 v2 995:37522 and its dark twin 1008:41353 to drop the row. For "Always for Dad", match the shared What was this? page (on by default) unless Jira says otherwise.

### [product owner] 2026-11-09 · Dark money-in green: #6EDB94
The Figma library value #6EDB94 for `color/text/money-in` (dark) is right. The app changes to it (engBOT). Nothing changes in Figma.

### [product owner] 2026-11-09 · THL-291's $85 AC example
engBOT rewords it to match (b′). Nothing for designBOT.

### [product owner] 2026-11-09 · Round 8 frames: build
The product owner has already said to build designBOT's SPLIT-18 and SPLIT-19 frames, so they're marked "Approved — build", not "Awaiting product owner".

### [designBOT] 2026-11-09 23:30 · round 8 start
engBOT isn't running this round, so I'm keeping the log. I read THL-291, THL-289 and THL-254 (descriptions and comments), commit aa07127, and the shared page as built (`AnswerSheet.swift` intoSheet / kinds step, `CategorySheet.swift` CaseTile.income, `finance/income.py` KINDS). In Figma I opened only S-22 v2, S-11 v2 and their dark twins by node. The six new frames sit in my column at x = 28620–29959 of section 536:14142 (now 30100 × 2287). Each one is a copy of S-11 v2 or S-11 v2 Dark, so every colour stays bound to a token and the dark twins keep mode 2:2. The amount line is bound to `color/text/money-in` in both modes.

### [designBOT → engBOT] 2026-11-09 23:30 · SPLIT-17 · Split into parts removed; Always on
**Status:** Redesigned
**Jira:** THL-291, THL-254   **Figma:** S-22 v2 995:37522 (toggle 995:37570 now On; removed 995:37625, 995:37627; tag 995:37802, note 995:37803); dark 1008:41353 (toggle 1008:41401 On; removed 1008:41456, 1008:41458; tag 1008:41633)
- **Split into parts:** I removed it, and the OPTIONS caption with it. Money in has no other option on the shared page, so the section is gone. Paying me back → "Who paid you back?" (S-09) is the one way into paybacks, as aa07127 built it. You were right that I'd reversed a decision without saying so; my mistake.
- **Always for Dad: on by default.** Neither THL-291 nor THL-254 sets a default. THL-254's AC says "Changes feed merchant rules and categorization learning", which supports on. So it matches the shared page: `rememberInto = pageAlways ?? true`. My round-2 note ("one payback doesn't make a rule") is withdrawn. She can turn it off before tapping a tile.
- The frame's note and tags now say SPLIT-05 decided (b) · SPLIT-17 · Approved — build. There's nothing to change in code: the app already matches.

### [designBOT → engBOT] 2026-11-09 23:30 · SPLIT-18 · What Other income asks next
**Status:** Redesigned · Approved — build
**Jira:** THL-291 Rules ("income (any income kind)"), THL-289 Rules ("income (any of the 7 kinds)"), THL-254   **Figma:** S-11k 1017:103 / dark 1017:419 (a part); T-08k 1017:715 / dark 1017:1013 (shared page); tags 1018:1911, 1018:1913, 1018:1914, 1018:1916; notes 1018:1912, 1018:1915
- **The kinds list is the app's own:** `finance/income.py` KINDS has 7 kinds. The four income tiles (My pay, Bonus, A gift, Other income) cover salary, bonus and gifts. Other income opens **"What kind of income?"** with the other four as tiles: **Interest** (`interest`), **Government credits** (`government`), **Tax refund** (`tax_refund`) and **Other income** (`other`). The labels match `TransactionDetailView`'s kind names. The four-tile rule still holds on the main page; this is a follow-up, like My pay → "How often is this pay?".
- **S-11k (a part):** the header is the deposit. The row under it reads "Other income · $172.00", the amount "How much of it?" gave on S-11 v2, and it can't be edited here. A tile answers at once and adds `Part(kind: "income", incomeKind: <key>)`. Then the flow continues as S-11 v2 does: it comes back for what's left, or goes to Check and save. There's no Options and no Always. Close or Back returns to S-11 v2 with nothing added.
- **T-08k (shared page, whole deposit):** yes, the shared page asks it too, so the two stay the same. It's reachable from Transactions, Needs a look and Quick sort. Other income on T-08 opens this, instead of saving "other" straight away. A tile saves `incomeType(t.id, kind:)` / `mark(case: pay, income_kind:)` with the usual Undo. The page's Always switch carries over (`pageAlways`) and isn't shown again. From a Quick sort card's page, the choice is held for the card like any other answer.
- **Error:** the tile un-highlights, and "Couldn’t save that. Try again." appears under the grid. Tiles are 44pt+; VoiceOver reads "Interest, income kind, button".
- **Code:** `AnswerSheet` already has a `.kinds` step and title. Point Other income at it with these four tiles. In `PartsFlow.take("other")`, push the same step instead of saving `other`.

### [designBOT → engBOT] 2026-11-09 23:30 · SPLIT-19 · The extra from cash or another app
**Status:** Redesigned · Approved — build
**Jira:** THL-291 (Rules: parts kinds, "they overpaid", Cash in hand "never counted twice", "Pearl never fills in a leftover itself"), THL-289 flow 5 and flow 7 ("payback bigger than everything they owe"), THL-181   **Figma:** S-11c 1017:1309 / dark 1017:1607; tags 1018:1917, 1018:1919; note 1018:1918. Flows from S-06 v2 999:38403 and S-06 v3 1004:38392, and into S-09 538:14642.
A shorter page, **"What’s the extra $17.94?"**, opens from S-06 v2's "Next: the extra" whenever the payment method is Cash in hand or Another app. A bank deposit still goes to S-11 v2, because it has a transaction to split. "How much of it?" is on top, as on S-11 v2, so $10.00 gift + $7.94 overpaid works in two passes. Four tiles:
1. **Sam overpaid** → a "they overpaid" record of $17.94 tied to this cash/app payment. It shows under You owe in Owed to you, and on S-05 as "Overpaid $17.94". This is the result today, now chosen rather than assumed.
2. **Paying me back** → S-09 "Who paid you back?", with Sam's other open shares first and ticked, then everyone else's (as aa07127). Each ticked share gets a cash/app payback for its part, with the same `via`, `app` and **origin** as the $60 (SPLIT-15). Lists show one payment: "Sam · Cash · $60.00 · Nov 13 · paid back Loblaws and Pizza Nova". If the ticks cover less than $17.94, the page comes back for the rest.
3. **A gift** → a cash/app gift record: kind Gift, $17.94, dated the payment day, with the same origin. It counts as money in once, in that month (THL-291 "a gift counts as money in"). Allowance goes up $17.94. Income shows "A gift · Sam · Cash". No bank transaction row is made.
4. **I gave it back** (cash) / **I sent it back** (Another app) → the payment is recorded as $42.06, what Sam owed. Nothing else is saved. S-05 reads "Paid back · Cash · Nov 13" with "$60.00, $17.94 given back" under it.
- **Left out, and why:** My pay, Bonus and Other income (a split payback isn't her pay; cash income on its own is out of scope in THL-291). My own money and Out of savings (no account of hers moved). Money back, Work paying me back and Off a category (they come from a store or an employer, and there's no deposit to take off a category). Lent me this and Money I lent, back (there's no cash record for loans). Not mine (if it's for someone else's share, that's Paying me back).
- **No "Sort the rest later":** there's no deposit to keep in Needs a look, and THL-291 says Pearl never fills in a leftover itself. So nothing is saved until all of the $17.94 is said. Close or Back returns to S-06 v2 with $60.00 still typed, so she can change it to $42.06 instead.
- **Later cash deposit (Cash in hand only):** S-13 offers the payment as one row, "Sam · $60.00 cash · Nov 13", grouped by origin. Linking it makes the deposited amount Moving money across every piece, including the gift, so the gift counts once and only on Nov 13. With "I gave it back", only $42.06 is offered. Another app is never offered in S-13 (the SPLIT-11 rule).
- **Undo** on the Sorted toast removes the whole payment: the payback, the gift, the overpaid record and the extra paybacks, all by origin.
- **Server:** `split_cash` takes `extra: [{kind: overpaid|payback|gift|returned, amount, charge?, person?}]`, which must add up to `amount − owed`. Every record shares the origin. `gift` adds a cash income record (kind gifts) that Allowance and income read. `returned` lowers the stored amount to what was owed. Refuse it with "$x of the extra isn’t said yet" if it doesn't add up.

### [engBOT] 2026-11-09 23:50 · round 9 start
I checked each round-8 frame by node with get_screenshot (light and dark) and didn't fetch any page-wide metadata. I also opened S-06 v2 999:38403 by node, because S-11c starts from it. designBOT isn't running this round, so I'm keeping the log.

### [engBOT → designBOT] 2026-11-09 23:50 · SPLIT-17 · Accepted
**Figma:** S-22 v2 995:37522, dark 1008:41353
- Split into parts and the OPTIONS caption are gone. Always for Dad is on.
- This matches `AnswerSheet` intoSheet: there are no options on money in, and `rememberInto = pageAlways ?? true`. Nothing in the code changed.

### [engBOT → designBOT] 2026-11-09 23:50 · SPLIT-18 · Accepted (built)
**Figma:** S-11k 1017:103 / 1017:419, T-08k 1017:715 / 1017:1013
- Both frames show the same four tiles: Interest, Government credits, Tax refund and Other income. They map to `finance/income.py` keys `interest`, `government`, `tax_refund` and `other`.
- S-11k has "Other income · $172.00" and its caption. T-08k has the "Always … isn’t asked again" caption.
- The dark twins match the light frames.
- **One note, not blocking:** T-08k's error line ("Couldn’t save that. Try again.") isn't a separate line in the app. The screen that opened the shared page saves the answer and shows its usual error.

### [engBOT → designBOT] 2026-11-09 23:50 · SPLIT-19 · Accepted (built)
**Figma:** S-11c 1017:1309 / 1017:1607, from S-06 v2 999:38403
- The frame shows four tiles (Sam overpaid, Paying me back, A gift and I gave it back), "How much of it?" and "Nothing is saved until you say what the other $17.94 is."
- The dark twin matches.
- **Checked:**
  - Rounding: the pieces are checked in cents on the server.
  - One person, or several shares on Paying me back.
  - Close goes back to S-06 v2 with $60.00 still typed.
  - An app payment is never offered to a deposit.
  - Undo works by origin.
- **Two small differences:**
  1. "I gave it back" also saves a `returned` piece. Without it, S-05 couldn't show "$60.00, $17.94 given back". It counts nowhere and is never offered to a deposit.
  2. The list line "paid back Loblaws and Pizza Nova" isn't built. The payment now carries `whole`, but the app doesn't name the other purchases yet.

### [engBOT] 2026-11-09 23:55 · round 9 · build
Branch `feat/split-bot-round` (PR #315, open, not merged).
- **SPLIT-17:** no change. The app already matched S-22 v2.
- **SPLIT-18:**
  - New `CaseTile.otherIncome` tiles.
  - AnswerSheet has a new `.otherKinds` step, reached from Other income on T-08 and from the T-71 `.kinds` step. It saves through `incomeType` or `mark(case: pay, income_kind:)`, as before.
  - PartsFlow has a new `.otherKind` step (S-11k). In it, Close goes back to S-11 v2.
  - `CaseGrid` now takes `role`, so VoiceOver reads "Interest, income kind".
  - The shared page reaches this from Transactions, Needs a look and Quick sort, because all three use `AnswerSheet`.
- **SPLIT-19 server:**
  - `txn_split_cash.kind` is new (migration added).
  - `split_cash` now takes `extra`. Its pieces must add up to amount − owed, or it says "$x of the extra isn’t said yet." / "That’s $x more than the extra." A payback piece can't be more than that share owes.
  - The records share one origin:
    - What was owed, plus anything overpaid, stays on this split.
    - A payback goes onto the other split.
    - A gift is a `split_gift` income row (Gift, on the payment's day). `query_transactions` doesn't list it.
  - `cash-matches` groups the pieces it offers by origin (`ids`) and leaves out given-back pieces.
  - `rejoin_split_cash` now groups by origin, purchase, person and kind.
  - `/transactions/undo {cash_payment}` and DELETE on the payment remove every piece and the gift.
  - `payments` carries `whole` and `given_back`.
- **SPLIT-19 app:**
  - In `MarkPaidSheet`, S-06 v2 now shows the red caption and "Next: the extra $x".
  - The S-11c page has the tiles, "How much of it?", and the open shares (theirs ticked first, from `api/owed`).
  - It saves once, with `extra`, and the Sorted toast's Undo goes through `onUndoable`.
  - S-05 shows "$60.00, $17.94 given back".
- **Dark money-in:** `Pearl.moneyIn` dark changed from 0x56D48F to 0x6EDB94 in `ios/Pearl/Theme/Theme.swift`.
  - The web app's `src/tokens/tokens.css` is a separate file (generated, "re-export from Figma") and doesn't share the Swift token. I left it at #56d48f.
- **Tests:**
  - New in `tests/test_split_round.py`: TestOtherIncomeKinds (8) and TestCashExtra (11).
  - `python3 -m pytest -q`: 1768 passed, 0 failed.
  - `xcodebuild … -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` files were added, so `make_project` wasn't needed.
- **Commit:** 8176985, "Splits round 9: Other income's kinds, the extra from cash or an app, dark money-in #6EDB94". 13 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:**
  - THL-291: only the $85 AC line changed. It now reads: With "I had some too" off, $85 split as Priya $30 / Sam $20 blocks Save with "$35.00 left to assign" (85 − 50 = 35). The Evenly clause after it is unchanged.
  - Commented on THL-291 and THL-254. No ticket was moved; both stay where they were (THL-291 in Testing).

### [product owner] 2026-11-09 · Finish the two small engBOT items
Build the SPLIT-19 list line and T-08k's own error line. Leave the web token (#56d48f) alone; that question is still open.

### [engBOT] 2026-11-10 00:30 · round 10 start
Before building, I opened S-11c 1017:1309, its note 1018:1918 and T-08k 1017:715 by node with get_screenshot. Neither frame draws the list line or the error state. Both are described in designBOT's round-8 entries (SPLIT-19 point 2, SPLIT-18 "Error"), so I built them from that text. I didn't fetch any page-wide metadata, and designBOT isn't running this round.

### [engBOT] 2026-11-10 00:30 · round 10 · build
Branch `feat/split-bot-round` (PR #315, open, not merged). Commit d2dc59d.
- **SPLIT-19 list line:**
  - **Server:** `Store.splits()` gives each cash or app record `charges`, the purchases its payment paid back, with its own purchase first. `splits.payments()` turns these into `paid_back` (merchant names) when there's more than one. `/api/owed` lists such a payment once across splits, as the payer's row on the purchase it was recorded on. Its amount is what paid back purchases, so a gift piece isn't counted in it. Deposited amounts are summed.
  - **Owed to you:** "Sam · Cash · Nov 13 · paid back Loblaws and Pizza Nova", with $60.00 on the right. A payment for one purchase reads as before.
  - **S-05:** "$60.00 · paid back Loblaws and Pizza Nova" under the person. Any given-back amount is added: "$60.00, $5.00 given back · paid back …".
  - **Long lists:** neither the frame nor the code shortens a list, and the SPLIT-16 alert already lists every name. So it reads "Loblaws, Costco and Pizza Nova", with no "and 2 more". The new `Format.andList` is shared with that alert.
- **T-08k error line:**
  - **Saving:** `AnswerSheet` saves an Other income kind itself (`saveOtherKind`). While it saves, the tile stays highlighted and the grid is disabled.
  - **On failure:** the tile un-highlights, "Couldn’t save that. Try again." shows under the grid in `Pearl.caution`, and VoiceOver announces it.
  - **On success:** the opener gets `.done(reply)`, so Transactions (`run`), Needs a look (`send`) and Quick sort (`answered`) show their usual toast and Undo. None of them sees an error, so none shows a second one.
  - **Held answers:** the new `holds` flag is set by Quick sort's sheet and by a Quick sort card's page (`onDraft`). With it set, the answer is held for the card as before, and nothing is saved on the page.
- **Tests:**
  - New: TestPaymentNamesWhatItPaid (4) in `tests/test_split_round.py`.
  - `python3 -m pytest -q`: 1772 passed.
  - `xcodebuild … -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand.
  - No `.swift` file was added.
- **Commit:** 11 files; `git show --stat` checked. Pushed, and PR #315's body updated (both items moved out of "Not built").
- **Jira:** commented on THL-291. Nothing was moved; THL-291 stays in Testing.
- **Not touched:** `src/tokens/tokens.css` (#56d48f).

### [product owner] 2026-11-09 · SPLIT-06 (a) everywhere: the Quick sort sheet holds a split too
A split made from Quick sort's sheet is held for the card, like one made on the card's page. The card shows "Groceries, split with Sam?". Yes saves the split and the category in one request with one Undo, and Skip drops it. The Summary was wrong to call SPLIT-06 fully built: the sheet still saved at once (round 7 said so under "Not changed"). Log it as SPLIT-20 and build it.

### [product owner] 2026-11-09 · THL-181: Pearl asks who a payback is from
When Pearl can't tell who a payback is from, it asks; it doesn't pick someone. designBOT is drawing it now. engBOT doesn't build it this run; log it as SPLIT-21, "Open → designBOT (approved to build)".

### [product owner] 2026-11-09 · Jira edits approved
THL-291, THL-289, THL-278 and THL-260 are brought in line with what was decided and built: Allowance wording, the part kinds, the (b′) rule, the tiles page coming back for what's left, six months, and the SPLIT-06/20 line. THL-181's AC stays; the app changes to match it. Move nothing past Testing.

### [product owner] 2026-11-09 · Web money-in dark: #6EDB94
The web's dark `--money-in` changes to #6EDB94 to match Figma. Leave the light value; designBOT is checking the Figma light value, and it comes in the next round.

### [engBOT] 2026-11-09 · round 11 start
designBOT is working in Figma only this run and isn't writing here. I didn't open Figma: SPLIT-20 builds T-98s 998:37418, which I already accepted in round 7, and SPLIT-21's frames aren't drawn yet.

### [engBOT → designBOT] 2026-11-09 · SPLIT-20 · Quick sort's sheet saved a split at once
**Severity:** Major
**Jira:** THL-278 ("a split made from a Quick sort card's page or sheet is held for the card"), THL-291   **Figma:** T-98s 998:37418   **Code:** `ios/Pearl/Views/Review/AnswerSheet.swift` (the SplitSheet in `.sheet(isPresented: $splitting)`, formerly lines 184–188; the `holds` doc comment, formerly line 36)
**Problem:** Quick sort opens What was this? as a sheet (with `holds: true`) for asks that don't open a page. There, Options › Split with others showed SplitSheet without `onHold`, so the split saved at once. Example: in Quick sort, a $84.12 Loblaws card opens as a sheet. Split with Sam evenly, then Skip: the split was already saved, and Skip didn't drop it. The `holds` comment said "nothing is saved here", which wasn't true for a split.
**Ask:** None. T-98s already covers this; the product owner decided (a) everywhere. Built below.

### [engBOT → designBOT] 2026-11-09 · SPLIT-21 · Ask who a payback is from (THL-181)
**Severity:** Major
**Jira:** THL-181 (its AC stands: Pearl asks when it can't tell who a payback is from); THL-278's "An unnamed payback counts for whoever owes that amount, otherwise the first person who still owes"   **Figma:** being drawn by designBOT   **Code:** the unnamed-payback match on the server (THL-278, PR #208)
**Problem:** Today an unnamed payback (TD, or one picked from search) counts for whoever owes that amount. Failing that, it counts for the first person who still owes, so Pearl picks someone without asking.
**Ask:** Draw the "Who is this from?" step (light and dark): when it shows, the people it lists, what happens on save and Undo, and how she gets out. The product owner has approved building it. engBOT builds it once the frames are in and checked. Not built this run.

### [engBOT] 2026-11-09 · round 11 · build
Branch `feat/split-bot-round` (PR #315, open, not merged).
- **SPLIT-20 (app):**
  - `AnswerSheet` has a new `onHeldSplit`. When `holds` is set and an opener passes it, SplitSheet gets `onHold`: the split is kept on the sheet (Split with others shows as done), and nothing is saved.
  - The category she picks next on the same page goes with the split, "for this one", as T-98s says (no rule).
  - Picking a different answer, such as Not mine, drops the split, as on the card's page. Closing the sheet drops it too.
  - `QuickSortView` sets the card's draft to `CardDraft(label: "Groceries, split with Sam", category:, split:)`. The card shows YOUR CHOICE, "Groceries, split with Sam?" and "Your share $42.06 · Sam owes you $42.06".
  - Yes sends one PUT …/split with the category, and the Sorted card's Undo puts back the split, her share and the category. Skip drops the held split. Both reuse the round-7 code.
  - `CardSplit.held(_:mine:total:)` is new and shared with the card's page (`TransactionDetailView.holdSplit`).
  - The `holds` doc comment now says what is and isn't saved.
  - Opened anywhere else (Transactions, Needs a look), the sheet still saves a split at once, as before.
- **Web token:** dark `--money-in` changed from #56d48f to #6edb94 in `src/tokens/tokens.css` (lines 98 and 130). The light value (#1e7b4c) is unchanged.
  - The file says "generated, re-export from Figma", but the repo has no generator. `--money-in` isn't in `tokens.json` or `tokens.ts` either; it was added to the css by hand in 38aa320. So I edited `tokens.css` directly.
- **Tests:**
  - New: TestHeldSplitFromQuickSortSheet (2) in `tests/test_split_round.py`. These are wiring checks on the Swift source. The server half (one PUT, one Undo) is already covered by TestHeldSplitFromQuickSort.
  - `python3 -m pytest -q`: 1774 passed, 0 failed.
  - `npm run build`: built.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` file was added.
- **Commit:** 1abc302, "Splits round 11: Quick sort's sheet holds a split for the card (SPLIT-20), web dark money-in #6edb94". 5 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:**
  - Descriptions edited: THL-291, THL-289, THL-278 and THL-260. Each got a comment saying what changed.
  - THL-181: comment only; its AC is unchanged.
  - No ticket was moved.

### [designBOT → engBOT] 2026-11-09 · AUDIT-FIGMA · Superseded frames marked, decided frames retagged, tags fixed
**Status:** Redesigned
**Jira:** THL-291, THL-289, THL-254, THL-278   **Figma:** 1028:41057–1028:41107 (red Superseded tags), 994:36735, 994:36903, 998:37483, 999:38553, 995:37802, 1008:41633, 1018:1911, 1018:1913, 972:36148
Product owner approved fixing every Figma mismatch from the three-way audit. I opened each old frame and checked it against its replacement before marking it. These are dimmed to 40% with a red "Superseded by …" tag, light and dark: S-03b (the "I had some too" off case keeps S-03b's blocked Save), S-11, S-11n, S-36b (bank → S-11 v2; cash or app → S-11c 1017:1309), S-22, S-12, S-02, S-04, S-06 (→ S-06 v3), S-15, S-17 and S-33. S-18 is not superseded, because an even split with no odd cent is still correct; it has a grey "Still current" tag pointing to S-18 v2. Every round-2 and round-5 frame and its dark twin now reads "Decided · Built (PR #315)", and so do S-22 v2, S-11k, T-08k and S-11c. The T-98s note states SPLIT-06 (a) only. The S-06 v2 note points to S-11c. S-22 v2 drops THL-213. S-11k is THL-291, THL-289. T-08k stays on THL-254. The T-96 note now says a split made on the Quick sort sheet is held for the card ("Groceries, split with Sam?"; Skip drops it; Undo covers it). No new build work.

### [designBOT → engBOT] 2026-11-09 · SPLIT-18/19 · Frames for built behaviour
**Status:** Redesigned
**Jira:** THL-291, THL-289, THL-254   **Figma:** S-14p 1029:41057 (dark 1029:41156), S-05p 1029:41258 (dark 1029:41332), T-08k error 1030:41151 (dark 1030:41353)
These draw what d2dc59d already built, so there's nothing new to build. S-14p: Owed to you › Paid back this month, "Sam · Cash · Nov 13 · paid back Loblaws and Pizza Nova" at $60.00, plus a three-purchase row ("Loblaws, Costco and Pizza Nova"). S-05p: the line under Sam, "$60.00 · paid back Loblaws and Pizza Nova". The note gives the ", $x given back" form. I didn't draw "$60.00, $17.94 given back · paid back Loblaws and Pizza Nova" because those numbers can't all be true for one $60.00 payment. T-08k error: no tile highlighted, "Couldn't save that. Try again." under the grid in color/text/caution.

### [designBOT → engBOT] 2026-11-09 · THL-181 · If Pearl can't tell who, it asks
**Status:** Redesigned · THL-181 · Approved — build
**Jira:** THL-181 (AC: "If Pearl can't tell who, it asks"), THL-291, THL-289   **Figma:** S-35a 1030:41556 (dark 1030:41771), S-35b 1030:41984 (dark 1030:42199)
On the shared What was this? › Paying me back, this reuses the built "Who paid you back?" sheet (S-09, aa07127/8edd375); no new page. S-35a: the payback names no one, or someone not on any split, and its amount fits more than one open share. Those shares go on top under COULD BE EITHER with nothing ticked, plus the line "Sam and Priya each owe $30.00, so Pearl won't guess. Tick who sent it." Next stays off until she ticks one, and ticking works as on S-09. This replaces S-35's pre-ticked guess. When exactly one share fits, the current "Amount matches" pre-tick stays. S-35b: nothing fits. Every open share is listed with nothing ticked, plus "Jordan isn't on any of your splits, and no one owes $45.00. Tick what it paid back, or search for the purchase." Anything left goes to S-11 v2, and Close saves nothing. VoiceOver labels are in the notes.

### [designBOT → engBOT] 2026-11-09 · TOKENS · Light money-in
**Status:** Redesigned (already approved by the product owner: web tokens follow Figma)
**Jira:** —   **Figma:** library color/text/money-in (read on 538:15997)
The Figma library's light money-in is #167A40, the same as iOS. The web has #1e7b4c, so the web changes to #167A40 along with the dark #6EDB94.

### [engBOT] 2026-11-09 · round 12 start
designBOT's four entries above were written in Figma while round 11 ran; I appended them as given. I checked these by node with get_screenshot and get_metadata (no page-wide metadata): the Superseded tags 1028:41057 and 1028:41073, S-14p 1029:41057, S-05p 1029:41258 (dark 1029:41332) and its note 1029:41407, T-08k error 1030:41151, S-35a 1030:41556 (dark 1030:41771) and its note 1030:42413, and S-35b 1030:41984 (dark 1030:42199) and its note 1030:42416. For the S-35 cases I also opened S-35 545:19575 and S-09 538:14642.

### [engBOT → designBOT] 2026-11-09 · AUDIT-FIGMA · Accepted
1028:41057 reads "Superseded by S-03b v2 994:36736 (dark 1008:40898) — with I had some too on, the rest stays yours (SPLIT-01 b′). With it off, Save stays off as here." 1028:41073 reads "Superseded by S-22 v2 995:37522 (dark 1008:41353)". Both point to the frames that were built. There's one leftover, listed under Still open: S-27's kind step isn't marked superseded.

### [engBOT → designBOT] 2026-11-09 · SPLIT-18/19 · Frames for built behaviour · Accepted
- **S-14p:** matches d2dc59d. Paid back this month shows "Sam · Cash · Nov 13 · paid back Loblaws and Pizza Nova" at $60.00, and the three-purchase row reads "Loblaws, Costco and Pizza Nova" with no "and 2 more".
- **S-05p:** matches. The line under Sam is "$60.00 · paid back Loblaws and Pizza Nova". The note's pattern, "$80.00, $20.00 given back · paid back Loblaws and Pizza Nova", is what the app does: `SplitFlow.swift` `deposited(_:)` prints `whole` first, and `whole` (`Store.splits()`) adds up every piece of the payment, the returned one included. So the first amount is always the whole payment and can't contradict the given-back amount. With nothing else paid back it reads "$60.00, $17.94 given back", as the note says.
- **T-08k error:** matches. No tile is highlighted, and "Couldn't save that. Try again." sits under the grid in the caution color.

### [engBOT → designBOT] 2026-11-09 · THL-181 · S-35a / S-35b · Accepted (built)
Both frames, their dark twins and the notes work. Each case has a way in (What was this? › Paying me back) and a way out (Close saves nothing). The server supports it once the guess is removed. Built below. Two small gaps are logged as SPLIT-22.

### [engBOT → designBOT] 2026-11-09 · TOKENS · Light money-in · Accepted (built)
The web's light `--money-in` is now #167a40, which matches iOS and the Figma library.

### [engBOT → designBOT] 2026-11-09 · SPLIT-22 · Two cases S-35a and S-35b don't draw
**Severity:** Minor
**Jira:** THL-181 ("Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks.")   **Figma:** S-35a 1030:41556, S-35b 1030:41984   **Code:** `ios/Pearl/Views/Transactions/PartsFlow.swift` (`askText`), `finance/splits.py` (`people_status`, ASK_FROM)
**Problem:**
1. **One person, two fits.** Sam owes $30.00 on both Pizza Nova and Loblaws, and $30.00 comes in with no name. There's one name, so "Sam and Sam each owe $30.00" can't be right. For now the app says "Sam owes $30.00 on Pizza Nova and Loblaws, so Pearl won't guess. Tick what it paid back." That's my wording, not a drawn one.
2. **Linked somewhere else.** A payback with no name can still be linked to a split purchase without the sheet: a purchase picked from search, the web's Paid back, or `POST …/paybacks` with no person. If it's dated from 2026-11-10 and two shares fit (or none does), it now counts for nobody, so the purchase is paid back but Sam and Priya both still owe. Nothing on S-04 or S-05 lets her say who it was afterwards.
**Ask:** (1) Confirm or reword the one-person line. (2) Draw where an unassigned payback shows on the split card and how she answers it, or decide that those paths must go through S-35a/S-35b first.

### [engBOT] 2026-11-09 · round 12 · build
Branch `feat/split-bot-round` (PR #315, open, not merged).
- **SPLIT-21, server (`finance/splits.py` `people_status`):**
  - A payback that names nobody on the split, dated on or after `ASK_FROM` (2026-11-10), counts for someone only when exactly one share still owed is its amount. If two shares fit, or none does, it counts for nobody until she says who.
  - Named paybacks are unchanged, and so is the single exact fit.
  - **Old data:** credits are worked out each time they're read; nothing stores who a payback was given to. So with no migration, a payback dated before 2026-11-10 keeps the old rule (exact fit, else the first who still owes) and reads exactly as it did. Only paybacks dated from 2026-11-10 follow the ask rule.
  - **Limit:** an old-dated deposit that she links for the first time now, with no person, still gets the old guess.
  - `/owing` also returns `named`: the name on a deposit when it isn't on any of her splits (for S-35b's "Jordan isn't on any of your splits…"). It's None when the deposit names nobody or names someone who is on a split.
- **SPLIT-21, app (`PartsFlow.swift`, the shared "Who paid you back?" sheet):**
  - When the sender is unknown and exactly one share is the amount left, that share is now ticked, as S-35 drew it ("same amount", "It was Dad" / "None of these").
  - **Two or more fit (S-35a):** COULD BE EITHER lists them with nothing ticked. Under it: "Sam and Priya each owe $30.00, so Pearl won't guess. Tick who sent it." (first names). Anyone else who owes her is under Others who owe you.
  - **None fits (S-35b):** OWES YOU lists every open share with nothing ticked, then "Jordan isn't on any of your splits, and no one owes $45.00. Tick what it paid back, or search for the purchase." With no name, it reads "No one owes $45.00. …".
  - **Rows:** "Sam" over "Pizza Nova · Nov 2 · Sam's share". Under the rows is the Linked / Not linked bar.
  - **Next:** a single Next (or "Link these n purchases"), off until she ticks one. Whatever is left goes straight to "What's the other $x?" (S-11 v2). Close saves nothing, as before.
  - **VoiceOver:** "Sam, Pizza Nova, November 2, $30.00, not selected" (the new `Format.monthDay`). The row speaks its own state rather than also adding the Selected trait.
  - With no open shares at all, the page is still search only ("Search for the purchase, or tap Next if it isn't one.").
- **Web:** light `--money-in` changed from #1e7b4c to #167a40 in `src/tokens/tokens.css` (line 66), edited by hand as in round 11. Dark stays #6edb94.
- **Tests:**
  - New: TestPearlAsksWhoItWas (9) in `tests/test_split_round.py`. It covers two fits, no fit, one fit after a named payback, a named payback, an old payback keeping its credit (both fits, and no fit), `named` for Jordan / no name / someone on a split, and the Swift wiring.
  - I also ran the whole suite with ASK_FROM moved back to 0000-00-00: 1774 passed. So no existing test depends on the old guess, and the cutoff doesn't make the suite depend on the calendar.
  - `python3 -m pytest -q`: 1783 passed, 0 failed.
  - `npm run build`: built.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` file was added.
- **Commit:** 1f5bfd4, "Splits round 12: Pearl asks who a payback is from (SPLIT-21, THL-181), web light money-in #167a40". 6 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:**
  - THL-278's unnamed-payback line now gives the ask rule.
  - THL-181 and THL-278 each got a comment.
  - Nothing was moved; both stay in Testing.

### [designBOT] 2026-11-09 · round 13 start
engBOT isn't running this round, so I'm keeping the log. I read SPLIT-22, THL-181 (its AC, and the PR #98 comment that already had the split card ask "Who sent the $X on …?") and THL-278's unnamed-payback line. In Figma I opened S-35a 1030:41556, S-05p 1029:41258, S-04 v2 1001:38264, S-21 543:16404, S-27 543:17648 and S-11 v2 995:37232 by node. The product owner has already approved the THL-181 ask, so the new frames are tagged "THL-181 · Approved — build".

### [designBOT → engBOT] 2026-11-09 · SPLIT-22a · One person owes it on two purchases
**Status:** Redesigned · THL-181 · Approved — build
**Jira:** THL-181 ("If Pearl can't tell who, it asks"), THL-278   **Figma:** S-35a1 1033:41943 (dark 1033:42155), note 1034:42633
Your line is right, but I've reworded it slightly so it says what she's choosing: **"Sam owes $30.00 on Pizza Nova and on Loblaws, so Pearl won't guess. Tick which one this paid back."** With three or more purchases it lists them: "on Pizza Nova, Loblaws and Costco". If the shares that fit belong to two or more people (for example Sam twice and Priya once), use S-35a's line and name each person once. The sheet is otherwise S-35a: COULD BE EITHER, both rows read "Sam" over their purchase ("Pizza Nova · Nov 2 · Sam's share", "Loblaws · Nov 11 · Sam's share"), nothing is ticked, and Next stays off until she ticks one. VoiceOver already tells the rows apart by purchase ("Sam, Loblaws, November 11, 30 dollars, not selected"). The only change is the `askText` string.

### [designBOT → engBOT] 2026-11-09 · SPLIT-22b · Where she says who sent a payback linked somewhere else
**Status:** Redesigned · THL-181 · Approved — build
**Jira:** THL-181 ("Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks."), THL-278 (search-picked unnamed paybacks)   **Figma:** S-05u 1033:42367 (dark 1033:42469), S-35c 1033:42573 (dark 1033:42879), S-35c error 1033:42728 (dark 1033:43032), S-21u 1033:43183 (dark 1033:43339); notes 1034:42636, 1034:42639, 1034:42642, 1034:42645
I'm not blocking those paths. Search, the web and the API can still link it, and Pearl asks afterwards in the places she already looks. No new page: the ask reuses the built "Who paid you back?" sheet and the existing "Who sent this?" chip.
- **S-05u, the split card:** a payback linked to this purchase that the ask rule left credited to no one (dated from ASK_FROM) shows under PAID BACK as "$30.00 from an e-Transfer" / "Nov 16 · no name · paid back Loblaws" / "Who sent this?" in the accent colour, with a chevron. It has no amount column. Sam and Priya stay under OWED TO YOU with "Owes you $30.00". If there are several, each gets its own row, newest first. With none, the card is S-05p / S-04 v2 as built. VoiceOver: "30 dollars from an e-Transfer, November 16, not credited to anyone yet. Who sent this? Button."
- **S-35c, the sheet** (S-09/S-35a, titled "Who sent this?"), opened from S-05u, S-21u's chip, or the deposit in Transactions. It's already linked, so there's no search field. It lists only the open shares on the purchase(s) the payback pays back, under ON LOBLAWS (or ON LOBLAWS AND PIZZA NOVA), with nothing ticked, plus "Sam and Priya each owe $30.00 on Loblaws, so Pearl won't guess. Tick who sent it." The bar reads Credited / Not credited. Save stays off until she ticks someone; ticking works as on S-09. Save credits it in one request, closes the sheet and shows "Sam paid back $30.00 · Undo". Sam moves to PAID BACK and the S-05u row disappears. Anything above the share goes to S-11 v2 ("What's the other $15.00?"). If no one owes that amount: "No one on Loblaws owes $45.00, so Pearl won't guess. Tick who sent it." If only one person is on the split: "Sam owes $42.06 on Loblaws and this is $30.00, so Pearl won't guess. Tick Sam if it was them." Close saves nothing and the row stays. While saving, Save shows a spinner.
- **S-35c error:** Sam stays ticked. The line becomes "Couldn't save that. Try again." in color/text/caution (as on T-08k), and Save stays on so she can try again.
- **S-21u, Needs a look:** the same deposit is one row in To sort ("Interac e-Transfer · Nov 16 · paid back Loblaws · +$30.00") with the existing "Who sent this?" chip, which opens S-35c. In Quick sort it's one card. Yes/Skip can't answer who, so the card opens S-35c as a sheet. The tick is held for the card as "Paid back by Sam?": Yes saves it with one Undo, and Skip drops it, the same as SPLIT-20. This is the Paying me back follow-up on the one What was this? page, not a new answer.
- **Server needs:** the split's `people_status` (or `/owing`) returns its uncredited paybacks: id, amount, date, sender name if any, and the purchases it pays back. Answering also needs a way to set the person on an existing link, with Undo. Old-dated paybacks keep their old credit, so they never show this row.

### [designBOT → engBOT] 2026-11-09 · AUDIT-FIGMA · S-27's kind step superseded
**Status:** Redesigned
**Jira:** THL-289, THL-291   **Figma:** S-27 543:17648 (dark 543:19084), tags 1033:41939, 1033:41941
I opened S-27 first. It's the old parts sheet ("The other $172": A gift $108.00, Pays back Loblaws $64.00, Review / Add a part), where each part gets its kind. S-11 v2 995:37232 (dark 1008:41065) replaces that: every kind is a tile that answers at once for How much of it?, and the page comes back for what's left (SPLIT-04). Both S-27 frames are now 40% with "Superseded ·" names and the red tag "Superseded by S-11 v2 995:37232 (dark 1008:41065) …", the same style as round 11. There's nothing to build.

### [engBOT] 2026-11-09 · round 14 start
designBOT's three round-13 entries above were left uncommitted in the working tree; I've committed them with mine, unchanged. I checked these by node only (get_screenshot, plus get_metadata on 1033:42155): S-35a1 1033:41943 (dark 1033:42155), S-05u 1033:42367 (dark 1033:42469), S-35c 1033:42573 (dark 1033:42879), S-35c error 1033:42728 (dark 1033:43032), S-21u 1033:43183 (dark 1033:43339), the notes 1034:42633, 1034:42636, 1034:42639, 1034:42642 and 1034:42645, and the S-27 tag 1033:41939. I also re-read THL-181.

### [engBOT → designBOT] 2026-11-09 · SPLIT-22a · Accepted (built)
S-35a1 and its note match the entry. Both rows read "Sam" over their purchase, nothing is ticked, Next is off until a tick, and the line is "Sam owes $30.00 on Pizza Nova and on Loblaws, so Pearl won't guess. Tick which one this paid back." The dark twin has the same layers (metadata 1033:42155: "Why Pearl asks", Next off). Built below.

### [engBOT → designBOT] 2026-11-09 · SPLIT-22b · Accepted (built), with SPLIT-23
- **S-05u:** the frame and its dark twin draw PAID BACK with "$30.00 from an e-Transfer" / "Nov 16 · no name · paid back Loblaws" / "Who sent this?" and a chevron, with Sam and Priya under OWED TO YOU. Note 1034:42636 gives the VoiceOver line.
- **S-35c:** titled "Who sent this?", with no search, ON LOBLAWS, both shares unticked, the S-35a-style line, a Credited / Not credited bar and Save off. Note 1034:42639 covers the other two lines, the extra going to S-11 v2, Close and the spinner.
- **S-35c error:** Sam stays ticked, "Couldn't save that. Try again." is in the caution colour, the bar reads "Credited $30.00 to Sam", and Save is on. Note 1034:42642 adds the VoiceOver announcement.
- **S-21u:** "Interac e-Transfer · Nov 16 · paid back Loblaws · +$30.00" with the dashed "Who sent this?" chip, light and dark. Note 1034:42645 covers Quick sort's held "Paid back by Sam?".

Every case has a way in (S-05u, S-21u, Quick sort) and a way out (Close saves nothing), and the server now supports it. Built below. Three small gaps are logged as SPLIT-23.

### [engBOT → designBOT] 2026-11-09 · AUDIT-FIGMA · S-27's kind step superseded · Accepted
1033:41939 reads "Superseded by S-11 v2 995:37232 (dark 1008:41065) — the kind step is now the shared What was this? tiles: each answers at once for How much of it?, and the page comes back as "What's the other $x?" for what's left (SPLIT-04). No Add a part or Review here." This closes the leftover from round 12.

### [engBOT → designBOT] 2026-11-09 · SPLIT-23 · Three edges S-35c doesn't draw
**Severity:** Minor
**Jira:** THL-181 ("Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks.")   **Figma:** S-35c 1033:42573, note 1034:42639; S-05u 1033:42367   **Code:** `ios/Pearl/Views/Transactions/WhoSentSheet.swift` (`toggle`, `save`), `ios/Pearl/Views/Transactions/TransactionDetailView.swift` ("Pays back" › Options), `finance/splits.py` (`people_status`, `credit_question`)
**Problem:**
1. **Entry from the deposit's own page.** Note 1034:42639 says S-35c also opens from "the deposit in Transactions (What was this? › Paying me back, already answered)". A linked deposit's page has no What was this? card. It shows Pays back, then Options › Unlink. So nothing drawn leads to S-35c from there. I didn't add a row. If the deposit's page is opened from its Needs a look question, S-35c opens (built).
2. **Nobody left owing.** Example: Sam and Priya have each paid $30.00 on Loblaws by name, and an unnamed $30.00 is linked to it from search. No share is open, so there's nothing to tick, and the payback counts for no one. I show no S-05u or S-21u row for it, because S-35c would be empty. The purchase reads as paid back, but this payback is credited to no one.
3. **One payment, two people.** A payback over Loblaws and Pizza Nova lists the open shares on both. Pearl stores one sender per payment, so ticking Priya after Sam replaces Sam's tick instead of adding to it. The note says "ticking works as on S-09", where ticks add up.
**Ask:** (1) Draw the deposit-page entry, or confirm S-05u and S-21u are enough. (2) Decide what happens when nobody is left owing: say who anyway (list everyone on the split?), or leave it uncredited. (3) Confirm one sender per payment, or say how one payment from two people should look.

### [engBOT] 2026-11-09 · round 14 · build
Branch `feat/split-bot-round` (PR #315, open, not merged). Commit 1ca13a6.
- **SPLIT-22a (`PartsFlow.swift` `askText`):**
  - One person on two purchases: "Sam owes $30.00 on Pizza Nova and on Loblaws, so Pearl won't guess. Tick which one this paid back."
  - Three or more: "on Pizza Nova, Loblaws and Costco".
  - Two or more people still get S-35a's line, with each name once.
- **SPLIT-22b, server:**
  - `people_status` takes `left_out`, which collects each payback the ask rule credits to no one while someone still owes.
  - `splits.uncredited` and `uncredited_rows` feed the new `splitting.uncredited` (id, amount here, whole, date, sender, word, name, paid_back), newest first.
  - `credit_question` lists the open shares on every purchase the payback covers.
  - `GET /api/transactions/<id>/credit` returns the question, or None.
  - `POST /api/transactions/<id>/credit {person, charge?}` sets `txn_payback_person` on the existing link (`Store.set_payback_person`); "Priya" matches "Priya S.". The link and the amounts stay. Its title is what's newly credited ("Sam paid back $30.00"), and its Undo is the new `payback_person` mark in `undo_marks`.
  - Needs a look adds `credit:<id>` rows to `who_sent`, with `credit.paid_back`. A linked payback never gets the bank-name row, so each is listed once, and Quick sort walks the same list. Old-dated paybacks never show.
  - **Fix:** splitting a linked deposit into parts used to drop its link with no way back. Its Undo now links it back as it was (`paybacks` and `payback_more` marks).
- **SPLIT-22b, app:**
  - **S-05u:** PAID BACK rows on the split card (`SplitPeople.uncreditedRow`). The people caption reads OWED TO YOU while anyone owes. VoiceOver reads the note's line.
  - **S-35c:** the new `WhoSentSheet.swift`, with the three lines from the note, a Credited / Not credited bar ("to Sam" once ticked), Save off until a tick, and a spinner while saving.
  - **S-35c error:** Sam stays ticked, the line becomes "Couldn't save that. Try again." in `Pearl.caution`, Save stays on, and VoiceOver announces it.
  - **Over the share:** Save opens `PartsSheet(credited:)` on "What's the other $15.00?" (S-11 v2), with Sam's payback part filled in. Both are saved in one parts request, and Close saves nothing.
  - **Opened from:** S-05u, Needs a look's chip (S-21u: "Nov 16 · paid back Loblaws"), and the deposit page's question card.
  - **Quick sort:** the tick is held as "Paid back by Sam?". Yes sends one POST with one Undo, and Skip drops it. Over the share, the parts save from the sheet, as S-28's sheet already does.
- **Web:** the web's Needs a look lists the same `who_sent` row. Naming the sender there (PUT …/party) credits them, and a test covers it. No web code changed.
- **Tests:**
  - New: TestWhoSentThis (15) and TestOnePersonTwoPurchases (1) in `tests/test_split_round.py`.
  - `python3 -m pytest -q`: 1799 passed.
  - `npm run build`: built.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - `WhoSentSheet.swift` was added, and `make_project.py` was run (46 Swift files).
- **Commit:** 1ca13a6, 15 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:** commented on THL-181. Nothing was moved; it stays in Testing.

### [product owner] 2026-11-09 · SPLIT-23 (1): nobody left owing → "What's the other $x?"
An unnamed payback linked to a purchase where nobody still owes isn't left uncredited. It goes to "What's the other $x?" (S-11 v2 995:37232) as extra money, like any other leftover, and Pearl asks there.

### [product owner] 2026-11-09 · SPLIT-23 (2): one sender per payment
One sender per payment stays. One transfer comes from one person, so picking someone else replaces the tick.

### [product owner] 2026-11-09 · SPLIT-23 (3): no entry on the deposit's own page
There's no "Who sent this?" entry on the linked deposit's own page; S-05u and S-21u are enough. Remove that entry point from the S-35c note 1034:42639.

### [designBOT] 2026-11-09 · round 15 start
engBOT isn't running this round, so I'm keeping the log. I read SPLIT-23 and THL-181 (its AC and all six comments, including round 14's "one edge left"). In Figma I opened S-21u 1033:43183, S-11 v2 995:37232, S-35c 1033:42573 and its note 1034:42639 by node. The product owner approved all three answers, so the new frames are tagged "THL-181 · Approved — build".

### [designBOT → engBOT] 2026-11-09 · SPLIT-23 (1) · Nobody left owing: Needs a look asks "What was this?"
**Status:** Redesigned · THL-181 · Approved — build
**Jira:** THL-181 ("Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks."), THL-291 (S-11 v2), THL-278   **Figma:** S-21x 1037:43551 (dark 1037:44012), S-11x 1037:43724 (dark 1037:44185); tags 1037:44471–1037:44474; notes 1037:44475, 1037:44476
**Where she meets it: the Needs a look row, not the split card.** Once nobody owes, the question is no longer "who sent this?" about Loblaws. It's "what was this money?" about the deposit, and that's a sorting answer. Sorting answers live on the one What was this? page, which has to be reachable from Transactions, Needs a look and Quick sort. A Needs a look row covers all three: Quick sort walks the same list, and opening the deposit from the row shows its question card (as built). A row on the Loblaws split card would only exist in Transactions, and it would put a question about a different transaction on a purchase that is fully paid back. So the split card shows nothing new and gets no S-05u row.
- **S-21x, Needs a look › To sort:** one row for that one deposit, "Interac e-Transfer" / "Nov 16 · extra on Loblaws" / +$30.00, with the existing "What was this?" chip. It's S-21u's row with new copy; the row component is unchanged. Answering removes it. Only paybacks dated from ASK_FROM get the row, as with S-05u. VoiceOver: "Interac e-Transfer, November 16, extra on Loblaws, plus 30 dollars. What was this? Button."
- **S-11x, the chip's page:** this is S-11 v2 (the shared tiles), opened for the whole payback. The title is "The $30.00", because there is no "other": the whole amount is extra. "How much of it?" reads $30.00. Under it, in S-35c's "Why Pearl asks" style: "Sam and Priya have both paid you back for Loblaws, so this $30.00 is extra. Tap what it was." For one person it reads "Sam has paid you back for Loblaws, so …", and for two purchases "… for Loblaws and Pizza Nova, so …". Every tile answers at once, as on S-11 v2. Paying me back opens S-09 so she can pick another purchase or person; Loblaws isn't listed because nobody owes on it. "Sort the rest later" reads "Sort it later" here and leaves the row in place. The error is T-08k's "Couldn't save that. Try again." under the grid. Close saves nothing.
- **Quick sort:** it's one card. Yes or Skip can't answer it, so the card opens S-11x as a sheet. The tile she taps is held for the card (for example "A gift?"). Yes saves it with one Undo, and Skip drops it, the same as SPLIT-20 and S-21u.
- **Server needs:**
  - List these paybacks (linked, dated from ASK_FROM, no name, and no open share on any purchase they pay back) as Needs a look rows, separate from `credit:<id>` because the question is different.
  - Saving a tile moves the $30.00 off Loblaws, where it changed nothing, and records the answer in one request. Its Undo links it back as it was (the round-14 `paybacks` marks).
  - After that, `left_out` is empty for it, so THL-181's "credited to someone" holds on every path: either a person is ticked (S-35c), or the money is no longer a payback.

### [designBOT → engBOT] 2026-11-09 · SPLIT-23 (2) and (3) · S-35c note: one sender, two ways in
**Status:** Redesigned · THL-181 · Approved — build
**Jira:** THL-181   **Figma:** note 1034:42639 (rewritten, now 560 wide so it clears the dark twin), tags 1034:42637 and 1034:42638
- **(2) One sender per payment:** the note now says it. One transfer comes from one person, so ticking someone else replaces the tick instead of adding to it, even across ON LOBLAWS AND PIZZA NOVA. That's unlike S-09, where ticks add up. `WhoSentSheet` already does this, so there's nothing to change.
- **(3) Ways in:** the note now reads "Opened from S-05u (the split card) or S-21u's chip (Needs a look, and its Quick sort card)". It says the linked deposit's own page has no "Who sent this?" entry, and the "or the deposit in Transactions" clause is gone. Both tags now read "(from the split card or Needs a look)" instead of "(from the split card, Needs a look or Transactions)". Opening the deposit from its Needs a look question still shows S-35c, as built. That's still the S-21u way in, not a separate entry.
- The note also points the nobody-left-owing case to S-21x › S-11x.

### [engBOT] 2026-11-09 · round 16 start
This is the last round of the bot loop. designBOT's round-15 entries and its Summary edits above were left uncommitted; I've committed them with mine, unchanged. I checked these by node only (get_screenshot, plus get_metadata on the notes and the first tag): S-21x 1037:43551 (dark 1037:44012), S-11x 1037:43724 (dark 1037:44185), the tags 1037:44471–1037:44474, the notes 1037:44475 and 1037:44476, the S-35c note 1034:42639 and its tags 1034:42637 and 1034:42638.

### [engBOT → designBOT] 2026-11-09 · SPLIT-23 (1) · Accepted (built)
- **S-21x:** the light and dark frames draw the To sort row "Interac e-Transfer" / "Nov 16 · extra on Loblaws" / +$30.00 with the dashed "What was this?" chip. Note 1037:44475 gives the VoiceOver line and says the Loblaws split card shows nothing new.
- **S-11x:** titled "The $30.00", "How much of it?" $30.00, then "Sam and Priya have both paid you back for Loblaws, so this $30.00 is extra. Tap what it was." over the S-11 v2 tiles, with Options › "Sort it later". The dark twin matches. Note 1037:44476 covers one person, two purchases, Paying me back → S-09 without Loblaws, T-08k's error, Close and Sort it later.
- **Tags:** 1037:44471–44474 read "THL-181 · THL-278 · S-21x · Needs a look: a payback with nobody left owing" and "THL-181 · THL-291 · THL-278 · S-11x · The $30.00 (S-11 v2, nobody left owing)", light and dark, each "THL-181 · Approved — build".

Every case has a way in (Needs a look, its Quick sort card, and the deposit's own question card) and a way out (Close or Sort it later saves nothing). The server already supported the save. Built below. One drawing detail is listed under Still open for the product owner: the frame's "Dad overpaid" tile.

### [engBOT → designBOT] 2026-11-09 · SPLIT-23 (2) and (3) · Accepted
- **Note 1034:42639** now says one sender per payment ("ticking someone else replaces the tick instead of adding to it, even across two purchases (unlike S-09…)"), names only S-05u and S-21u's chip as ways in, says the linked deposit's own page has no "Who sent this?" entry, and sends nobody-left-owing to S-21x › S-11x.
- **Tags** 1034:42637 and 1034:42638 read "(from the split card or Needs a look)", light and dark.
- **Code, (2):** `WhoSentSheet.toggle` clears the ticks when she ticks a different person (`if let who = person, who != s.person { picked = [] }`). It matches; no change.
- **Code, (3):** the deposit's page opens S-35c only from its Needs a look question card (`openQuestion`, the S-21u way in) and from S-05u on the split card. It matches; the only change is a stale comment in `TransactionDetailView.swift` that still said "or from the deposit itself".

### [engBOT] 2026-11-09 · round 16 · build
Branch `feat/split-bot-round` (PR #315, open, not merged). Commit 34af59b.
- **Server:**
  - `people_status` takes `extra_out`. It collects each unnamed payback dated from ASK_FROM that came when nobody on the split still owed anything.
  - The new `splits.extra_question` is asked only when every purchase the payback pays back is split and it is extra on all of them. It returns id, amount, date, purchases, `paid_back` and `people` (who has paid back there).
  - Needs a look lists it in `money_in` as `extra:<id>` with `guess: {action: "extra"}` and `extra: {paid_back, people, amount}`. That keeps it apart from `credit:<id>`. Quick sort walks the same list, and `ids_in` gives the deposit its question card.
  - `pairs.annotate` skips these rows, so no evidence question rides on one.
  - A tile saves through `POST …/parts`. It already unlinks a linked payback and returns an Undo that links it back as it was (the round-14 `paybacks` / `payback_more` marks).
  - **Fix:** the web answers the same row through `POST …/mark`. For Paying me back, its Undo now also restores `payback_more`, so a payback over two purchases comes back on both.
- **App (`PartsSheet(whole:)`, S-11x):**
  - Opens on the tiles for the whole amount, titled "The $30.00". Under "How much of it?" it reads "Sam and Priya have both paid you back for Loblaws, so this $30.00 is extra. Tap what it was." One person: "Sam has …". Three or more: "… have all …". Two purchases: "for Loblaws and Pizza Nova".
  - A tile that uses up the amount saves at once (or is held), with no Check and save.
  - Paying me back opens S-09 with the open shares from `/owing`, so Loblaws isn't listed.
  - Options › "Sort it later" closes and leaves the row. Close saves nothing.
  - On error, nothing stays chosen, and "Couldn't save that. Try again." shows under the grid in `Pearl.caution`, announced to VoiceOver.
  - The overpaid tile names the one person who paid back ("Sam overpaid"). It isn't offered when more than one did (see Still open).
  - Typing less than the whole continues as S-11 v2 does ("What's the other $x?").
- **App, wiring:**
  - `Review.Item.extra` is new. The row reads "Nov 16 · extra on Loblaws" with the "What was this?" chip (`Ask.chip`).
  - Needs a look's chip opens S-11x. So does the deposit page's question card (`openQuestion`).
  - Quick sort holds the answer for the card as `ReviewAnswer.extra` ("A gift?"). Yes sends the one parts request with its Undo, and Skip drops it.
- **Tests:**
  - New: TestNobodyLeftOwing (10) in `tests/test_split_round.py`. It covers the row and its keys, no S-05u / credit row, one row per deposit, Quick sort's list, a tile with Undo, Paying me back to another purchase with Undo, the web's /mark with Undo over two purchases, one person, still owing (S-35c instead), old or named (no row), skip, the THL-181 invariant, and the Swift wiring.
  - `python3 -m pytest -q`: 1809 passed.
  - `npm run build`: built.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` file was added, so `make_project.py` wasn't needed.
- **Commit:** 34af59b, 10 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:** commented on THL-181 (whether its AC is now met on every path). Nothing was moved; it stays in Testing.

### [product owner] 2026-11-09 · Round 16 notes decided
- **Two purchases, extra on one:** made a ticket, THL-301 (Bug, To Do). It's the one place THL-181's "credited to someone" isn't met yet.
- **Paybacks dated before 2026-11-10:** accepted. They keep the old guess on purpose, so past numbers don't change.
- **S-11x overpaid tile:** accepted as built. It names the one person who paid back ("Sam overpaid") and is hidden when more than one did.
- **S-11x answer stored as one part:** accepted as built.
- **Less than the whole on S-11x:** accepted. It carries on as S-11 v2 does.

### [designBOT] 2026-11-09 · THL-301 start
engBOT isn't running this round, so I'm keeping the log. The product owner approved working on THL-301. I read THL-301 (no comments or links yet; its AC: every extra part asked about once, answering it leaves the other purchases' credit alone with Undo, Paid back + Owes still equal each share), THL-181's AC, and SPLIT-21/22/23 above. In Figma I opened S-21x 1037:43551, S-11x 1037:43724, S-21u 1033:43183 and the S-35c error 1033:42728 by node, plus the S-21x/S-11x notes 1037:44475 and 1037:44476. The new frames are tagged "THL-301 · Approved — build". No code was touched.

### [designBOT → engBOT] 2026-11-09 · SPLIT-24 · A payback over two purchases that's extra on only one
**Status:** Redesigned · THL-301 · Approved — build
**Jira:** THL-301, THL-181 ("Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks."), THL-278, THL-291   **Figma:** S-21xw 1043:1005 (dark 1043:1311), S-21xm 1043:1041 (dark 1043:1347), S-11xm 1043:1077 (dark 1043:1383), S-11xm over 1043:1194 (dark 1043:1498); tags 1044:99–1044:106; notes 1044:107–1044:110. Section 536:14142 widened to 39400 to fit them.
Example: an unnamed $60.00 e-Transfer, dated from ASK_FROM, linked to Loblaws (nobody owes) and to Pizza Nova (Jo owes $30.00). I drew new frames rather than notes on S-21x/S-11x. The row meta, the S-11x header, the "is extra" line and the overpaid tile all change, and a note can't show the over-the-extra state or the meta wrapping to two lines. S-21x and S-11x stay as they are for the whole-extra case.
- **One row, never two, and who comes first.** One deposit is one row in Needs a look and one card in Quick sort ("one card is one transaction"), so To sort counts it once. Pizza Nova's question comes first because the extra line and the overpaid tile need to know who sent it. If the ask rule already credits Jo (Jo alone owes $30.00, an exact fit), there's no first question and S-21xm shows straight away.
- **S-21xw (only when Pizza Nova's part needs S-35c, for example Jo and Kim each owe $30.00):** "Interac e-Transfer" / "Nov 16 · paid back Pizza Nova and Loblaws" / +$60.00, with the existing "Who sent this?" chip. S-35c lists ON PIZZA NOVA only. Save credits that part as built ("Jo paid back $30.00 · Undo") and closes. It does **not** chain into "What's the other $x?", so the credit and the extra each have their own Undo (THL-301: "Answering the extra part leaves the other purchases' credit alone"). The row stays where it is and becomes S-21xm. If she undoes the credit, it turns back into S-21xw. In Quick sort, the card holds "Paid back by Jo?". Yes saves the credit only, and the same deposit comes back as the next card (S-21xm), so it never has two cards at once.
- **S-21xm, the row (part vs whole):** the amount column is always the whole deposit, +$60.00. The meta names the part: **"Nov 16 · $30.00 extra on Loblaws"**. The amount appears in the meta only when the extra is less than the deposit, so S-21x keeps "extra on Loblaws". Extra on two purchases reads "$50.00 extra on Loblaws and Costco", still one row asked once. The meta wraps to two lines rather than truncating (it truncated at one line in the frame). The chip is "What was this?" and opens S-11xm, as do the deposit's question card and the Quick sort card (the tile is held, e.g. "A gift?"; Yes saves with one Undo; Skip drops it). VoiceOver: "Interac e-Transfer, November 16, 30 dollars extra on Loblaws, plus 60 dollars. What was this? Button."
- **S-11xm, the page:** the title is **"The $30.00"** (the part), and the header keeps the whole deposit, "$60.00 · Nov 16", so both show. How much of it? reads $30.00 and is capped there. **The "is extra" line for the mixed case:** "Jo paid back $30.00 of this for Pizza Nova. Sam and Priya have both paid you back for Loblaws, so the other $30.00 is extra. Tap what it was." The usual variants apply: one person ("Sam has paid you back …"), credited on two purchases ("… for Pizza Nova and Costco."), extra on two ("… for Loblaws and Costco, so the other $50.00 is extra."). A tile saves in one request that takes the $30.00 off Loblaws and leaves Jo's $30.00 on Pizza Nova untouched. Its Undo links it back to Loblaws. Paying me back opens S-09 with only the open shares. Less than $30.00 carries on as S-11 v2. Sort it later, Close and the T-08k error line are as on S-11x.
- **Overpaid tile, this case only:** it names the sender credited on this deposit, "Jo overpaid" (Jo sent $60.00 and owed $30.00). On S-11x the round-16 rule is unchanged (the one person who paid back, hidden when there are several). Product owner: say if you'd rather keep the round-16 rule here too.
- **S-11xm over (the amounts don't add up):** she types $45.00. The line turns color/text/caution: "Only $30.00 of this is extra. Jo's $30.00 for Pizza Nova stays as it is, so make it $30.00 or less." VoiceOver announces it, and the tiles dim to 40% and don't answer until the amount is $30.00 or less.
- **Server needs:** `extra_question` asks when the payback is extra on *some* of its purchases (not only all of them), with `amount` set to the extra part and `whole` set to the deposit, plus `credited` (person, purchases, amount) for the line. The row should be one `money_in` item per deposit. It is `credit:<id>` while a part is uncredited, then `extra:<id>`, never both at once. The parts save moves only the extra links, and its Undo restores only those (`paybacks` / `payback_more`). Paybacks dated before ASK_FROM keep the old guess (product owner, round 16).

### [engBOT] 2026-11-09 · THL-301 start
designBOT's THL-301 entries above were left uncommitted. I've committed them with mine, unchanged. I read THL-301: no comments yet, three ACs. I checked these by node only, with get_screenshot and get_metadata: S-21xw 1043:1005 (dark 1043:1311), S-21xm 1043:1041 (dark 1043:1347), S-11xm 1043:1077 (dark 1043:1383), S-11xm over 1043:1194 (dark 1043:1498), the tags 1044:99, 1044:101, 1044:103, 1044:105 and 1044:106, and the notes 1044:107–1044:110.

### [engBOT → designBOT] 2026-11-09 · SPLIT-24 · Accepted (built)
- **S-21xw:** "Interac e-Transfer" / "Nov 16 · paid back Pizza Nova and Loblaws" (two lines) / +$60.00 with the "Who sent this?" chip, light and dark. Note 1044:107 says it shows only when Pizza Nova still needs S-35c. S-35c lists ON PIZZA NOVA only, and Save credits and closes with no chaining. Undo turns the row back. Quick sort holds "Paid back by Jo?", and the deposit comes back as the next card.
- **S-21xm:** "Nov 16 · $30.00 extra on Loblaws" (two lines) / +$60.00 with "What was this?", light and dark. Note 1044:108 covers part vs whole, two purchases, Quick sort, the question card and VoiceOver.
- **S-11xm:** "The $30.00" over "$60.00 · Nov 16", How much of it? $30.00, and "Jo paid back $30.00 of this for Pizza Nova. Sam and Priya have both paid you back for Loblaws, so the other $30.00 is extra. Tap what it was." The grid includes "Jo overpaid". Light and dark match, and note 1044:109 covers the variants.
- **S-11xm over:** $45.00 typed, the caution line "Only $30.00 of this is extra. Jo’s $30.00 for Pizza Nova stays as it is, so make it $30.00 or less.", tiles at 40%, light and dark. Note 1044:110 adds VoiceOver and how it comes back.
- **Tags:** each frame reads "THL-301 · THL-181 · … · THL-301 · Approved — build", and the dark tags end with "· Dark".

Every case has a way in (Needs a look, its Quick sort card, and the deposit's question card) and a way out (Close or Sort it later saves nothing). Each answer has its own Undo. The server needed the changes below. **Overpaid tile:** "Jo overpaid" names the one sender credited on this deposit. That follows the product owner's accepted round-16 rule (one person known, so name them; several, so don't offer it). It isn't a new rule, so there's nothing left to decide.

### [engBOT] 2026-11-09 · THL-301 · build
Branch `feat/split-bot-round` (PR #315, open, not merged). Commit 68579a1.
- **Server:**
  - `splits.extra_question` now also asks when the payback is extra on *some* of its purchases. It returns `amount` (the extra: the deposit less what was credited), `whole`, and `credited` (purchase, person, amount). It returns None while any purchase still has it in `left_out`. Who comes first, so Needs a look has one item per deposit: `credit:<id>`, then `extra:<id>`, never both.
  - `people_status` takes `credited_to`, which records who each payback counted for. A payment over several purchases whose sender was named (S-35c) for another of them now goes to `extra_out` on a purchase where nobody owes. Before this change it counted for no one there.
  - `review`: the `extra:<id>` row carries `whole` and `credited` when only part is extra, and its reason names the amount. The `credit:<id>` row lists the purchases she's asked about first ("paid back Pizza Nova and Loblaws").
  - `POST …/parts` with `extra: true` (`parts_api.extra_parts` / `save_parts`) keeps each credited part as a payback to the same purchase and person, and adds her answer. Over the extra it returns S-11xm over's line as a 400. The Undo is the round-14 `paybacks` / `payback_more` marks, which link it back as it was, with Jo still named. The toast counts only her answer.
  - The web's `/mark` on the same row maps the answer to that one part (gift, income, own money, savings, loan, money lent back, payback, refund, reimbursement) and saves it the same way. Cash, joint and Not mine are refused for a partly-extra payback, because they'd undo Jo's credit.
  - Paybacks dated before ASK_FROM are unchanged.
- **App:**
  - `Review.Item.Extra` has `whole`, `credited` and `isPart`.
  - **Row (`ReviewView`):** "Nov 16 · $30.00 extra on Loblaws" when only part is extra, and "extra on Loblaws" otherwise. The S-21xw and S-21xm meta wraps to two lines.
  - **Openers:** `PartsDeposit.part(of:)` opens S-11xm on the extra amount, with `whole` for the header. It's used from Needs a look, the Quick sort card and the deposit's question card.
  - **S-11xm (`PartsSheet`):**
    - The header reads "$60.00 · Nov 16".
    - The title is "The $30.00", with the mixed line, including several senders or purchases.
    - The overpaid tile names the credited sender.
    - Over the extra, the line turns to `Pearl.caution`, the tiles dim to 40% and are disabled, and VoiceOver announces it.
    - The save sends `extra: true`.
  - **S-35c (`WhoSentSheet`):** the line and bar use only what was paid toward the purchases she's asked about (it said "each owe $60.00" before). It doesn't chain into parts when a purchase it pays back has no open share.
  - **Quick sort:** after Yes on "Paid back by Jo?", the `extra:<id>` card for the same deposit goes in as the next card. Undo puts the deck back without it.
- **Tests:**
  - New: TestExtraOnSome (10) in `tests/test_split_round.py`. It covers credited by the ask rule, who first then the extra (never both) with Undo back to S-21xw, a tile taking only the extra with Undo, the cap, less than the extra, overpaid, extra on two purchases, old paybacks, the web answer, and the Swift wiring. Each AC is covered, including Paid back + Owes = share.
  - `python3 -m pytest -q`: 1819 passed.
  - `npm run build`: built.
  - `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. Not run by hand in a simulator.
  - No `.swift` file was added, so `make_project.py` wasn't needed.
- **Commit:** 68579a1, 11 files; `git show --stat` checked. Pushed, and PR #315's body updated.
- **Jira:** commented on THL-301 and moved it to Testing. THL-181 wasn't commented on, because one edge (below) means its "credited to someone" isn't met on every path yet.

### [product owner] 2026-11-09 · THL-301 notes decided, bot loop stopped
- **Named sender not on one of the purchases:** made a low-priority ticket, THL-302 (Bug, To Do). No bot round now.
- **Split plus unsplit purchase, S-35c over the share in the mixed case, web refusals on a partly-extra payback:** accepted as they are.
- **Bot loop:** stopped here. Next: test PR #315 by hand on a device, then merge.

### [product owner] 2026-11-09 · Figma clean-up
- Cash flow, transaction, sorting, Needs a look and Quick sort sections moved from the "Pearl app" page to a new "Cash flow" page (`1051:44500`). Node IDs are unchanged, so every node ID in this log still works.
- Every frame marked superseded was deleted, with its ticket and status tags. This covers the split frames listed as superseded in round 11 and round 13 (S-02, S-03b, S-04, S-06, S-11, S-11n, S-12, S-15, S-17, S-22, S-27, S-33, S-36b, light and dark). Their node IDs in earlier entries no longer exist.

### [designBOT] 2026-11-09 · SPLIT-25 start
engBOT isn't running, so I'm keeping the log. The product owner tested by hand and reported: "if I wanted to unlink a paid back I had to do it from the paid back itself rather than the transaction it paid back for (which I want it to do)." I've logged it as SPLIT-25. The product owner asked for this behaviour, so the frames are tagged "Approved — build".

Jira already requires it:
- THL-291 AC: "Unlinking any part from either side restores both sides."
- THL-289 flow 7: "unlink or edit from either side."

I read THL-291, THL-289, THL-181, THL-260 (a payback that made the split takes its sender off again) and THL-264. In Figma I opened, by node only, S-05p 1029:41258, S-34 545:19355 (dark 545:21336), S-04 v2's action sheet 1001:38345 (dark 1008:40267) and S-12d's toast 998:37835 (dark 1007:39754). No code was touched.

**What the code does today** (main):
- **Split purchase:** SplitFlow.swift `SplitPeople` disables a row once that person has paid in full (`.disabled(p.owes < 0.005 && p.letGo == nil)`), and a partly-paid person's dialog has no Unlink. TransactionDetailView.swift's "Paid back with" rows are only tappable when `t.splitting == nil`. So a split purchase can't unlink anything.
- **Unsplit purchase:** its PAID BACK rows already open S-34 and call `DELETE …/paybacks/<inflow>`.
- **Refunded by:** these rows aren't tappable. "Unlink refund" exists only on the refund itself.
- **Cash or another app:** these can only be removed by Undo or Edit split.
- **Server, `api.remove_payback`:**
  - It 404s unless `inflow.repays == txn_id`, so a payback where this purchase is the second or third it paid can't be unlinked from this purchase.
  - `store.unlink_payback` deletes `txn_payback_more`, so unlinking from one purchase would unlink every purchase it paid.
  - It runs `drop_payer_all`, which takes the person off every split it made, not only this one.
  - It returns no Undo.
- **Server, `repaid_by`:** it lists only `x.repays == txn_id`, so the second purchase doesn't show the payback at all.
- **Server, cash:** `split_cash_undo` refuses cash that a deposit holds ("Unlink the deposit first").

### [designBOT → engBOT] 2026-11-09 · SPLIT-25 · Unlink a payback from the purchase it paid back
**Status:** Redesigned · SPLIT-25 · THL-291 · Approved — build
**Jira:** THL-291 ("Unlinking any part from either side restores both sides"), THL-289 flow 7, THL-181, THL-260, THL-264, THL-279   **Figma:** S-05v 1069:29642 (dark 1069:29742), S-05o 1069:29844 (dark 1069:30227), S-34s 1069:29931 (dark 1069:30314), S-34s error 1069:30029 (dark 1069:30410), S-05t 1069:30128 (dark 1069:30507), S-34k sheets 1069:30782, 30808, 30834, 30860, 30886, 30912, 30938, 30964, 30990 (dark 1069:31016, 31040, 31064, 31088, 31112, 31136, 31160, 31184, 31208); tags 1070:30028–1070:30055; notes 1070:30056–1070:30060. S-05p 1029:41258 (dark 1029:41332) is superseded (40%, red tags 1070:30061 / 1070:30062). Section 536:14142 widened to 40400 × 2700.

Example: Loblaws, −$120.00, split four ways at $30.00 each. Jo paid with a $60.00 e-Transfer that also paid back Pizza Nova. Sam paid in cash on Nov 13. Priya paid through PayPal on Nov 14.

- **S-05v, the split card:**
  - Every PAID BACK row taps, including someone who paid in full, and has a chevron.
  - With one person, the caption reads PAID BACK and the rows work the same.
  - On a split purchase, the separate "Paid back with" list goes: the card is the one place.
  - A purchase that isn't split keeps its PAID BACK list, but its rows open S-05o instead of going straight to Unlink.
  - REFUNDED BY rows open S-05o too.
  - VoiceOver: "Jo, paid back 30 dollars, November 16, part of a 60 dollar e-Transfer that also paid back Pizza Nova. Button." The hint is "Shows options, including Unlink".
- **S-05o, the options (`.confirmationDialog`):**
  - Title: "Jo paid back $30.00".
  - Message: where the money came from, e.g. "Part of a $60.00 e-Transfer on Nov 16 that also paid back Pizza Nova".
  - Buttons: **View the e-Transfer**, **Unlink…** (destructive) and Cancel.
  - View opens the transaction in the app. It reads "View the deposit" for a part of a deposit or for cash a deposit holds, and "View the refund" for a refund. There's no View for cash or an app payment that wasn't deposited.
  - Someone paid by two payments gets one Unlink per payment ("Unlink the $10.00 cash…", "Unlink the $20.00 e-Transfer…").
  - Someone who still owes part keeps Mark paid back, Remind and Let it go, plus their payment's View and Unlink.
- **S-34s, Unlink? (the S-34 sheet):**
  - "This $60.00 also paid back Pizza Nova. Unlink only Loblaws’ $30.00?"
  - Then: "Jo will owe you $30.00 again on Loblaws. Pizza Nova stays paid back, and this $30.00 goes back to Needs a look as left to sort."
  - Buttons: **Unlink $30.00** / Keep linked. To unlink the whole $60.00, she uses View the e-Transfer and unlinks it there (S-34, unchanged).
  - Loading: a spinner on Unlink, both buttons disabled, and the sheet stays open.
  - **Error** (S-34s error): "Couldn’t unlink that. Nothing changed. Try again." in color/text/caution, announced by VoiceOver. The button reads Try again.
- **S-05t, after Unlink:**
  - Jo's row springs to "Owes you" $30.00 in ink (250 ms; a cross-fade with Reduce Motion), with a light success haptic.
  - The toast reads "Unlinked · Jo owes $30.00", with **Undo**. Undo links it back exactly as it was, and its toast reads "Linked again".
  - Needs a look stays at one row per deposit. A deposit already there as "$x left to sort" grows; it doesn't get a second row.

**Behaviour per payback kind (S-34k):**

| Kind | Unlink? line | This purchase | The money | Toast |
|---|---|---|---|---|
| e-Transfer / bank, this purchase only | "Sam will owe you $30.00 again. The e-Transfer goes back to Needs a look." | Sam owes $30.00 again | Back to Needs a look, unsorted | "Unlinked · Sam owes $30.00" |
| e-Transfer / bank, also paid other purchases | S-34s, above | Jo owes $30.00 again | The other links stay (same person); this $30.00 is "left to sort" on it (as SPLIT-16) | "Unlinked · Jo owes $30.00" |
| Cash | "…The cash you marked is forgotten, so nothing goes to Needs a look." | Sam owes again | The cash record goes | "Unlinked · Sam owes $30.00" |
| Cash that also paid other purchases (SPLIT-19) | "This $60.00 cash also paid back Pizza Nova. Unlink only Loblaws’ $30.00? … Pizza Nova stays paid back." | Sam owes again | Only this purchase's piece goes | same |
| Cash a deposit holds | "…Your $200.00 deposit on Nov 20 keeps its other parts, and this $30.00 goes back to Needs a look as left to sort." | Sam owes again | The deposit gets "$30.00 left to sort" | same |
| Another app | "Priya will owe you $30.00 again. The PayPal payment is forgotten, so nothing goes to Needs a look." | Priya owes again | The app record goes | "Unlinked · Priya owes $30.00" |
| Work paying me back | "Loblaws goes back to waiting to be reimbursed. The $84.12 from Acme Corp goes back to Needs a look." If it wasn't waiting before: "Loblaws counts as your spending again." | Waiting again, or spending | Back to Needs a look | "Unlinked · Loblaws is waiting to be reimbursed" |
| Refund (title "Unlink refund?") | "The $8.50 stops coming off Loblaws. It stays in Groceries and goes back to Needs a look." | Full cost again | Stays in its category, in Needs a look | "Refund unlinked" |
| Part of a deposit (S-26) | "Dad will owe you $228.00 again. Your $600.00 deposit keeps its other parts, and this $228.00 goes back to Needs a look as left to sort." | Dad owes again | Only that part goes; the deposit shows "$228.00 left to sort" | "Unlinked · Dad owes $228.00" |
| Payback that made the split (THL-260) | "Priya joined this split when you linked this e-Transfer, so she comes off the split too. The e-Transfer goes back to Needs a look." | Priya is off this split only | Back to Needs a look | "Unlinked · Priya taken off the split" |

These combine: a shared payback that also made the split shows both lines.

**Server needs:**
1. **`repaid_by` / split payments:**
   - List every inflow with this purchase in `repays_all`, with `paid = part_for(txn_id)`.
   - Add an `unlink` preview per row: `others` (the other purchases' names), `here`, `whole`, `goes` (`needs_a_look` / `left_to_sort` / `forgotten`), `deposit` (id, amount, date when a deposit holds it), `made_split`, `was_waiting` and `kind`.
   - Each `Person.payments` entry needs an id (`inflow` or `cash_id`) so the row knows what to unlink.
2. **`DELETE /api/transactions/<charge>/paybacks/<inflow>`, scoped to this purchase:**
   - Accept a secondary purchase.
   - When the payback paid other purchases, remove only this link and keep the others with the same person, as `_edit_split` does for SPLIT-16 (`dp.apply(…, later=True)`), or by moving `also_repays` up.
   - For a part (`part_of`), remove only that part and leave the deposit with "$x left to sort", not `DELETE …/parts`.
   - Run `drop_payer` for this purchase only, not `drop_payer_all`.
   - Return `undo` marks (`paybacks`, `payback_more`, `splits`, `unparts`) and a `title` for the toast.
3. **`DELETE …/split/cash/<id>` from the purchase:**
   - Remove only this purchase's piece of an origin.
   - For cash a deposit holds, take it out of the deposit's match instead of refusing, so the deposit gets "left to sort".
   - Return Undo.
4. **`DELETE /api/transactions/<refund>/refund`:** called from the purchase with the refund's id. Add an Undo that re-links it.
5. **Reimbursement:** the existing "waiting again" logic stays. The preview just reports `was_waiting`.
6. **Tests:** one per row of the table, plus Undo for each and "Paid back + Owes = share" after each (THL-181).

### [engBOT] 2026-11-09 · SPLIT-25 start
designBOT's SPLIT-25 entries above were left uncommitted; I've committed them with mine, unchanged. Branch `fix/unlink-from-purchase`, made from main with `git switch -c` after PR #315 merged. I read THL-291 (in Testing) and checked these by node only, with get_screenshot and get_metadata on the "Cash flow" page: S-05v 1069:29642 (dark 1069:29742), S-05o 1069:29844, S-34s 1069:29931, S-34s error 1069:30029 (dark 1069:30410), S-05t 1069:30128, the nine light S-34k sheets 1069:30782, 30808, 30834, 30860, 30886, 30912, 30938, 30964, 30990, the dark S-34k 1069:31016 and 1069:31208, and notes 1070:30056–1070:30060.

### [engBOT → designBOT] 2026-11-09 · SPLIT-25 · Accepted (built)
- **S-05v:** every PAID BACK row has a chevron and taps, Jo in full included; "$60.00 · paid back Loblaws and Pizza Nova" under Jo; no separate "Paid back with" list. Dark matches.
- **S-05o:** "Jo paid back $30.00" / "Part of a $60.00 e-Transfer on Nov 16 that also paid back Pizza Nova" / View the e-Transfer / Unlink… / Cancel. Note 1070:30057 covers View per kind (none for cash or an app not deposited) and one Unlink per payment.
- **S-34s and its error:** the ask line, the both-sides line, "Unlink $30.00" / Keep linked; the error in caution with Try again. Light and dark match. Note 1070:30058 covers loading, Dynamic Type and VoiceOver.
- **S-05t:** Jo's row back to "Owes you" $30.00 in ink, the toast "Unlinked · Jo owes $30.00" with Undo. Note 1070:30059 gives the toast per kind and "Linked again".
- **S-34k:** e-Transfer (one purchase), cash, cash that paid Pizza Nova too, cash a deposit holds, PayPal, Work paying me back, refund ("Unlink refund?"), part of Dad's $600.00, and the payback that made the split. Each line matches the table in designBOT's entry and note 1070:30060.

Every AC path has a screen, a way in (the row) and a way out (Cancel, Keep linked, the close button, Undo). The server needed the work in the build entry below. Two small wording choices, noted for the product owner rather than sent back: the made-the-split line uses the person's name instead of "she" ("so Priya comes off the split too"), since Pearl doesn't know anyone's pronouns; and a Work-paying-me-back unlink where the purchase wasn't waiting toasts "Unlinked · Hotel counts as your spending again" (the table only drew the waiting toast).

### [engBOT] 2026-11-09 · SPLIT-25 · build
Branch `fix/unlink-from-purchase`.
- **Server (`finance/unlink.py`, new):**
  - **1. `repaid_by` and the split card:** `repaid_by` lists every inflow with this purchase in `repays_all`, `paid = part_for(id)`, so the second purchase shows it too. Each row, each REFUNDED BY row and each split person's new `links` carry the S-05o and Unlink? words (`dialog`, `message`, `view`, `noun`, `sheet` {title, name, face, sub, ask, line, button}, `toast`) and the facts (`kind`, `others`, `goes`, `deposit`, `made_split`, `was_waiting`). Each link has its id: `inflow` or `cash_id` (the payment's origin).
  - **2. `DELETE …/paybacks/<inflow>`:** accepts a secondary purchase. Only this purchase's link comes off; other purchases keep theirs as parts of the deposit and this part is "left to sort" (as SPLIT-16). A part of a deposit (S-26) is taken out of the deposit's parts, which are saved again with the rest left to sort. `drop_payer` runs for this purchase only. It returns `undo` (marks `paybacks`, `payback_more`, `splits`, `unparts`, `reparts`, `exclusions`, `waiting`) and the toast `title`. `?whole=1` is the payback's own Unlink (S-34, every purchase), used by the deposit side in the app and on the web.
  - **3. `DELETE …/split/cash/<id>`:** removes only this purchase's piece of the payment (all of it, with its gift, when it paid nothing else). Cash a deposit holds comes out of the deposit's cash part instead of being refused, so the deposit gets "$x left to sort". Undo puts the records back with their ids and the deposit's parts back as they were (`cash_rows`, `reparts`).
  - **4. `DELETE …/refund`:** returns `title` "Refund unlinked" and an Undo that links it again.
  - **5. Reimbursement:** the "waiting again" rule is unchanged; the preview reports `was_waiting`, and Undo forgets the wait again.
- **App:**
  - `SplitPeople` (S-05v/S-05o): no row is disabled; S-05o's title, message, View per payment and one Unlink per payment ("Unlink the $10.00 cash…" when there are two); VoiceOver label and hint "Shows options, including Unlink"; rows at least 44 pt; the owes amount springs (250 ms, ease with Reduce Motion).
  - `TransactionDetailView`: PAID BACK only on a purchase that isn't split; its rows and REFUNDED BY rows open the same S-05o; View opens the transaction in the app; `UnlinkLinkSheet` (S-34s/S-34k) with the spinner, disabled buttons, the error line announced by VoiceOver and Try again; S-05t toast with a success haptic and Undo, whose toast reads "Linked again".
  - The deposit side's Unlink (Pays back → Options) sends `whole=1`, so it still unlinks the whole payment.
- **Web:** `unlinkPayback(id, inflow, whole)`; the deposit side passes `whole`.

### [engBOT] 2026-11-09 · SPLIT-25 · product owner change: no stock dialogs
The product owner asked, mid-build, that S-05o and S-34s not be stock iOS components (no `.confirmationDialog` or `.alert`). designBOT is drawing them as custom Pearl pages and sheets, with a ••• menu on each person's row of the split card, on the "Design refresh" page. So:
- S-05o is now `PaybackOptionsSheet`, a plain Pearl sheet (title, where the money came from, View, Unlink…, Cancel). S-34s / S-34k stay `UnlinkLinkSheet`, a Pearl sheet. Both live in `ios/Pearl/Views/Transactions/PaybackOptions.swift` and read only the server's `LinkInfo`. **Presentation to be replaced by custom design, see design refresh.**
- The split card's rows and the PAID BACK / REFUNDED BY rows still tap to open it. Someone with no payment here (still owes, nothing paid) keeps the old Mark paid back / Remind / Let it go dialog, which predates SPLIT-25.
- No new design loop opened. The server, Undo and tests are unchanged by this.

### [engBOT] 2026-11-09 · SPLIT-25 · tests, PR and Jira
- **Tests:** `tests/test_unlink_from_purchase.py` (17): one test per S-34k kind (e-Transfer, shared e-Transfer from either purchase, cash, cash that also paid Pizza Nova, cash a deposit holds, another app, part of a deposit, Work paying me back, refund, made the split). Each one unlinks from the purchase, checks the sheet's words, undoes, and checks Paid back + Owes = share after both (THL-181). Swift wiring checks too, including no stock dialog for S-05o. Two older tests now ignore the new `links` field.
- `python3 -m pytest -q`: 1835 passed. The one wiring test added after that run passes on its own. `npm run build`: built. `xcodebuild … 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED. `make_project.py` run for the new `PaybackOptions.swift`. Not run by hand on a simulator or device.
- **Commit:** the build commit on `fix/unlink-from-purchase`, 17 files; `git show --stat` checked. **PR:** https://github.com/mariapapadimitriou/finance/pull/316 (open, not merged).
- **Jira:** commented on THL-291, which stays in Testing.

### [product owner] 2026-11-09 · Design refresh decisions
From the design refresh (ios/bots/design-refresh-log.md, REFRESH-00 to REFRESH-02):
- **Ink spending:** spending amounts are ink, not red; red means only "over". Approved.
- **Sort now → Quick sort:** Home's "Sort now" opens Quick sort directly; "See the list" opens Needs a look. Approved.
- **••• menus with custom pages:** each person on the split card gets a ••• menu. "I need a new design for those option pages, and everything presented after them should have a design as well — don't just use iOS components." The product owner then went with designBOT's reading: the ••• replaces the inline Mark paid back / Remind buttons for every person state, and the new copy is approved as written ("Hey Sam! Thanks for the $10.00. Your share of Loblaws on Nov 11 was $30.00, so $20.00 to go." and "Loblaws already counts in full until it's paid back, so your Allowance doesn't change.").
- **Pearl paper background:** the calm "pearl paper" for in-app pages, iridescent kept for onboarding and celebrations; used on the new split menu and confirmation screens now, the rest of the app last.
- **Look before animation:** look and functionality first; motion comes later and nothing depends on it.

### [designBOT → engBOT] 2026-11-09 · REFRESH-02 · Person options (•••) and every screen after them (relayed by engBOT)
designBOT logged this in ios/bots/design-refresh-log.md (it doesn't write here); relayed unchanged in substance.
**Status:** Redesigned · Design refresh · Approved — build
**Jira:** THL-289 (flow 2, flow 7), THL-291 ("Unlinking any part from either side restores both sides", Undo), THL-181 (Paid back + Owes = share), THL-301, THL-260, THL-279, THL-282   **Figma:** "Design refresh" page 1070:30063, section 11 1088:1695; kit 1088:1696; notes 1096:4466 (options per state), 1096:4483 (accessibility, colour, motion), 1096:4498 (handoff)
- **Screens:** S-04r v2 1090:1743 (split card, ••• on each person); S-40a–d 1090:1846, 1090:1979, 1090:2130, 1090:2235 (c2), 1090:2355 (options for owes, paid part, paid in full, two payments, let go); S-05or 1090:2457; S-06ra–rd 1091:2131, 2219, 2312, 2372 (Mark paid back); S-07ra/rb 1091:2433/2480 (Remind); S-08ra–rd 1091:2527–2686 (Let it go, with loading and error); S-03re 1092:2360 (Change share); S-03fr/fr2 with loading and error 1092:2464–2648; S-34sr with loading and error 1092:2716–2829; S-34kr1, 3–10 1092:2890–3332; S-44a–i 1093:2719–3576 (toasts, including Undo failed). Dark twins 1093:3991–5839.
- **Rule:** no `.alert`, no `.confirmationDialog`, no action sheet in these flows; every menu, confirmation, error, loading and success state is a Pearl sheet or toast, on pearl paper, colours bound to the Pearl Color variables; no red (errors use the champagne Banner at 22%).
- **Options per state:** Owes: Mark paid back · Remind · Let it go · Change their share · Remove (at once, with Undo). Part-paid: PAID SO FAR with each payment's View (bank or deposit) and Unlink · Mark the rest paid back · Remind (for what's left) · Let the rest go · Change their share · Remove (asks first). Paid in full: PAID WITH, one card per payment with View and Unlink · Change their share · Remove (asks first). Let go: Undo let it go (at once, with Undo) · Change their share · Remove (at once, with Undo).
- **Handoff (1096:4498):** S-40/S-05or from `Splitting.Person` + `links`, one sheet view replacing SplitPeople's `.confirmationDialog` and the stop-gap `PaybackOptionsSheet`; S-06r: the bank POST should return undo marks + a title (S-44b); S-07r no server call, editable, clipboard; S-08r POST/DELETE …/split/let-go, each the other's Undo; S-03re the existing SplitSheet with that person's field focused; Remove from S-40 saves at once with PUT …/split (undo + title for an unpaid person too), S-03fr replaces SplitSheet's `.alert`; S-34sr/kr same calls as SPLIT-25, new look; View opens the transaction in the app, never the web. Out of scope: TransactionDetailView's Delete `.confirmationDialog`, PartsFlow's and TransactionsView's `.alert`, CalendarView's `.confirmationDialog`.
- **Copy for engBOT to check:** S-07rb's part-paid reminder; S-08's Allowance line; the remove-at-once toast "Priya removed · $30.00 back to your share".

### [engBOT] 2026-11-09 · REFRESH-02 start
Branch `fix/unlink-from-purchase` (PR #316), as asked. I read the role file again (custom SwiftUI views, never stock dialogs), design-refresh-log.md (REFRESH-00 to REFRESH-02 and the product owner's decisions) and THL-291 (in Testing). In Figma I opened, by node only (create_session first): the kit 1088:1696; notes 1096:4466, 1096:4483 and 1096:4498 (get_design_context); S-04r v2 1090:1743 and dark 1093:3991; S-40a 1090:1846 (get_design_context), S-40b 1090:1979 and dark 1093:4099, S-40c 1090:2130, S-40c2 1090:2235, S-40d 1090:2355; S-05or 1090:2457; S-06ra–rd 1091:2131, 2219, 2312, 2372; S-07ra/rb 1091:2433/2480; S-08ra, rb, rd 1091:2527, 2579, 2686 and dark 1093:4640; S-03re 1092:2360; S-03fr, fr2, loading, error 1092:2464, 2526, 2583, 2648; S-34sr, its error 1092:2716, 2829; S-34kr1, 3, 4, 5, 6, 7, 8, 9, 10 1092:2890, 2944, 2999, 3054, 3109, 3163, 3220, 3278, 3332; S-44a, b, c (metadata), d, e, f, g, h, i 1093:2719–3576. get_variable_defs on 1093:4099 and 1091:2686 for the dark blush (#4E2238), the control fill and champagne (#F3D9A4).

### [engBOT → designBOT] 2026-11-09 · REFRESH-02 · Accepted (built)
- **S-04r v2 / dark:** each person has a 44 pt ••• and a paid-back bar (rose part-paid, money-in in full), the amount in ink, money-in or muted for let go; Edit split beside "Split 5 ways". Dark matches.
- **S-40a–d:** one sheet, sections by state, exactly as note 1096:4466; the subtitles ("By bank or e-Transfer, cash, or another app", "Copy a message for the $20.00 left", "Asks first: the $10.00 cash is forgotten", "Goes at once, with Undo"…) and S-40b's PAID SO FAR card with "Unlink $10.00…". S-40c's View the e-Transfer + Unlink…; S-40c2's two cards. Dark S-40b matches.
- **S-05or:** "PAID BACK / Jo paid back $30.00", View the e-Transfer "Opens it here in Pearl", Unlink… "Jo will owe you $30.00 again on Pizza Nova".
- **S-06ra–rd:** How did Priya pay? (three rows), Which payment was it? (search, SUGGESTED, OTHER MONEY IN, Link $30.00), Cash from Priya (amount card, Received, the never-counted-twice note), Which app did Priya use? (chips, Other…), each with Back and Close.
- **S-07ra/rb, S-08ra–rd, S-03re, S-03fr/fr2 with loading and error, S-34sr with error, S-34kr1–10, S-44a–i:** every line, button and toast as drawn; the loading states put a spinner in the main button with both buttons off.
- **Copy:** the S-07rb reminder and the S-08 Allowance line, both approved by the product owner; "Allowance" everywhere, never the other phrase.
- Every option has a frame and a way out (Close, Back, Keep…, Undo). The server needed small additions (build entry). Two handoff details were already true or slightly off, noted rather than sent back: the bank POST already returned an Undo (it lacked only the toast's words), and S-44f's Undo for Remind empties the clipboard, as the app did before.

### [engBOT] 2026-11-09 · REFRESH-02 · build
- **Server:**
  - `POST …/paybacks/<inflow>` returns `toast` ("Priya paid back $30.00") next to its existing `undo` (S-44b).
  - `PUT …/split` returns `toast` when someone comes off, including someone who paid nothing or was let go: "Priya removed · $30.00 back to your share" (S-44d); `undo` as before.
  - `POST` / `DELETE …/split/let-go` return `toast` ("Let go · the $30.00 is your spending now", "Priya owes you $30.00 again", S-44c / S-44e). `title` is unchanged, so the web is untouched.
  - `finance/unlink.py`: each `LinkInfo.sheet` also carries S-34sr/kr's `heading` ("Unlink Sam’s e-Transfer?", or the ask), `overline`, `card` {label, amount}, `confirm` ("Unlink $30.00", "Unlink refund", "Unlink and take Priya off"), `keep` ("Keep linked", "Keep it") and `note` ("To unlink the whole $60.00, open the e-Transfer and unlink it there.").
- **App (`ios/Pearl/Views/Transactions/SplitMenus.swift`, new):** the kit (Close and ••• 44 pt, Primary / Secondary / pill buttons, Option row ≥ 60 pt, champagne `CautionBanner` announced by VoiceOver, `InfoNote`, `PearlSheet` on pearl paper sized to content with the grabber, `PearlToast`), `PersonOptionsSheet` (S-40a–d), `RemindSheet` (S-07r, editable, `UIPasteboard`), `RemovePersonSheet` + `RemoveWords` (S-03fr/fr2 with loading and error).
  - `SplitFlow.swift`: `SplitPeople` (S-04r v2) opens S-40 from the row and the ••• (".confirmationDialog" gone); `SplitSheet`'s `.alert("Remove …?")` is now S-03fr, and it takes `focus` for S-03re (Amounts, that field focused, "Split updated" with Undo); `MarkPaidSheet` is S-06ra–rd (S-11c's extra page is unchanged); `LetGoSheet` is S-08ra–rd.
  - `PaybackOptions.swift`: `PaybackOptionsSheet` is S-05or; `UnlinkLinkSheet` is S-34sr/kr.
  - `TransactionDetailView.swift`: S-40's choices, Remove at once (S-44d) or after S-03fr, the ink S-44 toasts with Undo, "Linked again" (S-44g), and S-44h "Couldn’t undo that. Nothing changed." with Try again. View opens the transaction in the app. Success haptic on Mark paid back, Unlink and Let go; none on Remind. The toast stays 6 s, 15 s with VoiceOver.
  - Tokens (`Theme.swift`): `bubble` (blush, dark #4E2238), `control`, `champagne`, `borderStrong`. Spending is ink on these screens; red appears nowhere in them.
- **Left for a later pass (not split flows):** TransactionDetailView's Delete `.confirmationDialog`, PartsFlow's `.alert("Leave without saving?")`, TransactionsView's `.alert("Leave out …?")`, CalendarView's `.confirmationDialog`; and in Profile: IncomeBillsView, ProfileView, JointMergeViews, CategoriesRulesView, AccountsViews, SettingsViews, PrivacyViews.

### [engBOT] 2026-11-09 · REFRESH-02 · tests, PR and Jira
- **Tests:** `tests/test_split_menus.py` (22): S-44b's toast and Undo for a bank link (whole and part) and cash; Remove from S-40 for someone who paid nothing, someone let go and someone who paid, each with Undo and Paid back + Owes = share (THL-181); Change share's Undo with no removed toast; Let go and Undo let it go toasts (whole and the rest); S-34sr/kr's heading, card, buttons and footnote for an e-Transfer, a shared e-Transfer, cash, an app, a refund and the payback that made the split; and Swift wiring: no `.confirmationDialog`, `.alert` or action sheet in SplitFlow, PaybackOptions or SplitMenus, only the Delete dialog left on the detail page, S-40 from the row and the •••, each screen's words, the S-07rb copy, "Allowance", S-44h, and no web hand-off. Two SPLIT-25 wiring checks were updated for S-40.
- `python3 -m pytest -q`: 1858 passed. `npm run build`: built. `xcodebuild … 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED, no warnings in the changed files. `make_project.py` run for the new `SplitMenus.swift`. Not run by hand on a simulator or device.
- **Commit:** c90ff92 on `fix/unlink-from-purchase`, 13 files (with designBOT's design-refresh-log.md, unchanged); `git show --stat` checked. **PR:** https://github.com/mariapapadimitriou/finance/pull/316 (open, not merged), body updated.
- **Jira:** commented on THL-291, which stays in Testing. Nothing moved.

## Summary

This is the state after sixteen rounds, the THL-301 follow-up, SPLIT-25 and SPLIT-26 (REFRESH-02, the custom split menus) (2026-11-09 to 11-10). Every issue, SPLIT-01 to SPLIT-26, is decided and built. SPLIT-25 and SPLIT-26 are on their own branch and PR (below). SPLIT-26 replaced every stock iOS menu, alert and action sheet in the split flow with designBOT's Pearl sheets and toasts. Correction: earlier versions of this Summary called SPLIT-06 fully built. It wasn't. A split made from Quick sort's sheet still saved at once, and that is now built as SPLIT-20 (round 11).

**Before merging:** test it by hand on a device. No round was run by hand on a simulator or a phone. Every check was automated: pytest, the web build, the simulator build, and wiring checks on the Swift source.

**PR:** https://github.com/mariapapadimitriou/finance/pull/315 (merged). SPLIT-25 and SPLIT-26: https://github.com/mariapapadimitriou/finance/pull/316 (open, not merged), branch `fix/unlink-from-purchase`.
**Branch:** `feat/split-bot-round` (rounds 1–16, THL-301)
**Commits:**
- e0da5fa: iOS, round 4
- 572b6b6: server, round 4
- 6bb6713: log, rounds 1–3
- f465bc3: log, round 4
- f067b04: round 6 build
- da79b51: log, rounds 5–6
- 22bf661: round 7 build (SPLIT-01/04/05/06/12)
- 1520b54, 5ebddf4: log, round 7 and dark twins
- 8176985: round 9 build (SPLIT-18/19, dark money-in)
- 49564f4: log, rounds 8–9
- d2dc59d: round 10 build (SPLIT-19 list line, T-08k error line)
- 9dc1a2f: log, round 10
- 1abc302: round 11 build (SPLIT-20, web dark money-in)
- 4ed7916: log, round 11
- 1f5bfd4: round 12 build (SPLIT-21, web light money-in)
- f95471e: log, designBOT's Figma entries and round 12
- 1ca13a6: round 14 build (SPLIT-22a/22b)
- c759176: log, designBOT's round 13 and round 14
- 34af59b: round 16 build (SPLIT-23 (1))
- a738225, 4dc8b2d: log, designBOT's round 15, round 16, and the product owner's round-16 decisions
- 68579a1: THL-301 build (SPLIT-24)
- this log commit: designBOT's SPLIT-24 entry and the THL-301 round
- on `fix/unlink-from-purchase`: bcd8fbd SPLIT-25 build, e1df1d4 SPLIT-25 log; c90ff92 SPLIT-26 (REFRESH-02) build, then its log commit

**Tests:**
- `python3 -m pytest -q`: 1858 passed (SPLIT-26). That's 80 new in tests/test_split_round.py across rounds 7, 9, 10, 11, 12, 14, 16 and THL-301, 17 in tests/test_unlink_from_purchase.py for SPLIT-25, and 22 in tests/test_split_menus.py for SPLIT-26.
- `npm run build`: built (SPLIT-26).
- iOS Simulator build: BUILD SUCCEEDED (SPLIT-26), no warnings in the files it touched.
- Not run by hand on a simulator or a device.

### Every issue

| ID | Title | Final status |
|----|-------|--------------|
| SPLIT-01 | Save before the split adds up | Decided (b′). Built (S-03b v2): short saves only with "I had some too" on; app and server |
| SPLIT-02 | Edit split after someone has paid | Built (S-03e, S-03f) |
| SPLIT-03 | Edit on a deposit in parts | Built (S-33 v2, S-10e) |
| SPLIT-04 | One "What's the other $x?" | Built (S-11 v2): every tile is a part, including Dad overpaid, Out of savings and Off a category |
| SPLIT-05 | Tabs and Continue on S-22 / S-11 | Decided (b). Built: splits use the shared tiles |
| SPLIT-06 | Split from Quick sort: held or saved at once | Decided (a). Built from the card's page in round 7 (T-98s). The sheet was missed until SPLIT-20 |
| SPLIT-07 | Split and link as one save | Built (S-24x, S-12c with WHAT CHANGES, S-12d) |
| SPLIT-08 | Joint-account purchase | Built (S-01j, S-02 v2) |
| SPLIT-09 | Effect on Allowance in Check and save | Built (S-12 v2) |
| SPLIT-10 | Odd cents and thirds | Built (S-18 v2, S-15 v2) |
| SPLIT-11 | Cash or app above what's owed, cash partly deposited | Built. "Next: the extra" opens S-11c (SPLIT-19) |
| SPLIT-12 | Code ahead of Figma | Built (T-09r title; the income list is replaced by S-11 v2's tiles) |
| SPLIT-13 | Home owes-you nudge | Built (H-00n) |
| SPLIT-14 | Another app: which app | Built (S-06 v3 / v3a) |
| SPLIT-15 | Partly deposited cash listed twice | Built |
| SPLIT-16 | Removing a person unlinks their whole payback | Built. The alert uses the name instead of "Her" |
| SPLIT-17 | S-22 v2: Split into parts and Always off | Decided by the product owner: Split into parts stays removed (aa07127), Always on. Accepted round 9; the app already matched |
| SPLIT-18 | Other income's follow-up has no frame | Accepted and built (S-11k, T-08k): "What kind of income?" on the parts page and the shared page, with its own error line (round 10) |
| SPLIT-19 | S-06 v2's extra for cash or an app | Accepted and built (S-11c): four outcomes, `split_cash` `extra`, shared origin, Undo by origin, and the list line "paid back Loblaws and Pizza Nova" (round 10) |
| SPLIT-20 | Quick sort's sheet saved a split at once | Decided (SPLIT-06 (a) everywhere). Built (round 11): the sheet holds it for the card; Yes saves split and category with one Undo; Skip drops it |
| SPLIT-21 | Ask who a payback is from (THL-181) | Accepted and built (round 12, S-35a/S-35b): no guess when two or no shares fit; one exact fit ticked; paybacks dated before 2026-11-10 keep the old credit |
| SPLIT-22 | Two cases S-35a/S-35b don't draw | Redesigned (round 13), Accepted and built (round 14, 1ca13a6): (a) S-35a1 line; (b) S-05u row on the split card, S-35c "Who sent this?" sheet with error and extra → S-11 v2, S-21u in Needs a look and Quick sort ("Paid back by Sam?"), server list + POST …/credit with Undo |
| SPLIT-23 | Three edges S-35c doesn't draw | Decided by the product owner and redesigned (round 15). Accepted and built (round 16, 34af59b): (1) nobody left owing → S-21x row `extra:<id>` "Nov 16 · extra on Loblaws" → S-11x "The $30.00", a tile saves in one request with Undo that links it back, held on a Quick sort card; (2) one sender per payment, already built; (3) no entry on the deposit's own page, already built |
| SPLIT-24 | A payback over two purchases that's extra on only one (THL-301) | Redesigned (designBOT), Accepted and built (68579a1): one row per deposit, `credit:<id>` (S-21xw) then `extra:<id>` (S-21xm "Nov 16 · $30.00 extra on Loblaws", +$60.00); S-35c credits and closes; S-11xm "The $30.00" under "$60.00 · Nov 16" with the mixed line, capped (S-11xm over), "Jo overpaid"; the save keeps the credited parts, with Undo; Quick sort brings the deposit back as the next card. THL-301 in Testing |
| SPLIT-25 | Unlink a payback from the purchase it paid back (product owner, hand test; THL-291, THL-289 flow 7) | Redesigned (designBOT), Accepted and built (PR #316): every PAID BACK / REFUNDED BY row → S-05o → S-34s / S-34k → S-05t with Undo; purchase-scoped server unlink for every kind. Restyled by SPLIT-26. THL-291 in Testing |
| SPLIT-26 | Custom split menus (REFRESH-02) | Decided by the product owner (••• for every state, the new copy) and drawn by designBOT on "Design refresh" section 11. Accepted and built (PR #316): S-04r v2 ••• → S-40a–d; S-05or; S-06ra–rd; S-07r; S-08r with loading/error; S-03re; S-03fr/fr2 with loading/error; S-34sr/kr; S-44a–i toasts incl. Undo failed. No stock dialog left in the split flow. THL-291 in Testing |

### Still open

**SPLIT-26 (REFRESH-02), built (2026-11-09), PR #316, not merged.** Notes for the product owner, not a design loop:
- **Remove the only person who paid:** a split needs someone on it, so the server refuses, and S-03fr's banner shows "Add someone to split it with." Removing the only person who paid nothing works (the split goes; Undo puts it back). No frame says what removing the last payer should do.
- **Remove someone whose payback is part of a deposit, or whose cash a deposit holds:** the server still refuses ("Unlink the deposit first"), and S-03fr's banner shows those words instead of the general error. Unlinking that payment from S-40 first works (SPLIT-25).
- **Mark paid back with several deposits ticked (S-26):** each is linked in turn. If a later one fails, the earlier ones stay linked although the banner says nothing changed.
- **Not restyled, because they aren't approved yet:** How to split itself (S-03r; Change share opens it with the field focused), S-11c "What's the extra?" after cash or an app over the share, and the detail page around the split card (still iridescent until pearl paper reaches every page, last in the build order).
- **Icons:** SF Symbols stand in for the Option and Category icon sets on these sheets.
- **S-06rb rows:** the line under a suggested payment says "Amount matches" or the account; Pearl doesn't know whether the name matched.
- **Stock dialogs left outside the split flow** (a later pass): TransactionDetailView's Delete, PartsFlow's "Leave without saving?", TransactionsView's "Leave out …?", CalendarView's band dialog, and Profile's (IncomeBillsView, ProfileView, JointMergeViews, CategoriesRulesView, AccountsViews, SettingsViews, PrivacyViews).
- Test SPLIT-25 and SPLIT-26 by hand on a device before merging.

**SPLIT-25, built (2026-11-09), PR #316, not merged:** unlinking a payback from the purchase it paid back, for every payback kind, with Undo. Its S-05o and S-34s are now designBOT's custom S-05or and S-34sr/kr (SPLIT-26). Notes for the product owner, not a design loop:
- The made-the-split line names the person ("so Priya comes off the split too"), since Pearl doesn't know pronouns.
- A Work-paying-me-back unlink where the purchase wasn't waiting toasts "Unlinked · Hotel counts as your spending again". Only the waiting toast was drawn.
- A payback on the split card credited to no one (S-05u) still opens "Who sent this?", not Unlink. It can be unlinked from its own page.
- Unlinking a part of a deposit saves the deposit's other parts again, so a part that was itself split into parts would lose that inner split.
- Test SPLIT-25 by hand on a device before merging.

**Decided by the product owner (2026-11-09):**
- **Before merging:** test it by hand on a device (see above).
- **Two purchases, extra on only one:** made a ticket, THL-301, drawn as SPLIT-24 and built. THL-301 is in Testing.
- **Named sender not on one of the purchases** (an unnamed $60.00 over Loblaws, where Sam owes, and Pizza Nova; she ticks Jo; Loblaws' $30.00 counts for no one): made a low-priority ticket, [THL-302](https://thalloapp.atlassian.net/browse/THL-302), To Do. No bot round.
- **Also accepted as they are:** a payback over a split and an unsplit purchase isn't asked about; in the mixed case, over the share on S-35c shows as overpaid on that purchase's card; the web refuses Cash, joint and Not mine for a partly-extra payback.
- **Accepted as they are:** paybacks before 2026-11-10 keep the old guess; S-11x's overpaid tile names the one person who paid back and is hidden when there are several (S-11xm follows the same rule, naming the one credited sender, "Jo overpaid"); an S-11x answer is stored as one part; less than the whole on S-11x carries on as S-11 v2 does.

**THL-181:** "Every repayment linked to a split is credited to someone on the split card. If Pearl can't tell who, it asks." This is met on every linking path (the sheet, search, the web's Paid back, the API) for paybacks dated from 2026-11-10, including the mixed two-purchase case (THL-301). The one exception is the named-sender edge (THL-302). Paybacks dated before then keep the old guess. THL-181 stays in Testing.

**Web tokens:** money-in follows Figma: light #167a40 (round 12) and dark #6edb94 (round 11). Both were edited by hand, because the repo has no token generator.

### Dark twins (done in round 7 by designBOT)
- **Dark alerts and action sheets:** the S-03f, S-24x and S-04 v2 twins are tagged "iOS system alert/action sheet — drawn by iOS, colours indicative". S-03f and S-04 v2 are now Pearl sheets (SPLIT-26, product owner's no-stock-dialogs rule), with the REFRESH-02 dark twins.
- **Positive green:** every green on the twins is bound to `color/text/money-in`. The round-8 frames are too.
- **Money-in dark (decided 2026-11-09):** #6EDB94, in the app (`ios/Pearl/Theme/Theme.swift`, round 9) and on the web (`src/tokens/tokens.css`, round 11). Light is #167A40 in Figma, iOS and (round 12) the web.

### How the bots communicated
| Round | Who | What was sent |
|-------|-----|---------------|
| 1 | engBOT → designBOT | An audit of Jira (THL-291, THL-289 and related), the 37 S-frames and the code. Logged SPLIT-01 to SPLIT-13, each with a Jira quote, Figma nodes, code lines and an ask. No changes. |
| 2 | designBOT → engBOT | Replies to all 13 and new light frames in column 994:36735. Three were put to the product owner (SPLIT-01, 05, 06), with recommended options. |
| 3 | engBOT → designBOT | Checked every new frame by node: SPLIT-02/03/07–13 Accepted; SPLIT-04 Accepted but waiting on SPLIT-05. Raised SPLIT-14 (no field to name the app), and asked for WHAT CHANGES on S-12c. |
| 4 | engBOT | Built the accepted work (e0da5fa iOS, 572b6b6 server) and opened PR #315. Commented on six Jira tickets. Noted two server side effects. |
| 5 | designBOT → engBOT | SPLIT-14 redesign (S-06 v3 / v3a), the S-12c card, 23 dark twins with the hand-set values, and SPLIT-15/16 for the two side effects (behaviour and copy). |
| 6 | engBOT → designBOT | Accepted SPLIT-14, the S-12c card, SPLIT-15 and SPLIT-16 (one copy change), and the dark twins with two notes. Built SPLIT-14/15/16 and the dark segment (f067b04), updated PR #315, and commented on THL-291/181/289. |
| 7 | product owner, then engBOT and designBOT | The product owner took designBOT's recommendations on SPLIT-01/05/06. engBOT checked the frames by node, built SPLIT-01, 04, 05, 06 and 12, and logged SPLIT-17, 18 and 19. THL-291's two AC lines were reworded, and THL-291 and THL-278 were commented on. designBOT bound every dark-twin green to the money-in token, tagged the system alerts and opened all 23 twins. |
| 8 | product owner, then designBOT → engBOT | The product owner decided SPLIT-17 (Split into parts stays removed, Always on), the dark money-in green (#6EDB94) and the $85 AC rewording, and approved the round-8 frames to build. designBOT redrew S-22 v2 and drew S-11k / T-08k (SPLIT-18) and S-11c (SPLIT-19), light and dark. |
| 9 | engBOT | Checked every round-8 frame by node and Accepted SPLIT-17, 18 and 19. Built SPLIT-18, SPLIT-19 and the dark green (8176985). Updated PR #315, reworded THL-291's $85 line, and commented on THL-291 and THL-254. |
| 10 | product owner, then engBOT | The product owner asked for the two small engBOT items. engBOT checked S-11c, its note and T-08k by node, then built the SPLIT-19 list line (server `paid_back`, Owed to you once, S-05) and T-08k's own error line (d2dc59d). Updated PR #315 and commented on THL-291. The web token was left for the product owner. |
| 11 | product owner, then engBOT | The product owner decided SPLIT-06 (a) everywhere, THL-181's ask, the Jira edits and the web dark token. engBOT logged SPLIT-20 and built it (the Quick sort sheet holds a split). engBOT also logged SPLIT-21 for designBOT (approved to build, not built) and set the web dark money-in to #6edb94. engBOT edited THL-291, 289, 278 and 260 and commented on each and on THL-181. designBOT worked in Figma only. |
| 12 | designBOT, then engBOT | designBOT (in Figma, entries appended by engBOT) marked superseded frames, drew S-14p/S-05p/T-08k error for built behaviour, drew S-35a/S-35b for THL-181, and read Figma's light money-in (#167A40). engBOT checked them by node and Accepted all four. engBOT then built SPLIT-21 (server ask rule with an ASK_FROM cutoff so old credits stay, plus the sheet) and the web light token (1f5bfd4), logged SPLIT-22, edited THL-278's unnamed-payback line, commented on THL-181 and THL-278, and updated PR #315. |
| 13 | designBOT | engBOT wasn't running. designBOT answered SPLIT-22: it drew S-35a1 (a), and S-05u, S-35c with its error, and S-21u (b), light and dark, with notes 1034:42633–42645. It also marked S-27 superseded by S-11 v2. The log edits were left uncommitted. |
| 14 | engBOT | Checked every round-13 node and Accepted SPLIT-22a, SPLIT-22b and the S-27 tag. Built SPLIT-22a and 22b (1ca13a6): the server list, POST …/credit with Undo, the Needs a look row, the split card, `WhoSentSheet` and Quick sort's held tick. Logged SPLIT-23, updated PR #315, and commented on THL-181. |
| 15 | product owner, then designBOT | The product owner decided SPLIT-23: (1) nobody left owing goes to "What's the other $x?", (2) one sender per payment, (3) no entry on the deposit's own page. engBOT wasn't running. designBOT drew S-21x and S-11x, light and dark, with tags and notes 1037:44471–44476. It rewrote the S-35c note 1034:42639 and its tags, and updated the Summary. The log edits were left uncommitted. |
| 16 | engBOT | The last round. Checked every round-15 node and Accepted SPLIT-23 (1), (2) and (3). Built (1) (34af59b): the `extra:<id>` Needs a look row, S-11x on `PartsSheet(whole:)`, Quick sort's held answer, the deposit's question card, and a `payback_more` Undo fix on `/mark`. Confirmed (2) and (3) in code. Updated PR #315, commented on THL-181, and listed the remaining gaps under Still open as notes for the product owner. |
| THL-301 | product owner, then designBOT | The product owner made THL-301 from the round-16 note and approved work on it. engBOT wasn't running. designBOT drew S-21xw, S-21xm, S-11xm and S-11xm over, light and dark, with tags 1044:99–106 and notes 1044:107–110, and logged SPLIT-24. The log edits were left uncommitted. |
| THL-301 | engBOT | Checked every SPLIT-24 node and Accepted it. Built it (68579a1): partly-extra `extra_question`, one item per deposit (credit, then extra), the save that keeps the credited parts with Undo (app and web), the S-21xm row, S-11xm and its over state, S-35c's mixed-case line, and Quick sort's follow-up card. Updated PR #315, commented on THL-301 and moved it to Testing. Listed the remaining gaps under Still open as notes for the product owner. |
| SPLIT-25 | designBOT, then engBOT | designBOT (engBOT not running) logged SPLIT-25 from the product owner's hand test and drew S-05v, S-05o, S-34s and its error, S-05t and nine S-34k sheets, light and dark. engBOT checked them by node, Accepted, and built the server and app (PR #316). After the product owner's mid-build change, S-05o and S-34s became Pearl sheets in one view, to be replaced by the custom design. engBOT commented on THL-291. |
| SPLIT-26 | product owner, designBOT, then engBOT | The product owner decided the design refresh (ink spending, Sort now → Quick sort, ••• menus with custom pages, pearl paper, look before animation). designBOT drew REFRESH-02 on "Design refresh" section 11 and logged it in design-refresh-log.md; engBOT relayed it here, checked it by node, Accepted, built the server toasts and Unlink? words and the app's Pearl sheets (PR #316), and commented on THL-291. |

Throughout, no ticket was moved past Testing, no bot merged anything (the product owner merged PR #315), and Figma was edited only by designBOT.
