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
| SPLIT-01 | Save before the split adds up: Jira and S-03b block it, the app allows it | Major | THL-291 | Needs product owner |
| SPLIT-02 | Edit split after someone has paid, or removing someone who paid | Major | THL-291, THL-181 | Built — PR #315, THL-291/THL-181 in Testing |
| SPLIT-03 | S-33 Edit on a deposit in parts has no edit state and can't save | Major | THL-291, THL-289 | Built — PR #315, THL-291/THL-289 in Testing |
| SPLIT-04 | "What's the other $172?" is drawn three ways and leaves out Jira's kinds | Major | THL-291 | Accepted, waiting on SPLIT-05 (not built) |
| SPLIT-05 | S-22 / S-11 use Income/Not income tabs and Continue, against the sorting rules | Minor | THL-291, THL-254 | Needs product owner |
| SPLIT-06 | Split from Quick sort: held for the card (T-96) or saved at once (THL-278)? | Major | THL-278, THL-254 | Needs product owner |
| SPLIT-07 | S-23/S-24 split and link aren't one save; leaving halfway keeps the split | Major | THL-260, THL-264 | Built — PR #315, THL-260/THL-264 in Testing |
| SPLIT-08 | Splitting a purchase on a joint account: offered, then refused by the server | Major | THL-291, THL-282 | Built — PR #315, THL-282 in Testing |
| SPLIT-09 | S-12 Check and save doesn't show the effect on Allowance | Major | THL-289, THL-291 | Built — PR #315, THL-289/THL-291 in Testing |
| SPLIT-10 | Odd cents and uneven percents: no frame, and the preview disagrees with what's saved | Minor | THL-291 | Built — PR #315, THL-291 in Testing |
| SPLIT-11 | Cash or Another app for more than they owe, and cash only partly deposited | Minor | THL-291 | Built in part — PR #315; extra path waits on SPLIT-04/05; app name → SPLIT-14 |
| SPLIT-12 | Code is ahead of Figma: split screens with no frame, or that differ from it | Minor | THL-291 | Built (T-09r title) — PR #315; income list waits on SPLIT-04/05 |
| SPLIT-13 | Owed to you from a Home nudge: in Jira, no frame | Minor | THL-291 | Built — PR #315, THL-291 in Testing |
| SPLIT-14 | Another app has no field for which app | Minor | THL-291, THL-289 | Still blocked → designBOT |

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
