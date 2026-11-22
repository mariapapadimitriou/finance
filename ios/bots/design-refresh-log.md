# Design refresh log

How designBOT and engBOT talk about the look-and-feel refresh. Append only.
Proposals live on the Figma page **"Design refresh"** (`1070:30063`) in the iOS
handoff file `ohcxhB9hV25H6nANVw3lq4`. Nothing on "Pearl app" or "Cash flow"
was changed. Every item below is **Awaiting product owner**: the product owner
picks what gets built. Nothing here has gone to engBOT yet.

---

### [designBOT → product owner] 2026-11-09 · REFRESH-00 · Scan, design language and refreshed key screens
**Status:** Needs product owner (all items Awaiting product owner)
**Jira:** THL-104, THL-119, THL-120, THL-122, THL-123, THL-125, THL-181, THL-213, THL-231, THL-232, THL-254, THL-263, THL-282, THL-289, THL-301
**Figma:** page `1070:30063` (sections `1070:30064` to `1079:1485`, listed below)

## 1. What I scanned

Read only. I listed the sections on both pages, took low-scale screenshots of
each section, then looked at key frames one at a time. I also read
`ios/Pearl/Theme/Theme.swift`, `Nacre.swift`, the Pearl Design System "Color"
variables (Light/Dark modes) and styles (`Iridescent/Light`, `Moonlit sea/Dark`,
`Nacre/Diagonal`, which already says "one nacre element per screen"), and the Jira
tickets above (acceptance criteria for THL-125, THL-213 and THL-254 in full).

- **Pearl app** `751:6166`: Onboarding, sign-in and settings `86:99` · Profile `730:28816` · Accounts `731:29084` · Joint/merging `732:29466` · Categories and rules `732:29467` · Your data and Start over `733:29986` · Privacy `733:29987` · Home, Save and Wins `752:33772` · Income and bills `805:31224` · Debts `806:31526` · Set up again `808:31593` · Recurring transfers `812:31829` · Home: a bank needs you `814:32391` · Recovery codes and devices `814:32430` (deferred) · Approving a device `815:32490` · Remove a bank `829:32695`.
- **Cash flow** `1051:44500`: Happy path `331:99` · Alternate states `475:14288` · Splits and paybacks `536:14142` (being edited by another designBOT run, so read only) · Logic coverage `614:19428` · Sorting on one page `885:34544` · Select `813:31995` · Category preview `813:32588` · Leave out `829:32613` · Joint purchases `812:32107` · Needs a look `832:33069` · Third paycheque `809:31673` · Quick sort `862:33313`, `893:35391`.

## 2. Findings per flow

**Across the app**
- Every screen sits on the full-strength iridescent gradient with frosted-glass cards. It looks lovely, but nothing leads: the background competes with the number she came for, and contrast on muted text is low. The library's own rule ("one nacre element per screen") isn't followed.
- Red is used for *all* spending (rows, transaction page, sort card), so red stops meaning "over". That makes the app feel like a telling-off.
- There's almost no motion specified. The moments that should feel rewarding (sorting a card, finishing Needs a look, a split adding up) are static.
- What's working: clear copy, consistent components (library tab bar, rows, chips, Option/Category icon sets), the pearl/shell identity, real light and dark coverage, and the dashed "guess" chip as a clear AI marker.

**Onboarding** (`86:99`, e.g. O-01 `112:1707`, O-10 `88:508`)
- Working: warm welcome, the shell-progress header (closed → open shell over three parts) is a great on-brand progress device, and "Your pay and bills" asks her to confirm, not type.
- Could be better: the shell progress is static. Animating it opening a step at a time and a short pearl moment on O-11 "You're all set" would add momentum for free. Bank linking is Plaid's in-app SDK, not a web hand-off, so that's fine.
- Taps: about 12–15 screens from Welcome to linked; not changed in this pass.

**Home + Allowance** (H-00 `752:33773`)
- The Allowance number is small (inside a ring with a separate title above); the Needs a look card is three lines of text with a small "Review one by one" link. THL-125 asks for one primary action.
- Taps to start sorting: 3 (Review → Quick sort → Yes). Delight: the ring should fill and the number should count up after sorting.

**Cash flow list** (T-01 `331:100`)
- Three equal-weight numbers in three colours; every spending amount is red; each row repeats its date.
- Working: search, filters, Transactions/Calendar, Select, guess chips.

**Transaction detail** (T-03 `487:14288`, T-103 `977:36426`)
- Red hero amount; "Always for Loblaws" is mixed in with options, though it's really part of the category decision. Five options plus a note under two headers.

**What was this? / sorting** (T-08 `348:11846`, Outcome table `349:9375`)
- 12 equal tiles in a 3-column grid; long labels wrap ("Work paying me back"); Split into parts sits below the fold. The four income answers (the common case) get no more weight than the rest.
- Answering takes 1 tap (tiles answer at once). Good. The problem is finding the answer.

**Needs a look** (T-83 `832:33070`, T-16 `338:4432`)
- Quick sort, the fastest way through, looks like one more row. Chips and Skipped behave as THL-213 asks.
- The zero state "All sorted" doesn't show what changed. THL-254 asks the done screen to show the Allowance change.

**Quick sort** (T-93 `893:35392`, T-95 `893:35466`)
- The shape is already right: one card, Skip or Yes, Undo. Missing are a progress feel ("2 of 54" is small text), a visible "Later" (THL-254) and motion telling her where the card went.

**Splits and paybacks** (S-03b v2 `994:36736`, T-39 `523:14239`, S-04 v2 `1001:38264`, S-12 v2 `999:37852`)
- The logic is thorough (THL-289/181/301). The UI makes her *read* whether amounts add up ("$4.12 isn't anyone's yet"). Acting on someone who owes takes a tap on them, then an action sheet.
- Taps to mark someone paid back: 3 (person → Mark paid back → S-06 sheet).

**Profile / Accounts** (P-01 `730:28817`, AM-01 `731:29085`)
- Working: plain grouped lists, status badges ("1 needs you", Anchor, Joint 50%, Not in budget, Manual).
- Could be better: Profile's last group sits under the floating tab bar, and five Money rows each repeat an icon and a two-line subtitle. No redesign in this pass; the visual system (pearl paper, solid cards) applies directly.

## 3. Design language (on the Design refresh page)

- **Principles** `1070:30070`: one job per screen · numbers first, big and calm · colour means something (rose = action, green = money in, ink for spending, red only for "over") · one nacre moment per screen · every motion explains something · reward progress, never nag · native first · inspired, never copied.
- **Visual system** `1070:30095`: type scale on Fraunces/Figtree (adds a 48 pt hero number; the rest maps to `Pearl.display/heading/text`), 4-pt spacing, Theme.swift's radii unchanged, colour use bound to the library Color variables. Pages sit on `surface/page` "pearl paper" with a soft nacre aura at the top. Cards are solid `surface/card` with a 1 pt `border/subtle` and no shadow at rest. Existing Option/Category icon sets are reused.
- **Motion system** `1070:30216`: twelve named motions with what each explains, key frames, timing/easing (SwiftUI springs), haptic and Reduce Motion fallback: `sort.flyAway`, `check.pop`, `number.countUp`, `ring.fill`, `progress.advance`, `queue.zero`, `sheet.present`, `tile.answer`, `row.sorted`, `toast.undo`, `split.meter`, `press.scale`.

## 4. Refreshed screens (all tagged "Design refresh · Awaiting product owner")

Each section has the BEFORE thumbnail (a locked clone of the current frame), light, dark and a note.

| Screen | Section | Light | Dark | Extra states / key frames | Why it's easier or more fun |
|---|---|---|---|---|---|
| H-00r Home (Allowance) · THL-125, 254, 213, 123 | `1073:101` | `1073:146` | `1073:251` | – | Allowance at 48 pt inside the nacre ring; one primary "Sort now" with a progress bar (40 of 48 already sorted); taps to reach Quick sort 2 → 1 (to the first Yes 3 → 2). ring.fill / countUp. |
| T-01r Cash flow list · THL-122, 123, 231, 213 | `1074:277` | `1074:356` | `1074:497` | – | Leftover is the one headline; spending in ink, so red means "over"; day headers take dates out of the rows; "8 need a look · Sort". |
| T-03r Transaction detail · THL-122, 123, 254, 289 | `1074:588` | `1074:670` | `1074:814` | – | Ink hero amount; category + "Always for…" in one card with a plain-words caption; all options kept. |
| T-08r What was this? · THL-231, 232, 254, 263, 289 | `1075:798` | `1075:911` | `1075:1056` | tile.answer `1075:1142` | Who and how much lead; four big income tiles (2 × 2); eight one-line not-income answers; Split into parts above the fold; same shared page. |
| T-83r Needs a look · THL-213, 232, 123, 254 | `1076:1144` | `1076:1191` | `1076:1268` | – | Quick sort becomes the hero card (nacre edge, time, progress, Start); chips and Skipped unchanged. |
| T-16r All sorted · THL-254, 213, 232 | `1076:1144` | `1076:1386` | `1076:1429` | queue.zero 0 ms `1076:1462`, 350 ms `1076:1495` | Shows the Allowance change (THL-254); "54 sorted today"; shell opens and the pearl glows, once a day, never blocks Done. |
| T-93r Quick sort card · THL-254, 263, 213, 122 | `1077:1373` | `1077:1412` | `1077:1464` | Yes 120 ms `1077:1498`, Yes 280 ms + Undo `1077:1560`, Skip 120 ms `1077:1616` | Progress bar, "Later" (THL-254), bigger Yes; card flies the way she answered; light haptic on Yes only. |
| S-03r How to split · THL-289, 282 | `1079:1485` | `1079:1600` | `1079:1668` | over `1079:1736`, adds up `1079:1801` | split.meter shows "not yet / adds up / too much" before she reads; rest-stays-yours rule and "Split the rest evenly" unchanged. |
| S-04r Split card · THL-289, 181, 301 | `1079:1485` | `1079:1947` | `1079:2004` | many people `1079:2042` | Each person has a paid-back bar; Mark paid back and Remind inline, Let it go under •••; taps to reach "Mark paid back" 2 → 1 (to the S-06 sheet 3 → 2). |

Notes: `1073:286`, `1074:572`, `1074:888`, `1075:1289`, `1076:1332`, `1076:1537`, `1077:1681`, `1079:1867`, `1079:2129`.

House rules checked: "Allowance" everywhere (never the other phrase); no web hand-offs; one shared What was this? page reachable from Transactions, Needs a look and Quick sort; one card is one transaction, never grouped; merchant names are sample data only, nothing hard-coded; recovery-code frames untouched (deferred). No Jira behaviour was removed. A daily streak was considered and **not** designed because Jira has no ticket for it.

**Decisions for the product owner** (flagged in the notes):
1. Spending amounts in ink instead of red across the app.
2. Home's "Sort now" opening Quick sort directly ("See the list" still opens Needs a look).
3. Split card: inline Mark paid back / Remind instead of the S-04 v2 action sheet.
4. Pearl paper background for in-app pages (iridescent kept for onboarding and celebrations).

## 5. What I'd build first (biggest gain for least work)

All **Awaiting product owner**.

1. **Motion primitives**: `number.countUp` (`.contentTransition(.numericText())`), `check.pop`, `press.scale`, `toast.undo`. Small shared modifiers, used on every screen after. Awaiting product owner.
2. **Quick sort momentum** (T-93r): progress bar, "Later", `sort.flyAway` with haptic on Yes. Contained in one view; THL-254 asks for "Later" already. Awaiting product owner.
3. **All sorted with the Allowance change + `queue.zero`** (T-16r): closes a THL-254 gap and gives the payoff moment. Awaiting product owner.
4. **Spending in ink, red only for "over"**: a colour swap in the amount views; calms every list. Awaiting product owner (decision 1).
5. **Home hero + "Sort now" card** (H-00r) with `ring.fill`. Awaiting product owner (decision 2).
6. **What was this? layout** (T-08r): 2 × 2 income tiles, 2-column not-income answers, `tile.answer`. Awaiting product owner.
7. **`split.meter`** in How to split (S-03r). Awaiting product owner.
8. **Split card inline actions** (S-04r). Awaiting product owner (decision 3).
9. **Pearl paper background** across in-app pages: the biggest visual change, touching every screen, so build it last, once the product owner has seen it on a few. Awaiting product owner (decision 4).

Not refreshed in this pass (findings only): onboarding, Profile, Accounts, settings.

---

### [product owner] 2026-11-09 · Decisions on REFRESH-00
1. Spending in ink, red only for "over": **Approved**.
2. Home "Sort now" opens Quick sort directly; "See the list" opens Needs a look: **Approved**.
3. Split card: each person's row gets a ••• menu. "I need a new design for those option pages, and everything presented after them should have a design as well — don't just use iOS components."
4. Background: not decided at first; then decided the same day (next entry).
5. Look and functionality first; animation comes later (keep motion notes, nothing depends on them).

### [product owner] 2026-11-09 · Background: pearl paper in the app
Use the calm, plain "pearl paper" background for in-app pages; keep the iridescent background for onboarding and celebrations. Use it on the new split menu and confirmation screens. Build-first order is unchanged: the background stays last because it touches every screen.

### [designBOT → engBOT] 2026-11-09 · REFRESH-01 · Retagged after the decisions
**Status:** Redesigned (tags only)
**Jira:** THL-125, THL-254, THL-213, THL-123, THL-122, THL-231, THL-289   **Figma:** H-00r `1073:101` (`1073:146`, dark `1073:251`, tag `1073:287`) · T-01r `1074:277` (`1074:356`, dark `1074:497`, tag `1074:573`) · T-03r `1074:588` (`1074:670`, dark `1074:814`, tag `1074:889`) · background tag `1096:4519` · S-04r superseded `1079:1947`, `1079:2004`, `1079:2042` (40%), note tag `1079:2130`
- **Approved — build:** H-00r (decision 2, plus ink spending), T-01r and T-03r (main change is ink spending, decision 1).
- **Background (decision 4):** no refreshed screen has the background as its *main* change. Every in-app refresh frame already sits on pearl paper, so I tagged the background itself as Approved — build in the Visual system section (`1096:4519`) instead of re-labelling screens whose main change hasn't been decided. The new section 11 below uses pearl paper throughout.
- **Still Awaiting product owner:** T-08r, T-83r, T-16r (the celebration, which stays iridescent under decision 4), T-93r, S-03r and the motion system.
- **S-04r** (inline Mark paid back / Remind) is superseded by S-04r v2 under decision 3. It's left at 40% for the product owner to clear out.

Build-first list update: item 4 (ink spending) and item 5 (Home "Sort now") are now **Approved — build**. Item 8 is replaced by section 11 (Approved — build). Item 9 (pearl paper) is Approved, still built last. The rest remain Awaiting product owner.

### [designBOT → engBOT] 2026-11-09 · REFRESH-02 · Person options (•••) and every screen after them
**Status:** Redesigned · Design refresh · Approved — build
**Jira:** THL-289 (flow 2: Mark paid back, Remind "copy a message", Let the rest go; flow 7: unlink or edit from either side), THL-291 (partial paybacks, Let the rest go, "Unlinking any part from either side restores both sides", Undo), THL-181 (Paid back + Owes = share; amount-match suggestions), THL-301, THL-260, THL-279, THL-282   **Figma:** section 11 `1088:1695` on Design refresh (below section 10); kit `1088:1696`; notes `1096:4466` (options per state), `1096:4483` (accessibility, colour, motion), `1096:4498` (handoff)

Example used throughout: Loblaws −$150.00, split five ways at $30.00. Jo paid by a $60.00 e-Transfer that also paid back Pizza Nova. Sam paid $10.00 in cash. Priya owes. Alex was let go. Dana paid with two payments.

**No `.alert`, no `.confirmationDialog`, no action sheet anywhere in these flows.** Every menu, confirmation, error, loading state and success state is a Pearl sheet or toast. They're built from a small local kit (`1088:1696`) of Option row, Primary/Secondary/Text button, 44 pt Close and ••• buttons, and Toast with Undo. Colours are bound to the Pearl Design System Color variables, and dark frames switch the collection to Dark.

| Screen | Light | Dark |
|---|---|---|
| S-04r v2 · split card, ••• on each person | `1090:1743` | `1093:3991` |
| S-40a · options: owes | `1090:1846` | `1093:4058` |
| S-40b · options: paid part | `1090:1979` | `1093:4099` |
| S-40c · options: paid in full (shared e-Transfer) | `1090:2130` | `1093:4154` |
| S-40c2 · options: paid by two payments | `1090:2235` | `1093:4203` |
| S-40d · options: let go | `1090:2355` | `1093:4263` |
| S-05or · payback options (unsplit PAID BACK, REFUNDED BY) | `1090:2457` | `1093:4300` |
| S-06ra · how did they pay? | `1091:2131` | `1093:4329` |
| S-06rb · which payment was it? | `1091:2219` | `1093:4360` |
| S-06rc · cash in hand | `1091:2312` | `1093:4418` |
| S-06rd · another app | `1091:2372` | `1093:4452` |
| S-07ra · Remind (owes) | `1091:2433` | `1093:4490` |
| S-07rb · Remind (part-paid) | `1091:2480` | `1093:4519` |
| S-08ra · Let it go? | `1091:2527` | `1093:4548` |
| S-08rb · Let the rest go? | `1091:2579` | `1093:4578` |
| S-08rc · Let it go loading | `1091:2631` | `1093:4608` |
| S-08rd · Let it go error | `1091:2686` | `1093:4640` |
| S-03re · change their share | `1092:2360` | `1093:4671` |
| S-03fr · Remove Jo? (paid by bank) | `1092:2464` | `1093:4757` |
| S-03fr2 · Remove Sam? (cash) | `1092:2526` | `1093:4800` |
| S-03fr · loading | `1092:2583` | `1093:4838` |
| S-03fr · error | `1092:2648` | `1093:4883` |
| S-34sr · "This $60.00 also paid back Pizza Nova. Unlink only Loblaws’ $30.00?" | `1092:2716` | `1093:4927` |
| S-34sr · loading | `1092:2771` | `1093:4960` |
| S-34sr · error | `1092:2829` | `1093:4995` |
| S-34kr1 · e-Transfer, this purchase only | `1092:2890` | `1093:5029` |
| S-34kr3 · cash | `1092:2944` | `1093:5061` |
| S-34kr4 · cash that also paid another purchase | `1092:2999` | `1093:5093` |
| S-34kr5 · cash a deposit holds | `1092:3054` | `1093:5125` |
| S-34kr6 · another app | `1092:3109` | `1093:5157` |
| S-34kr7 · Work paying me back | `1092:3163` | `1093:5189` |
| S-34kr8 · refund | `1092:3220` | `1093:5221` |
| S-34kr9 · part of a deposit | `1092:3278` | `1093:5253` |
| S-34kr10 · payback that made the split | `1092:3332` | `1093:5285` |
| S-44a · after Unlink | `1093:2719` | `1093:5317` |
| S-44b · after Mark paid back | `1093:2825` | `1093:5381` |
| S-44c · after Let it go | `1093:2936` | `1093:5450` |
| S-44d · after Remove (paid nothing) | `1093:3045` | `1093:5517` |
| S-44e · after Undo let it go | `1093:3140` | `1093:5574` |
| S-44f · after Remind (copied) | `1093:3249` | `1093:5641` |
| S-44g · after Undo ("Linked again") | `1093:3358` | `1093:5708` |
| S-44h · Undo failed | `1093:3467` | `1093:5775` |
| S-44i · after Change share | `1093:3576` | `1093:5839` |

(Kind 2 of the ten SPLIT-25 unlink kinds is S-34sr itself; S-34kr1 and S-34kr3–10 are the other nine, numbered by the SPLIT-25 table.)

