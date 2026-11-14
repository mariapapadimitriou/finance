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
