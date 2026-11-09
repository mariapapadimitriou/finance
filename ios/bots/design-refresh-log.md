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