**Options per person state**
- **Owes:** Mark paid back (bank or e-Transfer, cash, another app) · Remind · Let it go · Change their share · Remove from the split (at once, with Undo).
- **Part-paid:** PAID SO FAR, each payment with View (bank or deposit only) and its own Unlink · Mark the rest paid back · Remind (for what's left) · Let the rest go · Change their share · Remove (asks first, S-03fr).
- **Paid in full:** PAID WITH, one card per payment with View the e-Transfer / deposit / refund (none for cash or an app that wasn't deposited) and Unlink · Change their share · Remove (asks first).
- **Let go:** Undo let it go (at once, with Undo) · Change their share · Remove (at once, with Undo). Any payments they made before show as in part-paid.

**Why** (the gain is the same in every state):
- Every state has one sheet, laid out the same way: what they owe or paid at the top, then the payments with their own View and Unlink, then the usual action first, then "Change the split".
- Unlink moves onto the payment itself, so the S-05o step goes away. Reaching Unlink from the card takes 3 taps → 2.
- Mark paid back is still 2 taps to S-06.

**Colour:**
- Amounts owed and the hero purchase are in ink; paid back is money-in; let go is muted.
- Red appears nowhere in these flows (decision 1). Errors use the champagne Banner. I overrode its fill to 22% champagne so the caution text reads in dark, where the library Banner's text was unreadable. That's worth fixing in the library.
- Pages are pearl paper (decision 4).

**Copy that's new or changed (for engBOT to check):**
- S-07rb's part-paid reminder: "Hey Sam! Thanks for the $10.00. Your share of Loblaws on Nov 11 was $30.00, so $20.00 to go." Today the app says "is $20.00".
- S-08: "Loblaws already counts in full until it's paid back, so your Allowance doesn't change." This follows the payback rule.
- Remove-at-once toast: "Priya removed · $30.00 back to your share".

**Motion** (notes only, built later): sheet.present, row.sorted, check.pop, toast.undo, with Reduce Motion cross-fades. Nothing depends on them.

**A reading to confirm with the product owner:** I took decision 3 to mean the ••• replaces S-04r's inline Mark paid back / Remind buttons, so every state uses one pattern. Tapping the row still opens the same sheet. If the product owner wants the inline Mark paid back kept as well for people who owe, it can sit under the row without changing S-40.

The handoff (what each screen calls, and what replaces SPLIT-25's dialog and its stop-gap `PaybackOptionsSheet`) is in note `1096:4498`. I haven't written to split-transactions-log.md; engBOT owns it.

### [designBOT → engBOT] 2026-11-09 · REFRESH-03 · Less words, less clutter (split screens)
**Status:** Redesigned · Approved — build
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-260, THL-282, THL-172; SPLIT-C, JOINT-A and JOINT-B (Jira pending)   **Figma:** section 14 1138:9246 (rules 1138:9247, handoff note 1138:9769); edited in place on Cash flow 536:14142 (+ 614:20363 / 614:22019) and Design refresh sections 10 (1079:1600 / 1079:1668), 11 (1088:1695), 12 (1102:4466) and 13 (1112:6476)
The product owner ordered a declutter pass to make screens read like Wealthsimple: few words, one clear action, numbers first. She then narrowed it to the split screens. I edited 158 split frames in place, 316 counting their dark twins: 55 + 55 on Cash flow and 103 + 103 on Design refresh. The edits are copy only and every frame keeps its ID. Removed: explainer sentences, row subtitles that only describe the row, footnotes and swipe hints, and lines that repeat the hero. Titles and buttons are now 1–4 word verbs, toasts are about 5 words plus Undo, and every confirmation keeps each consequence once (who owes you again, and what goes back to Needs a look). There is one layout change: S-41j / S-41j2 lose the emptied "Sam Lee’s $50.00 stays theirs" row. No flow, state, confirmation, Undo or Try again was removed. Every loading, error, one-person and many-person frame is still there. Removed lines inside component instances are hidden, so build them as removed. VoiceOver hints that carry the old sentences are listed in the spec. The full spec, grouped by screen code with exact old → new text, is in refresh03-changes.md. No non-split frame was changed.

### [engBOT] 2026-11-09 · REFRESH-03 · Start
Read designBOT's entry above and the full spec (refresh03-changes.md, grouped by screen code with light and dark node IDs, exact old → new text, REMOVED elements, VoiceOver hints and the shared patterns P1–P3). Working on branch `refresh/split-less-words` from `origin/main` at df880d5 (SPLIT-25 to SPLIT-29 already in). Scope: copy and clutter only. No new screens, no new server behaviour, no animation. Mapped every old string to the code first (Swift views, `finance/unlink.py`, `finance/api.py`, `finance/parts_api.py`, `finance/profile_api.py`, Info.plist), then built.

### [engBOT → designBOT] 2026-11-09 · REFRESH-03 · Accepted
Checked by node and screenshot: S-41j 1107:6316 (the list is now two rows, "Priya won’t owe you $16.66" and "Jo’s $16.66 goes back to sort", with the joint-share row and its divider gone), the rules note 1138:9247 and the handoff 1138:9769. They match the spec, and the spec matches what I built. Accepted as a whole; nothing is blocked. Notes, not a design loop:
- **Names, not pronouns:** the S-03e hint reads "Priya paid $8.04 more than Priya’s share. It shows under You owe in Owed to you." (name interpolated, as the product owner asked). S-14 / S-14p's You owe row already said "Overpaid for Pho Hung" in the app, so nothing changed there.
- **Already short in code, so nothing to apply:** S-01jr's "Joint with Sam Lee · 50/50 · your part $50.00" and S-01jr2's "all yours unless you say otherwise" (the app's Whose was it? row says "$50.00 of $100.00" / "Joint with Sam · yours, Sam’s or shared"); S-03j's "Your share is counted in your spending"; S-03j1's "…and it stays yours"; S-03u0's "Add at least one person…" (Save is simply off until someone is added); S-03fu1's "A split needs at least one person…" (the server's refusal is "Add someone to split it with."); AM-08p5's "Type their name above…" (the empty picker shows "Type a name" only); AM-08p7's error (the app shows the API's own error text); S-06 v3's "Shows on the split as…" line and S-06 v3a's helper (the field's prompt already says "Which app? (optional)"; the spec's hint was added to it).
- **S-44u1–u4 toasts:** the app shows the server's S-44b toast "Priya paid back $25.00" when linking from a Not sure yet card (S-44b is unchanged by the spec), "Undone." after an Undo, "Unlinked · Priya owes $25.00" after an unlink and "Linked again" after undoing one. None carried the old long text, so none changed.
- **Product owner item 1 (Home):** `HomeView` draws H-00 and H-00n/H-00u from the same strings (one NeedsALookCard, one OwedNudgeCard, one ring caption), so the short copy is built for Home as a whole: "54 to sort", "Pearl sorted 40 by itself.", "Sam and Priya owe you $70.10" (+ " · 1 not settled"), "October had 3 paycheques.", the Cash flow footnote gone, and the ring's "Left to spend or save on non-essentials." hidden on Home and kept as the ring's VoiceOver hint. Onboarding's O-11b keeps that line (not a split screen).
- **Product owner item 2 (S-34sr footnote):** built as the spec's hint on the payment row ("To unlink the whole $60.00, open the e-Transfer."); the server no longer sends `note`.
- **Product owner item 3 (AM-08p title):** built as "Shared with", as the spec says.
- **Product owner item 4 (S-05o):** the built sheet is S-05or (a Pearl sheet, `PaybackOptionsSheet`); no stock action sheet is used anywhere in the split flow (tests/test_split_menus.py checks the source).

### [engBOT] 2026-11-09 · REFRESH-03 · Build
Built on `refresh/split-less-words` (commit 73c3337, app and server). The spec lists 110 distinct `old → new` strings, 32 removed elements and 16 hints; about 95 strings and 30 removals had a counterpart in the code and were applied, with 14 `accessibilityHint`s added. Where a string is built by code, the format changed, not one instance (`"Remove \(p.name)"`, `"\(count) to sort"`, the Unlink? lines in `finance/unlink.py` for every payback kind, the toasts in `finance/api.py`, `parts_api.py` and `profile_api.py`).
- **Pearl sheets (SplitMenus.swift, SplitFlow.swift, PaybackOptions.swift, JointSplitViews.swift):** S-40a–d / S-40u / S-40u2 row titles alone ("Remove Priya"; Mark paid back and Remind keep their meaning as hints; the money subtitles stay); S-07ra/rb/u one line and the field's hint; S-03fr/fr2 and S-03fu's lines, with "Pizza Nova counts as $100.00 again." on a Not sure yet split (`RemovePersonSheet(countsAgain:)`); S-03b v2 / S-03r / S-03re "$4.12 left · stays yours" and "Your share $44.12"; S-03e "Adds up ✓ · you owe Priya $8.04" (S-03 keeps "Adds up to $84.12 ✓"); S-03u's card and no footnote; S-04u Settle up / That's everything / Reopen split titles with hints, and no "Amounts not set" line; S-06ra three titles, S-06rc, S-06 v2, S-06 v3a's hint; S-08r "Your Allowance doesn’t change."; S-11c the one fact; S-05or's View row alone; S-34sr's footnote as the payment row's hint (the server stops sending `note`); S-40c's payment card line; S-45a "How to settle?" and "Nobody owes after this."; S-46a; S-41j / S-41j2's two-row list (the joint-share row and its divider are gone); AM-08p–p4, AM-08r/x, AM-21j / AM-08n's lines and footnote; S-17j and the server's refusal "Sam Lee’s part is already off."; T-06jr1 "None of it is yours to split." (app and server); O-09cr; the contacts purpose string.
- **Pages (PartsFlow.swift, TransactionDetailView.swift, WhoSentSheet.swift, Review, Home):** S-09u2, S-10e (the swipe hint is the rows' VoiceOver hint), S-11k, S-11x / S-11xm and the over line (app and the server's matching error), S-12c, S-13 v2, S-14u / S-14u0, S-35a / S-35a1 / S-35b / S-35c / S-35u, S-36; T-98s "Skip forgets the split." with hints on Yes and the card; P1 "6 to sort" (QuickSortCard) and "Tap one to sort it." gone (T-10, T-70, every Needs a look backdrop); H-00n / H-00u / H-00u0 as in the Accepted entry.
- **Toasts (server unless noted):** "Priya removed" (and the app's own), "Let go · $30.00", "Copied" (app), "Split removed", "Split closed", "Split reopened", "Settled · $46.66 owed" / "Settled up" (app), "Not joint now" (app and server), "Share 60% · 2 splits updated". Undo on every one as before.
- **Kept on purpose (Jira):** every confirmation sheet, Undo, Try again, loading spinner and error banner. Nothing was dropped to make a line shorter; where the spec's new line left out a consequence that Jira requires, the consequence is still on the sheet once (S-34sr: who owes again, and what goes back to Needs a look).
- **No stock iOS dialog** was added; the split flow still has none (checked by `tests/test_split_menus.py`).

### [engBOT] 2026-11-09 · REFRESH-03 · Tests and PR
- `python3 -m pytest -q`: 1907 passed (1901 before; 6 new in `tests/test_split_menus.py::TestLessWords`: the removed phrases are gone from the split views and the server by source, a sample of the new words is there, each removed line that carried meaning is an `accessibilityHint`, no pronoun stands in for a name, "Allowance", and the server's Unlink? and Let go words). Assertions on the old words were updated in `tests/test_split_round.py`, `tests/test_unlink_from_purchase.py` and `tests/test_joint_and_unsure_splits.py`.
- `npm run build`: built. The web shows the server's new strings as they are; no web code changed.
- `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED, no warnings in the changed files.
- Not run by hand on a simulator or a device. Please test the split screens by hand before merging.
- **Commits** on `refresh/split-less-words` (from `origin/main` df880d5): 73c3337 app and server; 2nd commit tests; then this log commit. `git show --stat` checked after each.
- **PR:** https://github.com/mariapapadimitriou/finance/pull/318 against `main`. Open, not merged.
- **Jira:** commented on THL-291 with the PR and what changed. Nothing moved.

### [designBOT → engBOT] 2026-11-10 · REFRESH-05 · Light mode colour: C‴ with the darker grey
**Status:** Redesigned · Approved — build
**Jira:** THL-125, THL-254, THL-213, THL-123 (Home), THL-122, THL-231, THL-232, THL-263 (transactions, sorting), THL-289, THL-291, THL-181, THL-301, THL-282 (splits), SPLIT-C / JOINT-A / JOINT-B (Jira pending)   **Figma:** Design refresh page 1070:30063 · section 15 1181:15794 · chosen column C‴ 1188:16852 · overview 1185:16490 · library 3fdfPDKIjhiluGHtXWSF32 Section/Home: `Allowance orb` set, `Pearl dust` component; mist/600 VariableID:302:67
The product owner found the pearl-paper light mode too white. Of three options (A blush paper, B rose wash, C iridescent lite) she chose C and then asked for it to match the as-built Home exactly, with its pearl-dust bubbles and the glowing Allowance orb. So light mode is now: the Iridescent/Light background unchanged, Pearl dust (two white auras + ten bubbles, fixed positions) on top, glass cards with the Nacre/Horizontal 1.2 pt edge, and the H-00 Allowance orb on Home with the refresh words inside. Instead of lightening the background for contrast, muted text steps to #514D67 (color/text/muted light; passes AA on every stop, 4.59:1 worst). color/surface/card light = glass/light, color/border/subtle light = glass/edge-light. Dark mode, type, action colours, red-only-for-over and the money-in green do not change; the disabled/placeholder, money-text and link-red steps are noted in Figma and on hold. Every current light frame in Design refresh sections 1–14 is re-painted (paint only; IDs, labels, copy and layout unchanged); dark frames untouched. Exact values, layer lists and SwiftUI sketches: refresh05-handoff.md. Library changes are not published; the product owner publishes once, with REFRESH-04.

### [engBOT] 2026-11-10 · REFRESH-05 · Start
Read designBOT's entry above, the handoff (refresh05-handoff.md: tokens, the Pearl dust positions, the orb layer by layer, the card treatment, the screens that change) and the Figma frames by node and screenshot: the chosen column C‴ `1188:16852` (Home `1188:16854` with the orb `1192:17083`, S-04u `1188:16945`), the re-rendered H-00r `1073:146` and T-01r `1074:356`, and the as-built H-00 (`NacreBackground`, `GlassCard`, `AllowanceRing` in the code). Branch `refresh/light-iridescent` from `origin/refresh/split-less-words` (PR #318, REFRESH-03) at 22d3cb3. Scope: light mode paint only. Dark values do not change; no copy changes; no animation.
What the code already had: every page except the Pearl sheets already sat on `NacreBackground` (the Iridescent/Light gradient, two proportional auras and a `Bubbles` picture with seven bubbles). What it did not have: the Pearl dust at the component's ten positions, glass on the solid white cards (`PearlCard`, `PearlOptionCard`, `InfoNote`, the split cards drawn by hand with `Pearl.card` + `Pearl.border`), the sheets (on the flat `Pearl.page` #FBF8F6 and a pale `SheetBackground` wash), the darker muted grey, and the orb (Home drew O-11b's ring with a different halo, track, thumb and type).

### [engBOT → designBOT] 2026-11-10 · REFRESH-05 · Accepted
Checked the handoff against the frames and the code. Accepted as a whole; nothing is blocked. Notes, not a design loop:
- **Home's words.** H-00r and C‴ Home have no "Your Allowance" title above the orb: the orb's label "Allowance" is the heading. The app's Home had the title plus the ring's month overline ("NOVEMBER"). Built as the frames show: date overline, then the orb with "Allowance" / amount / "left in November" (the label carries the header trait for VoiceOver), the REFRESH-03 caption hidden and kept as the hint. For the other Allowance states the orb's sub line reuses the overline's words as they were: "12 days left" when over, "Nov 20–30" when started part-way, nothing without income. No other words changed. If the product owner wanted "Your Allowance" kept, it is one line to put back.
- **O-11b.** The onboarding ring is the same shared view now (`AllowanceOrb`), with O-11b's own words left alone (its month overline as the label, no sub line); its type follows the component (Figtree Medium 15 label, Fraunces SemiBold 44 amount) instead of the old small caps and 52 pt amount. O-11b is not a refresh frame; say if it should keep the old proportions.
- **Pearl dust positions.** The app's old bubble picture had seven bubbles at other positions (and the two auras sized to the screen). Light now draws the component's ten bubbles and two auras at the handoff's fixed positions, scaled with the screen's width so the top-right cluster stays by the corner on a wider iPhone. Dark keeps its own auras and picture.
- **Card radii.** Kept as each card had them (24 pt `PearlCard`, 26 pt `GlassCard`, 20 pt option cards, 16 pt rows): the handoff says paint only and the re-painted frames kept their layout. The handoff's "radius 20" is read as the Home card's own radius, which stays 24 in the app as before.
- **Lists.** The glass is one blur per card, never per row: a day's transactions share one `GlassCard`; Needs a look (T-83r) and the Categories list keep a flat white @72% row fill (no blur) because they are `List` rows, with the new white @80% dividers. They read as glass on the gradient without a blur per row.
- **Fields and answers** (text fields, the amount row with the action stroke, `ChoiceRow`) take the new tokens (white @72% fill, white @80% hairline) but no blur, edge or shadow: they are controls, not cards.

### [engBOT] 2026-11-10 · REFRESH-05 · Build
On `refresh/light-iridescent`. Light mode only; dark branches keep their old values and are tested for it.
- **Tokens (`Theme.swift`):** `Pearl.muted` light `#605D76` → `#514D67` (dark `#B4B1CC` unchanged); `Pearl.card` light white → white @72% (dark `#151B44`); `Pearl.border` light `#EEDFE6` → white @80% (dark `#252C5E`); `Pearl.rule` the same; `Nacre.separator` (the line between rows in a card) = `Pearl.border`; `Pearl.cardShadow` `#664D99`; `Pearl.page` removed (no flat light page any more), with `Pearl.onInk` for the toast's words. `pearlPage()` removed. `Pearl.track`, `answered`, `bar`, ink, action, money-in/out untouched.
- **Background (`Nacre.swift`, new `Theme/PearlDust.swift`):** `NacreBackground` light = the unchanged Iridescent/Light gradient + `PearlDust` (two white auras 360 @50% at (−60, 40) and 280 @40% at (160, 420), blur 90; ten bubbles with the radial white fill and the white @85% 0.8 pt stroke at the component's positions; `.accessibilityHidden`, no hit testing). Every screen already used `nacreScreen()`, so every light page has it. `SheetBackground` light = `NacreBackground()` (dark gradient unchanged), used by every `.sheet` and by `PearlSheet` (its body and `presentationBackground`), so the split sheets S-03*, S-04*, S-40*, S-05or, S-06r*, S-07r*, S-08r*, S-34*, S-44*, S-45*, S-46*, the JointSheet and the pay-and-bills sheet sit on the gradient with the dust.
- **Cards:** `GlassSurface(radius:)` is the one glass: `Nacre.glass` (white @72%) over `.ultraThinMaterial` (one blur), `Nacre.horizontal` 1.2 pt edge, shadow `#664D99` @10% y 8 blur 20 (dark: ocean glass, the pink edge and the softer shadow as before). `GlassCard` uses it; `.pearlCard(radius:)` turns the old solid cards into it in light and keeps the solid card with the 1 pt border in dark: `PearlCard` (H-00's cards), `PearlOptionCard`, `InfoNote`, the S-40c payment card, the S-03 person rows, the S-06r received row, the S-05or link card, the joint part card, `SolidCard` (T-03r). Long lists: one `GlassCard` per day or section in Cash flow; `List` rows (Needs a look, Categories) keep a flat glass fill with no per-row blur.
- **Allowance orb (new `Views/Components/AllowanceOrb.swift`):** `AllowanceOrb(progress:label:amount:sub:)`, 262 pt, built from the handoff's layers: halo 330 (angular nacre `#FF8FB1` → `#C9A8FF` → `#8FE0D4` → `#FFD6E0` → `#FF8FB1`, blur 60, 45%), track 14 pt white @55%, the arc from 12 o'clock with the `#D999FF` @45% glow, the 24 pt pearl at radius 124 (radial white → `#F3ECFF` → `#D9C6FF`, white @90% stroke, `#FFD9F2` glow), the 216 pt disc (glass @72% over a blur, Nacre/Horizontal 1 pt edge, `#734D99` @15% shadow y 10 blur 30), the words (Figtree Medium 15 muted / Fraunces SemiBold 44 −0.88 ink / Figtree 13 muted). One VoiceOver element, "Allowance, $6,413 left in November". No motion. Home and O-11b use it; `AllowanceRing` is gone.
- **Home (`HomeView.swift`):** date overline, the orb, the hidden caption as the hint, the glass cards. `Allowance.orbSub(month:)` gives the sub line.
- `make_project.py` run for the two new files. No stock dialog added; no copy changed on the split screens; "Allowance" throughout.

### [engBOT] 2026-11-10 · REFRESH-05 · Tests and PR
- `python3 -m pytest -q`: 1915 passed (1907 before; 8 new in `tests/test_light_refresh.py::TestLightIridescent`: the muted light grey is #514D67 and dark is unchanged; no pearl-paper light page remains (`Pearl.page`, `pearlPage`, the pale sheet wash); sheets sit on the iridescent background; the card tokens and `GlassSurface` match the handoff; the solid split cards go through `.pearlCard()`; `PearlDust` has the ten bubbles and two auras at the fixed positions; `AllowanceOrb` exists with the handoff's layers and Home and O-11b use it; "safe to spend" appears nowhere in the app).
- `npm run build`: built. The web is untouched.
- `xcodebuild -project ios/Pearl.xcodeproj -scheme Pearl -destination 'generic/platform=iOS Simulator' build`: BUILD SUCCEEDED; no warnings in the changed files (the one Swift warning is in `PrivacyViews.swift`, untouched and already there).
- Not run by hand on a simulator or a device. Please look at Home, a split sheet (S-04u) and Cash flow (T-01r) in light mode before merging; the orb and the cards are what matter most.
- **Commits** on `refresh/light-iridescent` (from `origin/refresh/split-less-words` 22d3cb3): fc4ad49 the app; 2nd commit the tests; then this log commit. `git show --stat` checked after each.
- **PR:** https://github.com/mariapapadimitriou/finance/pull/319, base `refresh/split-less-words` (stacked on #318). Open, not merged.
- **Jira:** one comment on THL-291 with the PR (the split sheets' cards are glass now). Nothing moved.

### [designBOT → engBOT] 2026-11-09 · REFRESH-04 · Split screens rebuilt on Pearl Design System components
**Status:** Redesigned · Approved — build
**Jira:** THL-289, THL-291, THL-181, THL-282, THL-301, THL-172 (SPLIT-C, JOINT-A, JOINT-B Jira pending)   **Figma:** Design refresh `1070:30063` → sections 10 `1079:1485`, 11 `1088:1695`, 12 `1102:4466`, 13 `1112:6476`, new section "Split components (to publish) · REFRESH-04" `1155:9588`; Cash flow `1051:44500` → Splits & paybacks `536:14142`, T-39/T-40/T-40b/T-41b/T-73 (Alternate states), T-70 `614:20363`, T-75/T-76 (Joint purchases)

The product owner asked for the split screens to sit on the Pearl Design System library instead of hand-drawn frames, so library changes flow into them and every piece maps to one SwiftUI view. Nothing you build from changes: every frame keeps its ID, name and label, every string is character for character what REFRESH-03 set, no line was added or removed, and layout moved by a few points at most (buttons 50→52, segmented control 40→36, rows a line-height). 421 frames were rebuilt, light and dark.

What is now a component (details and SwiftUI names in `refresh04-components.md`):
- **From the library as is:** Button (Primary/Secondary/Text), Glass button (close x, ••• more), Toast (Positive with Undo; Neutral with Try again), Toggle, Search field, Status pill (Joint), Banner (errors, already there), Choice, Segment. The section-11 kit's buttons, close, more and toast are gone; the kit frame is renamed "Superseded".
- **New, in the to-publish section (library candidates):** Sheet header (Eyebrow = the refresh header with avatar, eyebrow, Fraunces title, sub, glass close; Centered = the sheet as built), Person row (12 trailing variants: amount, ••• more, amount field, remove, tick, chevron and combinations), Option row (the kit row, now with Title/Sub/Icon/Show chevron properties), Avatar (Blush/Glass × 36–64), Amount field (Default/Focused/Over), Segmented control (3–5 segments, built from the library Segment), Callout (icon + title + body explainer), Chip button (44pt capsule action such as "Unlink $10.00…", "PayPal"). Each carries a description with its SwiftUI counterpart. I could not publish to the library file from this session, so they are local components in that section, built on the library's variables and text styles, ready to move.

Kept hand-drawn on purpose, so copy and layout stay (listed in the doc): loading buttons (the library Loading state hides the label), the 6pt paid-back bars (library Progress bar is 40pt with a label), split.meter, the "Received · Today, Nov 21" value row, the "Not settled" chip, and the two legacy iOS action sheets (S-04 v2, S-05o) which the S-40 sheets replace.

Layout deltas to know about (all listed in the doc): buttons are 52pt, the method control 36pt, rows whose sub wraps are 2pt taller per line (library Subheadline is 15/20), and the S-04r v2 split card is 24pt taller than the REFRESH-03 screenshot (three-line payment row + row padding), so "See everyone who owes you" sits at y=770 instead of 746. Nothing else moved more than a few points.

For you: a card of people = `List Section` of `PersonRow`; a sheet = `.sheet` with the `SheetHeader` view on top; ••• = a 44pt Button labelled "Options for <name>"; the method control = a segmented `Picker`. The hero, category row and captions on each screen are unchanged text.

### [designBOT → engBOT] 2026-11-10 · REFRESH-04 · Split components added to the Pearl Design System library
**Status:** Redesigned · Approved — build (library publish pending)
**Jira:** THL-289, THL-291, THL-181, THL-282, THL-301, THL-172   **Figma:** library `3fdfPDKIjhiluGHtXWSF32` → Components page, heading "Section/Splits" (298:693): Avatar 298:722, Amount field 298:729, Chip button 298:734, Segmented control (3–5) 298:762, Callout 298:763, Sheet header 298:799, Option row 298:800, Person row 298:951, Progress bar/Track 298:1018; Button 3:296 and Status pill 91:742 gained a property each

The eight split components are now in the library itself, in its structure and naming, bound to its Color/Layout variables and text styles, light and dark through the Color modes, each with a description that names the SwiftUI view. Three gaps are filled there too: Progress bar/Track (6pt, no label, same tones) for the paid-back bar under a part-paid person; Button "Label while loading" so "Letting it go…", "Removing…" and "Unlinking…" keep their words beside the spinner; Status pill "Show icon" for the "Not settled" chip. Sheet header is the official header for sheets the screen lays out; Bottom sheet keeps Title + Body for one-question sheets with a Content slot.

What is still pending: the library has to be published from the Figma UI (no API for it). The moment it is, I run the prepared swap so every split frame in the handoff file points at the library components (same variants, same values, same geometry), rebuild the six loading buttons, the paid-back bars and the "Not settled" chip from the new library pieces, and delete the local "Split components (to publish)" section. Nothing you build from changes before or after that swap. split.meter and the "Received" value row stay hand-drawn (no library piece fits without changing them). Keys are in refresh04-components.md.

**Closing check, 2026-11-10 (later):** asked to run the swap after publishing, I found the library still unpublished — every new split component reports UNPUBLISHED in `3fdfPDKIjhiluGHtXWSF32` and the handoff file cannot import the keys (Button still without “Label while loading”, muted light still mist/500). Nothing is lost; the swap (`refresh04-swap-to-library.js`) runs the moment the publish goes out. Status stays: library built, swap pending publish.

**Closing, 2026-11-10 (published and swapped):** the library is published and every split screen in the handoff file now uses it: Design refresh 1,081 swaps (Sheet header 166, Person row 395, Option row 202, Callout 24, Segmented control 32, Chip button 22, Avatar 240) plus 6 loading buttons (Button Loading, label kept), 53 paid-back bars (Progress bar/Track) and 4 "Not settled" chips (Status pill, icon off); Cash flow 548 (Sheet header 119, Person row 182, Segmented control 20, Avatar 227). Local section 1155:9588 deleted. Look kept by two overrides you should build as values: paid-back bars stay money-in green (paid in full) / action rose (part paid), and the lead option in S-40a and S-06ra keeps its filled action bubble. Section 14 "Before" frames, S-04 v2 and S-05o untouched. Still hand-drawn: split.meter and the "Received" value row.

### [designBOT] 2026-11-10 · REFRESH-05 · Closing

**Closing check, 2026-11-10 (later):** the Allowance orb and Pearl dust report UNPUBLISHED in the library and `color/text/muted` light still resolves to mist/500 (#605D76) in the handoff file, so the publish has not gone out. The Design refresh frames keep their local stand-ins and directly painted #514D67 until it does (re-binding now would revert the grey). Ready to run on publish: `refresh05-swap-to-library.js` — swaps 147 Pearl dust and 3 Allowance orb instances (Progress=70, words copied), re-binds the #514D67 text to `color/text/muted`, and puts Pearl dust under H-00 as built; the as-built orb stays as drawn because its inside copy (“NOVEMBER” / “$6,413”) does not fit the component’s Label/Amount/Sub slots without changing lines. H-00 has no dark twin on the Pearl app page.

**Closing, 2026-11-10 (published and swapped):** the Design refresh page now uses the published Pearl dust (147 instances) and Allowance orb (3: H-00r, H-00u, H-00u0, Progress=70, words unchanged; H-00r matches its pre-swap render); the 394 texts painted #514D67 are re-bound to `color/text/muted`, which now resolves to mist/600 #514D67 in light. Cash flow (2,691 texts) and Pearl app (610) show the new grey through the variable. H-00 as built uses a Pearl dust instance in place of its two auras and bubbles (identical positions, no visual change); its orb stays as drawn because its inside copy does not fit the component's slots. H-00 has no dark twin. The section 15 stand-ins 1196:17083 / 1196:17096 have no instances left and are renamed "Superseded". Dark frames untouched.

### [designBOT → engBOT] 2026-11-13 · CONSOLIDATE-01 · Figma is one snapshot of the app as built
**Status:** Redesigned (file structure) · T-93o and the bar-only split cards Awaiting product owner
**Jira:** THL-275, THL-289, THL-291, THL-181, THL-303, THL-304, THL-305 (labels), THL-127, THL-45 (IB-04)   **Figma:** Pearl app `751:6166`; Proposals `1284:99`
The product owner reviewed the 39 in-app refresh items and kept 38; item 08 (T-93n) is to become T-93o. Before this pass the product owner saved the version "Before consolidation 2026-11-13" by hand. Everything removed below can be restored from it.
- **One page.** The Cash flow page and the in-use Design refresh frames are now on Pearl app, under eight top-level sections: Home `1285:72187`, Cash flow and transactions `1285:72188`, Sorting `1285:72189`, Splits and paybacks `1285:72190`, Joint accounts `1285:72191`, Profile and settings `1285:72192`, Onboarding and sign-in `1285:72193`, Confirmation sheets `1285:72194`. The frames were moved, not copied, so every node ID cited in Swift comments and in these logs still points at the same frame. The Design refresh and Cash flow pages are deleted.
- **Deleted (140 frames, plus one empty section):**
  - Old frames the refresh replaced: H-00, T-01, T-03, S-04 v2, S-05o, S-07, S-08, S-03f, S-03b v2, S-34s and its error state, S-34k ×9 and S-05t, with their dark twins.
  - Every frame already marked superseded: SEC-04, SEC-12, CN-05, S-24x, S-01j, S-05p, S-03j, S-46a, S-45c, S-45e, S-45c2–c4, S-47c2 and the section-11 kit.
  - The unpicked or history refresh items: principles, visual and motion systems, T-08r, T-83r, T-16r, T-93r, S-03r/S-04r, the REFRESH-03 pairs and the REFRESH-05 colour columns.
- **Proposals `1284:99`:**
  - Awaiting product owner `1284:100`:
    - T-93o `1284:103` / `1284:170`. When Pearl's best guess is Other, the card still offers Yes and Skip, and Yes sorts only this one transaction, with no "always for" rule.
    - 20 split cards that show only the bar. Jo's "$60.00 e-Transfer · paid back…" line is hidden (Person row, Show detail off).
  - Deferred: the recovery codes, `1284:101`.
  - To check `1284:102`: S-03, S-05, S-19, S-20, S-06 v2, S-06 v3, S-06 v3a, T-75 and O-09c. The code still cites these codes, but newer frames may have replaced them.
- **Renames:**
  - The "Are these your rent?" sheet is now IB-04 (six frames). Its Swift comment at `IncomeBillsView.swift:82` still says IB-03.
  - "Jira pending" is replaced by THL-303 (SPLIT-C), THL-304 (JOINT-A) and THL-305 (JOINT-B).
  - "· Design refresh · Approved — build" is removed from 393 names.
  - Codes such as S-04r v2, S-40 and S-03r2 are kept because the Swift cites them.
- **For engBOT:**
  - T-01r groups Cash flow by day (TODAY, WED, NOV 12), but the app draws one card for the default sort (`TransactionsView.swift:950-968`).
  - T-03r keeps "Always for" in the category card, but the app still shows it among the options.
  - O-11b `260:4705` doesn't show the orb the app now uses.
  - Nothing new to build until the product owner picks from Proposals.

### [designBOT → engBOT] 2026-11-13 · CONSOLIDATE-02 · Built in #334 moved into Pearl app; TEST-31 drawn
**Status:** Redesigned (Pearl app now matches #334) · TEST-31 Awaiting product owner
**Jira:** THL-254, THL-275, THL-213, THL-122 (T-93o) · THL-289, THL-291, THL-181 (split cards, TEST-31)   **Figma:** Pearl app `751:6166`, Proposals `1284:99`
- **T-93o** `1284:103` / `1284:170` moved into Quick sort `893:35391` (Sorting `1285:72189`), in the place of T-93n. T-93n `1231:20937` / `1231:21001` is deleted. Matched to the build: the header is "Quick sort" over "11 left", with no Later and no progress bar. The first caption line is in ink and the second muted. Its ID is unchanged, so `QuickSortView.swift:123` and `Models.swift:1624` still point at it.
- **Bar-only split cards:** the change is applied to the 20 built frames in Splits and paybacks, not by moving the Proposals copies. Show detail is off on the paid-back person's row, so "✓ Paid back · <day>" and the bar stay. That keeps the IDs the code and logs cite (`SplitFlow.swift:1212` cites `1090:1743`). The 20 Proposals copies and their two notes are deleted. Not sure yet cards are unchanged.
- **T-01r, T-03r, dark switch:** the frames already drew what #334 built (day headers with no total and Select on the first header, "Always for" inside the category card, the selected segment on color/surface/card), so nothing changed. Search (T-45) is one card with the day on each row, as built.
- **TEST-31**, on Proposals › Awaiting product owner `1284:100`, light and dark:
  - T-09w `1294:1507` / `1294:1727`
  - S-04w `1292:1716` / `1292:1838`
  - S-40w `1294:1929` / `1294:2052`
  - S-04w2 `1292:1948` / `1292:2071`
  - S-11w `1294:2157` / `1294:2374`
  - S-04w3 `1292:2182` / `1292:2305`
  - Note with seven product owner decisions: `1294:2593`

  Built from the existing T-09, S-04r v3, S-40c and S-11c frames and the library Person row and Progress bar/Track. Nothing goes to engBOT until the product owner picks.
- **TEST-31 approved (product owner, 2026-11-13), all seven decisions as drawn.**
  1. "Your share" is its own match in What did this pay back?.
  2. "All of it · $120.00" stays and works as any whole-purchase payback: it covers Sam's part too.
  3. If work pays only part of your share, the uncovered $15.00 stays yours.
  4. The extra's answers don't include "Part of Sam's share".
  5. Linking lowers the cost and raises the Allowance straight away, without waiting for Sam (Rule A).
  6. The deposit page reads PAID BACK · Your share of Pai Northern Thai $60.00.
  7. The bar's 10% steps are fine.

  Now drawn: the deposit page T-41w `1297:64759` / dark `1297:64849`, built from T-41 and the library Row. The row reads "Pai Northern Thai" over "Your share · Nov 12" because the Row is one line. VoiceOver reads the full wording.

  Note `1294:2593` and all 14 TEST-31 frames now read "Approved, ready to build". They stay on Proposals `1284:100` until built.
- **Colour pass on Pearl app:** 758 spending amounts now use color/text/primary, the token the app uses for spending.
  - 750 of them were bound to color/text/money-out and 8 were hard-coded #BE2634, in light and dark, across about 230 Cash flow, sorting and split frames (T-01b, T-07–T-110, S-02–S-36 and their v2 versions, S-03e, S-05u/v, S-10e–S-36). Several of these are inside library Row instances, where the fix is an override.
  - Still red on purpose: T-01b's "Over $760", the over-total amount fields in S-03r2c and S-03rh, and destructive actions such as Sign out, Remove this account and Delete your account. Hard-coded rose (#B22657) is the action colour, not spending, and is untouched.
  - Before and after screenshots of T-46 are in scratchpad/test31.
- **Library: the Transaction row draws spending in ink** (Pearl Design System `3fdfPDKIjhiluGHtXWSF32`, product owner's request).
  - In the Transaction row set `91:808`, the money-out amount in both Out variants is now color/text/primary instead of color/text/money-out: Counts=Yes, Direction=Out `91:809` (text `91:819`) and Counts=No, Direction=Out `91:820` (text `91:830`, still at 70% opacity). Checked in light and dark.
  - The set's description now says spending uses color/text/primary.
  - No other library component draws spending in red. The money-out variable is kept as it is.
  - It's still used in the library only by Amount field State=Over (`298:727`, text `298:728`), which is the over-the-total error. In the handoff file it's still used by "Over $760" on T-01b, the over-total fields in S-03r2c and S-03rh, and the destructive text (Sign out, Remove this account, Delete your account, Disconnect TD).
  - **Not published yet:** the product owner publishes the library by hand. Accepting the update in the handoff file is safe: the 758 amounts I fixed one by one are overrides that are already ink, and the main component is ink now too.

### [designBOT → engBOT] 2026-11-14 · TEST-31b · Money back covers your share too
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181   **Figma:** Proposals `1284:99` › `1284:100`, below the work frames. Note `1303:3395`.
The product owner wants TEST-31 to work for deposits answered Money back (tile key "refund") as well as Work paying me back. I copied the work frames and changed only the refund wording, light and dark:

| Frame | Light | Dark |
|---|---|---|
| T-09rs | `1302:2312` | `1302:2517` |
| S-04m | `1302:2720` | `1302:2791` |
| S-04m2 | `1302:2850` | `1302:2921` |
| S-04m3 | `1302:2980` | `1302:3052` |
| S-40m | `1302:3112` | `1302:3215` |
| T-41m | `1302:3306` | `1302:3400` |
| S-11m | `1302:3494` | `1302:3708` |

- **T-09rs:** keeps T-09r's title, "What was this a refund for?". "Your share of Pai Northern Thai · $60.00" is its own match beside "all of it · $120.00".
- **S-04m, S-04m2, S-04m3:** your row reads "✓ Refunded · Nov 14", or "Refunded $45.00 of $60.00 · $15.00 stays yours", and the hero reads "· refunded". This follows the app's "Refunded in full" and REFUNDED BY.
- **S-40m:** REFUNDED BY, View the refund, and Unlink… (S-34kr8).
- **T-41m:** the chip stays "Refund" (not "Paid back"), with REFUND FOR, Unlink refund, and the Dining out category row, as on T-41. "Paid back" stays for people and work.
- **S-11m:** a $75.00 refund against a $60.00 share uses the existing extra tiles Another purchase · Not mine · Something else. There's no Split into parts on money in.
- I also changed 40 spending amounts on Proposals from red to ink (color/text/primary).

Open for the product owner:
1. Should a shop refund on a shared purchase offer "your share" first, or ask whether it was for you, for Sam, or for both?
2. Should a refund larger than your share be able to lower what Sam owes?
3. Should the T-41m chip stay "Refund"? I recommend it.
- **Approved (product owner, 2026-11-14):** your share comes first; a refund bigger than your share can count toward what Sam still owes (unlike work); the chip stays "Refund". The Money back frames and section `1284:100` are now "Approved, ready to build", and note `1303:3395` has the decisions and rules.
- **S-11m** `1302:3494` / `1302:3708`: the extra's tiles are now Another purchase · Not mine · Part of Sam's share (library people icon) · Something else.
- **New S-04m4** `1304:3403` / dark `1304:3490`: after "Part of Sam's share", Sam's row reads "Paid $15.00 of $60.00 · owes $45.00" with the rose part bar, as any part-paid person.
- **Rules for the extra:**
  - Only people on the split who still owe get a tile, one each, named, in the split card's order.
  - The extra goes toward what that person still owes, up to that amount. It counts as a payment from them, so Unlink is on their •••.
  - If the extra is more than they still owe, they're paid in full and Pearl asks once more about what's left, without that person's tile. It never spreads an extra across people by itself.
- **Bars:** the part-paid bars in S-04w2 and S-04m2 (light and dark) now use the same rose part bar as the built S-04r v3, instead of yellow Caution.

### [designBOT → engBOT] 2026-11-14 · AI-01 · AI in Pearl, phase 1 screens and phase 2 sketches
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-117, THL-139, THL-213, THL-254, THL-123, THL-127, THL-45, THL-198, THL-295, THL-125   **Figma:** Proposals `1284:99` › section "AI · Awaiting product owner" `1313:3507`, note `1316:5612`
On-device Apple Intelligence. Every frame extends a screen the app already has (H-00r, T-107 "Pearl sorted", S-40 sheets, CR-00x, CR-00, CN-04, T-93o, T-01r, T-02, T-46, IB-01), built from library parts, in light and dark:

| Frame | Light / dark | What it is |
|---|---|---|
| AI-01 | `1313:3508` / `1313:3567` | Home card "Pearl sorted 12 for you this week · See them" |
| AI-02 | `1313:3611` / `1313:3813` | Needs a look › Pearl sorted, one row per transaction with its reason |
| AI-03 | `1313:4078` / `1313:4198` | Why: Undo this one, Stop sorting like this |
| AI-04 | `1313:4306` / `1313:4359` | Stop sorting Ana's deposits? |
| AI-05 | `1313:4400` / `1313:4509` | Learned rules beside yours in Categories and rules |
| AI-06 | `1313:4615` / `1313:4735` | A learned rule's page, with its off switch |
| AI-07 | `1315:4227` / `1315:4282` | Quick sort AI guess with its reason, still Skip or Yes |
| AI-08 | `1313:4855` / `1313:4951` | Privacy: "On this iPhone · nothing leaves it" |
| AI-10 | `1315:4325` / `1315:4424` | "Search or ask Pearl" in Cash flow |
| AI-11 | `1315:4511` / `1315:4727` | Ask Pearl with suggestions |
| AI-12 | `1315:4924` / `1315:5112` | The answer, with the transactions behind it |
| AI-13 | `1315:5295` / `1315:5379` | Working |
| AI-14 | `1315:5462` / `1315:5545` | Nothing found |
| AI-15 | `1315:5628` / `1315:5711` | Apple Intelligence not available |

Phase 2 sketches, light only:
- AI-20 `1316:5243`: one insight at a time on Home.
- AI-21 `1316:5302`: Insights.
- AI-22 `1316:5400`: Your plan, a realistic month built on Income and bills.

Nothing to build until the product owner picks. The open decisions are in the note.
- **Approved (product owner, 2026-11-15).** Phase 1 frames are now "Approved, ready to build"; the decisions are in note `1316:5612`. The phase 2 sketches (AI-20 to AI-22) are not part of this approval.
  1. Pearl sorts by itself after 5 earlier answers that agree, or 8 for money between people.
  2. P1a sorts categories and joint "theirs" deposits only, up to 20 a day, new transactions only.
  3. The summary is the Home card plus the Pearl sorted filter. No notifications.
  4. "Stop sorting like this" asks first.
  5. Learned rules sit alongside the user's own.
  6. "Pearl sorts for you" and "Ask Pearl" each get their own switch.
  7. Ask Pearl gets a Home button.
  8. Suggestions are labelled. "Use this plan" replaces the numbers in Income and bills.
- **New frames:**
  - AI-16 `1320:5509` / `1320:5539`: Home with a 44 pt Glass button, sparkle icon, VoiceOver "Ask Pearl".
  - AI-17 `1320:5576` / `1320:5732`: the answer with a "Suggestion" Callout ("Nothing changes unless you set it.").
  - AI-03b `1321:5770` / `1321:5892`: Farm Boy → Groceries, "Like your last 5 at Farm Boy" over "All sorted as Groceries by you", with the same actions.
- **Changed frames:**
  - AI-08: two switches.
  - AI-02: the 20-a-day line. The rent and pay rows are swapped for Coffee and Health, because P1a sorts no transfers. Ana now shows 8.
  - AI-03: Ana now shows 8.
  - AI-06: "Tell me each time" is removed.
  - AI-07: the category caption.
- **P1a wording:** the server matches your own past answers, so P1a can't say "on this iPhone".
  - AI-08: "Up to 20 new ones a day · learns from your own answers"
  - AI-02: "Sorted from your own past answers, up to 20 a day. Tap one to see why or undo it."
  - AI-06: "Pearl learned this from 8 you sorted. Nothing new is shared."

  When the Apple Intelligence phase ships, these three switch to "on this iPhone" (exact strings in the note). Ask Pearl keeps "on this iPhone", since it only ships on-device.
- **AI-07 caption strings:** line 1 is the first case that applies.
  1. "Pearl's not sure: {k} of your last {n} here were {Category}." With k = 1: "…{k} of your last {n} here was {Category}."
  2. "Pearl's not sure: you split {k} of your last {n} here."
  3. "Pearl's not sure: {k} of the last {n} from {Name} were {Name}'s share."
  4. "Pearl's not sure: you've sorted only {n} here so far."

  Line 2 is always: "Yes sorts it as {Guess}. Tap the card for more."
- **Three controls, three outcomes (product owner, 2026-11-15).**
  - **Switch "Pearl sorts these":** off sends new matches to Quick sort. The rule and the rows it already sorted stay. Sub: "Off: new ones go to Quick sort. What it sorted stays."
  - **"Stop sorting like this":** asks first, undoes every row it sorted, and the pattern is never relearned.
    - AI-03 sub: "Asks first · undoes the 6 and won't learn it again"
    - AI-03b sub: "Asks first · undoes the 3 and won't learn it again"
    - AI-04 body: "The 6 Pearl sorted this way go back to Needs a look, and Pearl won't learn this again. New ones from Ana go to Quick sort."
  - **"Forget this rule":** asks first in the new AI-04f `1322:6047` / `1322:6100`, removes the rule and keeps what it sorted.
    - Title: "Forget Farm Boy?"
    - Eyebrow: "LEARNED BY PEARL"
    - Body: "What Pearl already sorted stays. Pearl may learn it again once you've sorted Farm Boy the same way 5 more times."
    - Buttons: "Forget" · "Keep it"
- **New AI-06b** `1322:5853` / `1322:5950`: the category version of the learned rule page, in the same layout as AI-06.
  - Title: "Farm Boy"
  - Top line: "Pearl learned this from 5 you sorted. Nothing new is shared."
  - WHAT PEARL DOES: "Sorts them as Groceries" over "Any card or account", and "Purchases at Farm Boy" over "Any amount". Add ", about every 2 weeks" (or every week / every month) only when the past answers have a regular rhythm.
  - Then the switch, "See the 3 it sorted" and "Forget this rule".

### [designBOT → engBOT] 2026-11-15 · AI-02b · P1a frames moved into Pearl app
**Status:** Redesigned (Figma now matches #341)
**Jira:** THL-117, THL-139, THL-213, THL-254, THL-123, THL-125   **Figma:** Pearl app `751:6166`
- **Moved from Proposals.** Node IDs are unchanged, so the code's citations still hold. Light and dark stay paired.
  - Home `1285:72187` › "Pearl sorts for you" `1325:68972`: AI-01.
  - Sorting `1285:72189` › `1325:68973`: AI-02, AI-03, AI-03b, AI-04, AI-09 (new), AI-07.
  - Profile and settings `1285:72192` › `1325:68974`: AI-05, AI-06, AI-06b, AI-04f, AI-08.
  - Ask Pearl (AI-10 to AI-17) and the phase 2 sketches stay on Proposals.
- **Deleted CN-04** `733:30857` / `733:32225` (Privacy and consent). AI-08 replaces it.
- **The four built-without-a-frame items:**
  1. **"See the n" / "See the n it sorted":** new AI-09 `1325:6340` / `1325:6517`, titled "The 5 you sorted". It's a plain list of Row components, each opening its page, with no totals card. Its title is "The {n} you sorted" from "See the n" (AI-03), or "The {n} Pearl sorted" from "See the n it sorted" (AI-06).
  2. **"Change it…":** no frame needed. It opens the transaction's own page, which is the right place.
  3. **CN-05r wording**, updated in all six frames (`1228:20535`, `1228:21153`, `1234:22996`, `1234:23052`, `1234:23112`, `1234:23156`):
     - Eyebrow: "PEARL SORTS FOR YOU"
     - Title: "Stop Pearl sorting for you?"
     - Body: "New ones wait for you in Quick sort. What Pearl already sorted, and your own rules, stay. You can turn it back on any time."
     - Buttons unchanged: "Turn off" · "Keep it on".
  4. **AI-02:** Pearl's own sorts come first. A "FROM YOUR RULES" heading follows, then the rows your own rules sorted (pay, rent), with the meta "{Category} · your rule". Those rows open the transaction's page, not AI-03.
- **AI-08:** the Ask Pearl switch is hidden until Ask Pearl ships, matching `PrivacyViews.swift:175`.

### [designBOT → engBOT] 2026-11-15 · AI-03c · AI detects, you confirm: ask once per pattern; Trips; AI-02 sections (#343)
**Status:** Redesigned · AI-18 and Trips Awaiting product owner
**Jira:** THL-117, THL-139, THL-213, THL-254, THL-123 (pattern ask) · THL-122, THL-123, THL-226 (Trips)   **Figma:** Pearl app Sorting › `1325:68973` (note `1329:63964`); Proposals › Trips `1327:4973` (note `1329:69536`)

**Confirm once per pattern (changes P1a).**
- **AI-18** `1326:64004` / `1326:64059`: one pattern card in Quick sort. It reads apart from a transaction card because it shows a rhythm ("Each one · into Joint · every 2 weeks") where a transaction shows its date and card.
  - Eyebrow: "A pattern"
  - Question: "Always Ana's share?"
  - Caption line 1: "You sorted the last {n} as {Category | Name's share}."
  - Caption line 2: "Yes sorts new ones for you. Skip asks again after {n} more."
  - Answers: Skip or Yes.
- **Skip:** Pearl asks again after {n} more agreeing answers. A second Skip stops it asking about that pattern.
- **Yes:** starts the rule. It sorts nothing that's already in Needs a look.
- **Copy updated in Pearl app frames:**
  - AI-01 "the ways you said yes to"
  - AI-02 "Sorted the ways you said yes to, up to 20 a day."
  - AI-03/03b "You said yes on {date}, after sorting {n} yourself"
  - AI-06/06b the same, plus "Nothing new is shared."
  - AI-05 "· you said yes"
  - AI-08 "Asks you once for each pattern · up to 20 a day"
  - AI-04f "Pearl may ask you again once…"

**AI-02 (#343)** `1313:3611` / `1313:3813`, three sections:
1. Pearl's sorts, the ones you said yes to. These open AI-03.
2. FROM YOUR RULES: your rule, where you said these go, dates you sorted.
3. NOT CHECKED BY YOU · TAP ONE TO CHECK IT: your bank said so, from its name, Pearl's best match, moved between your accounts, a payment to your card.

Rows in sections 2 and 3 open the transaction's page. Northwind reads "Income · your rule", because the line is always the category as the app names it.

**Trips (design only)** on Proposals:

| Frame | Light / dark | What it is |
|---|---|---|
| TR-01 | `1327:4974` / `1327:5035` | One Quick sort card for the whole trip, "A trip?" |
| TR-02 | `1327:5084` / `1327:5267` | The trip page, "Counts in March" |
| TR-03 | `1327:5447` / `1327:5671` | By category |
| TR-04 | `1327:5894` / `1327:6011` | Options: add, remove, rename, it wasn't a trip |
| TR-05 | `1327:6116` / `1327:6255` | Cash flow rows "{Category} · Trip to Montréal", kept in their days and month |
| TR-06 | `1327:6382` / `1327:6536` | Transaction page line "… · Trip to Montréal" |

Paying a trip from a piggy bank is not drawn. Open decisions are in the note.
- **Approved (product owner, 2026-11-15).**
  - Rows sorted only by "Pearl's best match" become Quick sort questions. AI-02's "Not checked by you" stays for rows already sorted that way.
  - Two Skips and Pearl stops asking about a pattern.
  - At migration, rows P1a sorted before asking go back to Needs a look. This is noted on `1329:63964`; no frame implied otherwise.
  - Trips: asked in Quick sort. A trip is its own thing and adds a matching tag. After a Skip, Pearl never asks about those dates again. You can make a trip yourself.
- **Trips are "Approved, ready to build"** (all 12 earlier frames and the section). The decisions and all strings are in note `1329:69536`.
- **Tag link:**
  - TR-02 has a footer: "Counts in March, as usual · Tagged “Trip to Montréal”".
  - On TR-04, the trip card reads "They still count in March · tagged Trip to Montréal", and Rename's subtitle reads "Renames its tag too".
- **New frames:**

| Frame | Light / dark | What it is |
|---|---|---|
| TR-07 | `1331:5763` / `1331:6097` | Cash flow › Select › "Make a trip" in the Select bar |
| TR-08 | `1331:6480` / `1331:6551` | Name the trip: "Trip name", "Make the trip" · "Cancel" (Rename reuses it with "Save") |
| TR-09 | `1331:6604` / `1331:6657` | Tags › removing a trip's tag ends the trip, and asks first |

### [designBOT → engBOT] 2026-11-15 · AI-18 · After #344: shop amounts, who line, Yes toast; trips in two currencies
**Status:** Redesigned
**Jira:** THL-117, THL-139, THL-213, THL-254, THL-123 · THL-122, THL-226   **Figma:** Pearl app Sorting › `1325:68973` (note `1329:63964`); Proposals › Trips `1327:4973` (note `1329:69536`)

| Frame | Light / dark | What it is |
|---|---|---|
| AI-18 | `1326:64004` / `1326:64059` | Renamed "built (#344)" |
| AI-18b | `1332:63964` / `1332:64019` | A shop with varying amounts: "Purchases at Farm Boy", "$12–$48" over "Usually $27 · about every week", "Always Groceries?" |
| AI-18y | `1332:64062` / `1332:64123` | After Yes: the next card, with a Toast reading "{Pattern name}: sorted from now on" and Undo |
| TR-02m | `1332:70213` / `1332:70317` | A trip in two currencies: "$1,240 CAD + $310 USD" |

- **Amount:**
  - If every amount is within $1, show "$400.00" over "Each one · {where} · {rhythm}".
  - Otherwise show the range ("$12–$48") over "Usually ${median, whole dollars} · {rhythm}".
  - Leave out the rhythm when there isn't one.
- **Who:** "{Kind} from {Full name}", where Kind is "e-Transfers" if every one was an e-Transfer, otherwise "Deposits". For a shop: "Purchases at {Merchant}".
- **Question:** "Always {Name}'s share?" for a person, "Always {Category}?" for a shop.
- **Undo** takes the Yes back, and Pearl can ask about the pattern again. Skip shows no toast.
- **Trips in two currencies:** rows in another currency carry the code ("−$142.00 USD"). "Counts in March" moves to the footer only. TR-08's eyebrow and TR-01's card use the same per-currency total.

### [designBOT → engBOT] 2026-11-15 · TR-10 · Trips on the Calendar
**Status:** Redesigned · Approved, ready to build
**Jira:** THL-122, THL-257, THL-226   **Figma:** Proposals › Trips `1327:4973`, rules in note `1329:69536`

| Frame | Light / dark | What it is |
|---|---|---|
| TR-10 | `1339:8555` / `1339:8900` | March: Montréal Mar 4–9 runs across two weeks; Québec City Mar 13–15 sits close by; "Trips this month" card |
| TR-10b | `1339:9245` / `1339:9587` | November: Lisbon Oct 29 – Nov 2 runs in from the left edge; Nov 1 tapped, its list starts with the trip row |

How trips show on the Calendar:
- **The band:** a 6 pt Nacre/Diagonal band in the gap under the trip's days, so day numbers and marks stay readable.
- **Ends:** rounded where the trip starts and ends; flat where it carries into the next week or month.
- **Tapping:** the band isn't a tap target. "Trips this month" under the grid and the day's "Trip · Trip to {place} · {dates} · {total}" row open TR-02.
- **Large text:** at AX sizes the day rows end "· Trip to {place}".
- **VoiceOver:** "{date}, {status}, part of Trip to {place}".

### [designBOT → engBOT] 2026-11-15 · CHAT-01 · Pearl chat replaces Tell Pearl and Ask Pearl's entry points
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-117, THL-139, THL-213, THL-254   **Figma:** Proposals › Pearl chat `1337:7559`, note `1340:8893`; Tell Pearl `1334:6451` renamed "Superseded by Pearl chat"

**The Pearl button**
- PB-01 `1337:7575`: built from library parts (a Glass button with Logo/Mark), because the library has no Pearl button.
- It sits right of the tab bar, and the tab bar narrows to make room. It shows on the five tabs only. When Pearl has a suggestion, a Nacre ring shimmers once.
- PC-01 `1337:7650` / `1337:7760` and PC-02 `1337:7855` / `1337:8012` show it on Home and Cash flow.

**The chat** is a full-screen Pearl sheet:

| Frame | Light / dark | What it is |
|---|---|---|
| PC-03 | `1338:7879` / `1338:8040` | Start, with starters |
| PC-04 | `1338:8200` / `1338:8355` | An answer |
| PC-05 | `1338:8507` / `1338:8574` | A told guess |
| PC-06 | `1338:8629` / `1338:8698` | A split suggestion with who |
| PC-07 | `1338:8755` / `1338:8875` | "Sorted 7. 2 left for later." |
| PC-08 | `1338:8994` / `1338:9061` | One card for a trip |
| PC-09 | `1338:9116` / `1338:9183` | One card for a pattern |
| PC-10 | `1338:9238` / `1338:9356` | Nothing matched |
| PC-11 | `1338:9474` / `1338:9587` | Unavailable |

**TR-01 and AI-18:** keep both in Quick sort, and offer the same card in the chat as well.
- **Product owner feedback (2026-11-15):**
  - **The Pearl button** now floats above the tab bar at the bottom right (16 pt from the edge), and the tab bar keeps its full width. Updated frames: PC-01 `1337:7650` / `1337:7760`, PC-02 `1337:7855` / `1337:8012`, and PB-01 `1337:7575` renamed.
    - It is always visible and never hides on scroll.
    - Scrolling lists need bottom padding of tab bar + 56 + 16 pt, so the last row clears the button.
    - It stays 56 pt at large text sizes. Bottom right is within reach of a thumb, with or without Reachability.
  - **Nothing changes until you confirm**, for everything: sorting, trips, patterns, rules, splits, plans, renames.
    - PC-12 `1344:8893` / `1344:9043`: a preview card, "Make a Dining out plan of $220 a month?", with "Set it" · "Not now".
    - PC-13 `1344:9178` / `1344:9285`: "Done. Dining out plan set to $220 a month." and "See it in Your plan".
    - After "Not now": "Okay, nothing changed."
  - **Settled:** full screen, starts fresh each time, and trip and pattern questions show in both Quick sort and the chat. Note `1340:8893` is updated.
- **Approved, ready to build (product owner, 2026-11-15):** the Pearl chat section `1337:7559`, its 27 frames and note `1340:8893`. engBOT builds it after trips. TR-01 to TR-10 move into Pearl app once the trips PR merges.

### [designBOT → engBOT] 2026-11-15 · TR-11 · Trips after #346: moved into Pearl app, follow-ups, wording
**Status:** Redesigned
**Jira:** THL-122, THL-123, THL-226, THL-257, THL-263   **Figma:** Pearl app (Sorting `1347:64070`, Cash flow and transactions › Trips `1347:64071`, Calendar · trips `1347:64072`); Proposals › Trips follow-ups `1327:4973`, note `1329:69536`

**Moved into Pearl app** and renamed "built (#346)": TR-01, TR-02, TR-02m, TR-04 to TR-10b. TR-03 stays on Proposals because it isn't built yet.

**Follow-ups on Proposals:**

| Frame | Light / dark | What it is |
|---|---|---|
| TR-02c | `1347:74145` / `1347:74261` | "By category" pill on the trip page (opens TR-03), and the toast after Make a trip |
| TR-11 | `1347:74377` / `1347:74575` | Add transactions |
| TR-12 | `1347:74773` / `1347:74972` | Remove some… |
| TR-13 | `1347:75171` / `1347:75224` | Not a trip? |
| TR-14 | `1347:75265` / `1347:75432` | The 23, from the TR-01 card |
| TR-15 | `1347:75596` / `1347:75933` | Leave out as the last Mark as… tile (agreed) |

The strings and toasts are in note `1329:69536`.

**Wording:**
- No place: "…then 5 days away."
- One row: "The transaction stays as it is."
- Trip totals never carry a minus. TR-10/10b are updated.
- Avatar: two letters, "MO". TR-01 and TR-04 are updated.
- Agreed: "They stay in March and April." and "Oct 29 – Nov 2".

### [designBOT → engBOT] 2026-11-15 · PLAN-01 · Your plan, build-ready
**Status:** Redesigned · Approved, ready to build
**Jira:** THL-127, THL-45, THL-198, THL-117   **Figma:** Proposals › "Your plan" `1353:10205`, note `1353:11493`. AI-22 `1316:5400` is marked replaced.

| Frame | Light / dark | What it is |
|---|---|---|
| YP-01 | `1353:10206` / `1353:10356` | Proposed |
| YP-02 | `1353:10585` / `1353:10642` | Use this plan? (asks first) |
| YP-03 | `1353:10687` / `1353:10844` | In use, with a toast |
| YP-04 | `1353:11034` / `1353:11103` | Change a category |
| YP-05 | `1353:11157` / `1353:11213` | Remove from plan? |
| YP-06 | `1353:11257` / `1353:11337` | Empty |

- **Rounding:** plans round to the nearest $5, not 5% steps, so the $220 from the chat stays $220. engBOT should change the rounding; the copy stays.
- **Chat plans:** a plan set in Pearl chat appears as a row marked "· set in Pearl chat".
- **Approved (product owner, 2026-11-15):** one "Paid back" tile; A person first. The section `1351:8769` and its 12 frames are "Approved, ready to build", and note `1352:10319` is updated.
- **New PB-13b** `1354:10841` / `1354:10901`: when "All of it" is picked but the deposit is smaller than the share, Pearl asks first.
  - Eyebrow: "SAM · PAI NORTHERN THAI"
  - Title: "Let the other $45.00 go?"
  - Body: "Sam paid $15.00 of $60.00. Letting it go marks Sam paid in full, and the other $45.00 stays yours."
  - Buttons: "Let it go" · "Sam still owes it" (the second records it as Part of it).
  - Toast after Let it go: "Sam paid in full · $45.00 let go" · Undo.
- **T-08** `348:11846` / `348:14648`: the leftover "Split into parts" on money in is now hidden.
- **Replaced in Pearl app once built:**
  - The tile grids in T-08 (`348:11846` / `348:14648`), T-08n (`877:37854` / `877:38944`) and T-37n (`877:38331` / `877:39393`).
  - T-09 (`348:12082` / `348:14882`), for a person only.
  - S-35 stays and leads into PB-13.

### [designBOT → engBOT] 2026-11-15 · TR-16 · Trips follow-ups after #349
**Status:** Redesigned (Figma matches the build)
**Jira:** THL-122, THL-123, THL-226, THL-263   **Figma:** Pearl app › Cash flow and transactions › Trips `1347:64071`; note `1329:69536`
- **Moved into Pearl app** as "built (#349)": TR-02c, TR-03, TR-11 to TR-15.
- **TR-15:** frame aligned to the build. The bar reads Category · Mark as… · Make a trip · Confirm {n}.
- **TR-03:** the Spent/Saved/Leftover bar and the ⌄ by the dates are removed from the frame. The row chevrons stay: a category row opens the trip page filtered to that category, with the title "{Category} · Trip to {place}". **engBOT: add this.**
- **TR-04:** the xmark is fine.
- **Wording:**
  - Agreed: "Not a trip · 1 stays as it is"; TR-14 "{dates} · {n}".
  - Change: "Asks first · the 1 stays sorted as it is" → "Asks first · it stays sorted as it is". **engBOT: change this.**
- **TR-12:** select-all opening TR-13 is agreed.

### [designBOT → engBOT] 2026-11-15 · PAID-01 · One “Paid back” tile; part or all of a person's share
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-231, THL-232   **Figma:** Proposals › "Paid back · Awaiting product owner" `1351:8769`, note `1352:10319`

**Gap on main:** "Paying me back" (S-35) takes min(share, what's left of the deposit) for each ticked share (PartsFlow.swift:707). There's no way to say "part of it" or "all of it" for a person.

**Proposal:**

| Frame | Light / dark | What it is |
|---|---|---|
| PB-10 | `1351:8770` / `1351:9048` | One "Paid back" tile |
| PB-11 | `1351:9324` / `1351:9461` | "Who paid you back?": A person · The shop · Work |
| PB-12 | `1351:9586` / `1351:9791` | The person's splits |
| PB-13 | `1352:716` / `1352:913` | "How much of Sam's $60.00?": Part of it · $15.00 / All of it · $60.00 |
| PB-14 | `1351:10402` / `1351:10500` | Result on the split card, "Paid $15.00 of $60.00 · owes $45.00", toast with Undo |
| PB-15 | `1351:10581` / `1351:10785` | No split |

- More than owed: S-11c.
- Several people: S-35's ticks, then PB-13 for each.
- The shop and Work: unchanged (T-09rs, T-09w, S-11m, S-11w).

Not-income tiles go from 8 to 6. T-08's "Split into parts" on money in is out of date and should be corrected.

### [designBOT → engBOT] 2026-11-15 · PAID-01 (cont.) · Paid back from the purchase
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181   **Figma:** Proposals › Paid back `1351:8769`, note `1352:10319`

| Frame | Light / dark | What it is |
|---|---|---|
| PB-20 | `1359:9271` / `1359:9386` | Your ••• on the split card offers "Find what paid it back", even before anything is linked. Other people's rows already have Mark paid back → S-06rb. |
| PB-22 | `1359:9489` / `1359:9694` | "What paid back your share?": a search field and likely deposits (amount, date after the purchase, known payer) |
| PB-23 | `1359:9897` / `1359:9978` | Nothing found |
| PB-24 | `1359:10057` / `1359:10117` | "Move this deposit?" when it's already linked, with "Move it" · "Leave it on {other}" |

- **After picking a deposit**, the existing steps are reused: PB-11 with the payer preselected, PB-13/13b, then the result on the split card (PB-14 / S-04w / S-04m) with a toast and Undo.
- **On the deposit's own page**, the link shows as in T-41w / T-41m.
- **A deposit bigger than the share** goes to S-11w / S-11m / S-11c.
- **Approved (product owner, 2026-11-15):** PB-20, PB-22, PB-23 and PB-24 are "Approved, ready to build".
- **PB-24 rule:** the free part of the deposit is used first, with no question. Taking more always asks.
  - Title: "Take {$more} from {other}?"
  - Body: "{$free} of this deposit is free, so it pays back your share first. The other {$more} pays back {other}. Taking it means {other} counts {$more} more again."
  - Buttons: "Take {$more}" · "Use only the {$free}"
  - Toasts: "Linked {$free} · {purchase}" (free part) and "Moved {$more} from {other}" (after Take), both with Undo.
- Note `1352:10319` is updated.

### [designBOT → engBOT] 2026-11-15 · PAID-02 · Paid back built (#351): frames moved, labels settled
**Status:** Redesigned (Figma matches the build). PAID-01's "Awaiting product owner" is now approved (2026-11-15) and built.
**Jira:** THL-289, THL-291, THL-181, THL-231, THL-232   **Figma:** Pearl app › Sorting › Paid back `1361:67898`

- **Moved** into Pearl app › Sorting › Paid back and marked "built (#351)": PB-10 to PB-15 and PB-13b.
- **Tile grids:**
  - T-08 `348:11846` / `348:14648`: "Paid back" replaces the three tiles.
  - T-08n `877:37854` / `877:38944` and T-37n `877:38331` / `877:39393`: the separate Refund tile is gone. "Loan" now reads "Lent me this", to match the built tiles.
- **engBOT's undrawn choices:** all agreed.
  - The inline Part-of-it field disables Save when the amount isn't valid.
  - PB-11's preselected option is listed first and carries the reason in its subtitle ("Sam is on this split", "your employer", "this shop"). No extra frame is needed.
  - With several people, PB-13 reads "Next" until the last person, then "Save".
- **Old labels:** every link now reads "Paid back · {who}". Change these:
  - SplitMenus "Deposit · Work paying me back" → "Paid back · work"
  - SplitMenus "Refund · Money back" → "Paid back · refund"
  - T-41w's category row "Work paying me back" → "Paid back · work". The frame is updated.
  - Onboarding "Paying me back" (SetupPayQuestions) → "Paid back", to match the tile.
  - The cash-extra tile "Paying me back" (S-11c) → "Pays back something else". There it means the extra covers a different purchase.

### [designBOT → engBOT] 2026-11-15 · PLAN-02 · Your plan follow-ups after #350
**Status:** Redesigned · Approved, ready to build
**Jira:** THL-127, THL-45, THL-198   **Figma:** Pearl app › Profile and settings › Your plan `1356:77254` (YP-01–YP-06 built); Proposals › Your plan follow-ups `1353:10205`, note `1353:11493`

| Frame | Light / dark | What it is |
|---|---|---|
| YP-07 | `1356:9351` / `1356:9411` | "Stop using this plan?", with "Stop using it" · "Keep using it" |
| YP-08 | `1356:9456` / `1356:9661` | Add a category: a "NOT IN YOUR PLAN" list, then YP-04 with "Add" |
| YP-09 | `1356:9864` / `1356:9956` | Income and bills: a "Your plan" card above INCOME |

- **Plan row tick:** it was decoration, so it's removed.
- **Review of engBOT's choices:**
  - Agreed: Suggest a plan; YP-02 without income; the trip page filtered by category.
  - Change: "Suggest a plan" should round the usual up to the next $10, as the chat does. Typed amounts round to the nearest $5.

The strings are in the note.

### [designBOT → engBOT] 2026-11-15 · PAID-03 · Paid back from the purchase, built (#353)
**Status:** Redesigned (Figma matches the build)
**Jira:** THL-289, THL-291, THL-181   **Figma:** Pearl app › Sorting › Paid back `1361:67898`
- **Moved and marked built (#353):** PB-20, PB-22, PB-23 and PB-24. PB-22's frame now lists newest first, as built.
- **Agreed:**
  - PB-20's subtitle works as the VoiceOver hint.
  - PB-23 shows inside the PB-22 sheet.
  - Search results have no LIKELY heading.
  - The "why it matches" phrases, the footnote and the three error lines are fine.
- **engBOT to change:**
  1. On the deposit side, PB-11 in AnswerSheet should preselect the likely payer and show the reason line, as it does from the purchase.
  2. Use one vocabulary for the leftovers: "Money back for X?" → "Paid back for X?", and "Money back on your share of X." → "Paid back on your share of X."

### [designBOT → engBOT] 2026-11-15 · TR-17 · A Trips card always on the Calendar; All trips
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-122, THL-257, THL-226   **Figma:** Proposals › Trips `1327:4973`, note `1329:69536`

| Frame | Light / dark | What it is |
|---|---|---|
| TR-17 | `1362:8403` / `1362:8698` | One "Trips" card under the grid that replaces "Trips this month": this month's trips first, then recent ones, up to 3, then "See all trips" |
| TR-17e | `1362:8993` / `1362:9337` | No trips yet |
| TR-18 | `1362:9681` / `1362:9848` | All trips, grouped by year, newest first |

- **Large text:** dates wrap and rows grow.
- **VoiceOver:** each row reads as one element ("Trip to Montréal, March 4 to 9, $1,284.60"). The card heading is a header.
- **Approved (product owner, 2026-11-15):** TR-17, TR-17e and TR-18 are "Approved, ready to build". Note `1329:69536` is updated.

### [designBOT → engBOT] 2026-11-15 · TRANSFER-01 · Transfers read differently from spending
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-122, THL-123   **Figma:** Proposals › "Transfer colour" `1368:8299`, note `1368:10078`

| Frame | Light / dark | What it is |
|---|---|---|
| TC-A (recommended) | `1368:8300` / `1368:8405` | "⇄ $500.00" in lagoon, no sign |
| TC-B | `1368:8498` / `1368:8603` | ⇄ in muted grey |
| TC-C | `1368:8696` / `1368:8803` | A "Transfer" chip |
| TC-A on the Calendar day list | `1368:8898` / `1368:9189` | TC-A applied |
| TC-A on a trip page | `1368:9480` / `1368:9628` | TC-A applied |

- **Token:** repoint color/text/money-transfer from mist to lagoon/700 (light, 5.1:1 on the card) and lagoon/400 (dark, 8.9:1). No new token is needed.
- **Other not-counted rows** stay muted, with no sign.

### [designBOT] 2026-11-15 · CLEAN-01 · Handoff file: Pearl app = built, Proposals = not built
**Status:** Done (product owner's rule, 2026-11-15)

**Moved into Pearl app:**
- New "Pearl chat" group, section `1369:70113`: PB-01 and PC-03 to PC-13 (light and dark), plus note `1340:8893`.
- PC-01 → Home › `1369:70114`. PC-02 → Cash flow and transactions › `1369:70115`.
- All marked "built (#348, #352)". PC-05/PC-06 now quote the user ("You said: “Out with friends Saturday.”"), as #352 built.
- TEST-31 (built in #338): T-09w/rs, S-04w/w2/w3, S-04m/m2/m3/m4, S-40w/m, S-11w/m, T-41w/m, with notes `1294:2593` and `1303:3395` → Splits and paybacks › `1369:70116`.
- S-06 v2/v3/v3a (still built and cited in SplitFlow) → Splits and paybacks › `1369:70117`.
- The Paid back note `1352:10319` → Sorting › Paid back `1361:67898`.

**Deleted:**
- Ask Pearl AI-10 to AI-17. PC-12's preview card covers AI-17's suggestion.
- AI-22.
- The Tell Pearl section TP-01 to TP-09 and its note.
- From To check:
  - S-03 (covered by S-03r2 / S-03b v2)
  - S-05, S-19, S-20 (covered by S-04r v2 / S-44)
  - T-75 (covered by S-01jr)
  - O-09c (covered by O-09cr)
- The ticket tags and notes that belonged to those frames, and the now-empty sections To check, TEST-31, Paid back and Pearl chat on Proposals.

**Left on Proposals:**
- Deferred (recovery codes)
- AI phase 2 sketches AI-20 and AI-21 (note rewritten)
- Trips TR-17/TR-18 (approved, not built)
- Your plan YP-07 to YP-09 (approved, not built)
- Transfer colour (awaiting)
- **TRANSFER-01 approved (product owner, 2026-11-15): TC-A.**
  - The TC-A frames (Cash flow, Calendar day list, trip page) are "Approved, ready to build". TC-B and TC-C are deleted (`1368:8498`, `1368:8603`, `1368:8696`, `1368:8803`). Note `1368:10078` is updated.
  - **Library:** `color/text/money-transfer` now points to lagoon/700 (light) and lagoon/400 (dark); it was mist/500 / mist/300. The library is not published yet; the product owner publishes it by hand.

### [designBOT → engBOT] 2026-11-15 · PLAN-03 · Your plan follow-ups built (#354)
**Status:** Redesigned (Figma matches the build)
**Jira:** THL-127, THL-45, THL-198   **Figma:** Pearl app › Profile and settings › Your plan `1356:77254`, note `1353:11493`

- **Moved:** YP-07, YP-08 and YP-09 are now in Pearl app, marked "built (#354)". The empty Proposals section is deleted.
- **YP-08 rows:** one line, "{Category} · usual {$x}". The second lines are removed from the frame.
- **YP-08 empty state:** "Everything's in your plan" / "Change any category from Your plan." with a Done button. **engBOT: add this.**
- **Agreed:**
  - YP-04 opened from YP-08 shows only "Add" and ✕.
  - YP-08 leaves out rent and all-bill categories.
  - YP-07 with no income: body "Your usual amounts come back. The plan stays here to use again." and toast "Plan stopped" · Undo.

### [designBOT → engBOT] 2026-11-15 · TRANSFER-03 · Plum spending (SP-B), grey transfers
**Status:** Redesigned · Approved, ready to build. The library is waiting for the product owner to publish.
**Jira:** THL-122, THL-123   **Figma:** Proposals › "Transfer colour" `1368:8299`, note `1368:10078`; library `3fdfPDKIjhiluGHtXWSF32`

- **Frames:** SP-B is approved: `1373:2613` / `1373:2752`, `1373:2879` / `1373:3219`, `1373:3559` / `1373:3707`. SP-A and SP-C are deleted.
- **Library (not published):**
  - `color/text/money-out` → lilac/900 / lilac/200.
  - New `color/text/error` → red/700 / red/300.
  - Amount field Over `298:728` → error.
  - Transaction row Out amounts `91:819` / `91:830` → money-out.
- **Handoff, after the publish:** move 1,144 spending amounts from primary to money-out, and the 25 over, error and destructive texts from money-out to error. Then screenshot T-46 in light and dark.
- **Transfer subtitles:** keep engBOT's rule (the category, e.g. "Saved" / "Transfer"). "Moved to your savings" was sample wording only.
- **Correction to TRANSFER-01 and CLEAN-01:** the lagoon transfer colour (TC-A, lagoon/700 / lagoon/400) was withdrawn the same day. Transfers are grey (mist/500 / mist/300). The library change to lagoon was reverted before any publish.

### [designBOT → engBOT] 2026-11-15 · TRANSFER-04 · Plum applied across the handoff file
**Status:** Redesigned (Figma matches #357)
**Jira:** THL-122, THL-123   **Figma:** Pearl app and Proposals; note `1368:10078`
- **Library update:** money-out is now plum (lilac/900 / lilac/200) and error is red.
- **Rebound in the handoff:**
  - 1,144 spending amounts ("−$…") from color/text/primary → color/text/money-out.
  - 25 texts → color/text/error: 2× "Over $760", 4× over-total "$90.00", and 19 destructive labels (Sign out, Remove this account, Remove it and its history, Delete your account, Remove TD entirely, Disconnect TD).
  - The Cash flow summary (Leftover, "Spent $X", the bar) stays ink.
- **Transfer grey:** use color/text/muted (mist/600 #514D67), as the app builds it. That's 7.2:1 and AA on every page stop, where mist/500 isn't.
  - The 6 "⇄" amounts in the frames are rebound to muted.
  - color/text/money-transfer light should follow, mist/500 → mist/600, at the next library publish.

### [designBOT → engBOT] 2026-11-15 · TRANSFER-02 · Grey transfers, a darker spending colour
**Status:** Redesigned · Awaiting product owner. This replaces TRANSFER-01's TC-A; those frames are deleted.
**Jira:** THL-122, THL-123   **Figma:** Proposals › "Transfer colour" `1368:8299`, note `1368:10078`

- **Transfers:** grey "⇄ $500.00" with no sign. The library `color/text/money-transfer` is reverted to mist/500 / mist/300 (not published yet).
- **Spending options**, each shown on Cash flow, the Calendar day list and a trip page, in light and dark:

| Option | Light / dark colour | Contrast (light card / dark card) | Frames |
|---|---|---|---|
| SP-A navy (recommended) | ocean/800 / pearl/50 | 11.7:1 / 15.6:1 | `1373:1363` … `1373:2465` |
| SP-B plum | lilac/900 / lilac/200 | 10.6:1 / 11.9:1 | `1373:2613` … `1373:3707` |
| SP-C deepest navy | ocean/900 / pearl/50 | 14.7:1 / 15.6:1 | `1373:3855` … `1373:4949` |

- **Token plan:** spending uses `color/text/money-out`, repointed to the chosen colour.
  - Rebind the library Row's Out amounts and the 758 handoff amounts to money-out.
  - Over-the-total fields and destructive text move to an error token so they stay red.
  - The app's `Pearl.moneyOut` follows the same token.

### [designBOT → engBOT] 2026-11-15 · TELL-01 · Tell Pearl what you did
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-117, THL-139, THL-213, THL-254   **Figma:** Proposals `1284:99` › "Tell Pearl · Awaiting product owner" `1334:6451`, note with strings and decisions beside it
Apple Intelligence phase, on the iPhone. You describe what you did; Pearl guesses; each card is still Skip or Yes, one transaction each, with no "Yes to all" and nothing grouped.

| Frame | Light / dark | What it is |
|---|---|---|
| TP-01 | `1334:6536` / `1334:6591` | Way in: Quick sort pill |
| TP-02 | `1334:6634` / `1334:6699` | Way in: Needs a look pill |
| TP-03 | `1334:6814` / `1334:6928` | Way in: Ask Pearl's first suggestion |
| TP-04 | `1334:7042` / `1334:7114` | The telling sheet: example hint, days read from the words with Change, keyboard dictation, the on-device line |
| TP-05 | `1334:7168` / `1334:7249` | Working |
| TP-06 | `1334:7328` / `1334:7383` | Quick sort with "A guess for 7 of 9 from the weekend · nothing sorted yet", and a caption quoting the user |
| TP-07 | `1334:7426` / `1334:7483` | "Maybe split? You were with friends" pill, which opens S-02 |
| TP-08 | `1334:7528` / `1334:7607` | Nothing matched |
| TP-09 | `1334:7686` / `1334:7765` | Some days already sorted |

Apple Intelligence not available: AI-15. Nothing to build until the product owner picks.

### [designBOT → engBOT] 2026-11-15 · SETUP-01 · One account setup step
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-120, THL-172, THL-300, THL-294, THL-304, THL-305   **Figma:** Proposals › "Account setup" `1380:75770`

"Which accounts do you share?" and "Check how each account counts" become one step: "Your accounts" in onboarding, "Check your accounts" in Set Pearl up again.

| Frame | Light / dark | What it is |
|---|---|---|
| AS-01 | `1380:75771` / `1380:75917` | One list: how each account counts and who shares it, on one line; good defaults; "These look right" |
| AS-02 | `1380:76064` / `1380:76106` | One account: Include in my budget, Shared with someone (inline: who, then Half each / A different share / Each purchase: mine unless I say), Anchor, Nickname |
| AS-04 | `1380:76148` / `1380:76272` | Set Pearl up again with one item instead of two |

- **Start over** brings back every account with the defaults.
- **Replaces when built:** O-09b, O-09b2, SU-02, and SU-01's two rows.
- **Approved (product owner, 2026-11-15):**
  - "Each purchase: mine unless I say" is a split choice; it's the account-level mode in finance/joint.py.
  - "These look right" with nothing changed counts as done.
  - The section and its 6 frames are "Approved, ready to build". Note `1380:76572` is updated.

### [designBOT → engBOT] 2026-11-16 · POLISH-01 · Question sheets and the transfer page, redone
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-292, THL-295, THL-297, THL-232, THL-305, THL-181   **Figma:** Proposals › "Polish · Awaiting product owner" `1387:1741`

The product owner sent two phone screenshots: "they look sloppy and low effort." They are in the section as the "before" frames (`1387:1742`, `1387:1743`).

| Frame | Light / dark | What it is |
|---|---|---|
| RQ-01 | `1389:23274` / `1389:23646` | Is this a recurring transfer? Says why Pearl is asking, shows the 9 so far as a rhythm (one pill per payment, by month), then answer tiles with one line each. A tap answers; there's no Save |
| RQ-01b | `1389:24086` / `1389:24326` | After a tap: the card leaves Needs a look; ink toast "Rent · all 9 sorted, and the ones to come" with Undo |
| TF-01 | `1389:24632` / `1389:24833` | A transfer's page: ⇄ avatar, name in ink, grey amount with no sign, both dates, How it counts, both ends with "1 day apart", "This isn't a transfer" as an option row, Add a note |
| TF-01c | `1390:2451` / `1390:2586` | "This isn't a transfer?": a Pearl sheet asks before anything changes |
| PQ-01 | `1393:83919` / `1393:84293` | Whose pay is this? The paydays shown, then tiles Me / Sam / Both of us; "This isn't regular pay" as a row |
| PQ-02 | `1393:84663` / `1393:85042` | How often is this pay? The deposits shown, six tiles; Pearl's guess is dashed, never picked for you |
| RT-02 v2 | `1393:85417` / `1393:85693` | Profile › Recurring transfers › one: the current answer is a ringed tile, a tap changes it (with Undo), the 9 so far, Stop as a row |

Notes: `1394:3145` (overview), `1394:3146` (RQ-01, with motion), `1394:3147` (TF-01), `1394:3148` (the worst three), `1394:3149` (the rest of the audit).

What's behind the screenshots, from the code:
- **Half-empty sheets.** Every AnswerSheet step is shown at `.large` (AnswerSheet.swift:738), with a plain list and then Save at the bottom. Sheets should take the height of their content.
- **"…9 so f…".** QuestionHeader cuts the subtitle to one line (AnswerSheet.swift:1186). RQ-01 moves the schedule into the card.
- **The faint title behind the sheet.** It's the page's inline bar showing above a `.large` sheet. A content-sized sheet fixes it.
- **Grey transfer title.** The rename button is `.disabled(t.transfer != nil)` (TransactionDetailView.swift:882), and SwiftUI dims a disabled button. Keep it not tappable, but don't dim it.
- **"Yours." is a bug.** `run()` stores the last action's result in `@State message`, and line 405 draws it as a plain line under the page. "Yours." is what WhoseSheet returns for Mine (line 2819). Every transaction page does this after an action, and so does SettingsViews.swift:181. Show a toast with Undo instead.
- **The floating red link.** It comes from `Spacer(minLength: 120)` in `transferLegs` (line 2063).
- **Transfer amount colour.** #357 changed the rows only; the detail hero isn't in money-transfer grey with ⇄ yet.
- **RQ-01 needs each date in the series.** Today the series has ids, first, last and count. Add each payment's date (and the day of the month) so the rhythm can be drawn.

Product owner decisions:
1. **RT-02.** THL-295 says "What is it? with Save". Should a tap with Undo replace Save? Recommended: yes, it's how every other answer works now.
2. **Size to content.** Should every question sheet move to a content-sized sheet, `.large` only at accessibility text sizes? Recommended: yes.

Keep Save where you type or set an amount: WhoseSheet "Part of it", CategorySheet with Remember, WhoSentSheet, notes, tags, renames.

New library component: none. The tiles are the What was this? tile, and the icons are the handoff's Category icon set.

### [designBOT → engBOT] 2026-11-16 · PAYUNDO-01 · One Undo look; one e-Transfer for several purchases; link first, edit later
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-301   **Figma:** Proposals › "Paybacks & undo · Awaiting product owner" `1395:3376`

| Frame | Light / dark | What it is |
|---|---|---|
| PB-30 | `1395:3405` / `1395:3628` | What did Sam pay back? Pearl ticks the set that adds up to the e-Transfer; untick or tick, then one tap "Mark 2 paid back" |
| PB-30u | `1395:3847` / `1395:4068` | Less ticked than the deposit: "$13.35 left over", then the button "Next: the other $13.35" goes to S-11c |
| PB-30o | `1395:4287` / `1395:4511` | More ticked than the deposit: the oldest are paid in full, the newest part-paid on its row with "Change" (PB-13) |
| PB-41 | `1395:4794` / `1395:4922` | Deposit page: what it paid back, a row each. Options: Change what it paid back (reopens PB-30), Unlink both |
| PB-42 | `1395:5050` / `1395:5168` | One link's options, from the purchase or the deposit: How much, Who paid, Which purchase, View the e-Transfer, Unlink… |
| UN-01a | `1396:4365` / `1396:4517` | The one Undo: ink toast at the bottom, after PB-30 |
| UN-01b | `1396:4669` / `1396:4766` | The same toast on a purchase page, moved from the top to the bottom (PB-14 had it at the top) |

Notes: `1397:4696` (overview), `1397:4697` (PB-30 logic), `1397:4698` (PB-41/42), `1397:4699` (UN-01 audit).

**Undo.** The one look is PearlToast as built (SplitMenus.swift:421): fill color/text/primary, words and Undo in color/surface/page. It sits at the bottom, stays 6 s (15 s with VoiceOver) and swipes away. I added it to the library as Toast `Tone=Ink` (`330:751`); it isn't published yet. What to change:
1. `UndoToast` (AccountsViews.swift:111) is a glass capsule with a link-coloured Undo, used app-wide. Make it draw PearlToast.
2. `TransactionsView.toastView` (896) and `ReviewView.toastView` (475) are the light pink capsule you see after confirming a dashed guess. Switch both to PearlToast.
3. `CategoriesRulesView.toastView` (364): switch to PearlToast.
4. TransactionDetailView's `message` line: switch to PearlToast with Undo (see POLISH-01).

**Several purchases.**
- The likely set is purchases from the same person, dated before the deposit, oldest first, whose total is the deposit or the nearest under it.
- All is the default. Pearl asks about part only when the ticks come to more than the deposit.
- Send one request for the whole set, so a single Undo puts every link back.
- When the e-Transfer names someone Pearl knows, skip PB-11.

**PB-42** adds How much, Who paid and Which purchase to S-05or. S-40c gains How much and Which purchase.

**Replaces when built:** S-35 ticks then PB-13 for each person; PB-12's single pick when one person owes several. Toasts in 70 Figma frames get swapped once Tone=Ink is published; Neutral and Positive are then retired.

Product owner decisions:
1. **Dark mode.** Should the ink toast invert there (a light toast on dark, as iOS does), or stay dark? Recommended: invert.
2. **PB-30o.** When the ticks come to more than the deposit, should the newest be part-paid automatically (with Change on its row), or should Pearl always ask? Recommended: automatic, with Change.
3. **Publish the library.** It now has Toast Tone=Ink.


### [designBOT → engBOT] 2026-11-16 · ROWCOST-01 · A purchase shows what it costs you now
**Status:** Redesigned · Approved by the product owner (2026-11-16); the section is named "Awaiting product owner" as asked
**Jira:** THL-291, THL-289, THL-303, THL-122, THL-181, THL-301   **Figma:** Proposals › "Row shows your cost · Awaiting product owner" `1401:86306`, note `1402:5082`

| Frame | Light / dark | What it is |
|---|---|---|
| RC-01 | `1401:86307` / `1401:86412` | Cash flow rows. Gusto −$97.50, "$127.50 split · $30.00 back · $57.50 to come". Nopa −$19.79, "$59.33 split · $39.54 back". Pizza Nova (not sure yet) −$45.00. Pai Northern Thai −$60.00, "work paid your $60.00 · $60.00 to come" |
| RC-02 | `1401:86505` / `1401:86565` | Loblaws page header −$110.00, "$150.00 split 5 ways · $40.00 back · $50.00 to come", then the date and your share |
| RC-03 | `1401:86613` / `1401:86668` | Right after Sam pays $15.00: the header counts down from $120.00 to $105.00, with the ink toast |

What stays from Rule A:
- What's still owed counts as yours until it comes back.
- A split nobody has paid yet still shows the whole purchase.

What changes:
- The row (TransactionsView `shownMoney`) and the header (TransactionDetailView `heroAmount`) show the whole purchase minus what's come back, the moment each payback, cash or app payment, or work payment lands.
- Today they show the whole purchase until the last person pays.
- Spent and the Allowance don't move. They already use this cost (`split_owed`, `split_reimbursed`), so the rows now add up to Spent.
- The note becomes "{whole} split · {back} back · {owed} to come".
- Settled at $0 still reads "Paid back in full · not your spending".

**Replaces when built:** T-01r2 (`1244:26496` / `1244:26635`) and S-04r v2's header (`1090:1743` / `1093:3991`).

### [designBOT → engBOT] 2026-11-16 · PAYBACK2-01 · Who paid picker; a transfer that was someone paying you back
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-305, THL-172   **Figma:** Proposals › "Paybacks 2 · Awaiting product owner" `1406:5084`

| Frame | Light / dark | What it is |
|---|---|---|
| PP-01 | `1406:5216` / `1406:5547` | Who paid you back? The people on this split first (today's answer ticked), then people from past splits, then Someone new (S-35c). A tap answers (#362) |
| PP-02 | `1406:5860` / `1406:5984` | Back on PB-42 with Priya; ink toast "Priya paid this back, not Sam. Sam owes $26.65 again." with Undo |
| TP-01 | `1406:6098` / `1406:6232` | Transfer page for money in from a joint account: "Mom paid me back" above "This isn't a transfer" |
| TP-02 | `1407:6398` / `1407:6648` | What was this? on the money-in end opens the money-in answers, so Paid back is there; My own money is ringed as today's answer |
| TP-03 | `1407:6896` / `1407:7113` | PB-30 with Mom picked from the joint account: $240.00 of Mom's shares ticked; one line on what happens to the pair |
| TP-04 | `1407:7328` / `1407:7487` | After: "From Mom · Joint ••1123", paid back 3 purchases, the joint side is Mom's money; ink toast with Undo, which puts the transfer back |
| TP-05 | `1406:6361` / `1406:6494` | Two accounts that are only yours: no Paid back, with a callout saying why and pointing to "This isn't a transfer" |

Notes: `1406:5084` section, overview, PP, TP and decisions.

**The bug.** AnswerSheet.swift:158 sends `.transfer` to `.out`, so even the money-in end of a transfer opens the money-out sheet. That sheet has no Paid back. On the money-in end it should open `.into`.

What each side counts as after TP-03:
- **Money in:** a payback, not income and not a transfer. Under Rule A, each linked share stops counting as hers, so Spent drops by $240.00 and the Allowance rises by $240.00.
- **Money out of the joint account:** the other owner's money, nothing of hers. It's marked the way a joint charge said to be the other person's is (her share 0 / "them").
- **The joint ratio:** this money out isn't a spending category, so `joint.ratios` doesn't count it.
- **"Mine unless I say":** it's one "I say" exception.
- **A set share (50/50):** the whole amount is still Mom's (decision 1).
- **Undo:** unlinks the purchases and puts the transfer pairing back.

When the offer shows:
- Money into her own account from a joint account she shares. With two other owners, PP-01 asks who first.
- Never for money she moves into the joint account.
- Never between two accounts that are only hers (TP-05). There, "This isn't a transfer" unpairs it, and then Paid back is offered like any money in.

Product owner decisions:
1. **50/50 joint account:** is money Mom sends her from it all Mom's, or half hers? Recommended: all Mom's.
2. **Joint ratio:** take the $240.00 off Mom's "them" deposits for that month? Recommended: yes. It only matters on accounts without a set share.
3. **When to offer it:** on every transfer in from a joint account, or only once Mom has deposited there? Recommended: every one.

### [designBOT → engBOT] 2026-11-16 · SETUP-02 · Your accounts, calmer
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-120, THL-172, THL-300, THL-294, THL-304, THL-305   **Figma:** Proposals › "Your accounts v2 · Awaiting product owner" `1415:6440`, note `1415:88764`

The product owner on the built AS-01 (#359): "a bit less like info being thrown at me and more intuitive. Joint should show the colourful tag beside it."

| Frame | Light / dark | What it is |
|---|---|---|
| Before | `1415:87856` | The phone screenshot |
| AS-01 v2 | `1415:87857` / `1415:88299` | Grouped, short names, kind icons, tags only for what differs, the button at the end of the list |

The page now:
- **The Joint tag** is the library Status pill, Tone=Joint ("Joint · 50%"). It comes from **AM-01 · Accounts** (`731:29085`), where AM-08 also uses it. Anchor is Tone=Info, as on AM-01.
- **Quiet by default:** an account that's in her budget and only hers shows just its name. Tags appear only for Joint · 50% and Anchor.
- **Groups:** Everyday, Savings & borrowing, and Not in your budget. The group header says "not in your budget", so those rows need no tag.
- **Collapsed:** not-counted accounts from one bank collapse into one row ("Scotia iTRADE · 3 accounts"). A tap opens it inline, and each account opens AS-02.
- **Kind icons:** the circle shows what kind of account it is (chequing, card, savings, mortgage, investing) instead of repeated bank initials. These are the handoff's Category icons.
- **Short names:**
  - Use the nickname if she set one.
  - Otherwise, the bank plus the product, without "Account", "Card", "®" or "*" ("Amex Cobalt", "TD Minimum Chequing").
  - Show ••last four only when two names would otherwise match.
- **Lead line:** "Pearl set these up. Just check two things: what counts in your budget, and what you share." Under it, a summary: "7 in your budget · 1 shared · 3 not counted".
- **The button:** "These look right" sits at the end of the list and scrolls with it, so it never covers a row. It works the same in Set Pearl up again, with the tab bar.
- **AS-02:** its header uses the same kind icon and short name, and its rows set the same tags.
- **Motion:** "These look right" opens the third shell (350 ms spring, success haptic). With Reduce Motion, it fades.

Product owner decisions:
1. **Collapse:** should not-counted accounts from one bank collapse into one row? Recommended: yes.
2. **Group names:** are Everyday, Savings & borrowing and Not in your budget right?

**Library follow-up:** Account row has no slot for a kind icon or tags, so these rows follow AM-01's rows (library Status pill plus Category icons). If the product owner wants, I'll add both slots to Account row; the library would then need a publish.

### [designBOT → engBOT] 2026-11-16 · SETUP-02 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-16, as drawn)
**Jira:** THL-120, THL-172, THL-300, THL-294, THL-304, THL-305   **Figma:** Proposals › "Your accounts v2 · Approved, ready to build" `1415:6440`. AS-01 v2 `1415:87857` (light) / `1415:88299` (dark), note `1415:88764`

- Not-counted accounts from one bank collapse into one row.
- The groups are Everyday, Savings & borrowing and Not in your budget.
- The library Account row stays as it is for now, so no publish is needed. Build these rows like AM-01's rows, with the library Status pill and the Category icons.

### [designBOT → engBOT] 2026-11-16 · POLISH-02 · Is mPg paying you back?
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-231, THL-232, THL-301   **Figma:** Proposals › "Payback question · Awaiting product owner" `1418:88290`

The product owner: "This screen is also very bland and doesn't look finished." It was item 6 on POLISH-01's audit.

| Frame | Light / dark | What it is |
|---|---|---|
| Before | `1418:88291` | The phone screenshot |
| PQ-03 | `1418:88292` / `1418:88584` | Why Pearl is asking (amount and timing); the likely purchase as a dashed tile showing how $20.00 compares; Something else; Not a payback; a tap answers |
| PQ-03b | `1418:88874` / `1418:89179` | mPg is on the split and part-pays it ("$20.00 of mPg's $30.79 · $10.79 still to come"), with a second likely purchase |
| PQ-03c | `1419:89682` / `1419:89834` | After a tap: the card leaves Needs a look; ink toast "mPg paid back $20.00 for Añejo" with Undo |
| PQ-03p | `1419:89482` / `1419:89582` | The deposit page: a dashed question card in place of the grey "Not sorted yet" bar; "Name them" under the sender |

Build notes:
- **The reason** is the one review.py already writes (split, message or share-of-charge). Show it as a full sentence, plus a line saying what Yes does.
- **Candidates:** show up to three, best first. Only the best is dashed.
- **Short card names:** use the AS-01 v2 rule, so "Amex Cobalt".
- **Something else** opens PB-22. **Not a payback** goes on to T-08.
- **Name them** opens the existing T-14 / S-35c Who sent this? sheet.
- **Answers apply on tap,** with the ink toast and Undo. AnswerSheet `.payback` currently uses Continue; this replaces it.

### [designBOT → engBOT] 2026-11-16 · POLISH-02 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-16)
**Jira:** THL-289, THL-291, THL-181, THL-231, THL-232, THL-301   **Figma:** Proposals › "Payback question · Approved, ready to build" `1418:88290`, note `1419:89986`

The frames are PQ-03, PQ-03b, PQ-03c and PQ-03p, in light and dark. Build them as described in the POLISH-02 entry above.

### [designBOT → engBOT] 2026-11-16 · UNDO-02 · Every toast is Toast Tone=Ink
**Status:** Redesigned · Approved, ready to build
**Jira:** THL-289, THL-291, THL-181   **Figma:** library Toast `96:203` (Tone=Ink `330:751`)

- In the handoff, I swapped all 77 library toasts to Tone=Ink: 70 in Pearl app, 6 in Proposals and 1 in Archive.
- Each toast keeps its words.
- Success toasts have a check. The four "Couldn't undo that" toasts have an info icon.
- 14 toasts sat at the top of their screen. They now sit at the bottom, 12 above the tab bar or home indicator.
- One variant covers light and dark, because the tokens invert it.

In the library:
- Tone=Ink's words are now tied to the Message, Action and Show action properties. Before, they weren't, so instances showed the default words.
- Its icon is now a check.
- Neutral and Positive are deleted, since nothing used them.

**Needs another publish:** these library changes came after the product owner's publish.

For engBOT, UN-01's list stands: make UndoToast, TransactionsView.toastView, ReviewView.toastView and CategoriesRulesView.toastView draw PearlToast, and make TransactionDetailView's `message` line a toast.

### [designBOT → engBOT] 2026-11-16 · ROWCOST-01 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-16: as drawn, Rule A kept)
**Jira:** THL-291, THL-289, THL-303, THL-122, THL-181, THL-301   **Figma:** Proposals › "Row shows your cost · Approved, ready to build" `1401:86306`, note `1402:5082`

All six frames are marked "Approved, ready to build": RC-01 `1401:86307`/`1401:86412`, RC-02 `1401:86505`/`1401:86565` and RC-03 `1401:86613`/`1401:86668`.

Rule A is kept: a split nobody has paid yet still shows the whole purchase. Build it after your current two PRs.

### [designBOT → engBOT] 2026-11-16 · PAYBACK2-01 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-16, as recommended)
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-305, THL-172   **Figma:** Proposals › "Paybacks 2 · Approved, ready to build" `1406:5084` (all 14 frames marked)

1. **A 50/50 joint account:** money Mom sends her from it is all Mom's (her share 0).
2. **The joint ratio:** the amount comes off Mom's "them" deposits for that month, because it's money she took out, not money that paid joint bills. This applies only on accounts with no set share.
3. **When it's offered:** "Mom paid me back" appears on every transfer that comes in from a joint account.

### [designBOT → engBOT] 2026-11-16 · POLISH-02 · Built (#368), moved to Pearl app
**Status:** Built
**Jira:** THL-289, THL-291, THL-181, THL-231, THL-232, THL-301   **Figma:** Pearl app › Sorting › "Payback question … built (#368)" `1422:74413`, note `1419:89986`

The PQ-03, PQ-03b, PQ-03c and PQ-03p frames (light and dark), the before frame and the note are now in Pearl app › Sorting, and the frames are marked built. The sections below Sorting moved down 2160 to make room.

Agreed, both changes are now in the note:
1. **Something else** opens the sender's splits (PB-12), or the purchase search (PB-15) when they have none. PB-22 searches from a purchase for deposits, which is the wrong way round here.
2. **Name them** opens T-14 "Who sent this?". S-35c only works on a payback that's already linked.

The wording in #368 is fine as built, including "mPg owes you exactly $30.79 for Añejo." and "Pearl's guess: about a third of Añejo, $61.57 · tap to answer". If anything, "owes you $30.79 for Añejo, exactly what they sent" reads a little warmer. It's optional.

### [designBOT → engBOT] 2026-11-16 · TEXT-01 · Less text: copy rules and an audit
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-292, THL-120, THL-61   **Figma:** Proposals › "Less text · Awaiting product owner" `1425:6647`, rules `1426:8224`, string list `1426:8225`

A standing rule from the product owner: "There's so much text and the user likely won't even read any of it."

The rules:
1. **No next-step footnotes.**
2. **Say a reason once,** in a group header, a tag or an icon, never on every row.
3. **Tidy names, never raw descriptors.** An e-Transfer shows the person.
4. **At most one line of context,** and only if it changes the decision.
5. **Sentences become amounts, names and tags.**

Also: a row's second line is a date plus one fact. No "Pearl remembers…" or "Change it in Profile…" footers.

Before and after:

| After | Light / dark | Before |
|---|---|---|
| LT-01 · PB-22 | `1425:73658` / `1425:73900` | the phone screenshot `1425:73657` |
| LT-02 · RQ-01 | `1425:6768` / `1425:7025` | RQ-01 |
| LT-03 · PQ-03 | `1425:7351` / `1425:7552` | PQ-03 (built in #368) |
| LT-04 · AS-01 v2 | `1425:7857` / `1425:8059` | AS-01 v2 |
| LT-05 · YP-01 | `1425:72756` / `1425:72885` | YP-01 |

**The PB-22 bug:**
- Money from someone on the split pays back *their* share, not hers.
- After: the title is "What paid this back?", with YOUR SHARE (work, refunds) and SAM'S SHARE (people on the split) as separate groups.
- Picking a person's payment goes to their Mark paid back (PB-12/13).
- Today `parts_api.py` puts "{name} is on this split" on every row (line 1019), and PaidBackFindViews.swift:177 shows the "Next: …" footnote. Cut both.

**String list:** every string to cut or shorten is in note `1426:8225`. It covers PB-22, RQ-01, PQ-01/02/03, TF-01, AS-01 v2, YP-01–09, TR-*, PB-30/41/42, AI-02/03/06/18, the chat cards PC-01–13, the leftover message lines and AnswerSheet's "Pearl will remember…" footers.

### [designBOT → engBOT] 2026-11-16 · TEXT-01 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-16)
**Figma:** Proposals › "Less text · Approved, ready to build" `1425:6647`, notes `1426:8224` and `1426:8225`

The product owner approved:
- the copy rules, which now apply to every new design;
- the full string list in note `1426:8225`;
- the after frames LT-01 to LT-05.

When your PR merges, I'll make the same cuts in the matching Pearl app frames, so Figma and the app say the same thing.

### [designBOT → engBOT] 2026-11-16 · TEXT-01 · Built (#369): Figma updated, and your gaps answered
**Status:** Redesigned
**Figma:** Pearl app (whole page), plus the Proposals sections "Polish" and "Your accounts v2"

**Figma**
- **The cuts:** every string in note `1426:8225` is applied across Pearl app frames. That's 100 text layers and 4 component properties; 8 cut lines are hidden.
- **LT frames in the befores' places:**

  | Frame | Light / dark | Now in | Status |
  |---|---|---|---|
  | LT-01 | `1425:73658` / `1425:73900` | Sorting › Paid back | built (#369) |
  | LT-03 | `1425:7351` / `1425:7552` | Sorting › Payback question | built (#369) |
  | LT-05 | `1425:72756` / `1425:72885` | Profile › Your plan | built (#369) |
  | LT-02 | `1425:6768` / `1425:7025` | Proposals › Polish (RQ-01 isn't built yet) | approved |
  | LT-04 | `1425:7857` / `1425:8059` | Proposals › Your accounts v2 (AS-01 v2 isn't built yet) | approved |

- **The old frames:** each is renamed "SUPERSEDED by LT-0n · …" and moved to the right edge of its section, for the product owner to clear. Sorting and Profile grew to fit.

**Your gaps**
1. **PB-22, money Pearl can't place:** yes, give it a header, OTHER MONEY IN. Rows keep their usual form, for example "Anastasia · +$30.00" over "Nov 2", with no reason line.
2. **TR-02m without the month:** OK. The trip's dates ("Mar 4–9") already say March.
3. **YP-02 / YP-07 with no income:** add one short line, "Add your income to see your Allowance." It changes what she does next.
4. **TR-08 with one transaction:** make it "Adds the tag." ("to it" adds nothing).
5. **AI-18b:** "Last 5 at Farm Boy: Groceries." is right, keep it.
6. **Quick sort's "Yes sorts it as X. Tap the card for more.":** cut it. The dashed guess chip already says X, and the card can be tapped either way.
7. **PB-11's "{name} is on this split":** "On this split". The row already shows the person's name.

### [designBOT → engBOT] 2026-11-16 · TEXT-01 · Figma corrections
**Status:** Redesigned
**Figma:** Pearl app › Sorting `1429:83285`, Onboarding and sign-in `1429:83286`

**Deleted.** These were the frames LT-01 to LT-05 replace. Anything not used is deleted, not marked superseded:

| Was | Light / dark |
|---|---|
| PB-22 | `1359:9489` / `1359:9694` |
| PQ-03 | `1418:88292` / `1418:88584` |
| YP-01 | `1353:10206` / `1353:10356` |
| RQ-01 | `1389:23274` / `1389:23646` |
| AS-01 v2 | `1415:87857` / `1415:88299` |

**Moved.** RQ-01 and AS-01 v2 are built (#361, #367, then #369), so their frames now live in Pearl app:

| Frame | Light / dark | Now in |
|---|---|---|
| LT-02 (RQ-01) | `1425:6768` / `1425:7025` | Sorting › "Recurring transfer question" `1429:83285` |
| LT-04 (AS-01 v2) | `1425:7857` / `1425:8059` | Onboarding and sign-in › "Your accounts" `1429:83286` |

Both are labelled "built (#369)" and are off Proposals.

**Spacing.** Sections are shrunk back to their content. Sections below that grew were moved down: Splits and paybacks by 1352, Confirmation sheets by 915. Nothing overlaps.

### [designBOT → engBOT] 2026-11-17 · MANY-01 · The shop and Work pay back several purchases
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181, THL-301   **Figma:** Proposals › "Many purchases · Awaiting product owner" `1431:6590`

| Frame | Light / dark | What it is |
|---|---|---|
| MP-01 | `1431:6591` / `1431:6826` | Work: Northwind's $186.40, with 3 work purchases pre-ticked to add up; "Mark 3 reimbursed" |
| MP-02 | `1431:7059` / `1431:7285` | The shop: Costco's $64.97, with 2 Costco purchases pre-ticked; "Mark 2 refunded" |
| MP-03 | `1431:7509` / `1431:7741` | Less ticked: "$14.10 left over"; the button "Next: the other $14.10" opens S-11w or S-11m |
| MP-04 | `1431:7971` / `1431:8200` | Too much ticked: the oldest in full, the newest part-refunded on its row ("$35.03 of it · Change", which opens PB-13) |
| MP-05 | `1431:8427` / `1431:8579` | One ink toast, one Undo for all of them |

The note is `1432:8062`.

Replaces T-09w and T-09rs, which pick one purchase each.

Build notes:
- **Pre-ticking:** her own purchases, or her share of split ones, oldest first, adding up to the deposit.
- **Work candidates:** purchases she marked as work, or that match past reimbursements.
- **The shop candidates:** purchases at that shop dated before the refund.
- **One save:** S-11w and S-11m join the same save, so a single Undo reverts everything.

### [designBOT → engBOT] 2026-11-17 · MANY-01 · Approved, ready to build
**Status:** Approved, ready to build (product owner, 2026-11-17)
**Jira:** THL-289, THL-291, THL-181, THL-301   **Figma:** Proposals › "Many purchases · Approved, ready to build" `1431:6590`, note `1432:8062`

All 10 frames are labelled approved. The total line in MP-01 and MP-02 ("$186.40 of $186.40 ✓") now shows green (color/text/money-in) in light and dark. The Pai row reads "Pai Northern Thai · your $60.00" in MP-01 and MP-03.

### [designBOT → engBOT] 2026-11-17 · MANY-01 · Built (#374): moved, and the copy you wrote
**Status:** Built
**Figma:** Pearl app › Sorting › Paid back › "Many purchases … built (#374)" `1435:75733` (MP-01 to MP-05 in light and dark, plus note `1432:8062`). The Proposals section is gone. Splits and paybacks moved down 1733.

Your copy:
- **Titles:** use the payee's tidy name, not its first word. "The Home Depot" would come out as "The", and "TD Canada Trust" as "TD". Fall back to the first word only when the tidy name is too long for one line.
- **Captions:** OK as written.
- **Rows:** OK as written.
- **"$X over":** OK as written.
- **Shop toast:** "Costco refunded 2 · $64.97". Use "paid back" for Work only.
- **PB-13 from MP-04:**
  - The title, the caption and hiding "All of it" are OK.
  - Cut "Tap to change the amount". The amount field already looks editable (copy rule 4).
- **Empty and search states:** OK as written.
- **Error:** OK as long as there's a "Try again" button. If the button is there, the line is just "Couldn't load your purchases." so "Try again" isn't said twice.
- **S-11w after MP-03:** no line under the tiles is right.

### [designBOT → engBOT] 2026-11-17 · MIGRATE-01 · Designs move from Figma to Claude Design
**Status:** Done (first pass); Figma is now a read-only archive
**Jira:** —   **Design:** Pearl Design System https://claude.ai/artifact/3Zq5EtAAvrStZ1NAiYmy72 · Pearl app canvas https://claude.ai/artifact/NJhe1u5quJpJoyo4LFk2fR · Proposals canvas https://claude.ai/artifact/9WdzY4sYSxQHRjtE2ReC7v

The product owner decided today that the iOS handoff lives in Claude Design from now on. Nothing in Figma (`ohcxhB9hV25H6nANVw3lq4`, library `3fdfPDKIjhiluGHtXWSF32`) is edited again; read it only for frames not yet rebuilt.

- **Pearl Design System**: built from the app's code, not from the Figma library, so where they differed the app wins (REFRESH-05 glass, mist/600 muted, SP-B plum, TC-A grey ⇄, the link token). Tokens (colour light and dark, Fraunces and Figtree with the font files, spacing, radii, shadows, sizes, strokes), the brand book with the house rules and the TEXT-01 copy rules, the 21 marks from `Assets.xcassets`, and 24 hand-written components (Button, Toast, Status pill, Choice, Option row, Person row, Transaction row, Account row, Answer tile, Sheet, Glass button, Navigation bar, Tab bar, Search field, Filter chip, Callout, Avatar, Amount field, Toggle, Segmented control, Allowance orb, Shell mark, Glass card, Background). The previews are static markup; there is no bundle, the app is SwiftUI.
- **Pearl app** canvas: nine pages matching the Figma sections. Rebuilt as real markup, light and dark side by side, with the system installed: H-00r; T-01r, T-03r; RQ-01 (LT-02), PB-30; S-04r v2 (RC-02 header), S-40a; P-01, AM-01; O-01, A-01; SO-06. Every page carries a note listing what is still to be rebuilt from the archive, by screen code and Figma node, so nothing is dropped. The Figma tab bar (floating glass pill) is not what ships; the canvas draws the system tab bar tinted `action`, as the app does.
- **Proposals** canvas: AI phase 2 (AI-20, AI-21, the decisions note) as Awaiting product owner, and Deferred (SEC-08, SEC-09, A-12: recovery codes on iPhone). Every other Figma Proposals section (Trips TR-17/18, Transfer colour, Account setup, Polish, Paybacks & undo, Row shows your cost, Paybacks 2, Your accounts v2, Less text, Many purchases) is built on origin/main (#356 to #375), so it belongs on Pearl app, not Proposals; those screens are in the Pearl app "still to rebuild" notes.
- Role files: `.claude/agents/designBOT.md`, `engBOT.md`, `testingBOT.md` now point at the three artifacts; the rules are unchanged (Pearl app holds what's built, Proposals holds what isn't, anything unused is deleted, never "superseded"; `**Design:** canvas › page › artboard` replaces the Figma node in log entries).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Splits and paybacks, batch 1: person options (•••) rebuilt
**Status:** In progress (Splits and paybacks: 1 of 9 subsections done)
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-260   **Design:** Pearl app › Splits and paybacks

- Tab bar (product owner, 2026-11-17, phone screenshot): the system TabView tinted `action` ships as iOS 26's floating glass capsule, the selected tab on a soft lozenge, a red badge on Cash flow. The design system's TabBar component and every artboard with a bar (H-00r, T-01r, P-01, AI-20) now draw it; the Home note says it is as built, not a proposal.
- Drawn from SplitMenus.swift, SplitFlow.swift (S-06ra–rd, LetGoSheet) and PaybackOptions.swift, light and dark, one artboard per code: S-40a (corrected to the code's rows), S-40b, S-40c, S-40c2, S-40d, S-05or, S-06ra, S-06rb, S-06rc, S-06rd, S-07ra, S-07rb, S-08ra–rd (one artboard, four states), S-03fr, S-03fr2, S-34sr (+ loading, error), S-34kr1/kr3/kr8 (one artboard; kr2, kr4–kr7, kr9, kr10 share the frame, their words come from the server's `LinkInfo.sheet` and were not copied), S-44a–i (one artboard: the split card with the S-44b toast and the nine toasts' words).
- Not rebuilt in this subsection: S-03re (How to split opened from S-40; belongs with the S-03 flow in the next batch).
- Remaining in the group: Splits & paybacks main flow (536:14142, 106 frames), Not sure yet (1285:44513, 88), round-1 fixes (1285:59587, 14), you in a Not sure yet split (1285:59588, 34), option C (1285:59589, 14), your share gives way (1285:59590, 8), TEST-31 (1369:70116, 30), Mark paid back fields (1369:70117, 6). The Splits page note lists every code.

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Splits and paybacks, batch 2: main flow, Not sure yet, you in it, option C, TEST-31 cards, Mark paid back fields
**Status:** In progress (Splits and paybacks: 43 more artboards, light and dark; the group is drawn except T-98s, S-03j v2 and S-24xr, which belong with Sorting, Joint accounts and Confirmation sheets)
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-303, THL-260, THL-282, THL-172   **Design:** Pearl app › Splits and paybacks (rows from y 5400 down)

- Drawn from SplitFlow.swift, PartsFlow.swift, SplitMenus.swift, YourShareViews.swift, WhoSentSheet.swift and JointSplitViews.swift (PeoplePicker), several states per artboard where a code has many: S-02 v2; S-03 (S-18 v2, S-03e, S-15 v2, S-16, S-03re, S-24); S-03r2/r2b/r2c, S-03ax; S-03rg/rh/ri; S-17 v2; S-09, S-25, S-23, S-32; T-09w, T-09rs; S-35, S-35a, S-35a1, S-35b; S-09u, S-09u2, S-35u, S-35u2, S-35ux; S-10, S-10e, S-36; S-11 v2, S-11c, S-11x, S-11xm (+ over); S-11k, T-08k (+ error); S-11w, S-11m; S-12 v2, S-12c, S-12d; S-13, S-13 v2; S-14, S-14p, S-14u, S-14u0, S-14u3, S-14u4, S-14u5, S-14ul, S-14ux; S-21, S-21u, S-21x, S-21xw, S-21xm; S-22 v2; S-33 v2, T-41w, T-41m; S-35c (+ error); S-05u, S-05v, S-26; H-00n, H-00u, H-00u0; S-03u, S-03u0 to u3, S-03us, S-03ue; S-04u, S-04u0, S-04u5 to u8, S-04ul, S-04ue, S-04r v3, S-04r v2s, S-46c, S-48d; S-04w/w2/w3, S-04m/m2/m3/m4; S-40u, S-40u2, S-40y, S-40w, S-40m, S-48e; S-45a, S-45a2, S-45b, S-45bs, S-45bx, S-45d, S-48c, S-47f2; S-48a, S-48b; S-46a v2, S-46as, S-46ax, S-46a3; S-47a to S-47g; S-07u, S-06uc; S-03fu, S-03fu1; S-06 v2, S-06 v3, S-06 v3a; S-44u1 to u4, S-45f, S-45g, S-46b, S-46d, S-46e (one artboard: the card with its toast, and every toast's words).
- Not redrawn because a built frame already here covers them: S-29 (S-06rb), S-30 (S-40b), S-34 (S-34kr/S-34sr), S-28 (the S-21 row), Status tag (the design system's StatusPill).
- Figma was reference only; copy and rows follow the Swift views (TEXT-01 less-text cuts, #369/#370). Where the code reads from the server (S-11xm's lines, S-46's rows, toast words) the sample words are representative, not copied from a frame.
- Rebuilt with a generator (scratchpad/tools/pearl.py, splits_a.py, splits_b.py): one shared stylesheet from tokens.css, static light and dark markup, so later groups can reuse the same atoms (sheet header, option row, person row, tiles, meter, toast, tab bar).
- Next: the Splits page note lists where T-98s, S-03j v2, S-24xr and the approved Proposals screens (PB-30u/30o, PB-41, PB-42, UN-01a/b, PP-01/02, MP-01 to 05, TP-01 to 05, RC-01/03) go. Then Cash flow and transactions (1285:72188) with Calendar and Trips, Sorting, Joint, Profile, Onboarding, Confirmation sheets, Pearl chat, Home, each from its page note.

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Cash flow and transactions rebuilt (with Trips, Calendar, RC-01/03, TF-01)
**Status:** Done (Cash flow and transactions)
**Jira:** THL-122, THL-123, THL-125, THL-213, THL-226, THL-231, THL-232, THL-254, THL-255, THL-257, THL-263, THL-275, THL-288, THL-289, THL-291, THL-292, THL-293, THL-295, THL-297   **Design:** Pearl app › Cash flow and transactions (rows from y 1400)

- 32 artboards, 109 states, light and dark, drawn from TransactionsView, TransactionDetailView, CategorySheet, AddTransactionSheet, CalendarView, TripViews, RecurringTransfersView and AnswerSheet: T-01r2 (RC-01 rows with SP-B/TC-A ⇄ grey, T-01r3, PC-02, T-34); T-45 (T-17, T-18, T-46 to T-48); T-49 (T-50, T-21, T-22); T-04 (T-51); T-23; T-43; T-08 (T-08n, T-37n, T-14, T-15, T-09r); T-16 (T-57); TF-01 (TF-01c); RC-03; T-35 (T-02, T-54, loading, error); T-58 (T-59, T-36); T-01b (T-67, T-53, T-56, T-73); T-17b to d; T-77 (T-78); T-04n (T-79, T-80); T-42 (T-81, T-37); T-40 (T-40b, T-38b); T-41 (T-41b); T-07 (T-31, T-33, T-60, T-71); T-11 (T-72); T-61 (T-62); T-68; RT-01 (RT-02 v2 as built, T-82); Trips TR-02 to TR-16, TR-10/10b, TR-17, TR-17e, TR-18.
- Not redrawn, with the reason on the page note: T-01r2 (now RC-01), T-09 (PB-10/11), T-13 (PQ-01), T-05 (TF-01), T-39 (S-04r v2), T-69 (RQ-01), T-70 (PQ-03), T-20 and T-44 (tags are off, THL-286), the Outcome table (reference, not a screen).
- Server words (toasts, category lists, preview lines) are representative samples, not copied.

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Sorting rebuilt (one page, Needs a look, Quick sort, paybacks, many purchases)
**Status:** Done (Sorting)
**Jira:** THL-117, THL-122, THL-123, THL-139, THL-181, THL-213, THL-226, THL-231, THL-232, THL-254, THL-275, THL-289, THL-291, THL-301   **Design:** Pearl app › Sorting (rows from y 1400)

- 17 artboards, 97 states, light and dark, from AnswerSheet, ReviewView, QuickSortView, PearlSortsViews, PaidBack*, PaybackQuestionViews and PartsFlow (858–1300): T-83 (the full Needs a look: kinds, Skipped, empty, all sorted, error, T-104); T-107 (AI-02, T-108 to T-110); T-103 (What was this? money out and money in on one page, T-105, T-106); T-93 (T-93o, T-95, T-97, T-98, T-98s a card holding a split); T-99 (T-100 to T-102, AI-07, done); T-96; AI-18 (AI-18b, AI-18y, TR-01); AI-03 (AI-03b, AI-04 + busy/error/after, AI-09); PB-10 (PB-11); PB-12 (PB-13, PB-13b, PB-14, PB-15); PB-20 (LT-01/PB-22, PB-23, PB-24); PB-30u (PB-30o); PB-41 (PB-42, PP-01, PP-02); UN-01a/b; MP-01 to MP-05; LT-03 (PQ-03, PQ-03b, PQ-03p, PQ-03c); PQ-01/PQ-02.
- Not redrawn: T-74 (no sheet is built; it ships as Home's "3 paycheques" card), RT-02 v2 (drawn once, with RT-01 on Cash flow). The Sorting backlog notes are gone.
- For engBOT, as found while drawing (no change asked yet, product owner to decide): PB-13 still says "tap to change the amount" (TEXT-01 rule 4); PB-30o and MP-04 colour an allowed over-amount in `danger`; LT-01 and MP load errors have no Try again button.

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Joint accounts rebuilt (with S-03j v2 and TP-01 to TP-05)
**Status:** Done (Joint accounts)
**Jira:** THL-172, THL-181, THL-201, THL-203, THL-208, THL-217, THL-226, THL-234, THL-282, THL-289, THL-291, THL-304, THL-305   **Design:** Pearl app › Joint accounts (rows from y 1400)

- 13 artboards, 50 states, light and dark, from JointMergeViews, JointSplitViews, JointPaybackViews, WhoseAnswer and AccountsViews: AM-08p to p7 (people picker: contacts asked, off, search, six, empty, loading, error); AM-08r, r1, AM-08, AM-08x, x1; O-09cr; S-01jr, S-01jr2; T-06jr, T-06jr1; T-76 (+ Part of it, error, toast); S-03j v2, S-03j1 to j4, S-17j; S-04j, S-04j1; AM-21j, AM-21j1, AM-08n, AM-08n1; S-41j to j2; AM-09 (+ nothing to combine), AM-10; TP-01 to TP-05. Every Figma code in the group is drawn; the backlog note is gone.
- The iOS contacts permission prompt is the system's and is not drawn (AM-08p1 shows the loading rows).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Profile and settings rebuilt (with Your plan, account setup, Your accounts v2)
**Status:** Done (Profile and settings)
**Jira:** THL-45, THL-49, THL-104, THL-114, THL-115, THL-116, THL-117, THL-118, THL-120, THL-121, THL-123, THL-127, THL-128, THL-139, THL-172, THL-198, THL-205, THL-209, THL-214, THL-225, THL-226, THL-234, THL-262, THL-287, THL-294, THL-300   **Design:** Pearl app › Profile and settings (rows from y 1400)

- 24 artboards, 99 states, light and dark, from ProfileView, ProfileParts, AccountsViews, CategoriesRulesView, YourDataView, StartOverView, PrivacyViews, SettingsViews, ChangeEmailView, IncomeBillsView, DebtsView, YourPlanView, PearlSortsViews and AccountSetupViews: P-02, P-03; C-01; AM-02 to AM-04; AM-05 (the sheet AM-10 also opens); AM-06; AM-07; C-06; CR-00 to CR-03; CR-04 to CR-10; D-01, D-02; D-03 to D-05; SO-02 to SO-04 (SO-02 as the code: Start over keeps only banks); N-01, N-02; IB-01 to IB-03b; DB-01, DB-02; SO-05b; LG-01, LG-02; SEC-11; SEC-10, A-11, A-11b; AM-11 to AM-13, AM-07b; AI-05, AI-06, AI-06b, AI-04f, AI-08; LT-05 (YP-01) to YP-09; AS-04 with AS-02.
- The page note keeps two pointers: AS-01 is AS-01 v2 (LT-04) on Onboarding, and Your accounts v2 has no screen of its own (it is LT-04's grouping).
- Tab bar: the app hides it only on Your data, Delete your account, Start over and the full-screen results, so the pushed Profile pages draw it. The earlier AM-01 and T-03r artboards leave it off and need the same treatment (product owner's call).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Onboarding and sign-in rebuilt (with AS-01 v2, LT-04)
**Status:** Done (Onboarding and sign-in), with the gaps on the page note
**Jira:** THL-114, THL-119, THL-120, THL-172, THL-294, THL-300, THL-304, THL-305   **Design:** Pearl app › Onboarding and sign-in (rows from y 1400)

- 17 artboards, 58 states, light and dark, from AuthFlow, SetupFlow, SetupPayQuestions, PayAndBillsView, AllowanceView, SavingShareView, FaceIDViews, DeviceCheckViews, PlaidLinker, AccountSetupViews and Theme/Nacre.swift: O-00; A-08; O-02, O-02a, O-02b; O-03, O-03a; O-04, O-04a, O-04b, A-09; O-06; O-08, O-08a, O-08b; O-09, O-09a, O-09d, O-09f; LT-04 (AS-01 v2); O-10, O-10e; O-10a to O-10d; O-10f, O-10g; O-10s; O-11, O-11a to O-11d, O-12; A-02, A-03, A-04, A-10; A-05 to A-07; SEC-01, SEC-02. The two iOS system prompts (Face ID, notifications) are drawn and captioned as the system's.
- Not rebuilt (page note): O-07 to O-07e are Plaid Link's own SDK screens; O-09b, O-09b2 were replaced by AS-01 v2 (LT-04); SEC-03 passkeys aren't built (they wait for the associated domain); the closed and opening setup shells use the LogoMark as a stand-in until ShellClosed/ShellOpening are uploaded.
- Found while drawing: the first-pass O-01 and A-01 artboards don't match AuthFlow.swift ("Get started" / "I already have an account"; "Forgot password?", "New to Pearl? Create an account"). They are redrawn in the final pass.

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Confirmation sheets rebuilt (with S-24xr)
**Status:** Done (Confirmation sheets)
**Jira:** THL-45, THL-114, THL-116, THL-117, THL-120, THL-122, THL-123, THL-127, THL-139, THL-214, THL-226, THL-231, THL-234, THL-255, THL-257, THL-263, THL-287, THL-289, THL-291 · TEST-06   **Design:** Pearl app › Confirmation sheets (rows from y 1400)

- 14 artboards, 41 states, light and dark, from PearlConfirmSheet and each caller (Rule.removing for the rules): T-77c, T-77c2 (+ l, e); T-03x, x1, x2; S-24xr; T-49b; P-05 (+ l, e); SEC-12r (+ l, e); SEC-04r (one and two devices, + l, e); SO-06 Reset Pearl with SO-06a, SO-06b; CR-00x (leave-out and pay rule, + l, e); CR-10x (+ l, e); AM-09n, AM-14n, IB-04, CN-05r (each + l, e). All 39 light Figma frames are drawn; the backlog note is gone.
- The first-pass SO-06 artboard drew the Start over sheet under SO-06's name; it is removed. Reset Pearl? (SO-06, as built) now sits on the SO-06a artboard, and Start over is SO-02/SO-03 on Profile.
- Drawn as the code, not the frame name: P-05 "Sign out on this iPhone?"; IB-04 "Are these your rent?"; CR-10x with a plain tag (a trip's tag opens TR-09, drawn on Cash flow).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Pearl chat rebuilt
**Status:** Done (Pearl chat)
**Jira:** THL-117, THL-139, THL-213, THL-254   **Design:** Pearl app › Pearl chat (rows from y 1400)

- 4 artboards, 17 states, light and dark, from ios/Pearl/Chat (PearlChatView, ChatCards, ChatCore, PearlButton; not in the earlier Swift export, read from origin/main): PB-01 and PC-03, PC-04 (+ working it out); PC-05, PC-06 (+ split held, failed save); PC-07 to PC-11; PC-12, PC-13 (+ Not now, trip or rule made). All 12 Figma codes are drawn with the #369 less-text copy; the backlog note is gone.
- PC-01 (Home) and PC-02 (Cash flow) are on their own pages. The app shows the Pearl button on all five tabs wherever Apple Intelligence runs; the other tab-bar artboards don't draw it yet (product owner's call).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Home rebuilt
**Status:** Done (Home)
**Jira:** THL-117, THL-120, THL-123, THL-125, THL-139, THL-213, THL-232, THL-275, THL-291, THL-294, THL-300   **Design:** Pearl app › Home (rows from y 1400)

- 5 artboards, 13 states, light and dark, from HomeView and what it calls: H-01, H-02 (three banks, worst first) and the Reconnect sheet; SU-01 (3 left, accounts done) and SO-04b; AI-01 with Home's cards in built order; PC-01 (resting, with a suggestion); SV-00 and W-00 (blank tabs, as built).
- Card order in HomeView: Allowance, bank alerts, Set Pearl up again, Needs a look (when there is anything to sort), AI-01 (when Pearl sorted any this week), OwedNudgeCard, 3 paycheques (T-74 as built), the month card. OwedNudgeCard sits **below** Needs a look (and below AI-01 when it shows); it appears when someone owes at least a cent and the oldest share is 7+ days old, otherwise "X isn't settled yet" for a week-old Not sure yet split; it has no dismiss.
- Not rebuilt (page note): SU-02, replaced by Account setup's Check your accounts (AS-04 → AS-01 v2).

### [designBOT → engBOT] 2026-11-18 · MIGRATE-01 · Final pass: tab bar on pushed pages, the Pearl button on the five tabs, first-pass fixes
**Status:** Done (migration complete; every Figma group is on Pearl app)
**Jira:** THL-114, THL-117, THL-119, THL-122, THL-125, THL-139, THL-292, THL-295, THL-297   **Design:** Pearl app (version 23)

- Tab bar (PearlApp.swift: hidden only where a view hides it: Your data, Delete your account, Start over, Select): drawn on every pushed page on Cash flow, Splits and AM-01 that left it off (T-03r, S-04r v2, S-44, AM-01 and 28 more artboards); toasts on those pages now sit above the bar. Needs a look's question pages and Quick sort are fullScreenCovers (ReviewView.swift:100, HomeView.swift:88), so Sorting stays without it. Onboarding and Pearl chat have none.
- Pearl button (product owner, 2026-11-18; PearlApp.swift:267–269, "on the five tabs only, never on what's pushed over them"): added on every tab-root phone without a sheet over it: H-00r, H-00n, H-01, SU-01, AI-01, SV-00/W-00, T-01r, T-01r2, T-45, T-49, T-35, T-58, T-01b, T-68, TR-04's Cash flow toast, TR-05, TR-10, P-01 (15 artboards beside PC-01).
- H-00r and H-00n: dropped "Left to spend or save on non-essentials." under the orb (REFRESH-03; HomeView.swift:133 keeps it as the VoiceOver hint only).
- O-01: "Get started", "I already have an account", Privacy · Terms (AuthFlow.swift:101–109). A-01: "Forgot password?" under the card and "New to Pearl? Create an account" under Sign in; the Face ID line is gone (AuthFlow.swift:397–426).
- RQ-01: redrawn from AnswerSheet.swift recurringTiles: caption "Every month since March", the card's money line and "Next: around Tue, Dec 2", tiles Rent, Into savings, My other account, Something I pay for, then No, it isn't regular.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-01 · Three directions for a new look (nothing to build yet)
**Status:** Needs product owner (Awaiting product owner)
**Jira:** THL-125, THL-254, THL-213, THL-123, THL-122, THL-231, THL-291, THL-289, THL-181, THL-301, THL-232   **Design:** Claude Design › Pearl redesign (https://claude.ai/artifact/2k7iUpAwrxvqbFLpyazvWT), 12 artboards

The product owner asked for a full redesign of the look with the app working exactly as it does now. First step: 2–3 directions on four anchor screens, light and dark, for her to pick from. Each artboard was rendered and checked against the phone screenshots and the Swift views (origin/main 0e549fd) before publishing.

- **Screens (same four in each direction):** H-00r Home (HomeView, AllowanceOrb, NeedsALookCard, OwedNudgeCard, MonthCard, Pearl button); T-01r / RC-01 Cash flow (TransactionsView summaryCard, day headers with Select, TransactionRow with GuessChip, ⇄ transfer, a split row's cost line); S-04r v2 / RC-02 a split purchase (header cost and date lines, Counts pill, category row with Change, SplitPeople with Edit split, You / paid / part paid / owes / let go, See everyone who owes you, Details); LT-03 (PQ-03) Is mPg paying you back? (PaybackHeader with Name them, LOOKS LIKE, the dashed guess tile, Something else, Not a payback).
- **A · Refined Pearl:** the nacre ground softened with a white veil; one white-glass card; caps section labels outside the card with their quiet action; amounts on one right edge (the ••• on split rows goes; the row already opens PersonOptionsSheet); bars under the words; Home's owed and month cards as two rows of one card.
- **B · Nacre Blocks:** a plain paper page; colour only in a nacre block (Allowance, a purchase's header) and an ink block (Needs a look, the month); big Fraunces; tinted faces; a 12-dash sorting streak; a 5-part paid-back bar on a split; ••• kept in one column.
- **C · Pearl Paper:** paper with a faint nacre dawn; inset grouped lists, hairlines, no shadows; the Allowance as a big left-aligned number on a nacre thread with the pearl bead; one 32 pt left edge; PQ-03 as one list.
- **Polish 2** is folded into all three (one card, one label, one primary button, one face/payment row, one right edge, quiet actions in link colour, feedback above the tab bar, no red filter dot). Copy tidy-ups, all less-text: Sam's "· owes $20.00" and the category row's "Your share · $30.00 of $150.00" go (each is said once already).
- **Recommendation to the product owner:** A as the base, with two of B's delight moments (the sorting streak on Needs a look, the paid-back bar on a split). It keeps Pearl's identity, fixes what reads as sloppy today (four card styles, three label styles, amounts that wander), and is the smallest build: tokens, PearlCard and the row components, not new layouts.
- **Design system:** ShellClosed.svg and ShellOpening.svg were already in its asset store and Logos group (byte-identical after the server's SVG normalising); a fresh upload returned the same hashes, so the two new copies (b6904400…, 8ec3a2b8…) are unreferenced duplicates. Product owner, say if you want them deleted.
- engBOT: nothing to build until the product owner picks a direction.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-02 · Chosen direction (draft): A+ with a new navigation
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-125, THL-254, THL-213, THL-123, THL-122, THL-231, THL-291, THL-289, THL-181, THL-301, THL-232, THL-117, THL-139, THL-209   **Design:** Pearl redesign › row "A+ · Chosen direction (draft)" above A, B and C (AP-Home, AP-CashFlow, AP-Transaction, AP-Sheet, AP-Chat)

The product owner picked A · Refined Pearl plus B's sorting streak and B's paid-back bar, and asked for a new navigation. A, B and C stay on the canvas for reference. Every artboard was rendered and checked.

- **Combined:** the 12-dash streak replaces the bar on Home's "8 to sort" (10 of 12 for 40 of 48), with a small streak in Cash flow's "8 need a look" row. The 5-part paid-back bar sits at the top of the split card, one segment per row in row order; it replaces the per-row bars (each row's line still says it).
- **Navigation:** tab bar Home · Cash flow · Save · Wins · Pearl (line shell icon), floating glass pill kept, five even items, Cash flow badge kept. Profile leaves the bar for an initials button (36 visual, 44 tap) top right on Home, Cash flow, Save and Wins, lined up with the filter button's edge. The floating Pearl button is gone.
- **Pearl tab:** the same chat (PC-03 starters, composer, "On this iPhone only", cards, Yes/Skip and Set it/Not now before any change), drawn as a full tab screen with the tab bar showing. Close goes; "New chat" starts over. Recommended over a sheet: a tab should go somewhere rather than open a modal over the current tab, and the visible bar lets her check Cash flow mid-answer.
- **Open questions for the product owner:** (1) keep the conversation across tab switches, or start fresh each time as today; (2) where Apple Intelligence can't run, show the tab with PC-11 (recommended) or drop to four tabs; (3) Profile as a pushed page in the current tab (draft) or a large sheet; (4) move the button's suggestion ring/dot to the Pearl tab as a nacre dot; (5) a dot on the avatar when Profile needs her; (6) initials or a photo.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-03 · A+ decisions, photo, three fixes, Liquid Glass tab bar
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-125, THL-122, THL-291, THL-117, THL-139, THL-209   **Design:** Pearl redesign › A+ row (version 5): AP-Home, AP-CashFlow, AP-Transaction, AP-Sheet, AP-Chat updated; AP-NavOption, AP-PhotoHome, AP-Profile, AP-PhotoSheet, AP-Crop new

- **Decisions drawn:** the chat keeps its conversation across tabs and New chat clears it. Where Apple Intelligence can't run, the tab shows the unavailable screen with Search and the bar stays at five. The profile circle pushes Profile in the current tab. The Pearl tab gets a nacre dot for a suggestion. The profile circle gets a nacre dot only when Profile needs her (coordinator's default; shown with Accounts "1 needs you").
- **Photo:** initials by default. Add photo / Change photo sits under the Profile avatar and opens a Pearl sheet: Choose photo, Take photo, Remove photo (only when a photo is set, in danger red), Cancel. Then Move and scale with Use photo / Cancel. The Profile header is no longer the link to Sign-in and security; that row stays under You.
- **Fixes:** Alex is "Let go · Nov 17". The chat composer is a field with a send up-arrow, off (track grey) while empty and rose when there's text. The Cash flow badge and the "8 need a look" chip use the tab tint, Pearl.action (#B22757 with #FFFFFF; dark #FF8FB1 with #1C1A33). origin/main already sets the badge to this (PearlApp.swift badged()); the phone screenshots predate that.
- **Tab bar:** redrawn as the iOS 26 Liquid Glass bar: a clear capsule (light blur, saturate, brighten) over the content, a specular rim brightest top-left, a glass lozenge under the selected tab, and the app's own template icons at 10 pt labels. Colours as built: selected #B22757 / #FF8FB1, unselected system label #000000 / #FFFFFF. These sit fine with A+. Possible refinement for the product owner: unselected in ink (#2E2547 / #FBF8F6) through UITabBarAppearance to match the page text.
- **Option:** Pearl as its own glass circle (the Tab(role: .search) look) on AP-NavOption. Not recommended: that slot and its morph-into-field behaviour are search's in iOS 26, and VoiceOver would treat it as search.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-04 · A+ Home is attention only; Owed to you redesigned
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-125, THL-254, THL-213, THL-291, THL-289, THL-181, THL-303   **Design:** Pearl redesign › A+ row (version 6): AP-Home, AP-Transaction, AP-PhotoHome updated; AP-HomeCalm, AP-Owed, AP-OwedPerson new

- **Home:** the orb, then only cards with something in them. Needs a look (streak, Sort now; See the list moves to the label). "2 people owe you" with $70.10 on the right edge, opening Owed to you. Since you were last here, with Clear. MonthCard is gone. The calm state is the orb plus "You're all caught up." The orb is 188 when cards follow and full size when calm.
- **Since you were last here:** Jo paid back Loblaws +$30.00 → the purchase; Pay came in +$2,150.00 → the deposit; Pearl sorted 12 on its own → Needs a look, Pearl sorted (replaces AI-01's card). Tapping an item marks it seen, Clear marks all seen, and items older than 7 days drop off. A bank to reconnect keeps H-01's card; a Pearl suggestion stays a dot on the Pearl tab; a plan over shows in the orb.
- **Owed to you (OwedView):** same sections (Owes you, Not settled with its line, Paid back this month). The total sits in the header ("$70.10 · from 2 people"). Reached from Home's card and from the split purchase's "See who else owes you" (renamed from "See everyone who owes you"). A person row opens a new person page (what they owe for); a purchase there opens that person's existing options sheet for it, plus "Open Loblaws".
- **Scope for engBOT later:** new function = the feed (update types, last-seen per device, seen, Clear, the 7-day drop-off, an API for it), the person page, and "Open <purchase>" on the options sheet. Visual or wiring only = MonthCard removed, the owes card's words and target, AI-01 folded into the feed, the renamed button, the calm line.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-05 · "Worth a look" replaces "Since you were last here"
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-125, THL-254, THL-213, THL-291, THL-289, THL-181, THL-165   **Design:** Pearl redesign › A+ row (version 8): AP-Home and AP-PhotoHome updated; AP-WorthAnswer and AP-WorthCatalogue new

- **Product owner's rules:** 3 items at most, ranked Pearl needs a yes, then heads-ups, then ONE good-news item. No plain news, no transactions. Nothing qualifies and the section goes. One line each. Clear can be undone with the ink toast. 7-day drop-off.
- **Home:** New subscription: Crave $19.99/mo (Yes / Not now inline); Rent comes out Friday $1,800.00 (opens the bill); $120 less on takeout than October (opens Cash flow on Takeout).
- **Answering:** Yes resolves the row ("Crave added to subscriptions"), the ink toast offers Undo, and the next item (Visa is due in 4 days, $612.00) slides up.
- **Catalogue:** all 17 approved items, with the tap target or inline action for each, marked reuse or NEW.
  - Reuse: trips, recurring and price_change, duplicates, bill and debt dates, plan pace, Not sure yet splits, piggy progress, the Allowance.
  - NEW: free-trial end, low-balance forecast, the N-weeks-unpaid rule, the halfway milestone, month-on-month comparison, the sorting streak, the "Your month" recap screen (entry point only), and the section itself (ranking, cap, seen/Clear/Undo, drop-off, an API).
- **Removed:** every "Since you were last here" item.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-06 · Worth a look: decisions in, the answer shows once
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-125, THL-254, THL-213   **Design:** Pearl redesign › A+ row (version 9): AP-WorthAnswer redrawn; the row's note updated

- **Decided (product owner, "go with your suggestions"):**
  - Inline Yes / Not now stays on a second line.
  - "New month", "Sam hasn't paid back" and "Corner Bistro" rank with the heads-ups; "October wrapped" with the good news.
  - Not now is permanent for that same thing; a new event can show again.
  - Answering in Worth a look or Quick sort clears both.
  - Netflix keeps the inline "Update the bill".
  - "Your month" is designed later with the rest-of-app rollout; only its entry point is drawn.
- **Fix:** the resolved-row state is gone. On Yes the row leaves, the next item (Visa is due in 4 days) slides up, and only the ink toast says "Crave added to subscriptions", with Undo. Drawn as before and after in light, and after in dark.
- **Motion note (built later):** the row slides out left and fades (250 ms), the rows below spring up (300 ms), the toast rises above the tab bar, and Yes gets a .success haptic. Reduce Motion: a 200 ms cross-fade.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-07 · Tab icons are the app's own files
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-209   **Design:** Pearl redesign › A+ row (version 10): every A+ tab bar updated; AP-TabCompare new

- **Icons:** TabHome, TabCashFlow, TabSave and TabWins are embedded from Assets.xcassets as they are. Their #000000 is swapped for the tint, as template rendering does (template-rendering-intent "template"). They show at their 26 pt size with their own 1.75 strokes and fills. The earlier drafts had redrawn Save (missing the lifebuoy's segments) and Wins (missing the dots); both are fixed. TabProfile is out of the bar.
- **Labels:** the system font, 10 pt medium, 2 pt under the icon. PearlApp sets no tab font or item insets, so the system defaults apply. Tint behaviour is as built: selected Pearl.action, unselected system label.
- **Pearl:** LogoMark, which is what PearlButton renders (Image("LogoMark"), 30 × 25), drawn in its own colours. As a template it becomes a solid clam silhouette, heavier than the line icons, and the pearl and ribs disappear (AP-TabCompare row 2). In SwiftUI that means `.renderingMode(.original)` on the Pearl tab's image; selection still shows through the lozenge and the rose label.
- **Comparison:** AP-TabCompare shows the phone screenshot's bar, a reference rendered from the asset files in light and dark, and the A+ bar in light and dark.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-08 · See-through light tab bar, A+ in the design system, rollout group 1 (Cash flow and Quick sort)
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-122, THL-123, THL-213, THL-231, THL-232, THL-254, THL-257, THL-263, THL-292, THL-295, THL-296, THL-305, THL-165, THL-209   **Design:** Pearl redesign (version 12): A+ row re-rendered, AP-TabCompare updated; new section "Rollout · Group 1" (G1-*, 17 boards). Pearl Design System (version 7).

- **Light tab bar:** nearly clear glass (white 20% → 8%, a light blur and saturation), so the pink-to-mint page shows through, as on the product owner's phone. The selected lozenge is lilac-tinted glass (`tab-lozenge`). Dark is unchanged. Pearl keeps LogoMark in its own colours.
- **Design system (A+, marked draft until built):**
  - New tokens: `card`, `card-line`, `separator`, `chip`, `track-soft`, `face`, `tab-lozenge`, `streak-from`/`streak-to`, `shadow-card-a`.
  - New components: Card, SectionLabel, PaymentRow, SortStreak, PaidBackBar, WorthItem, ProfileCircle, CalmState.
  - TabBar rewritten to the A+ five tabs. Toast, Sheet and Button READMEs gained A+ sections.
  - README gained an "A+ · the chosen redesign" section with the REDESIGN-02 to 07 decisions.
  - Existing components and the built-app rules are kept.
- **Group 1:** 17 boards, each two states in light and dark:
  - Cash flow: over, sync and bank, empty, no matches, search, Filters, by category, a category, calendar, Sort these days, Select, Mark as…
  - Transaction pages: sorted, Pearl's guess, income, transfer, refund, left out. What was this? for spending and for money in. Change category (also moves others), Add a transaction.
  - Sorting: Needs a look (list, all sorted), Quick sort (guess, after Yes, no guess, done), RQ-01, PQ-01, PQ-02, Where did it go?, Who sent this?, Same purchase?
- **Copy cut:**
  - Quick sort's two footnotes go; the toast says what Yes did.
  - "Someone sent you $120.00" under a Needs a look row becomes "Who sent this?".
  - The category goes from each Same purchase? row.
  - A left-out amount has no sign.
  - "Why Pearl is asking" goes as a label.
- **New function:** none in group 1.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-09 · Fields you can see, group 1 fixes, rollout group 2 (Splits and paybacks)
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-289, THL-291, THL-181, THL-301, THL-303, THL-122, THL-123   **Design:** Pearl redesign (version 14): new section "Rollout · Group 2" (G2-*, 16 boards); G1-TxSpend, G1-Change, G1-Asks, G1-Calendar and AP-Chat updated. Pearl Design System (version 10).

- **Group 1 decisions in:** the Quick sort cuts stand; a guess opened from the list hides the tab bar; a category page shows its icon; a left-out amount has no sign.
- **Fix:** "Always for Loblaws" lost its repeated line. No other toggle or row on G1 or A+ repeats its title.
- **Where you can type (product owner's rule):**
  - New TextField in the design system: the `well` / `well-line` tokens; rest, focus (2 px action outline, caret, keyboard), filled, error (red only for a real error) and disabled states; 44 high; `$` before money, a magnifier before search.
  - AmountField, SearchField and the README updated.
  - On the canvas: Cash flow search and every sheet search are wells. Add a transaction shows the amount in focus with the number pad (light and dark). Sort these days' Name and the Pearl composer are wells.
- **Group 2:** 16 boards, two states each in light and dark:
  - The split card with the paid-back bar; Not sure yet with no bar.
  - Who was it with? (search in focus with the keyboard); Edit split: Evenly, Amounts with a share in focus and the number pad, Shares, doesn't add up, Not sure.
  - A person's options and How did Priya pay?; Cash in hand and Remind (message well); Let it go and Remove.
  - A payback's options, and the toast after Mark paid back.
  - Who paid you back? (kind, then people).
  - PB-30 with OTHER PURCHASES ("$26.65 of it", Change), less, and more; How much of Sam's $60.00? (field in focus).
  - MP-01 and MP-02; PB-20 and LT-01; the PB-41 deposit page and S-04w work reimbursed; S-10 and S-12; S-35a and S-46a.
  - Owed to you and its person page are AP-Owed and AP-OwedPerson; PQ-03 is AP-Sheet.
- **Copy cut:** Sam's options header no longer repeats "$30.00 of $30.00"; The shop's line is "A refund".
- **New function:** none.

### [designBOT → engBOT] 2026-11-19 · REDESIGN-10 · Group 2 tidy-ups, the keyboard rule, rollout group 3 (Save)
**Status:** Needs product owner (draft, awaiting product owner; nothing to build)
**Jira:** THL-240, THL-229, THL-230, THL-169, THL-168, THL-170, THL-194, THL-127, THL-198, THL-125, THL-265   **Design:** Pearl redesign (version 15): new section "Rollout · Group 3 · Save" (G3-*, 9 boards); G2 boards updated. Pearl Design System (version 12).

- **Group 2 decisions in:** Not sure yet has no bar until settled; the five-part switch stays one row; Let it go keeps "Your Allowance doesn't change."
- **Keyboard rule (app-wide):** with the keyboard up, the Primary sits just above it, greyed out until the answer is valid. It's in the README and TextField.
- **Tidy-ups:**
  - Edit split lines are now "Paid $20.00 · $8.04 let go" and "Paid $28.04 · $8.04 over". Elsewhere: "Paid $10.00 · owes $20.00", "All of it · Nov 12", "Not paid back yet", "Pizza Nova · Nov 2".
  - The switch sizes each segment to its word with equal padding and fits a 375 pt phone.
- **Group 3:** 9 boards, two states each in light and dark:
  - The Save tab (Anchor, piggy banks, what it could grow into) and its empty state.
  - The Anchor page (how it adds up, savings accounts) and What's a safety net?
  - A piggy bank, and the same piggy bank after Add money.
  - New piggy bank: every year (amount in focus, keypad) and by a date.
  - Add money and Pay from a piggy bank.
  - Your plan: proposed and in use; change one category (amount in focus); no plan yet.
  - Plans and pace, and a plan that's over.
  - How your Allowance adds up (from the orb), and an estimate.
- **New function** (Save is blank in the app today; THL-265 took it out): the Save tab and its pages; Add money (piggy banks fill from the Anchor monthly, so a manual top-up is new); plans with pace on Save; the Allowance breakdown from the orb.
  - Reuses finance/piggy.py, category_budgets.py and your_plan.py.
  - Restyle only: T-105 and YP-01 to YP-08.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-11 · Save parked; group 5, Profile and settings
**Status:** Awaiting product owner
**Jira:** THL-104, THL-114, THL-115, THL-116, THL-117, THL-118, THL-120, THL-121, THL-127, THL-139, THL-172, THL-198, THL-205, THL-208, THL-209, THL-214, THL-234, THL-262, THL-287, THL-294, THL-300, THL-304, THL-305   **Figma:** none (Claude Design canvas "Pearl redesign", version 16)
Save is parked for a later stage, by the product owner. The G3 boards stay on the canvas under "Group 3 · Save (parked: later stage)", with titles marked Parked. Four questions are still open: Add money, where plans live, the grow-into extras, and the Allowance breakdown. G3-Allowance is parked and Home's orb stays as built. No Save components went into the design system, so there is nothing to mark parked there. Wins is skipped.
Group 5 has 22 boards, 2 to 4 states each, in light and dark: G5-Profile, SignOut, Photo, Accounts, Account, Remove, AccountEdit, Setup, Income, IncomeEdit, Security, Devices, Lock, Email, Notifications, Privacy, Protect, Data, StartOver, Reset, Delete, Load. Every confirmation is a Pearl sheet. Fields are wells, and with the keyboard up the Primary sits just above it, greyed until valid. Red is only for destructive entries and errors. The copy cuts and the list of new function are in the canvas note nG5.
New function, only if picked: Appearance as a Pearl sheet, replacing the stock Menu in ProfileView. Add an account as a Pearl sheet from +. Yes / No on found pay and bills. Saving and couldn't-save states for the photo.
Start over keeps the banks; Reset Pearl also unlinks them. Recovery codes stay deferred. Not in this group: Recurring transfers, Debts, Categories and rules.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-12 · Group 5 decisions; group 5b, Recurring transfers, Debts, Categories and rules
**Status:** Awaiting product owner (group 5b); group 5 approved by the product owner, design only
**Jira:** THL-295, THL-128, THL-49, THL-300, THL-123, THL-225, THL-226, THL-234, THL-213, THL-254   **Figma:** none (Claude Design canvas "Pearl redesign", version 17)
The product owner settled group 5's open decisions; they're recorded in nG5:
1. Progress and Milestones notifications are hidden until Save and Wins come back. G5-Notifications is updated and re-rendered.
2. The Your plan row stays on Income and bills.
3. The Anchor tag and "Part of my Anchor" stay as built.
4. Appearance and Add an account become Pearl sheets (new function).
5. Found pay and bills get Yes / No on the row.
6. Red stays on the destructive entry row only. The final button is the rose Primary naming the action.
Group 5b has 10 boards: G5b-Recurring, RecurringOne, Debts, DebtEdit, Rules, Rule, Learned, Categories, Merchants, Tags. They cover every list, detail, edit, empty, swipe, confirmation, removing and couldn't-remove state the app has. It's a restyle only, with no new function. Visual notes and copy cuts are in nG5b.
Not drawn, because the app has none: creating, renaming or merging a category, and a sorting rule that also moves earlier transactions. Only a recurring transfer moves all of them, with Undo.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-13 · Group 5b decisions and fixes; group 6, Onboarding and sign-in
**Status:** Awaiting product owner (group 6); group 5b approved by the product owner, design only
**Jira:** THL-114, THL-116, THL-118, THL-119, THL-120, THL-125, THL-127, THL-45, THL-198, THL-123, THL-295   **Figma:** none (Claude Design canvas "Pearl redesign", version 18)
Group 5b, settled by the product owner and recorded in nG5b:
- Category create, rename and merge wait for later.
- Saving a changed rule says inline "Also moves the 14 earlier Loblaws transactions to Shopping, and new ones from now on." with Save and "Only new ones", as group 1's Change category does. New function (G5b-Rule).
- Undo on "No longer recurring", "Rule deleted" and "Fitness hidden", all the one ink toast. New function.
Fixes:
- G5b-RecurringOne now opens at the top. Its third state is the page scrolled to the 9 so far and Stop.
- Toasts are short: "Now Into savings", "No longer recurring", "Now Shopping · 15 moved", "Rule deleted", "Fitness hidden", "Details saved".
- G5-Account's toast is now "Not in your budget now". Groups 1 and 2 already had short toasts.
- G5-Setup's label is now "Part 3 of 3 · Your money", as in the app.
Group 6 has 13 boards: G6-Welcome, Create, Code, SignIn, Forgot, FaceID, Plaid, Reading, Linked, PayBills, Saving, Allowance, Offline. Reused, not redrawn: G5-Setup (Your accounts), G5-Lock (the app lock) and group 1's Quick sort (the first sort).
New function, only if picked: a "Can't reach Pearl" screen at launch; an offline banner over Home; Yes / No on found pay in setup. Visual notes and copy cuts are in nG6. Recovery codes stay deferred.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-14 · Group 6 decisions; group 7, Pearl chat, trips and AI (last group)
**Status:** Awaiting product owner (group 7); group 6 approved by the product owner, design only
**Jira:** THL-117, THL-139, THL-213, THL-254, THL-122, THL-123, THL-226, THL-257, THL-263, THL-127, THL-165, THL-181, THL-232   **Figma:** none (Claude Design canvas "Pearl redesign", version 19)
Group 6, settled by the product owner and recorded in nG6:
- Build Can't reach Pearl and the offline banner (new function).
- Hide "Build your safety net" while Save is parked; G6-Allowance is updated.
- Keep "How much do you want to save?".
- The welcome line is "See what's yours to spend, and plan ahead."; G6-Welcome is updated.
- Keep "Not you? Use a different email" (new function).
- The also-move banners are one line: G5b-Rule "Also moves the 14 earlier ones."; G1-Change "Also moves the 6 earlier ones · Allowance +$46".
Group 7 has 10 boards: G7-Chat, Tell, TellMore, Confirm, Unavailable, TripAsk, Trip, TripCal, Detect, AutoSort. They use AP-Chat's Pearl tab layout, the composer well with the send arrow, and the keyboard rule.
Rules kept: one card per transaction, never grouped; a trip and a pattern are asked once; nothing changes before Yes or Set it. Your plan appears only as the chat card (Save stays parked).
New function, only if picked:
- Undo on what Pearl did in chat (plan set, trip made)
- a "New chat?" Pearl sheet
- "Leave it as is" in a trip's options; "Pay from a piggy bank" waits for Save
- "Were you in Montréal?" wording for trip questions
Visual notes and copy cuts are in nG7.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-15 · Redesign approved: ready to build (Save and Wins parked)
**Status:** Redesigned (approved by the product owner; ready to build in stages)
**Jira:** see REDESIGN-02 to -14   **Figma:** none (Claude Design canvas "Pearl redesign", version 20)
The product owner settled group 7, and the decisions are recorded in nG7:
1. Undo in chat after Pearl sets a plan or makes a trip (new function).
2. "Start a new chat?" as a Pearl sheet before clearing (new function).
3. Trip questions say "Were you in Montréal?".
4. Trip options add "Leave it as is". "Pay from a piggy bank" is hidden until Save returns; G7-Trip is updated.
5. No separate "Pearl sorted" notification for now.
Every approved section on the canvas is titled "Approved: ready to build": A+, Rollout groups 1, 2, 5, 5b, 6 and 7, and their boards. Group 3, Save, stays "parked: later stage", and Wins was never started. Board titles carry the screen codes and Jira tickets. Each section's note lists its visual changes, copy cuts, new function and decisions.
engBOT: send design questions in this log with the board name (for example G5b-Rule), and I'll answer here.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-16 · Stage 1 answers: camera off, the Pearl tab dot, first name only
**Status:** Redesigned (answers, no new boards)
**Jira:** THL-209, THL-104   **Figma:** none (canvas boards AP-PhotoSheet, AP-Profile, AP-Chat)
1. Camera off: show the ink toast "Camera is off for Pearl" with a "Settings" action that opens Pearl's page in iOS Settings, not the web. Hide Take photo on an iPhone without a camera. Choose photo uses PHPicker, which needs no permission, so it has no denied state.
2. Pearl tab dot: the 10 pt nacre dot is drawn into the LogoMark tab image, top right.
   - Its 1.5 pt ring is the tab bar's background colour.
   - Use two image variants, with and without the dot.
   - VoiceOver label: "Pearl, has a suggestion".
3. Profile:
   - Back is the 44 pt glass circle.
   - The header shows her first name (the server has no last name).
   - With a first name only, the initials are one letter in the same ring.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-17 · Twin coverage, Jira-led names, twins rethought not copied
**Status:** Redesigned (64 new boards; 18 of them Need product owner, the rest Approved: ready to build)
**Jira:** per board (every board title and phone caption carries its tickets)   **Figma:** archive read only (ohcxhB9hV25H6nANVw3lq4, Pearl app 751:6166); canvas "Pearl redesign" version 23
Twin coverage of every screen and state that is built and working in the app:
- The built list is the Pearl app canvas (the as-built record), reconciled with the Figma archive and ios/Pearl.
- There are 534 screen codes:
  - 282 had an A+ twin
  - 221 are drawn now, on 64 new boards
  - 18 are replaced (Plaid's or iOS's own screens, the floating Pearl button, old set-up steps)
  - 13 are parked (Save)
  - 0 are deferred
- 39 twins were rethought rather than copied, on 18 boards marked "Needs product owner".
- The full table (screen code, Jira, Figma frame name, A+ board · state, status, Copied / Rethought, note) is in twin-coverage.md, with a summary note nTwin on the canvas.
Naming:
- Every A+ board title now leads with its screen code and Jira tickets, with the old G-name as a [tag].
- Every phone carries a caption with its own code, name and tickets.
- Screenshots also exist as `<CODE>_<G-name>.png` next to the old names, which are kept.
New section "Group 2b · Joint accounts" (11 boards).
New boards by engBOT area:
- Theme/Home: AP-BankAlert, AP-SetupAgain, AP-Paycheque.
- Cash flow: G1-Rows, Months, FilterOpen, Results, Days, TxNote, TxSheets, MoneyIn, Add, NeedsMore, PearlSorted, QuickMore, QuickAsk, TxPage, PConfirm.
- Splits: G2-A* (13 boards), G2-B* (14 boards), G2-PLeave, and G2b-* (11 boards).
- Profile/onboarding: G5-AccountMore, G5-Extras, G6-PayEdit, G6-Over, G6-NewDevice.
- Chat/trips: G7-TripRename, G7-TripMore.
Boards marked "Needs product owner" are not to be built until they are picked.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-18 · Cash flow follow-ups: Paid with sheet, the one-transaction banner, the streak count
**Status:** Redesigned
**Jira:** THL-122, THL-231, THL-125, THL-254   **Figma:** none (canvas "Pearl redesign" version 24, board G1-PaidWith)
1. **T-62 · Paid with** (G1-PaidWith, new): a Pearl sheet replaces the stock iOS Menu on Add a transaction.
   - Radio rows show Cash, then each account with its face and last four digits; a joint account says "joint".
   - Tapping a row picks it and closes the sheet: no Done button.
   - Money in uses the same sheet, titled "Goes into".
   - The second state shows the form after picking TD Visa ••9021.
   - Status: Approved: ready to build (a restyle of the approved picker pattern).
2. **Change banner, one transaction:** "Also moves the earlier one" is right.
   - With the Allowance change: "Also moves the earlier one · Allowance +$12".
   - Two or more: "Also moves the 6 earlier ones · Allowance +$46".
   - None: no banner.
3. **The sorting streak, one rule for both** (DS SortStreak): lit dashes = sorted ÷ (sorted + to sort), rounded to twelfths.
   - "Sorted" counts both her answers and Pearl's own sorts, over the same window as the "to sort" count.
   - Home's card and Cash flow's mini streak show the same dashes.
   - Cash flow should count everything sorted in that window, not only today's answers. Home should add her own answers to Pearl's.
   - The count of Pearl's own sorts stays in words ("Pearl sorted 40"). VoiceOver reads "40 of 48 sorted".

### [designBOT → engBOT] 2026-11-18 · REDESIGN-19 · Product owner: piggy banks hidden, T-74 approved, Your plan parked
**Status:** Redesigned
**Jira:** THL-169, THL-229 (piggy banks), THL-127, THL-168 (Your plan), THL-125 (T-74)   **Figma:** none (canvas "Pearl redesign" version 25)
1. **"Pay from a piggy bank" is hidden until Save returns.**
   - Its row is gone from the transaction page on G1-TxSpend (T-03r and T-103) and from the page behind G1-Change. Trip options (G7-Trip) already had it hidden.
   - Any other piggy bank entry stays on the parked G3 boards only.
   - T-105 stays parked.
   - Build note: don't show the row while Save is parked.
2. **T-74, "3 paycheques in October", is a Worth a look good-news item.** AP-Paycheque is now "Approved: ready to build".
3. **Your plan is parked with Save.**
   - **Quick sort:** T-101 ("Is TD Savings where you save?") and T-102 ("Still paid by Northwind?") on G1-QuickAsk are parked.
   - **Needs a look:**
     - T-109 (the Your plan tab, on G1-PearlSorted) is parked.
     - The "Your plan · 1" chip is gone from every Needs a look header, so All reads 6: G1-MoneyIn, NeedsMore, PearlSorted and TxSheets.
   - **Chat:** the plan card on G7-Confirm (PC-12, Done, and "Okay, nothing changed") is parked. The "trip made, with Undo" state stays approved.
   - **Income and bills:** the "Your plan" row is gone from G5-Income, G5-IncomeEdit and G5-Extras. YP-09 is parked.
   - Parked states carry "Parked with Save" in their captions, and board titles list the parked codes.
- The coverage table is updated: 535 codes; 280 twin exists, 219 drawn now, 18 replaced, 18 parked, 40 rethought.
- The rethought boards are unchanged and still need the product owner.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-20 · The 19 rethought twins are approved; build list
**Status:** Redesigned (approved; ready to build)
**Jira:** per board   **Figma:** none (canvas "Pearl redesign" version 28)
- The product owner approved all 19 rethought twins. They are now "Approved: ready to build":
  - Home: AP-BankAlert, AP-SetupAgain
  - Cash flow: G1-Months, G1-PConfirm, G1-TxSheets
  - Splits: G2-AAddPeople, G2-ADeposit2, G2-APersonStates, G2-BIncome, G2-BShare
  - Joint accounts: G2b-Account, G2b-Combine, G2b-JointIn, G2b-Picker, G2b-Purchase, G2b-Whose
  - Profile and onboarding: G5-Extras, G6-NewDevice, G6-PayEdit
- Anything parked with Save inside them stays parked (the Your plan row on G5-Extras).
- Phone captions still say "Rethought".
- The coverage table and the canvas notes (nTwin, nG2b) are updated. T-74 is labelled a Worth a look good-news item.
- **The canvas now cuts board titles at 120 characters.** Titles read "code · name — first tickets … · [G-name] · status". The full ticket list stays in each phone's caption.
- **Build list:** twin-build-list.md lists 65 approved boards that the app doesn't have yet, grouped by engBOT area:
  - theme/Home 3, cash flow 16, splits 28, joint accounts 11, profile/onboarding 5, chat/trips 2
  - Each entry gives screen codes, tickets, states, the PNG and the most likely app file (found from the code references in ios/Pearl).
  - Not in the list: the "Proposed rethinks" boards (-r), which are not approved.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-21 · Proposed rethinks of approved boards (not for building yet)
**Status:** Needs product owner
**Jira:** same as each approved board   **Figma:** none (canvas "Pearl redesign" version 29, section "Proposed rethinks · Needs product owner")
New section with 8 proposal boards. Each -r board does the same job as its approved board: same screen codes, Jira tickets and size. The approved boards are unchanged, and they are what to build until the product owner picks a proposal.
- G1-WhatWasThis-r: Pearl's guess leads with one button, plus 4 likely tiles. Every other answer is behind "Something else…" on the same page, so the one-page rule holds.
- G1-Search-r: Filters show Transaction type and Month first; the rest is behind "More filters".
- G2-PB30-r: the likely purchases come first, with one button. Other purchases appear only behind search.
- G5-Accounts-r: one list, with the bank in each row's sub-line.
- G5b-Rule-r: the rule page leads with the category it picks; the picker opens only on Change.
- G6-PayBills-r: each list shows 3 rows and "See all", with the count and total in the label.
- G7-AutoSort-r: "Why Pearl sorted this" is one line and one button, "Undo this one"; Change it and Stop sit behind "More options".
- G7-Tell-r: after the first card, a small "n of 7" streak replaces her whole sentence.
Also fixed: G2-Many's first state is now labelled MP-03, because it shows the less-ticked state on MP-01's page. The coverage row for MP-01 is updated.

### [designBOT → engBOT] 2026-11-18 · REDESIGN-22 · Answers: Only new ones when nothing moves; tag totals
**Status:** Redesigned
**Jira:** THL-123, THL-226   **Figma:** none (canvas "Pearl redesign" version 30, G5b-Tags)
1. **CR-04, a rule edit:**
   - When no earlier transactions would move (N = 0), show only Save: no banner and no "Only new ones".
   - When N > 0, show the banner ("Also moves the earlier one" when N is 1, "Also moves the N earlier ones." when N is more), then Save and the quiet "Only new ones".
2. **CR-03, tag totals:** plum (money-out) with no minus, like a trip's total.
   - A total isn't a single transaction, so it carries no sign.
   - A net money-in total is green with "+".
   - G5b-Tags is updated and re-rendered.

### [designBOT → engBOT] 2026-11-19 · REDESIGN-23 · The 8 rethinks are approved; old boards superseded
**Status:** Redesigned (approved; ready to build)
**Jira:** same as each board   **Figma:** none (canvas "Pearl redesign" version 32)
- The product owner approved all 8 proposals. They are now "Approved: ready to build":
  - G1-WhatWasThis-r, G1-Search-r, G2-PB30-r, G5-Accounts-r
  - G5b-Rule-r, G6-PayBills-r, G7-AutoSort-r, G7-Tell-r
- Build the -r board, and change the existing screen to match it.
- **Superseded:** the old boards (G1-WhatWasThis, G1-Search, G2-PB30, G5-Accounts, G5b-Rule, G6-PayBills, G7-AutoSort, G7-Tell) are marked "SUPERSEDED by …-r" in their titles and phone captions. Per my role file I mark them superseded; the product owner clears them out.
- **G5-Accounts-r fix:** the Wealthsimple row's sub-line is now just the "Disconnected" pill, so nothing is cut off. The account name already names the bank.
- **Coverage table:** the codes on those boards now point to the -r boards, with a "Rethought (approved 2026-11-19)" summary; 64 rethought in all. The canvas notes are updated (nPR, tPR).
- **Build list:** twin-build-list.md now has 73 boards:
  - the 8 -r boards, each with "Replaces: <old board> (now SUPERSEDED)"
  - theme/Home 3, cash flow 18, splits 29, joint accounts 11, profile/onboarding 8, chat/trips 4

### [designBOT → engBOT] 2026-11-19 · REDESIGN-24 · Superseded boards deleted; the rethinks take their names
**Status:** Redesigned
**Jira:** same as each board   **Figma:** none (canvas "Pearl redesign" version 33)
- The product owner said "delete the superseded boards". The 8 old designs are gone from the canvas, with their phones and captions:
  - G1-WhatWasThis, G1-Search, G2-PB30, G5-Accounts
  - G5b-Rule, G6-PayBills, G7-AutoSort, G7-Tell
- Nothing else on the canvas was marked SUPERSEDED. The parked Save boards and the A, B and C direction rows stay.
- Each rethought design now carries the original board name and sits in the old board's place in its group section. The -r boards and the "Rethinks" section are removed.
- Titles keep the screen code and Jira tickets, plus "rethought 2026-11-19"; phone captions say "Rethought".
- **PNGs:** `<board>.png` (and its code-led copy) now shows the new design. `<board>-r.png` stays on disk for the engineers mid-build, with the same content.
- The coverage table, the canvas note (nTwin) and the build list now name the boards without "-r". The build list still has 73 boards; the 8 rethought ones say "change the existing screen to match this board".

### [designBOT → engBOT] 2026-11-21 · REFRESH-06 · Boards brought in line with what shipped 2026-11-20/21 (PRs #403–#416)
**Status:** Redesigned (as built; nothing new for engBOT to build)
**Jira:** THL-254, THL-213, THL-263, THL-231, THL-289, THL-291, THL-181, THL-301, THL-303, THL-305, THL-172, THL-282, THL-232, THL-122, THL-165, THL-123, THL-226   **Design:** canvas "Pearl redesign" (84 files republished, index sent for G1-Asks) and the Pearl Design System (Toast, `moved`)
The product owner asked that the design file reflect the UI changes shipped on 2026-11-20 and 21. Nothing was redesigned: every edit copies the Swift. Each board keeps its title, code, tickets and status.
1. **Toast ✕** (`PearlToast`): every toast on the canvas (37 boards, light and dark) has the ✕ at the far right, a 44 × 44 target after Undo; the Design System's Toast preview and README show it, with the accessibility-size layout (✕ beside the words, Undo under them). G5-AccountMore's empty Undo slot is gone.
2. **Quick sort: no toast, Undo on the card.** G1-QuickSort (T-95), G1-QuickAsk (AI-18y) and G7-TripAsk (TR-01 after Yes) lose their toast; "↶ Undo" (arrow.uturn.backward + Undo, `link`, Figtree Medium 14, 44 high) sits at the card's top right. Captions now say "Undo at the card". `qs.css` carries the look. T-101's "Parked with Save" marker is removed: the saver question is asked while Your plan is parked.
3. **Cash flow Select bar** (G1-Select T-77): a Cancel chip after Category and Mark as… on the first row. While there, the bar now matches the code's rows exactly: Make a trip is the rose chip on its own row and Confirm 1 is a plain chip on its own row (the board had them the other way round).
4. **Transaction detail:**
   - The Counts pill ("↓ Spending", "↑ Not counted", "⇄ Doesn't count", Income, Refund, Paid back) moved from the top right to under the transaction's lines, 10 down, before the joint or pending pill, on 42 boards (every detail page on Cash flow; G1-TxNote's T-40b joint pill moved with it).
   - Joint charge (G2b-Purchase S-01jr, S-01jr2; G2b-SplitCard; G2b-SplitPart): hero pill "Joint with Sam · 50%" (or "· yours unless you say"), the share bar titled "Half each" with "You $50.00" / "Sam $50.00" under it, first names only.
   - "Always for this merchant" on G1-Change, G1-TxPage, G1-TxSheets, G1-TxSpend and G1-WhatWasThis. Income's "Always for <payer>" (G1-TxMore, G1-MoneyIn) is unchanged, as in the code.
   - "Your share $30.00" as a pill (person.2 in `money-out`) with "of $150.00" beside it under the category row, aligned with the category text, on 25 split-purchase boards (every RC-02 header with "split ·" and "your share").
   - "Put it back" at the foot of a left-out transaction is a `.btn2` (G1-TxRefund T-81).
   - "Between your accounts ›" (How it counts) now sits above the legs card on the joint-account transfer page (TP-01, TP-02 behind its sheet) and the own-accounts page (TP-05), G2b-JointIn and G2b-JointIn2; G1-TxMore's own row gained the chevron the code draws.
   - Money moved between her own accounts is `moved` (light #8B879E, dark #8E8BA8) in rows and heroes, its ⇄ smaller than the figures (12 pt semibold in rows and the 44 ring, 13 in the 56 ring): AP-CashFlow, G1-Months, G1-PearlSorted, G1-Rows, G1-QuickAsk, G1-TxMore, G1-TxSheets, G2b-JointIn, G2b-JointIn2, G5b-Recurring, G5b-RecurringOne. The token is in the Design System (tokens.css, tokens.json, the README's Money line) and on the canvas in dirA.css.
5. **Paid back:** "Not here? Search other purchases" is a `.btn2` (G2-PB30); PB-30 for a known person reads "LIKELY · SAM" with Change on the right (G2-PB30); PB-11's third tile is "Other · Work, insurance or anyone else" (G2-WhoPaid).
6. **Who sent this?** (G1-Asks, now 8 phones, 3440 wide; G1-Recurring, G1-Pay and G1-TxSpend moved right to make room): T-14 shows "Recent and contacts" in one card, contact rows saying "In your contacts"; new T-14c, a typed name nobody has ("Denise": Contacts, then "+ Add “Denise” as a new name" as one row); new T-14d, "Contacts are off for Pearl. Turn on" under Recent.
7. **Needs a look** (G1-NeedsALook T-83): the "Is TD Savings where you save?" row, drawn as G1-PearlSorted draws it (⇄ ring, the question in the sub-line, `moved` amount), with its "Your plan · 1" chip, which is how `ReviewView` groups `.check` even while Your plan is parked.
**Not reflected, and why:**
- The "Whose pay" row with its person.2 icon (T-40b) isn't drawn anywhere: G1-TxNote's T-40b phone shows the guess card instead. Nothing to update.
- A deposit that paid back one purchase showing PAYS BACK once, and a deposit in parts without "This is my regular pay": no board ever drew the "Part of a $58.00 deposit" section or that switch, and G2-Deposit and G2-BPayback already had the one Options card with circled icons on every row. Nothing to change.
- PB-11 being skipped from a work expense's Find what paid it back (Many purchases opens with the purchase ticked) is a flow, not a screen; G2-Many (MP-03) already shows the ticked list. Noted here only.
- The Who sent this? step before PB-30 (`WhoSentNamePage`) keeps RECENT and CONTACTS as two sections with "Search to find anyone in your contacts." under a capped list; it shares T-14's code and board, so the board follows the Needs a look sheet (`AnswerSheet`'s one card). engBOT: say if you want it drawn apart.
- Parked Save boards (G3-*) were left alone: G3-Money's counts pill stays top right and G3-Piggy/G3-Plan's toasts have no ✕.
- Statuses were not touched: the Quick sort boards still read "Approved: ready to build" although their Undo is built.

### [designBOT → engBOT] 2026-11-22 · REFRESH-07 · Boards brought in line with PRs #417 and #419
**Status:** Redesigned (as built; nothing new for engBOT to build)
**Jira:** THL-127, THL-292, THL-181, THL-305, THL-232, THL-296, THL-172   **Design:** canvas "Pearl redesign" › Cash flow › G1-TxMore, G1-TxNote, G1-Recurring
1. **Income's Always under the category** (#417): G1-TxMore (T-37, Regular pay) moves the switch out of Options into the category card, under the "Salary" row, labelled "Always for this merchant". G1-MoneyIn's "Always for e-Transfer from Alex" is unchanged: that is What was this?'s own switch (`AnswerSheet` line 663), which #417 didn't touch.
2. **Who put this in?** (#419): G1-Recurring's PQ-01 (both phones, captions and title) reads "Who put this in?"; its tiles are "My pay · Counts as your income" (briefcase), "My transfer · Not income" (arrows), "Alex · Not in your numbers", "Both of us · Your 50% counts". The why-card keeps "Every 2 weeks since September" (several deposits); the one-deposit sentence "… put $200.00 into your joint account." isn't drawn on any board. G1-TxNote's T-40b joint row reads "Who put it in" with its value "Sam's · not yours".
**Not reflected, and why:**
- G6-PayBills O-10f shows a joint account with one other person (Sam), so its last row stays "Both of us"; "Everyone" only appears with several people, and no board draws such an account on O-10f or PQ-01.
- No board draws the detail page's joint row for a "both" or "me" answer, so the value "Both of yours · your share 50% counts" isn't shown anywhere; the code's wording is unchanged by #419.

### [designBOT → engBOT] 2026-11-22 · REFRESH-08 · Boards brought in line with PR #422 (Link transfers; contacts on Who was it with?)
**Status:** Redesigned (as built; nothing new for engBOT to build)
**Jira:** THL-292, THL-181, THL-289, THL-291, THL-301, THL-303   **Design:** canvas "Pearl redesign" › Cash flow › G1-TxSheets (TF-02, TF-02l, TF-02e), G1-TxMore (TF-01), G2-WhoWith (S-02 v2)
1. **Link transfers** (`LinkTransfersSheet`): G1-TxSheets gains three phone pairs over the TF-01 transfer page (the board is now 6020 wide; G1-MoneyIn moved right to make room):
   - TF-02 · Link transfers: title bar, the transaction as the sheet's who (⇄ ring, "To Tangerine Savings", "$500.00" in `moved`, "TD Chequing ••4417 · Thu, Nov 12"), the footnote "Tick the other legs of this move. Linked, they count as one transfer: not spending, not income.", the label SAME AMOUNT, WITHIN A WEEK, a card of legs (merchant over "account · date", the amount on the right in `money-in` when it came in, a tick box; one leg says "· in another link"), and Link.
   - TF-02l · Linked transfers: the legs come ticked, Save, then Unlink as a secondary button; behind it the page's Options row reads "Linked transfers" with the accounts as its second line.
   - TF-02e · the empty card "Nothing else for $500.00 within a week." with Link disabled.
2. **Options row** on the transfer page (G1-TxMore TF-01): "Link to another transfer" with the link icon, under "This isn't a transfer".
3. **Who was it with?** (G2-WhoWith S-02 v2, the typing state "Pri"): under RECENT, a CONTACTS card of matching contacts in the same row style with tick boxes, then a card with the "+ Add “Pri” as a new name" row.
**Not reflected, and why:**
- The Options row on a Not sorted yet / Saved / Other / money-in page: no board draws those pages' Options with this row; TF-01 covers the look, and the row is the same everywhere.
- A paired linked row where "Linked transfers" replaces "This isn't a transfer": TF-02l's page shows the "Linked transfers" row on the paired TF-01 page, which is that case.
- "Contacts are off for Pearl. Turn on" on Who was it with?: not drawn (one state per phone; it is the same line as G1-Asks T-14d).
