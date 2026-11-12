# testingBOT · test log

testingBOT uses the Pearl iPhone app on the iOS Simulator with real taps, the
way a person would, and writes down what it found: bugs, differences from
Figma and Jira, confusing moments and suggestions. It doesn't fix code or edit
Figma.

- **How it runs:** `python3 ios/tools/run_journeys.py [journey…]` runs the
  journeys in `ios/PearlUITests/PersonJourneysUITests.swift` against a
  throwaway local server with the demo ledger (DATABASE_URL removed, temp DB,
  the 0.3 s slow proxy, its own simulator). Each step saves a screenshot and
  the accessibility tree.
- **Who replies:** engBOT answers bugs (`[engBOT → testingBOT] … · TEST-NN ·
  Fixed in …` or `Won't fix`), designBOT answers look and words
  (`[designBOT → testingBOT] … · TEST-NN · …`), and findings marked **both**
  need the two of them, and sometimes the product owner, to agree.
  testingBOT re-tests every fix and logs `Fixed` or `Still broken`.
- **Rules:** append only; never rewrite an entry. Findings are numbered
  TEST-01, TEST-02, … across rounds.

Format of a finding:

```
### [testingBOT → engBOT | designBOT | both] <timestamp> · TEST-NN · <short title>
**Kind:** Bug | Discrepancy | Confusion | Suggestion   **Severity:** Blocker | Major | Minor
**Where:** screen code and name   **Figma:** node-id   **Jira:** THL-… (quote it)   **Code:** file:line if known
**Steps:** what you did, numbered
**Saw:** what happened (screenshot path)
**Expected:** what should have happened, and why
**Advice:** what you'd like to see instead
```

Screenshot paths below are relative to the round's folder,
`/private/tmp/claude-501/-Users-mariapapadimitriou-GitHub-finance/47dab3d8-05be-4db9-b3fc-84667327b935/scratchpad/testing-run/`
(`shots/` is the first pass, `shots2/` and `shots3/` the re-runs). Each `.png`
has a `.txt` beside it with the accessibility tree at that moment.

---

### [testingBOT] 2026-11-10 · Round 1 start
- **Build:** worktree on branch `test/testingbot-round-1`, made from main at
  4a4ae84 (SPLIT-01 to SPLIT-29, REFRESH-03, REFRESH-05, #321). Debug build,
  Xcode 26.6.
- **Simulator:** iPhone 16 Pro, iOS 26.5, its own device ("Pearl journeys").
  Light and dark through the app's own Appearance setting
  (`-pearl.appearance`), Dynamic Type `large` and `accessibility-extra-large`.
- **Data:** `sample_data.generate.load_demo` (1,070 card rows over 14 months)
  plus, added by the runner: a TD chequing account with two e-Transfers in
  (Priya Shah $42.50, Sam Lee $30.00), a Scotiabank Visa with a $100.00
  Costco purchase (set to joint in the app), a $127.50 Gusto dinner, and six
  low-confidence guesses for Quick sort. Take-home pay $5,200, saving $900.
- **Covered:** Home (Allowance orb, "to sort", the counts), Quick sort (Yes,
  Undo, Skip, a category from the card, to the end), Needs a look, a
  transaction's category, Leave out, Split evenly, typed amounts that don't
  add up, "I had some too" off, Not sure yet → link a payback → Settle up →
  That's everything → Reopen, linking a payback and unlinking with Undo,
  Mark paid back with cash, the ••• person options, Change share, a joint
  card with Shared with and Split my part, Owed to you; light and dark; an
  accessibility text size; `performAccessibilityAudit()` on six screens.
- **Compared against:** Figma H-00r `1073:146`, T-01r `1074:356`, S-04r v2
  `1090:1743`, S-40a `1090:1846`, S-03j `1105:5893`, S-45c `1116:7844`, and the
  section lists of `1088:1695`, `1102:4466`, `1112:6476`; Jira THL-291, THL-289,
  THL-181, THL-172, THL-301; the house rules in engBOT.md and designBOT.md.

---

### [testingBOT → engBOT] 2026-11-10 · TEST-01 · Quick sort's card is unreadable in dark mode
**Kind:** Bug   **Severity:** Blocker
**Where:** T-93 Quick sort, and T-83 Needs a look's chips   **Figma:** T-93r dark `1077:1464`, T-83r dark `1076:1268`   **Jira:** THL-291 "Light and dark match the frames"   **Code:** `ios/Pearl/Views/Review/QuickSortView.swift:706-708` (CardFace), `:426` (Skip), `ios/Pearl/Views/Review/ReviewView.swift:237` (chip)
**Steps:**
1. Appearance Dark. Home → Review one by one → the Quick sort card.
**Saw:** the card keeps its light pink-to-mint gradient, but the text on it is `Pearl.ink`, which is near-white in dark. The merchant ("Corner"), the date and account line and the question ("Other?") are white on white; only the red amount and the overline can be read. The Skip button is a white circle with a white icon. On Needs a look the selected chip "All · 6" is a white capsule with white text. (`shots/testLookThroughNeedsALook-07-dark-quick-sort.png`, `shots/testLookThroughNeedsALook-05-dark-needs-a-look.png`)
**Expected:** in dark mode a person can read what they're being asked before they tap Yes. Quick sort is the main way to sort.
**Advice:** take the card face, the Skip circle and the selected chip from the dark tokens in the dark frames (or give the card fixed ink text if it stays light). A dark-mode run of `testLookThroughNeedsALook` would catch it again.

### [testingBOT → engBOT] 2026-11-10 · TEST-02 · Settle up › Type amounts opens "Who was it with?" on the leftover amount
**Kind:** Bug   **Severity:** Major
**Where:** S-04u → S-45a How to settle? → Type amounts   **Figma:** S-45c `1116:7844`   **Jira:** THL-291 (split methods)   **Code:** `ios/Pearl/Views/Transactions/TransactionDetailView.swift:538-543` opens `SplitSheet(… settling: true)` without `with:` names, so `SplitFlow.swift` starts at step 0
**Steps:**
1. Gusto $127.50 → Split with others → Priya, Sam → Not sure → Save split.
2. Priya's ••• → Mark paid back → Bank or e-Transfer → her $42.50 → Link.
3. Settle up → Type amounts.
**Saw:** the sheet is S-02 "Who was it with?" with Priya and Sam ticked, the "I had some too" card and Next, and the header says Gusto **−$85.00**, the part still counting as hers, not the purchase. (`shots/testSplitNotSureYetThenSettleUp-13-light-settle-type-amounts.png`)
**Expected:** S-45c: "SETTLE UP · TYPE AMOUNTS", the whole purchase (−$100.00 in the frame), the method segments, "I had some too", each person's row with what they've paid so far ("Paid $20.00 so far · owes $13.33 after"), and Settle up.
**Advice:** open settling at How to split with the split's people, and show the purchase's full amount in the header. She already said who; asking again reads as if the split was lost.

### [testingBOT → both] 2026-11-10 · TEST-03 · A split counts only your share straight away, before anyone pays
**Kind:** Discrepancy   **Severity:** Major
**Where:** T-03 transaction page after S-03, Home's Allowance   **Figma:** S-04r v2 `1090:1743` (hero −$150.00, "Your share $30.00 · Wed, Nov 11")   **Jira:** THL-291 Rules: "Payback rule unchanged: the full purchase counts until paid back; a payback is never income." THL-289: "if you pay for someone, the full amount counts as your spending until they pay you back. Their share then comes off the purchase's category."
**Steps:**
1. Gusto $127.50 → split by amounts: Priya $42.50, Sam $30.00, Jo $15.00 (you $40.00) → Save. Nobody has paid.
2. Same on the server: Nopa $59.33 split evenly 3 ways.
**Saw:** the page's hero says **−$40.00** with no "of $127.50" anywhere above the fold (`shots2/testFriendsPayBackForDinner-03-light-split-card.png`). On the server, splitting Nopa moved Allowance from $15,321.08 to $15,360.62 (+$39.54, Priya's and Sam's shares) before any payback; the transaction's `amount` becomes 19.79.
**Expected:** per THL-291/289, the $127.50 counts until Priya, Sam and Jo pay; each payback then comes off. The S-04r v2 hero shows the whole purchase and puts "Your share" under it.
**Advice:** this is a rule question, so it needs a decision before code: either the Jira rule stands (count the whole purchase until paid back, and the hero shows −$127.50 with "Your share $40.00") or the rule changed to "your share counts at once" and THL-291/289 and the frames say so. Either way, show the full purchase on the page so a person can recognise their card statement.

### [testingBOT → engBOT] 2026-11-10 · TEST-04 · Home has no "Sort now"; it still has "Review one by one"
**Kind:** Discrepancy   **Severity:** Major
**Where:** H-00r Home, the "to sort" card   **Figma:** H-00r `1073:146`   **Jira:** THL-125 (one primary action), THL-254   **Code:** `ios/Pearl/Views/Home/HomeView.swift:137-155` (NeedsALookCard)
**Steps:**
1. Open Pearl with 6 to sort.
**Saw:** "6 to sort / Pearl sorted 183 by itself. / Review one by one ›", which opens Needs a look; Quick sort is one more tap. (`shots2/testSortWhatPearlGuessedFromHome-01-light-home.png`)
**Expected:** product owner decision 2 on REFRESH-00 (design-refresh-log.md, 2026-11-09): "Home 'Sort now' opens Quick sort directly; 'See the list' opens Needs a look: **Approved**", and REFRESH-01 lists H-00r as "Approved — build". H-00r has the card icon, "About a minute", the progress bar, a filled **Sort now** and "See the list".
**Advice:** build H-00r's card. The number already agrees with the server (6 → 3 after sorting, and the Cash flow badge with it), so only the card changes.

### [testingBOT → engBOT] 2026-11-10 · TEST-05 · Spending is still red, and Cash flow's summary is the old Spent / Came in / Over
**Kind:** Discrepancy   **Severity:** Major
**Where:** T-01r Cash flow, T-03r transaction page, Quick sort card, split sheets   **Figma:** T-01r `1074:356`, T-03r `1074:670`   **Jira:** THL-122, THL-123
**Steps:**
1. Open Cash flow, a transaction, Quick sort.
**Saw:** every spending amount is red (Starbucks −$6.30, Costco −$100.00, the Quick sort card's −$18.40, the split sheets' headers). The November card says Spent $1,979 / Came in $0 / **Over $1,979** in red, which, with a $15,194 Allowance on Home, reads as an alarm. (`shots/testLookAround-01-light-cash-flow.png`, `shots/testLookAround-03-light-costco-detail.png`)
**Expected:** decision 1 on REFRESH-00, "Spending in ink, red only for 'over': **Approved**", and REFRESH-01's "Approved — build: H-00r (… plus ink spending), T-01r and T-03r". T-01r leads with Leftover, Spent / Saved / Leftover under a bar, "Came in" on the right, and "8 need a look · Sort".
**Advice:** build the ink colour swap first (it touches every list and calms them); then T-01r's summary. Until then "Over" in red next to a big Allowance is the most confusing number in the app.

### [testingBOT → both] 2026-11-10 · TEST-06 · Stock iOS alerts and action sheets are still in the app (house rule)
**Kind:** Discrepancy   **Severity:** Major
**Where:** Cash flow › Select › Leave out (seen with a tap), and 13 more in code   **Jira:** house rule: "No stock iOS components for menus, option pages or confirmations (no action sheets, `.confirmationDialog` or `.alert`)"
**Steps:**
1. Cash flow → Select → Spotify → Leave out.
**Saw:** a stock `.alert` "Leave out 1 transaction?" with a text field, Cancel and Leave out (`shots/testChangeACategoryAndLeaveOneOut-07-light-leave-out-confirm.png`). The others, from the code:
   - `Views/Transactions/TransactionsView.swift:173` Leave out (above)
   - `Views/Transactions/TransactionDetailView.swift:1755` Delete transaction (`.confirmationDialog`)
   - `Views/Transactions/PartsFlow.swift:294` "Leave without saving?" (S-24x)
   - `Views/Transactions/CalendarView.swift:187` calendar band action
   - `Views/Profile/ProfileView.swift:134` Sign out
   - `Views/Profile/SettingsViews.swift:195, 204, 215, 461` remove device, new recovery codes, sign out of other devices, Reset Pearl
   - `Views/Profile/CategoriesRulesView.swift:133, 140` remove a rule, take a tag off
   - `Views/Profile/AccountsViews.swift:644, 1053` Nickname, Name (alerts with a text field)
   - `Views/Profile/IncomeBillsView.swift:81` "Are your e-Transfers to … your rent?"
   - `Views/Profile/PrivacyViews.swift:142` Turn off AI sorting
**Expected:** each is a Pearl sheet from the Pearl Design System (Bottom sheet / Alert components), as S-08r and S-03fr are.
**Advice:** designBOT: frames for these confirmations, starting with the three in Cash flow (Leave out, Delete, Leave without saving?). engBOT: swap them once picked. Recovery codes stay deferred.

### [testingBOT → engBOT] 2026-11-10 · TEST-07 · Leave out without a reason does nothing, and says nothing
**Kind:** Bug   **Severity:** Major
**Where:** Cash flow › Select › Leave out   **Code:** `ios/Pearl/Views/Transactions/TransactionsView.swift:748-754`
**Steps:**
1. Cash flow → Select → Spotify → Leave out → leave the "Why?" field empty → Leave out.
**Saw:** the alert closes, Spotify is still selected and still in the list, nothing is left out (the server's `excluded` stays null 4 s later), and no message appears where she's looking. (`shots2/testChangeACategoryAndLeaveOneOut-08-light-after-leave-out.png`; same in the first pass)
**Expected:** either the reason is optional, or the button is off until she types one and the sheet says why. The code sets "Say why, so you can tell later." but it isn't on screen.
**Advice:** with the Pearl sheet from TEST-06, keep Leave out off until there's a reason (or make it optional), and show the line inside the sheet.

### [testingBOT → both] 2026-11-10 · TEST-08 · "I had some too" can't be changed on How to split, and there's no way back to "Who was it with?"
**Kind:** Discrepancy   **Severity:** Major
**Where:** S-03 How to split, S-03j Split my part   **Figma:** S-03j `1105:5893` (the "I had some too" toggle under the people), S-45c `1116:7844`   **Jira:** THL-291: "With 'I had some too' off, $85 split as Priya $30 / Sam $20 blocks Save with '$35.00 left to assign'"   **Code:** `ios/Pearl/Views/Transactions/SplitFlow.swift` `withMeCard` is shown on S-02 always but on S-03 only `if settling`
**Steps:**
1. Gusto → Split with others → Priya, Sam → Next → Amounts → Priya 100, Sam 50.
2. Look for "I had some too" to turn it off and see the "$x left to assign" rule.
**Saw:** "That's $22.50 too much" and Save off, which is right (`shots/testSplitWithAmountsThatDontAddUp-03-light-too-much.png`). But there's no "I had some too" on this page, and the sheet has only ✕, no Back: to change it she has to close and start the split again. Turned off on S-02, it's gone from S-03 too, so "it was all for them" can't be undone there (`shots/testSplitSomethingThatWasAllForThem-02-light-how-to-split-all-for-them.png`).
**Expected:** S-03j and S-45c show "I had some too" on the amounts page, where its effect ("stays yours" vs "left to assign") is.
**Advice:** show the toggle on S-03 under the people (as S-03j), or give S-03 a Back to S-02. Small: S-03j has no "Not sure" segment on Split my part, but the app shows one; designBOT to say which is right.

### [testingBOT → both] 2026-11-10 · TEST-09 · The floating Back button sits on top of the page once it scrolls
**Kind:** Bug   **Severity:** Minor
**Where:** T-03 transaction page with a split (S-04r, S-04u, S-04j)   **Figma:** S-04r v2 `1090:1743`
**Steps:**
1. Open a split transaction and scroll down to the people.
**Saw:** the page scrolls under the status bar with no bar behind it; the round Back button covers the start of "Split with 2 · Not sure yet" ("…it with 2"), "Your part, split 3 ways" ("…r part") and Priya's initials, and the heading sits under the clock. (`shots/testSplitNotSureYetThenSettleUp-10-light-card-after-link.png`, `shots2/testSplitMyPartOfAJointPurchase-17-light-joint-split-card.png`, `shots2/testSplitADinnerEvenlyWithTwoFriends-05-light-split-card.png`)
**Expected:** headings never sit under the Back button or the clock.
**Advice:** a glass top bar (or fade) behind Back once content scrolls under it, as the tab bar does at the bottom.

### [testingBOT → engBOT] 2026-11-10 · TEST-10 · Shop names are cut to "Unknown", "Corner", "Blue"
**Kind:** Bug   **Severity:** Minor
**Where:** every list (Needs a look, Quick sort, Cash flow)   **Jira:** THL-122   **Code:** `finance/models.py` `normalize_merchant` / `_strip_location_tail` (the city + province pattern)
**Steps:**
1. Import card rows `SP * NORTHSHOP CA`, `SQ *CORNER STORE 22`, `SQ *BLUE BOTTLE ON` (Shopify and Square descriptors).
**Saw:** "Unknown", "Corner", "Blue": the shop's last word is read as a city and the two letters after it as a province. Quick sort asks "Unknown · −$89.00 · Groceries?" (`shots2/testSortWhatPearlGuessedFromHome-10-light-card-shows-choice.png`). `SP NORTHSHOP CA` without the asterisk gives "Northshop".
**Expected:** "Northshop", "Corner Store", "Blue Bottle". A person can't answer a card about "Unknown".
**Advice:** after a processor prefix (`SP *`, `SQ *`, `TST*`), don't strip a one-word "city" that is the whole name left; and never return "Unknown" when the descriptor had a name. Add these three to the merchant tests.

### [testingBOT → designBOT] 2026-11-10 · TEST-11 · Lines that say nothing: "The $0.00 goes back to your share", "Sam · Done"
**Kind:** Confusion   **Severity:** Minor
**Where:** S-40u2 Person options (Not sure yet, nothing paid); S-46a That's everything?   **Figma:** S-40u2 `1114:7949`, S-46a `1117:8058`   **Code:** `ios/Pearl/Views/Transactions/SplitMenus.swift:563-566`
**Steps:**
1. Not sure yet split with Priya and Sam → Priya's •••.
2. Later, That's everything.
**Saw:** "Remove Priya · The $0.00 goes back to your share" (`shots/testSplitNotSureYetThenSettleUp-05-light-S-40u2-options.png`). On That's everything?, Sam's row reads "Sam · Won't show as owing · **Done**", and "Done" on the right looks like a button (`shots/testSplitNotSureYetThenSettleUp-14-light-thats-everything-confirm.png`).
**Expected:** on a Not sure yet split nobody has a share, so there's nothing to give back; and a status shouldn't look like an action.
**Advice:** no subtitle on Remove when nothing is owed or paid; on S-46a, say what changes for Sam in the row ("Won't show as owing") and drop "Done" or make it a muted "—".

### [testingBOT → designBOT] 2026-11-10 · TEST-12 · Pearl's guess is "Other?", with Yes as the main answer
**Kind:** Confusion   **Severity:** Minor
**Where:** T-93 Quick sort card, T-83 Needs a look chips   **Jira:** THL-254, THL-213
**Steps:**
1. Quick sort with purchases Pearl couldn't place.
**Saw:** "PEARL'S GUESS · Corner · −$18.40 · Other?" with a big Yes; Needs a look shows the chip "Other?" on four rows. Tapping Yes files it as Other, which isn't sorting it. (`shots/testSortWhatPearlGuessedFromHome-03-light-quick-sort-first-card.png`)
**Expected:** a guess worth a Yes is a real category. When the best Pearl has is "Other", the card is a question ("What was this?") with the category tiles one tap away.
**Advice:** treat an "Other" guess as no guess: NEEDS A LOOK, "What was it?", Answer instead of Yes.

### [testingBOT → engBOT] 2026-11-10 · TEST-13 · Small inconsistencies in names and amounts
**Kind:** Bug   **Severity:** Minor
**Where:** S-06rb Which payment was it?; AM-08 account page   **Figma:** S-06rb `1091:2219`
**Steps:**
1. Priya's ••• → Mark paid back → Bank or e-Transfer.
2. Profile → Accounts → Scotiabank Visa, then turn Joint account on.
**Saw:**
   - The suggested payment is titled "E-transfer From Priya Shah · Nov 9" with no account line, while the one under OTHER MONEY IN reads "Sam Lee · Nov 8 · TD Chequing ••2210" (`shots/testSplitNotSureYetThenSettleUp-07-light-which-payment.png`). Cash flow already calls it "Priya Shah".
   - The card's page shows "—" and "Owing · ••8830 · Manual" before, and "$0.00 · Credit card · Joint" after Joint is on, for a card with $164.20 on it (`shots/testSplitMyPartOfAJointPurchase-04-light-joint-on.png`, `shots2/testSplitMyPartOfAJointPurchase-09-light-shared-with-alex.png`).
**Expected:** the sender's name the same everywhere (THL-122/200), and one way to show "no balance".
**Advice:** use the e-Transfer's person name and account line in the suggestion row; show "—" (or no hero) when a card has no balance, before and after Joint.

### [testingBOT → both] 2026-11-10 · TEST-14 · Accessibility audit: contrast, small tap areas, the tab badge
**Kind:** Bug   **Severity:** Minor
**Where:** Home, Cash flow, T-03, S-03, S-04r, S-40a   **Jira:** designBOT rules: "Dynamic Type, VoiceOver labels, 44pt tap targets, light and dark"
**Steps:**
1. `testAccessibilityAuditOnTheMainScreens` (light, default text size).
**Saw:** (`run2.log`, lines starting `JOURNEY note: AUDIT`)
   - Contrast failed on the grey text over the iridescent background: "left in November", "TUESDAY, NOVEMBER 10", row captions ("Coffee · Today"), "OPTIONS", "DETAILS", "Add a note", "40 transactions", "Select", the people's "Owes you", and the S-40a rows on the sheet.
   - Hit area too small: "Review one by one", Cash flow's "Calendar" segment, "Edit split", "See everyone who owes you".
   - Uppercase overlines (dates, OPTIONS, DETAILS) and the initials circles don't grow with Dynamic Type.
   - The Cash flow tab's badge (3, 5, 6) isn't in its accessibility value (empty), so VoiceOver doesn't hear the count.
**Expected:** the audit passes on the screens Round 1 uses most.
**Advice:** designBOT: check `color/text/muted` on the lightest parts of the iridescent fill, and the overline style. engBOT: 44 pt frames on the text buttons; `.accessibilityValue` with the count on the tab.

### [testingBOT → both] 2026-11-10 · TEST-15 · "Let Jo's $15.00 go?" says the Allowance doesn't change, but it goes down
**Kind:** Bug   **Severity:** Major
**Where:** S-08ra Let it go   **Figma:** S-08ra `1091:2527`   **Jira:** THL-291: "Let the rest go moves their remaining share to the user's spending"
**Steps:**
1. Gusto $127.50 split by amounts (Priya $42.50, Sam $30.00, Jo $15.00, you $40.00); Priya and Sam paid.
2. Jo's ••• → Let it go.
**Saw:** the sheet says "Jo won't owe you anymore. The $15.00 becomes your spending in Other." and, in an info note, "**Your Allowance doesn't change.**" After Let $15.00 go, the page's hero goes from −$40.00 to −$55.00 (`shots3/testFriendsPayBackForDinner-16-light-let-jo-go-confirm.png`, `shots3/testFriendsPayBackForDinner-18-light-jo-back.png`). Checked on the server with the same call the app makes (`POST /api/transactions/<Nopa>/split/let-go` for Priya's $19.77): Allowance went from $15,360.62 to $15,340.85, down $19.77. So the note is wrong: because a split already counts only your share (TEST-03), letting a share go lowers the Allowance by that share.
**Expected:** the note tells the truth. Under the THL-291 rule (whole purchase counts until paid back) "doesn't change" would be right; under the app's current counting it's wrong.
**Advice:** settle TEST-03 first, then make this note follow from the server's answer (as S-12 v2's WHAT CHANGES does) instead of fixed words. Undo let it go worked (back to −$40.00, "Owes you").

### [testingBOT → engBOT] 2026-11-10 · TEST-16 · On Amounts the number pad can't be closed, and it hides what's wrong
**Kind:** Bug   **Severity:** Minor
**Where:** S-03 How to split › Amounts, S-03re Change share   **Figma:** S-03re `1092:2360`, S-03b v2
**Steps:**
1. Gusto → split with Priya and Sam → Amounts → Priya 40, Sam 30.
2. Sam's ••• → Change Sam's share → 35.
**Saw:** the decimal pad has no Done, and tapping the sheet's title doesn't close it. With it up, Save sits on top of "Split the rest evenly" (only its top edge shows), and on Change Sam's share the "too much" line is hidden, so Save is just off with no reason on screen. The You, Priya and Sam fields are all outlined in red while the split is fine ("$57.50 left · stays yours"), and You's field shows "$0.00" next to "Your share $57.50". (`shots3/testSplitWithAmountsThatDontAddUp-04-light-short,-stays-yours.png`, `shots3/testChangeAShareAndRemoveSomeone-05-light-share-changed.png`)
**Expected:** S-03re keeps the status line ("$10.00 left · stays yours") and the bar right above Save, the outline only on the field being edited, and each row's status ("Owes you", "Paid back $30.00").
**Advice:** a keyboard toolbar with Done (or dismiss on scroll), keep the status line and "Split the rest evenly" above Save while the pad is up, red only when it's over, and You's field showing the amount it will save.

### [testingBOT → designBOT] 2026-11-10 · TEST-17 · At the largest text size the merchant's initials turn into "…"
**Kind:** Discrepancy   **Severity:** Minor
**Where:** S-03 How to split header at accessibility-extra-large
**Steps:**
1. Dynamic Type accessibility-extra-large. Nopa → Split with others → Priya, Sam → Next.
**Saw:** the circle beside the merchant shows "…" instead of "NR", and the name is cut to "Nopa Restaur…". The rest holds up well: the method row becomes "How to split · Evenly ›" (S-03u), S-40a's rows wrap and scroll, Home's orb grows without clipping. (`shots3/testSplitADinnerAtTheLargestTextSize-06-light-S-03u-large-text.png`, `shots3/testSplitADinnerAtTheLargestTextSize-09-light-S-40a-large-text.png`, `shots3/testSplitADinnerAtTheLargestTextSize-01-light-home-large-text.png`)
**Expected:** initials never truncate (they're two letters), and the name wraps to two lines before it's cut.
**Advice:** fix the initials' size at AX sizes (or hide the circle) and let the header name wrap.

---

### [testingBOT] 2026-11-10 · What worked well (please keep)
- **The numbers agree.** Home's Allowance matched the server to the dollar on every launch; "6 to sort" went to 3 after Quick sort, and the Cash flow badge and Needs a look's chips moved with it.
- **Quick sort's Undo** puts the same card back at once, and the toast stays until the next answer. Choosing a category from the card ("YOUR CHOICE · Groceries?") and then Yes stays in the deck, as THL-254 asks. The "3 sorted" shell at the end is calm and clear.
- **Even split maths** is right: $59.33 three ways is $19.79 / $19.77 / $19.77; Split my part on a $100.00 joint purchase at 50/50 three ways is **$16.68 / $16.66 / $16.66**, as S-03j shows, with "Alex's $50.00 stays theirs · joint 50/50".
- **The save rules on Amounts:** "That's $22.50 too much" turns Save off; short with you in the split says "$57.50 left · stays yours" and Save is on.
- **Paybacks:** Which payment was it? suggested Priya's $42.50 e-Transfer first ("Amount matches"), Link worked, "Unlinked · Priya owes $42.50" with Undo brought it back, Cash in hand ("Deposit it later? Pearl won't count it twice.") marked Sam paid, Let it go and Undo let it go both worked, and Remind Jo's message is plain and in Pearl's own sheet.
- **Owed to you** added up: $39.54 by 2 people after the Nopa split; at the end $15.00 owed by Jo, with Sam (cash) and Priya under PAID BACK THIS MONTH.
- **Not sure yet** reads well end to end: "No amounts yet. Paybacks come off as they arrive.", "Priya paid back $42.50" toast, That's everything? with WHAT CHANGES, "Closed Nov 10 · You kept $85.00 · nobody owes you", "Split reopened" with Undo.
- **Every split menu and confirmation** in this flow (S-40a, S-40u, S-06, S-08, S-46a, Remind) is a Pearl sheet, not a stock dialog.
- **Joint:** Shared with asks for Contacts on open, then Type a name works; "Alex added" toast with Undo; the purchase page says "Joint with Alex · 50%" and offers Whose was it? and Split my part.
- **Words:** no "safe to spend" anywhere I went (app text and the accessibility trees), and no pronouns for other people: every line uses their name ("Priya paid back $42.50", "Jo won't owe you anymore").
- **Light mode (REFRESH-05)** looks the way C‴ intends on every screen passed: the iridescent background, glass cards with the nacre edge, the orb, and the darker grey is readable on cards (see TEST-14 for where it isn't on the background itself).

### [testingBOT] 2026-11-10 · Round 1 summary

| ID | Kind | Severity | To | Title |
|---|---|---|---|---|
| TEST-01 | Bug | Blocker | engBOT | Quick sort's card is unreadable in dark mode |
| TEST-02 | Bug | Major | engBOT | Settle up › Type amounts opens "Who was it with?" on the leftover amount |
| TEST-03 | Discrepancy | Major | both | A split counts only your share straight away, before anyone pays |
| TEST-04 | Discrepancy | Major | engBOT | Home has no "Sort now"; it still has "Review one by one" |
| TEST-05 | Discrepancy | Major | engBOT | Spending is still red, and Cash flow's summary is the old Spent / Came in / Over |
| TEST-06 | Discrepancy | Major | both | Stock iOS alerts and action sheets are still in the app (house rule) |
| TEST-07 | Bug | Major | engBOT | Leave out without a reason does nothing, and says nothing |
| TEST-08 | Discrepancy | Major | both | "I had some too" can't be changed on How to split, and there's no way back |
| TEST-09 | Bug | Minor | both | The floating Back button sits on top of the page once it scrolls |
| TEST-10 | Bug | Minor | engBOT | Shop names are cut to "Unknown", "Corner", "Blue" |
| TEST-11 | Confusion | Minor | designBOT | Lines that say nothing: "The $0.00 goes back to your share", "Sam · Done" |
| TEST-12 | Confusion | Minor | designBOT | Pearl's guess is "Other?", with Yes as the main answer |
| TEST-13 | Bug | Minor | engBOT | Small inconsistencies in names and amounts |
| TEST-14 | Bug | Minor | both | Accessibility audit: contrast, small tap areas, the tab badge |
| TEST-15 | Bug | Major | both | "Let Jo's $15.00 go?" says the Allowance doesn't change, but it goes down |
| TEST-16 | Bug | Minor | engBOT | On Amounts the number pad can't be closed, and it hides what's wrong |
| TEST-17 | Discrepancy | Minor | designBOT | At the largest text size the merchant's initials turn into "…" |

**Not covered in Round 1** (for Round 2): Owed to you's "Not settled" and "You owe" sections (needs a Not sure yet split left open and a "they overpaid" part; neither came up), a deposit bigger than what's owed (S-09u2 / parts), Remove a person who has paid (S-03fr), Remove Jo and the joint Change share save (both journeys stopped on the number pad, TEST-16), the Shared with picker with Contacts allowed, the offline and error states, and Reduce Motion.

---

### [designBOT → testingBOT] 2026-11-10 · Round 1 · designBOT's replies
Every finding to designBOT or both is answered below, one entry each. New frames are on the **Design refresh** page in two new sections: **16** `1227:18934` (TEST-06 sheets) and **17** `1231:20372` (the other look and word fixes). Every frame is built from Pearl Design System components and labelled with its Jira tickets. All are **Awaiting product owner**, so engBOT doesn't build them until she picks. Each section has a build note (`1231:21488`, `1231:21489`).

### [designBOT → testingBOT] 2026-11-10 · TEST-03 · How a split counts toward the Allowance
**Status:** Needs product owner
**Jira:** THL-291, THL-289   **Figma:** S-04r v2 `1090:1743`, S-08ra `1091:2527`, S-46a `1117:8058` (no change made)
I compared the screenshot with S-04r v2. The frame follows Jira: a −$150.00 hero with "Your share $30.00". The app follows a different rule. I haven't redesigned; the product owner needs to pick one of these two rules.

Example: a $127.50 Gusto dinner. Priya owes $42.50, Sam $30.00, Jo $15.00, and your share is $40.00.

| | **A · The whole purchase counts until it's paid back** (THL-291 "Payback rule unchanged", THL-289 Rules, S-04r v2) | **B · Only your share counts, straight away** (as built: the server saves `amount` = your share) |
|---|---|---|
| The big amount | −$127.50, the same as the card statement, with "Your share $40.00" under it | −$40.00. The statement says $127.50, so the page needs "of $127.50" for you to recognise it |
| Allowance when you split | Goes down $127.50 | Goes down $40.00 |
| Allowance when Priya pays $42.50 | Goes up $42.50, so a payback visibly helps | Doesn't move; the payback is only linked |
| Owed to you | $87.50 from 3 people. This is money on its way back, and the Allowance doesn't count it until it arrives | Also $87.50 from 3 people, but the Allowance already treats it as back. If Jo never pays, the Allowance has been $15.00 too high all along |
| Let it go (Jo's $15.00) | Nothing moves: the $15.00 was counted all along. "Your Allowance doesn't change." is true | The Allowance goes down $15.00. The note has to say so (see TEST-15) |
| Not sure yet and deposit parts | Same rule: S-46a's "Already counts the $85.00", and S-12 v2's "Travel $856 → $428" when a payback is linked | Different from Not sure yet, which already counts the whole purchase until paybacks arrive. Two rules in one app |

**My recommendation: A**, the Jira rule.
- **It's careful.** The Allowance never spends money you haven't got back yet. That matters most when someone doesn't pay.
- **The big number matches the card statement.**
- **Every payback raises the Allowance,** which is a small reward for chasing it.
- **The approved frames and copy already assume A:** S-04r v2, S-08ra, S-46a and S-12 v2.

The cost is on the server. The purchase keeps its full amount and each share comes off as it's paid back, the same way Not sure yet already works. THL-291 also contradicts itself: one acceptance criterion says "Let the rest go adds $15 to the user's Dining out". Under A it doesn't, because the $15 is already in Dining out. Once she picks, engBOT updates that line (with her OK, as on 2026-11-09).

Joint accounts are a separate question. "Only my share counts" (THL-172) is about who owns the money, not about lending it, so it stays as it is under either rule.

### [designBOT → testingBOT] 2026-11-10 · TEST-15 · Let it go says the Allowance doesn't change, but it goes down
**Status:** Needs product owner (follows TEST-03)
**Jira:** THL-291, THL-289   **Figma:** S-08ra `1091:2527`, S-08rb `1091:2579` (no change made)
The screenshot and the frame show the same words. The words are only right under rule A.
- **If she picks A:** keep S-08ra/rb as drawn. Once the server follows A, the note becomes true.
- **If she picks B:** the note changes to "Your Allowance goes down $15.00." Better still, it comes from the server's let-go preview, the way WHAT CHANGES does on S-12 v2 and S-46a. That way the sheet can't drift from the numbers again.

Until she decides, I'd ask engBOT to take the line out rather than ship a sentence that's wrong. I won't redesign this before TEST-03 is settled.

### [designBOT → testingBOT] 2026-11-10 · TEST-06 · Pearl sheets for the stock alerts and action sheets
**Status:** Redesigned · Awaiting product owner
**Jira:** see each row   **Figma:** section 16 `1227:18934`, note `1231:21488`
None of the 14 had a Pearl design. Four had frames drawn as iOS alerts; the new frames replace those once she picks one. Every new sheet is built from library components: Sheet header, Callout or Banner, Input, Option row, Person row and the Primary and Secondary Buttons. Like S-08ra and S-03fr, the Primary button names the action, and ✕ or swiping down means "keep it".

The table lists light and dark frames.

| # | Code (file:line) | Existing frame | New frame(s), light / dark | Jira |
|---|---|---|---|---|
| 1 | Leave out, `TransactionsView.swift:173` | none | T-77c no reason yet, Leave out off `1227:18935` / `1228:20609`; T-77c2 three selected, reason typed `1228:18999` / `1228:21194` | THL-263, THL-231, THL-122 |
| 2 | Delete a transaction, `TransactionDetailView.swift:1755` | none | T-03x `1227:19027` / `1228:20650`; deleting `1228:19090`; couldn't delete `1228:19169` | THL-226, THL-234, THL-122 |
| 3 | Leave without saving?, `PartsFlow.swift:294` | S-24x `998:37484` / `1007:39342` (an iOS alert) | S-24xr `1228:19249` / `1228:20691` | THL-291, THL-289 (SPLIT-07) |
| 4 | Days sorted together, `CalendarView.swift:187` | none | T-49b Change / Remove as Option rows `1228:19323` / `1228:20732`. Remove acts at once with an Undo toast | THL-257, THL-255 |
| 5 | Sign out, `ProfileView.swift:134` | none | P-05 `1228:19428` / `1228:20774` | THL-114 |
| 6 | Remove a device, `SettingsViews.swift:195` | SEC-12 `832:33371` (an iOS alert) | SEC-12r `1228:19504` / `1228:20814` | THL-287, THL-114 |
| 7 | New recovery codes, `SettingsViews.swift:204` | SEC-08/09 (deferred) | **Deferred, no frame.** The row stays hidden on iPhone | THL-287 |
| 8 | Sign out of other devices, `SettingsViews.swift:215` | SEC-04 `255:4181` / `255:4554` (an iOS alert) | SEC-04r `1228:19578` / `1228:20855` | THL-114, THL-287 |
| 9 | Reset Pearl, `SettingsViews.swift:461` | none (SO-02/03 is Start over, a different action) | SO-06 with WHAT GOES / WHAT STAYS and Type "reset" `1228:19652` / `1228:20896`; resetting `1228:19816`; couldn't reset `1228:19978` | THL-214, THL-234, THL-116 |
| 10 | Remove a rule, `CategoriesRulesView.swift:133` | none | CR-00x `1228:20144` / `1228:20946` | THL-123, THL-234 |
| 11 | Take a tag off, `CategoriesRulesView.swift:140` | CR-10 `796:31598` covers only rename | CR-10x `1228:20218` / `1228:20987` | THL-123, THL-226, THL-234 |
| 12 | Nickname, `AccountsViews.swift:644` | none | AM-09n `1228:20292` / `1228:21028` | THL-120, THL-234 |
| 13 | Name, `AccountsViews.swift:1053` | none | AM-14n `1228:20378` / `1228:21070` | THL-234, THL-226 |
| 14 | "Are your e-Transfers to … your rent?", `IncomeBillsView.swift:81` | none | IB-03 `1228:20461` / `1228:21112` | THL-127, THL-45 |
| 15 | Turn off AI sorting, `PrivacyViews.swift:142` | CN-05 `733:30993` / `733:32361` (an iOS alert) | CN-05r `1228:20535` / `1228:21153` | THL-117, THL-139 |

Loading and error states follow S-08rc/rd for every sheet. They're drawn in full for the two you can't undo, Delete and Reset. The build note covers the rules for each sheet: Save stays off while a name is empty; SEC-04r's wording changes for one device or several; a reason is needed for Leave out.

### [designBOT → engBOT] 2026-11-10 · TEST-06 · How to build the sheets, once picked
**Status:** Awaiting product owner
**Jira:** as above   **Figma:** section 16 `1227:18934`
Please don't build these until she picks. When you do, they should all be one view, a `PearlConfirmSheet` with these parts:
- the SheetHeader (eyebrow, title, optional avatar)
- a body Text
- an optional Callout, Banner, TextField, or Option rows / Person rows
- a primary and a secondary button
- the busy state, error text and retry

Present it with `.sheet` and `.presentationDetents([.height(fit)])`, the way S-08ra already is. Swap each `.alert` and `.confirmationDialog` in the table for it. Leave out shares this sheet with TEST-07: the button is off until there's a reason, and the line sits under the field. Removing days sorted together uses your existing Undo toast instead of a second question. Say if any server call has no undo and needs a confirmation I haven't drawn.

### [designBOT → testingBOT] 2026-11-10 · TEST-08 · "I had some too" on How to split, and the fifth segment
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-291, THL-289, THL-282, THL-172, SPLIT-C (Jira pending)   **Figma:** S-03r2 `1231:20373` / dark `1231:20448`, S-03r2b `1231:20510`, S-03j v2 `1231:20606`
You're right that the plain How to split (S-03r) never had the toggle, although S-03j and S-45c do. In S-03r2 it sits under the people:
- **On:** you can save short of the total, and the line says "$4.12 left · stays yours".
- **Off (S-03r2b):** your row goes, the line says "$4.12 left to assign", and Save is off. This is THL-291's rule.
- **Not sure:** the toggle is hidden.

I didn't add a Back button. Once the toggle is on this page, you can change who's in the split right here, by adding someone or swiping a row away, so you never need to go back to S-02.

On the small question: **the app is right.** Not sure belongs on Split my part too; SPLIT-C built "Not sure yet on Split my part". S-03j v2 shows it as the fifth segment. The old S-03j had four because it was drawn before SPLIT-C.

### [designBOT → testingBOT] 2026-11-10 · TEST-09 · The floating Back covers the page once it scrolls
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-289, THL-291, THL-181   **Figma:** S-04r v2s `1231:21143` / dark `1231:21214`
Your advice holds. Once the hero scrolls away, an inline bar (the library Navigation bar, Inline, titled with the merchant) and its scroll-edge material sit behind Back and the clock. Nothing scrolls under them without a backing.

engBOT: please use a real toolbar back button plus `.navigationTitle(merchant)` and `.navigationBarTitleDisplayMode(.inline)` on the pushed page. iOS 26 then draws the edge effect. Drop the floating glass Back on every page that scrolls, which covers T-03r, S-04r, S-04u and S-04j. The code side of this is yours.

### [designBOT → testingBOT] 2026-11-10 · TEST-11 · "The $0.00 goes back to your share" and "Sam · Done"
**Status:** Redesigned (S-46a) · Keep (S-40u2) · Awaiting product owner
**Jira:** SPLIT-C (Jira pending), THL-291, THL-181, THL-289   **Figma:** S-46a v2 `1231:20765` / dark `1231:20857`; S-40u2 `1114:7949` unchanged
- **S-46a:** the "Done" was in my frame, and you're right that it reads like a button. In S-46a v2 the row has nothing on the right; it just says "Sam · Won't show as owing".
- **S-40u2:** the frame already says "Remove Priya · Nothing to unlink". The "$0.00" line is a build difference, so engBOT should use the frame's text. I'm keeping "Nothing to unlink" because it tells you removing her is harmless.

### [designBOT → testingBOT] 2026-11-10 · TEST-12 · A guess of "Other?" with Yes as the main answer
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-254, THL-275, THL-213, THL-263   **Figma:** T-93n `1231:20937` / dark `1231:21001`
Agreed: Other isn't a guess (THL-275: "no best-guess card"). When Pearl's best is Other, the card is a question:
- the overline says NEEDS A LOOK and the question is "What was this?"
- the round button becomes **Answer** (with a chevron) and opens the shared What was this? page (T-08r), as the house rule requires
- Skip stays

Needs a look then shows no "Other?" chip, and the transaction page's category row asks "What was this?" without "Pearl's guess". The deck itself stays one card per transaction.

### [designBOT → testingBOT] 2026-11-10 · TEST-14 · Contrast, overlines and initials
**Status:** Keep (muted text) · Redesigned (link colour) · Awaiting product owner
**Jira:** THL-125, THL-122, THL-289 (designBOT rules: Dynamic Type, 44 pt, light and dark)   **Figma:** note `1231:21489`
I measured the Round 1 screenshots. `color/text/muted` (#514D67) is **6.7:1 to 7.3:1** behind "TUESDAY, NOVEMBER 10", "left in November", "Owes you" and "Pearl's guess". The audit is reading the see-through background behind the text, so those flags are false alarms, and I'm keeping the token.

The real miss is the rose text links on the bare background, such as "See everyone who owes you". They're 4.4:1 on the blue-lilac part of the background.

**Proposal:** set the light value of `color/text/link` to #9C1F4B, which gives 4.8:1 to 6.0:1 on every part of the background. Dark stays as it is. The other option is to put those links inside a card. This is a library change, so it waits for her.

Overlines should use a Dynamic Type style (Text/Caption in uppercase) instead of a fixed size, and the initials circles should use `@ScaledMetric`.

engBOT's part: the 44 pt hit areas, and `.accessibilityValue` on the badge.

### [designBOT → testingBOT] 2026-11-10 · TEST-17 · The initials turn into "…" at the largest text size
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-291, THL-289   **Figma:** S-03ax `1231:21270`
At AX1 and up, the sheet header drops the initials circle instead of shrinking it, so initials are never cut. The name wraps to two lines (`lineLimit(2)`), with the amount on its own line under it. The same rule applies to every Sheet header with an avatar.


---

### [engBOT → testingBOT] 2026-11-10 · Round 1 · engBOT's replies
Branch `fix/testing-round-1` (local, not pushed), off main at 4a4ae84. New checks, one per finding, are in `ios/PearlUITests/Round1FixesUITests.swift` (4f4e230); run them with `python3 ios/tools/run_journeys.py --suite PearlUITests/Round1FixesUITests` (your runner, with a `--suite` flag added). Server checks are in `tests/test_ingest.py` and `tests/test_paybacks.py`. `pytest`: 1,921 passed. All six UI checks pass on the branch and fail on main 4a4ae84, so each one catches its bug. Not touched, as asked: TEST-03 and TEST-15 (the product owner picks the rule), TEST-04 and TEST-05 (not this round), TEST-06 (waiting for her to pick designBOT's sheets), TEST-08, 11, 12 and 17 (design).

### [engBOT → testingBOT] 2026-11-10 · TEST-01 · Fixed in 31aeb5d
Reproduced from your shot. In dark, the card face, the two cards peeking under it and Skip are now `--surface-card` with a `--border` edge, as T-93r dark `1077:1464` has them. The Back button is the Glass button (glass fill and edge). On Needs a look, the Quick sort card is `--surface-card`, and the chosen chip is `--ink` with `--surface-page` words, as T-83r dark `1076:1268` has it. The answer sheet's No button had the same white-on-white, so it now uses the control fill. Light is unchanged.
Test: `testQuickSortReadsInDarkMode` measures the screen. The card must be dark (luminance under 0.35) in dark and still light in light, Skip's circle must be dark, and the chosen chip's words must stand out from its fill.

### [engBOT → testingBOT] 2026-11-10 · TEST-02 · Fixed in 821ca95
Reproduced. Settle up › Type amounts now opens on S-45c with the split's people, so "Settle up · type amounts" comes first, never "Who was it with?". The header shows the whole purchase (−$127.50), not the part still counting as hers. On a joint card it's her part, with "Your part … of …" under it.
Test: `testSettleUpTypeAmountsOpensOnHowToSplit` goes Not sure yet → Priya's e-Transfer linked → Settle up → Type amounts. It checks the title, that S-02 doesn't appear, that $127.50 is there, and that Priya's row says "Paid $42.50 so far".

### [engBOT → testingBOT] 2026-11-10 · TEST-07 · Fixed in 2ce0691
Reproduced: the server needs a reason, and the "Say why" error landed off screen. Until the product owner picks T-77c (TEST-06), the stock alert does what designBOT's build note asks: Leave out is off until a reason is typed, and the alert says "Say why, so you can tell later."
Test: `testLeaveOutWaitsForAReason` checks that Leave out starts off, turns on once a reason is typed, and that the server then has Spotify left out.

### [engBOT → testingBOT] 2026-11-10 · TEST-10 · Fixed in 5acf0e2 (two of three)
- "SP * NORTHSHOP CA" now reads Northshop. The SP prefix takes "SP *" as well, and a city strip that leaves only punctuation keeps the name.
- "SQ *CORNER STORE 22" now reads Corner Store. STORE stays on a Square, Shopify or Toast seller's name. "STARBUCKS STORE 08812" is still Starbucks.
- **"SQ *BLUE BOTTLE ON" is still "Blue". Won't fix this one alone:** it's the same shape as "SQ *BALZACS TORONTO ON", where the last word really is the city, so a rule that keeps "Bottle" would turn that one into "Balzacs Toronto". Real Square rows usually carry the city ("SQ *BLUE BOTTLE TORONTO ON" already gives Blue Bottle). If you've seen a real descriptor like this, send it and I'll look again.
- Rows already in a ledger keep the name they were saved with. Only new imports get the new names.
Tests: `test_a_processor_sellers_name_is_kept` and `test_a_chains_store_number_still_comes_off` in `tests/test_ingest.py`.

### [engBOT → testingBOT] 2026-11-10 · TEST-13 · Fixed in b8d38a6 and 821ca95
- **S-06rb:** payback candidates now carry the sender (`party`, the same name Cash flow shows), and the row uses it, so it reads "Priya Shah · Nov 9". As in S-06rb `1091:2219`, the suggested row's second line says "Amount matches" instead of the account; the Other money in rows keep the account. That difference is in the frame, so I've left it.
- **The joint card's page** (Shared with) showed "$0.00 · Credit card" where the account page shows "— · Owing". It now shows "—" when there's no balance, and "Owing" for a card, the same as AM-08. The pill changing from Manual to Joint is the state change, so that stays.
Tests: `test_candidates_name_the_sender_as_cash_flow_does` in `tests/test_paybacks.py`, and the TEST-02 UI check taps "Priya Shah" and fails if "E-transfer From" is on the sheet.

### [engBOT → testingBOT] 2026-11-10 · TEST-14 · Fixed in 2ce0691 and 821ca95 (the code side)
- **44 pt tap areas,** without moving anything on screen: "Review one by one", the Transactions · Calendar switch (the pill still draws at 32 pt), "Edit split" and "See everyone who owes you". The last two had a 44 pt frame outside the button, so only the words could be tapped.
- **The Cash flow tab** now has an accessibility value, "6 to sort".
- **Overlines:** every overline I found (`Overline`, the detail page's OPTIONS and DETAILS, the dates) already uses a text style with `relativeTo:`, so it grows with Dynamic Type. I couldn't find a fixed size to fix. If the audit still flags one by name after this build, send me the label.
- **Not mine to change:** the initials circles (`@ScaledMetric`, TEST-17) and the link colour are designBOT's, waiting for the product owner. designBOT measured the muted-text contrast flags and found them to be false alarms.
Tests: `testTheSmallTextButtonsHave44ptTapAreas` runs the hit-region audit on Home and Cash flow. `testTheCashFlowTabSaysHowManyToSort` checks the tab's value.

### [engBOT → testingBOT] 2026-11-10 · TEST-16 · Fixed in 821ca95 (designBOT asked about the rest)
- A tap on the sheet's title or the purchase header puts the number pad away. Dragging the list down already did. I haven't added a Done bar over the pad, because it's not in any frame (question to designBOT below).
- While typing, the sheet scrolls so the status line and "Split the rest evenly" sit right above Save, as in S-03re. On Change Sam's share, the "too much" line shows.
- The outline is on the field being typed in, or on someone who has already paid more than the share, as S-03re `1092:2360` draws it. Every field used to go red whenever the total was short.
- When left empty, your field shows what it will save as (the "Your share" amount), not $0.00.
- On Change their share (S-03re), a person with nothing paid reads "Owes you".
Test: `testTheNumberPadGoesAwayAndTheStatusStaysInView` types Priya 40 and checks that "… left · stays yours" and "Split the rest evenly" can be tapped with the pad up, then that a tap on "How to split" puts the pad away.

### [engBOT → designBOT] 2026-11-10 · TEST-16 · A Done bar over the number pad, and S-03re's bar
**Severity:** Minor
**Jira:** THL-291   **Figma:** S-03re `1092:2360`   **Code:** `ios/Pearl/Views/Transactions/SplitFlow.swift` (amountsHow)
**Problem:** the decimal pad on Amounts, %, Shares and Change share has no key to close it. Tapping the title or dragging the list now closes it, but nothing on screen says so. S-03re also draws a progress bar with "$140.00 of $150.00" above Save, which the app has never had. And S-03re says "Paid back $30.00" for someone who paid their whole share where the app says "Paid $30.00".
**Ask:** should the pad get a keyboard bar with Done (a Pearl one, or the stock bar)? Is S-03re's bar meant to be built (it isn't in REFRESH-01's approved list)? Which wording is right for a share paid in full? I'll build whatever she picks.

### [engBOT → designBOT] 2026-11-10 · TEST-09 · Noted, waiting for her pick
**Severity:** Minor
**Jira:** THL-289, THL-291   **Figma:** S-04r v2s `1231:21143` / `1231:21214`   **Code:** `ios/Pearl/Views/Transactions/TransactionDetailView.swift` (the floating glass Back)
Thanks. S-04r v2s is marked Awaiting product owner, so I haven't swapped the floating Back for an inline bar yet. Once she picks it, I'll do T-03r, S-04r, S-04u and S-04j together: the toolbar Back, `.navigationTitle(merchant)` and `.inline`, and no floating Back on pages that scroll. Nothing to fix in code until then, because any fix adds a bar the current frames don't have.

### [designBOT → product owner] 2026-11-10 · TEST-03 · Rule A: new wording for THL-291's contradictory criterion
**Status:** Needs product owner (wording for Jira; I haven't edited Jira)
**Jira:** THL-291, THL-289   **Figma:** S-04r v2 `1090:1743`, S-08ra `1091:2527`, S-08rb `1091:2579` (no change: they already follow Rule A)
You picked Rule A: the whole purchase counts toward the Allowance until it's paid back. One acceptance criterion in THL-291 still describes the other rule. I suggest replacing it as follows.

- **Now:** "Sam paying $10 of $25 shows "Paid $10.00 of $25.00" and "Owes $15.00"; Let the rest go adds $15 to the user's Dining out."
- **Suggested:** "Sam paying $10 of $25 shows "Paid $10.00 of $25.00" and "Owes $15.00"; the purchase counts in full until it's paid back, so Dining out has $15 more than if Sam had paid. Let the rest go keeps that $15 in the user's Dining out, Sam no longer owes, and the Allowance doesn't change."

THL-291's Rules line ("the full purchase counts until paid back") and THL-289's Rules already say this, so nothing else needs to change. The S-08ra/rb note "Your Allowance doesn't change." becomes true once engBOT's server change lands. TEST-15 needs no new frame.

### [designBOT → engBOT] 2026-11-10 · Round 1 · Approved — build, with the missing frames drawn
**Status:** Redesigned · Approved — build
**Jira:** see each frame name   **Figma:** section 16 `1227:18934`, section 17 `1231:20372`
The product owner approved everything from Round 1. Every frame in sections 16 and 17 is now named "Approved — build", and the old frames are marked "Superseded by …":
- S-24x `998:37484` / `1007:39342`
- SEC-04 `255:4181` / `255:4554`
- SEC-12 `832:33371`
- CN-05 `733:30993` / `733:32361`
- S-46a `1117:8058` / `1117:8128`
- S-03j `1105:5893` / `1105:6049`
- S-03r `1079:1600` / `1079:1668` / `1079:1736`

**What was missing, now drawn:**
- **Dark twins:**
  - S-03r2b `1234:23204`
  - S-03j v2 `1234:23287`
  - S-03ax `1234:23432`
  - S-03r2c, a new over state for How to split with the toggle ("That's $45.88 too much", Save off): `1234:23485` / `1234:23580`
- **Loading and error states (section 16, rows 3 to 6),** as light loading / light error / dark loading / dark error:

  | Sheet | Light loading | Light error | Dark loading | Dark error |
  |---|---|---|---|---|
  | T-77c2 | `1234:21056` | `1234:21117` | `1234:21182` | `1234:21231` |
  | P-05 | `1234:21284` | `1234:21339` | `1234:21398` | `1234:21441` |
  | SEC-12r | `1234:21488` | `1234:21544` | `1234:21604` | `1234:21648` |
  | SEC-04r | `1234:21696` | `1234:21752` | `1234:21812` | `1234:21856` |
  | CR-00x | `1234:21904` | `1234:21960` | `1234:22020` | `1234:22064` |
  | CR-10x | `1234:22112` | `1234:22168` | `1234:22228` | `1234:22272` |
  | AM-09n | `1234:22320` | `1234:22382` | `1234:22448` | `1234:22498` |
  | AM-14n | `1234:22552` | `1234:22614` | `1234:22680` | `1234:22730` |
  | IB-03 | `1234:22784` | `1234:22841` | `1234:22902` | `1234:22947` |
  | CN-05r | `1234:22996` | `1234:23052` | `1234:23112` | `1234:23156` |

  Loading uses Button State=Loading with "Label while loading" on ("Signing out…", "Removing…", "Saving…", "Turning off…"). Error uses a Banner, Tone=Caution, "Couldn't … Nothing changed. Try again.", with "Try again" as the primary. Delete and Reset Pearl already had theirs.
  - **S-24xr:** saves nothing, so it has no loading state.
  - **T-49b Remove:** a failure shows S-44h's toast with Try again.
- **Link colour (TEST-14):** done in the Pearl Design System library (`3fdfPDKIjhiluGHtXWSF32`). There's a new primitive, `rose/800` #9C1F4B, and `color/text/link` in Light now points to it. Dark stays `rose/300`. `color/action/primary`, used by buttons, is unchanged at `rose/700`. **It is ready to publish.** Once the product owner publishes it, set `Pearl.link` light to #9C1F4B and use it on every text link and text button that sits on the background ("See everyone who owes you", "Edit split", "Review one by one").
- **Build order I'd suggest:**
  1. TEST-06: one `PearlConfirmSheet` view, then swap the 14 dialogs.
  2. S-03r2/r2b/r2c: the toggle on How to split.
  3. S-04r v2s: the toolbar Back and inline title.
  4. S-46a v2.
  5. T-93n.
  6. S-03j v2.
  7. S-03ax.

### [designBOT → engBOT] 2026-11-10 · TEST-16 · Answers: Done bar, S-03re's bar, "Paid back $30.00"
**Status:** Approved — build (these are details of frames she has approved)
**Jira:** THL-291, THL-289   **Figma:** S-03re `1092:2360`, S-03r2 `1231:20373`, S-03r2c `1234:23485`
1. **Done bar: yes.** Use the system keyboard toolbar: `.toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { focused = nil } } }`, with the button tinted `pearlAction`. iOS draws the glass bar. The house rule is about menus and confirmations, not keyboard accessories, so I'm not drawing a Pearl one. Do it on every decimal pad in splits: Amounts, %, Shares, Change share, Settle up › Type amounts and S-47 Your share. Keep "a tap on the title closes it" as well.
2. **S-03re's bar: yes, build it.** It's the `split.meter`: a two-colour bar (the assigned part, then what's left) plus the status line ("$4.12 left · stays yours" / "$x left to assign" / "That's $x too much" / "Adds up ✓") and "$140.00 of $150.00" on the right. It's on every How to split, Settle up and Change share frame. S-03r2, r2b and r2c are now approved with it, so it's in scope now even though REFRESH-01 didn't list it. Bar tones:
   - fill `color/action/primary`
   - remainder track `color/fill/control`
   - over the total, the whole bar is `color/action/primary` and the line is plain ink (no red)
3. **Wording: "Paid back $30.00"** for a share paid in full, as S-03re and S-04r v2 have it ("Paid back · Nov 16"). "Paid $10.00 of $30.00" is only for part paid (THL-289: Owes / Paid $x of $y / Paid back). Use "Paid $30.00" only on Not sure yet splits, where there's no share to pay back ("Paid you · Nov 16").

### [testingBOT → both] 2026-11-10 · TEST-18 · Not sure yet with you in it: no row for you, and no way to say your share (from the product owner)
**Kind:** Suggestion   **Severity:** Major
**Where:** S-03u How to split › Not sure, S-04u split card, S-40u/S-40u2, Settle up S-45a/S-45c, Owed to you S-14u   **Jira:** SPLIT-C (Jira pending), THL-291, THL-289
**Steps (her words):** "I allocated five different people split a transaction with me including me in the five, and three people each transferred me back. One person still hasn't sent me money and I myself don't know the exact split that I had. I selected the option for the split that I'm not sure on how much everyone owes me."
**Saw:** a Not sure yet split always includes her (`include_me` is forced on in `SplitFlow.swift` save(), mode "unknown"), but she isn't listed. The card, S-40u/u2 and Owed to you show only the other people. The only place to give her own share is Settle up › Type amounts (S-45c), and there she has to work out everyone else's amounts too.
**Expected:** "If I am included in the split, then there should be a row for me as well everywhere. … I knew that I spent $17 of the total amount that was remaining, so then the leftover of that should have been allocated to the one remaining person that hasn't sent me money back."
**Advice:** a You row wherever the people are listed. Let her type her own share, and give what's left (the purchase − paybacks received − her share) to whoever hasn't paid: automatically when one person is left, or split evenly or by typed amounts when there are several.

### [designBOT → both] 2026-11-10 · TEST-18 · A You row, your share, and the rest to whoever hasn't paid
**Status:** Redesigned · Awaiting product owner
**Jira:** SPLIT-C (Jira pending), THL-291, THL-289, THL-181   **Figma:** section 18 `1237:23124`, note `1238:25742`
I checked the code first. In `SplitFlow.swift`:
- save() sends mode "unknown" with `include_me` forced on and no amounts.
- `unsureHow` lists only the other people ("Any amount they send you").
- The split card's `unsurePerson` rows are the other people only.
- Settle up › Type amounts (S-45c, `settleBody`) is the only place her share can be typed, and only together with everyone else's.
- The SPLIT-C decision (split log, 2026-11-09) left out "I had some too" on Not sure.

So the gap is real, and the PUT that Settle up already uses can carry the new step.

The example in every frame: Pizza Nova $120.00, split five ways (you, Priya, Sam, Jo and Alex). Priya, Sam and Jo each paid $25.00 and Alex hasn't. Under Rule A it counts $45.00 now.

| Frame | Light / dark | What it shows |
|---|---|---|
| S-03u2 | `1237:23125` / `1237:23295` | How to split › Not sure with "I had some too" on: a You row, "Your share · set it any time", no amount |
| S-03u3 | `1237:23454` / `1237:23605` | You're not in the split: the toggle is off and there's no You row anywhere |
| S-04u6 | `1237:23743` / `1237:23945` | The split card, "Split 5 ways · Not sure yet": You first ("Your share · not set yet" with •••), Priya, Sam and Jo "Paid you · $25.00", Alex "Nothing yet"; the TEST-09 top bar when scrolled |
| S-40y | `1237:25033` / `1237:25117` | Your ••• options: Set your share, "Pearl gives what's left to whoever hasn't paid" |
| S-47a | `1237:25322` / `1237:25440` | "What was your share?", not typed yet: WHAT'S LEFT $120.00 − $75.00 = $45.00, and Save is off |
| S-47b | `1237:25489` / `1237:25616` | $17.00 typed. Alex is the only one left, so Alex gets the $28.00 automatically. "Save · Alex owes $28.00", with the Rule A note: the Allowance doesn't change now, and when Alex pays, $17.00 stays counted |
| S-47c | `1238:24552` / `1238:24728` | Two haven't paid (Jo and Alex): what's left ($53.00) is split evenly, $26.50 each, "Adds up to $120.00 ✓" |
| S-47d | `1238:24892` / `1238:25071` | The typed amounts don't add up: "$13.00 left to assign", and Save is off |
| S-47e | `1237:25668` / `1237:25786` | Your share is more than what's left: the field shows an error, "Your share can be up to $45.00", and Save is off |
| S-04u7 | `1237:24135` / `1237:24363` | After saving it's a set split: You $17.00, Alex "Owes you · what was left" $28.00, Toast "Alex owes you $28.00" with Undo |
| S-14u3 | `1238:25238` / `1238:25327` | Owed to you: Alex $28.00, in the total |
| S-14u4 | `1238:25590` / `1238:25672` | Still open: the NOT SETTLED row reads "You and 4 · $75.00 paid · your share not set" |
| S-04u8 | `1237:24579` / `1237:24812` | Everyone has paid: You "Your share · what's left after paybacks" $17.00, and That's everything says "Everyone has paid. $17.00 stays yours." |
| S-46a3 | `1238:25404` / `1238:25502` | That's everything? lists You $17.00, "Priya, Sam, Jo and Alex · Paid back $103.00", and Allowance "No change" |

Settle up (S-45a, "You · What still counts as yours") and S-45c (your row) already list you, so they stay as drawn.

**For the product owner to decide:**
1. Put "I had some too" back on Not sure, on by default. This reverses SPLIT-C's "no I had some too". **Recommend yes:** it's the only way for "you're not in the split" to show no You row.
2. Saving your share makes the split a set split, the same as Settle up: Alex owes $28.00 and counts in Owed to you's total, and Undo goes back to Not sure yet. The other option is to keep it Not sure yet and show Alex's $28.00 as a guess. **Recommend turning it into a set split:** once your share is known, the amounts are known.
3. With two or more unpaid, what's left starts evenly split. **Recommend yes.** The other methods are one tap away.
4. You're not in the split and one person hasn't paid: should Pearl also offer "Alex owes the rest" automatically? **Recommend yes,** as a lead option on S-45a: "Alex owes what's left · $45.00". It's a small addition; I'll draw it if she says yes.
5. SPLIT-C still isn't in Jira. This extends it, so its story text needs these rules when it's created.

engBOT: please don't build this until she picks.

### [designBOT → both] 2026-11-10 · TEST-18 · Correction: who wrote the finding
The "TEST-18" finding entry above is headed "[testingBOT → both]", but testingBOT didn't write it. It's the product owner's finding, and designBOT logged it for her at the coordinator's request. testingBOT: please take it into Round 2 as hers, and re-test it once she picks a design and it's built.

### [designBOT → both] 2026-11-10 · TEST-18 · Linked payments are locked; you change only the people who haven't paid
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-303 (SPLIT-C with the TEST-18 extension), THL-291, THL-289   **Figma:** section 18 `1237:23124`, note `1238:25742`
The product owner's words: "once you link payments those should be locked and you can adjust the other people that haven't paid back accordingly."

**The rule:** anyone with a linked payback, or cash marked paid, is locked. Their row shows the amount as plain text, with no field, and the sub-line "Paid back · Nov 14 · locked". Only you and the people who haven't paid can be changed.

The rule applies on every method:
- **Amounts:** a locked row shows its amount as text.
- **%:** it shows its percentage as text (Sam $20.00 = 20%).
- **Shares:** it shows its share count as text.
- **Evenly:** splits only what's left (the purchase − locked paybacks), across you and the people who haven't paid. On S-47, your share is what you typed, so what's left goes to the unpaid people only.

Tapping a locked row shows a Toast: "Priya's $25.00 is linked. Unlink the payback to change Priya's share." Its **Options** action opens Priya's ••• sheet (S-40u: View the payment, Unlink…). Once she's unlinked, Priya's row gets a field again. I used the library's Person row (Trailing=Amount) and Toast; no new component.

**What changed:**
- **S-47c** `1238:24552` / `1238:24728` and **S-47d** `1238:24892` / `1238:25071`: Priya and Sam are marked "Paid back · … · locked".
- **S-47a** `1237:25322` / `1237:25440`, **S-47b** `1237:25489` / `1237:25616` and **S-47e** `1237:25668` / `1237:25786`: the Paid back row in WHAT'S LEFT reads "Priya, Sam and Jo · linked, locked".
- **New S-47f** `1239:25202` / `1239:25293`: tapping a locked row, with the Toast and Options.
- **New S-45c2** `1239:25426` / `1239:25532`: Settle up › Type amounts on Evenly. Sam's linked $20.00 is locked, and what's left ($80.00) goes $40.00 to you and $40.00 to Priya.
- **New S-45c3** `1239:25626` / `1239:25734`: the same on %. Sam is a locked 20%; you take 30% and Priya 50%.
- **Section 18 build note** `1238:25742`: now has the lock rule.
- **Ticket labels:** every frame and section name in sections 16, 17 and 18 now uses THL-303 (SPLIT-C), THL-304 (JOINT-A) and THL-305 (JOINT-B) instead of "Jira pending". That's 34 names. The section 17 note `1231:21489` is updated too.

**For the product owner to check:** under this rule, someone who has paid is settled at exactly what they paid. Two approved behaviours stop happening through Type amounts:
- S-45c's "Paid $20.00 so far · owes $13.33 after", where a payer still owes more.
- S-45e's extra step, where a share is below what someone paid.

To ask a payer for more, or to give some back, you'd unlink first. **I recommend keeping it that simple.** If she wants "Sam owes $13.33 more" to stay possible, the locked amount could instead be the least Sam's share can be, but that's harder to explain.

engBOT: please don't build this until she picks.

### [designBOT → engBOT] 2026-11-10 · TEST-18 · Approved — build: final frames
**Status:** Approved — build
**Jira:** THL-303 (SPLIT-C with the TEST-18 extension), THL-291, THL-289, THL-181   **Figma:** section 18 `1237:23124`, build note `1238:25742`
The product owner said yes to all four questions, and the lock rule above is part of what she approved:
1. "I had some too" comes back on Not sure yet, on by default.
2. Setting your share turns it into a set split, using the same PUT as Settle up. Undo goes back to Not sure yet.
3. When two or more haven't paid, what's left starts split evenly.
4. When you're not in the split and one person is left, Settle up leads with "Alex owes what's left".

Every frame in section 18 is now "Approved — build" and labelled THL-303. Final IDs (light / dark):

| Frame | Light / dark | What it shows |
|---|---|---|
| S-03u2 | `1237:23125` / `1237:23295` | Not sure with you in it: a You row, no amount |
| S-03u3 | `1237:23454` / `1237:23605` | You're not in it: the toggle is off, no You row |
| S-04u6 | `1237:23743` / `1237:23945` | The split card with You first, your share not set |
| S-40y | `1237:25033` / `1237:25117` | Your ••• options: Set your share |
| S-47a | `1237:25322` / `1237:25440` | Your share not typed yet, Save off |
| S-47b | `1237:25489` / `1237:25616` | $17.00 typed: Alex gets the $28.00 left automatically |
| S-47c | `1238:24552` / `1238:24728` | Two unpaid: what's left split evenly, payers locked |
| S-47d | `1238:24892` / `1238:25071` | Two unpaid, typed amounts don't add up: "$13.00 left to assign", Save off |
| S-47e | `1237:25668` / `1237:25786` | Your share is more than what's left: error |
| S-47f | `1239:25202` / `1239:25293` | Tapping a locked row: Toast "Unlink the payback to change Priya's share", with Options opening S-40u |
| S-04u7 | `1237:24135` / `1237:24363` | After saving: a set split, Alex owes $28.00, Toast with Undo |
| S-14u3 | `1238:25238` / `1238:25327` | Owed to you: Alex $28.00, in the total |
| S-14u4 | `1238:25590` / `1238:25672` | Still open: the NOT SETTLED row names you |
| S-04u8 | `1237:24579` / `1237:24812` | Everyone has paid: your share is what's left |
| S-46a3 | `1238:25404` / `1238:25502` | That's everything? with You in WHAT CHANGES |
| S-45c2 | `1239:25426` / `1239:25532` | Settle up › Type amounts, Evenly: locked payer, what's left split between you and the unpaid |
| S-45c3 | `1239:25626` / `1239:25734` | Settle up › Type amounts, %: a locked payer's percentage shows as text |
| **S-45a2 (new, Q4)** | `1241:25624` / `1241:25783` | Settle up when you're not in the split and only Alex is left: the lead option is "Alex owes what's left · $45.00 · the purchase less what's been paid back". Then "Use what each paid", whose sub-line is now "Alex pays nothing; the $45.00 stays yours", then "Type amounts". Paid rows are locked |

**Build notes:**
- **Locked rows:** a row is locked if that person has a linked payback or cash marked paid. Use `PersonRow` with trailing `.amount`, no field, sub-line "Paid back · {date} · locked". Tapping it shows the Toast with an Options action, and Options opens that person's S-40u sheet.
- **Evenly** divides the purchase minus locked paybacks (minus your typed share, on S-47) across the unlocked rows. The odd cent goes to you if you're unlocked, otherwise to the first unpaid row.
- **Errors on S-47:** your share can't be more than the purchase minus locked paybacks. When the unpaid amounts are short, Save stays off with "$x left to assign".
- **Allowance:** setting your share doesn't move it (Rule A). It goes up as each payback arrives, and only your share stays counted.
- **Joint:** apply the same to Split my part on a joint purchase (THL-305), with her part as the total.

Still open for the product owner: whether the lock may block a payer from owing more than they paid (S-45c "owes $13.33 after", and S-45e). The frames lock them at exactly what they paid.


---

### [engBOT → testingBOT] 2026-11-10 · Round 1 approvals · engBOT's replies
The product owner approved Rule A, sections 16, 17 and 18, the TEST-16 answers and TEST-04/05. They're built as local branches, each stacked on the one before and each meant as its own PR. Nothing is pushed and Jira is untouched.

| Branch | Base | Commits | What |
|---|---|---|---|
| `feat/split-rule-a` | `fix/testing-round-1` | 1b0d005, 3856389 | TEST-03 / TEST-15, Rule A |
| `feat/pearl-confirm-sheets` | `feat/split-rule-a` | ec5aa0a | TEST-06 (and TEST-07's sheet) |
| `feat/round1-redesigns` | `feat/pearl-confirm-sheets` | 73f8366 | TEST-08, 09, 11, 12, 16, 17, the link token |
| `feat/sort-now-cashflow` | `feat/round1-redesigns` | 43ca9b0 | TEST-04, TEST-05 |
| `feat/not-sure-yet-you-row` | `feat/split-rule-a` | a2c0808, 0f256f2 | TEST-18 (THL-303) |

- **Tests:** pytest passes on every branch: 1,930 on `feat/sort-now-cashflow` and 1,935 on `feat/not-sure-yet-you-row`. The new UI checks are in `Round1FixesUITests`. Run them with `python3 ios/tools/run_journeys.py --suite PearlUITests/Round1FixesUITests`; each one passed on its branch.
- **Builds:** each intermediate branch also builds on its own.

### [engBOT → testingBOT] 2026-11-10 · TEST-03 / TEST-15 · Fixed in 1b0d005 (Rule A)
- **The rule:** a split purchase counts in full until it's paid back. Each payback, whether linked, cash or another app, raises the Allowance by its amount. Let it go moves nothing, so S-08ra's "Your Allowance doesn't change." is now true.
- **Server:** the share as split is kept. Each split charge now carries what the others still owe (`split_owed`, from people_status), and spending counts it.
- **Not sure yet** keeps its own rule, which already worked this way.
- **Joint "only my share" (THL-172)** is about ownership, so it's unchanged. The split is of her part, and her part counts in full until paid.
- **Owed to you and the deposit parts flow** read people_status as before, so they're unchanged.
- **The transaction page** (S-04r v2) shows the whole purchase as the big amount, with "Your share $40.00 · date" under it.
- **Cash flow:** an unpaid split's note now says "Split with Priya" or "Priya paid you back" instead of "Your share of …". No frame covers this, so it's a question for designBOT below.
- **Tests:** `tests/test_split_rule_a.py` covers the $127.50 example. Splitting doesn't move the Allowance from the whole purchase; it rises $42.50 with Priya's payback and $30.00 with Sam's cash; Let it go and its Undo don't move it; Not sure yet is unchanged. The joint, parts and split tests that encoded the old rule now follow Rule A. UI check: `testASplitShowsTheWholePurchaseAndYourShare`.

### [engBOT → testingBOT] 2026-11-10 · TEST-06 · Fixed in ec5aa0a
- **One view:** `PearlConfirmSheet` (Sheet header, words, optional field, WHAT GOES / WHAT STAYS, Primary + Secondary, busy label, champagne Banner and Try again). It replaces every stock alert and action sheet: T-77c/c2, T-03x, S-24xr, T-49b, P-05, SEC-12r, SEC-04r, SO-06, CR-00x, CR-10x, AM-09n, AM-14n, IB-03 and CN-05r.
- **T-49b:** Change and Remove are Option rows. Remove acts at once, and its toast's Undo puts the days back, piggy bank included.
- **Recovery codes** stay deferred. Their alert was unreachable, so it's gone, and the row stays hidden.
- **Tests:** a pytest wiring test keeps `.alert`, `.confirmationDialog` and `.actionSheet` out of every Swift file. UI checks: `testLeaveOutWaitsForAReason` (now on T-77c) and `testSignOutAsksOnAPearlSheet`.

### [engBOT → testingBOT] 2026-11-10 · TEST-08, 09, 11, 12, 16, 17 · Fixed in 73f8366
- **TEST-08** (S-03r2/r2b, S-03j v2): "I had some too" sits under the people on How to split. With it off, your row goes and the line says "$x left to assign", with Save off.
- **TEST-16:**
  - The split meter (assigned in the action colour, the rest on the control fill) with "$80.00 of $84.12".
  - The status line is ink, never red.
  - The keyboard Done bar is on every number pad in the split sheet; the sheet now hosts a navigation stack for it.
  - Save rides on the scroll view, so "Split the rest evenly" stays above it.
  - A share paid in full says "Paid back $30.00".
- **TEST-09** (S-04r v2s): once the hero scrolls away, the page's bar takes the merchant's name and iOS's scroll-edge backing.
- **TEST-11:** S-46a v2 has nothing on the right of Sam's row; S-40u2 says "Nothing to unlink".
- **TEST-12** (T-93n): an Other guess is a question. The card says NEEDS A LOOK and "What was this?" with Answer and a chevron. Needs a look has no "Other?" chip, and the transaction page asks too.
- **TEST-17** (S-03ax): at AX sizes, sheet headers drop the initials circle and the name wraps.
- **TEST-14:** `Pearl.link` (#9C1F4B light) is in the theme but not used yet. It goes on the text links once designBOT confirms the library is published.
- **UI checks:** `testIHadSomeTooOnHowToSplit`, `testTheBarTakesTheMerchantOnceItScrolls`, `testRemoveOnNotSureYetSaysNothingToUnlink`, `testAnOtherGuessIsAQuestion`, `testTheNumberPadGoesAwayAndTheStatusStaysInView`.

### [engBOT → testingBOT] 2026-11-10 · TEST-04 / TEST-05 · Fixed in 43ca9b0
- **H-00r:** the "to sort" card has its icon, "About a minute. Pearl sorted 40 by itself.", the bar, a primary Sort now that opens Quick sort with every open question, and See the list.
- **T-01r:**
  - The month, with Came in on the right.
  - Leftover as the headline, or Over in red only when it's over.
  - The Spent / Saved / Leftover bar and line.
  - "8 need a look · Sort".
  - The list's month totals now carry what was saved.
- **Spending in ink:** spending amounts are ink everywhere. Red stays for over and for errors.
- **Tests:** pytest `tests/test_cash_flow_summary.py`. UI checks: `testSortNowOpensQuickSortFromHome`, `testCashFlowLeadsWithLeftover`.
- **Demo data:** the demo month has no pay in it, so Cash flow shows "Over".

### [engBOT → testingBOT] 2026-11-10 · TEST-18 · Fixed in a2c0808 and 0f256f2 (THL-303)
- **Server:**
  - "I had some too" is kept on a split (`splitting.me`) and restored by Undo.
  - Settling a Not sure yet split locks anyone with a linked payback or cash at exactly what they paid: "Priya's $25.00 is linked. Unlink the payback to change Priya's share."
  - Set your share (`your_share`) can't be more than what's left ("Your share can be up to $45.00", S-47e), and the rest must be given out ("$13.00 left to assign", S-47d).
  - Saving makes it a set split; Undo goes back to Not sure yet. Rule A holds.
- **App:**
  - S-03u2/u3: the toggle on Not sure, on by default, and a You row.
  - S-04u6: You first on the card ("Split 5 ways · Not sure yet").
  - S-40y Set your share, then S-47a–e: WHAT'S LEFT, one unpaid gets it all, several split it evenly and editable, and the error and "left to assign" states. Then S-04u7's toast "Alex owes you $28.00" with Undo.
  - S-45a2: "Alex owes what's left" leads Settle up when she isn't in it.
  - S-45c2/c3: locked rows show their amount or % as text with "Paid back · date · locked", Evenly splits only what's left, and a tap explains the lock.
  - S-14u4: "You and 4 · $75.00 paid · your share not set".
  - S-04u8 / S-46a3: "Everyone has paid. $17.00 stays yours." with You in WHAT CHANGES.
- **Tests:** `tests/test_not_sure_you_row.py` covers the Pizza Nova example, S-47b–e, the lock and S-45a2. The S-45e extra-step tests are replaced by the lock. UI check: `testSetYourShareOnNotSureYet`.
- **Not built yet:**
  - S-47c's method segments (only evenly + typed amounts so far).
  - Shares while someone is locked (the segment is hidden then).
  - S-47f's Toast with Options (an InfoNote explains the lock instead).
  - The Done bar on S-47.
  - A You row on a set split (S-04u7 shows one; S-04r v2 doesn't, see below).
- **Merge note:** this branch and `feat/round1-redesigns` both change `SplitFlow.swift` ("I had some too"), so whichever merges second needs a small conflict resolved.

### [engBOT → designBOT] 2026-11-10 · TEST-03 · Cash flow's note on an unpaid split under Rule A
**Severity:** Minor
**Jira:** THL-291, THL-289   **Figma:** T-01r `1074:356`   **Code:** `finance/txlist.py` (the split note)
**Problem:** under Rule A, an unpaid split's row shows the whole purchase, so "Your share of $127.50 · split with Priya" would be wrong. I changed it to "Split with Priya" (or "Priya paid you back") until everyone has paid, then back to "Your share of …". No frame shows this row.
**Ask:** what should a split row in Cash flow say while people still owe? Is it "Split with Priya · $87.50 to come back", or what I built?

### [engBOT → designBOT] 2026-11-10 · TEST-18 · Two open questions
**Severity:** Minor
**Jira:** THL-303   **Figma:** S-04u7 `1237:24135`, S-04r v2 `1090:1743`, S-47c `1238:24552`
**Problem:**
1. S-04u7 shows a You row on the set split after Set your share, but S-04r v2 (every other set split) has none. I've shown the You row on Not sure yet only.
2. S-47c has Evenly / Amounts / % / Shares. I built evenly-then-typed amounts, and on Settle up I hide Shares while someone is locked: there's no frame for a locked person's share count.
**Ask:** should every set split get a You row? And what does a locked row show on Shares?

### [designBOT → engBOT] 2026-11-10 · TEST-18 · A You row on set splits, Shares when someone is locked, S-47's methods, the lock note
**Status:** Redesigned · Approved — build (applies approved rules) / Awaiting product owner (new look), marked on each
**Jira:** THL-303, THL-289, THL-291   **Figma:** section 18 `1237:23124`
1. **Should every set split get a You row? Yes.**
   - The product owner's rule is "if I am included in the split, then there should be a row for me as well everywhere", so it isn't limited to Not sure yet.
   - **S-04r v3** `1244:25812` / dark `1244:25902` adds You first on the set-split card: "You · Your share · $30.00". It has no •••; tapping it opens Edit split.
   - Leave it out when "I had some too" is off.
   - **Approved — build** (it applies her rule). S-04r v2 stays the reference for everything else on the card.
2. **What does a locked row show on Shares?** Its amount as text, and it isn't part of the shares.
   - **S-45c4** `1244:25980` / dark `1244:26078`: "Paid back · Nov 16 · locked · not in the shares".
   - The shares divide only what's left (the purchase − locked paybacks) across you and the people who haven't paid. Each unlocked row's sub-line says what its shares come to ("1 share · $20.00", "3 shares · owes $60.00").
   - **%** stays as in S-45c3: a share of the whole purchase, with locked rows showing their percentage as text.
   - **Approved — build** (it applies the lock rule). Please show the Shares segment again.
3. **% and Shares on "What was your share?" when several haven't paid:** I recommend not offering them. On that sheet, what's left is a small remainder, and a percentage or share of a remainder is hard to read.
   - **S-47c2** `1244:26164` / dark `1244:26238` uses the library two-option Segmented control: Evenly · Amounts. That's what you built.
   - **Awaiting product owner:** it changes the approved S-47c, which drew four methods. Until she answers, keep what you have.
4. **Tapping a locked row: the toast with Options is required** (S-47f `1239:25202` / `1239:25293`, approved).
   - Her ask was to say how to change it *from that person's ••• options*. On the sheet there's no ••• to reach, so the note explains but leaves her stuck.
   - Options should open that person's S-40u (View the payment, Unlink…) on top of the sheet.
   - The InfoNote is fine until the toast lands.
   - Please also add the Done bar on S-47 (the TEST-16 answer covers every number pad).

### [designBOT → engBOT] 2026-11-10 · TEST-03 · Cash flow's note on a split under Rule A
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-291, THL-289, THL-303, THL-122   **Figma:** T-01r2 `1244:26496` / dark `1244:26635` (section 17)
"Split with Priya" is right as far as it goes. Under Rule A the row shows the whole purchase, so the note should also say why: how much is still coming back. In T-01r2:

| When | The row | The note |
|---|---|---|
| People still owe | −$127.50 | "Split with Priya +2 · $87.50 to come back" (one person: "Split with Priya · $42.50 to come back"; part paid: the remaining amount) |
| Everyone has paid | −$19.79 | "Your share of $59.33 · all paid back" |
| Not sure yet | −$120.00 | "Split 5 ways · not sure yet · $45.00 still counts" |

Shorten the names to "Priya +2" when there are three or more people. Keep what you built until she picks this.

### [engBOT → designBOT] 2026-11-10 · TEST-18 · Accepted, built in 1307951
I checked the new frames and built the ones marked Approved — build on `feat/not-sure-yet-you-row`:
- **S-04r v3** `1244:25812` / `1244:25902`: You first on every split with amounts ("You · Your share · $x"). It has no •••, and tapping it opens Edit split. It's left out when "I had some too" is off.
- **S-45c4** `1244:25980` / `1244:26078`: Shares is back on Settle up › Type amounts. A locked row shows its amount as text and "· not in the shares". The shares divide only what's left, and each unlocked row says what its shares come to ("1 share · $20.00").
- **S-47f** `1239:25202`: tapping a locked row shows the toast with Options, and Options opens that person's S-40u. To do that it closes the sheet first and opens S-40u from the page, because S-40u's actions belong to the page. On S-47 with several unpaid, each payer is its own locked row; with one unpaid, the "Paid back" line taps through when there's a single payer.
- **The S-47 Done bar** (the TEST-16 answer).

Not built, waiting for the product owner: **T-01r2** (Cash flow keeps "Split with Priya") and **S-47c2** (Evenly and Amounts, as built).

UI checks: `testASplitWithAmountsListsYouFirst`, `testSharesWithALockedPayerAndTheLockToast`, and the Done bar in `testSetYourShareOnNotSureYet`. All pass, along with the split pytest files.

### [designBOT → both] 2026-11-10 · TEST-18b · A payer's share differs from what they paid: Pearl asks (option C)
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-303, THL-291   **Figma:** section 19 `1249:26384`, note `1250:27544`
The product owner chose option C. Linked payments stay locked by default. When the split method gives a payer a share that differs from what they paid, Pearl asks once per person in a small Pearl sheet. If a payment already matches its share, Pearl never asks.

Example: $100.00 dinner with you, Sam and Priya. Evenly gives $33.33 each, and the extra cent is yours. Sam sent $20.00 and Priya sent $40.00.

| Frame | Light / dark | One line |
|---|---|---|
| S-48c | `1250:26672` / `1250:26777` | Settle up › Type amounts. Evenly runs over everyone. Sam and Priya stay locked at what they paid, each with "even share $33.33, Pearl asks next". The button is "Next · check Sam and Priya" |
| S-48a | `1249:26385` / `1249:26495` | "Sam paid $20.00 · An even share is $33.33" (1 of 2): **Ask Sam for $13.33**, or **Sam's share is $20.00** (the $13.33 is spread over the others). "Either way, your Allowance doesn't change now." |
| S-48b | `1249:26540` / `1249:26664` | "Priya paid $6.67 more" (2 of 2): **I owe Priya $6.67**, **Priya's share is $40.00** (you and Sam carry less), or **It's a gift**. The callout says only "I owe Priya" changes the Allowance (down $6.67) |
| S-48d | `1250:26870` / `1250:27055` | The split card afterwards: You $33.34; Sam "Paid $20.00 of $33.33 · owes $13.33"; Priya "Paid back $33.33 · you owe Priya $6.67". Toast "Settled · Sam owes $13.33 · you owe Priya $6.67" with Undo, which returns it to Not sure yet |
| S-48e | `1250:27228` / `1250:27332` | Priya's ••• afterwards: "Change what the extra $6.67 is" reopens S-48b for Priya, plus View the payment and Unlink… Sam's ••• gets "Change Sam's share", which reopens S-48a |
| S-14u5 | `1250:27424` / `1250:27490` | Owed to you: Sam $13.33 ("paid $20.00 of $33.33") under OWES YOU, and Priya $6.67 under YOU OWE |

**Where it asks:**
- **Settle up › Type amounts,** on every method: Evenly, Amounts, % and Shares.
- **Use what each paid never asks,** because it uses what was paid.
- **"What was your share?" (S-47) never asks either.** There, payers keep what they paid and only the unpaid share what's left, so a mismatch can't come up. I'd keep it that way.

**One at a time, not one list.** Each answer changes the others' numbers. If you answer "Sam's share is $20.00", the $13.33 spreads over you and Priya, so Priya's share becomes $40.00. That matches what she paid, and Pearl skips her. A single list would show stale numbers. "Back to amounts" leaves without saving. All the answers save together with Settle up, as one action with one Undo.

**"It's a gift" in the parts model.** It should be a part on the deposit, not a change to the split. THL-291's parts model already covers both overpaid answers:
- "I owe Priya": Priya's $40.00 e-Transfer becomes payback $33.33 + "they overpaid" $6.67, which creates You owe $6.67.
- "It's a gift": payback $33.33 + gift $6.67 (Gift income kind, counts as money in).

For cash, the same parts go on the cash payment. engBOT: build both answers by re-splitting the deposit into parts, not by adding new split fields.

**Allowance under Rule A.** The purchase counts in full until paid back, so each answer lands like this:
- **Sam's answers:** don't move it now. "Ask Sam" raises it $13.33 when Sam pays.
- **"I owe Priya":** lowers it $6.67, because that part is no longer a payback; it's money you'll send back.
- **"Priya's share is $40.00":** doesn't move it.
- **"It's a gift":** doesn't move it either; the $6.67 changes from payback to Gift income.

**The locked-row toast (S-47f) on Settle up** now says: "Priya's $40.00 is linked, so it stays. If Priya's share comes out different, Pearl asks you." Options still opens Priya's •••. On S-47, the toast stays as approved.

**Supersedes, once picked:**
- S-45c "Paid $20.00 so far · owes $13.33 after" (`1116:7844` / `1116:7922`)
- the S-45e extra step (`1116:8138` / `1116:8222`)
- S-45c2 / S-45c3 / S-45c4 (`1239:25426` / `1239:25532`, `1239:25626` / `1239:25734`, `1244:25980` / `1244:26078`), which split only what's left. Their result is now the "Sam's share is $20.00" answer.

I'll rename them once she picks.

**For the product owner to decide:**
1. **One person at a time** (recommended), or one sheet listing everyone?
2. **The default highlight:** should the first option be "Ask Sam" and "I owe Priya" (the fair-share answers)? I recommend yes. Nothing is preselected; a tap answers.
3. **"It's a gift" as a deposit part** (recommended), so Gift income appears on Priya's e-Transfer, as THL-291 already does for deposits.
4. **Should S-47 ever ask?** I recommend no, as above.

### [designBOT → coordinator] 2026-11-10 · THL-303 · Wording to paste into Jira
**Status:** Needs product owner (for Jira; I haven't edited it)
**Jira:** THL-303
Add this under THL-303's rules:

> **Settling when a payer's share differs (TEST-18b, option C).** Linked payments (bank, e-Transfer, cash, another app) stay locked at what was paid by default. On Settle up › Type amounts, every method (Evenly, Amounts, %, Shares) works over everyone. If a payer's resulting share differs from what they paid, Pearl asks once per person, one at a time, before saving. If a payment matches its share, Pearl doesn't ask. "Use what each paid" and "What was your share?" never ask.
> - **Underpaid** (Sam paid $20.00, share $33.33): "Ask Sam for $13.33" (share $33.33, Sam shows "Paid $20.00 of $33.33 · owes $13.33" and is in Owed to you) or "Sam's share is $20.00" (Sam stays at $20.00; the $13.33 is spread over the others).
> - **Overpaid** (Priya paid $40.00, share $33.33): "I owe Priya $6.67" (share $33.33; Priya's deposit becomes payback $33.33 + they overpaid $6.67, shown under You owe), "Priya's share is $40.00" (you and the others carry less), or "It's a gift" (share $33.33; deposit becomes payback $33.33 + gift $6.67, Gift income).
> - Each answer recalculates the people still to ask, and anyone who now matches is skipped. All answers save with Settle up as one action, with one Undo back to Not sure yet. Any answer can be changed later from that person's ••• options.
> - **Allowance (Rule A):** the purchase counts in full until paid back. "I owe Priya" lowers it by the overpaid amount; the other answers don't move it until money arrives.
>
> **Acceptance:** $100 split evenly three ways with Sam $20 and Priya $40 linked asks about Sam, then Priya. "Ask Sam" + "I owe Priya" gives Sam owes $13.33, You owe Priya $6.67, Allowance −$6.67. "Sam's share is $20.00" gives Priya a $40.00 share and skips her question.

### [designBOT → engBOT] 2026-11-10 · TEST-03 / TEST-18 · Two decisions applied in Figma
**Status:** Approved — build (T-01r2) · Rejected (S-47c2)
**Jira:** THL-291, THL-289, THL-303, THL-122   **Figma:** T-01r2 `1244:26496` / `1244:26635`; S-47c2 `1244:26164` / `1244:26238`; S-47c `1238:24552` / `1238:24728`
- **T-01r2 is approved and relabelled "Approved — build".** Cash flow's split note becomes:
  - "Split with Priya +2 · $87.50 to come back" while people owe
  - "Your share of $59.33 · all paid back" once everyone has paid
  - "Split 5 ways · not sure yet · $45.00 still counts" while it's Not sure yet
- **S-47c2 is rejected and relabelled "Superseded/Rejected".** "What was your share?" keeps all four methods (Evenly, Amounts, % and Shares), as in the approved S-47c. For % and Shares, follow the Settle up rule:
  - **%** is of the whole purchase. Your typed share and the locked payers show their percentage as text, and only the unpaid rows take input.
  - **Shares** divide only what's left after the payers and your share, across the unpaid. Locked rows read "· not in the shares", as on S-45c4.
- Section 19 (TEST-18b) is still waiting for her. The frames it would supersede (S-45c, S-45e, S-45c2/c3/c4) keep their names until she picks.

### [designBOT → engBOT] 2026-11-10 · TEST-18b · Approved — build: final frames
**Status:** Approved — build
**Jira:** THL-303, THL-291   **Figma:** section 19 `1249:26384`, note `1250:27544`
The product owner approved option C and said yes to all four questions:
1. Ask one person at a time.
2. "Ask Sam" and "I owe Priya" come first, with nothing preselected (as drawn).
3. "It's a gift" is a part on the deposit: payback + gift. Likewise, "I owe Priya" is payback + they overpaid.
4. "What was your share?" (S-47) never asks.

Final frames (light / dark):

| Frame | Light / dark |
|---|---|
| S-48c Settle up › Type amounts, before asking | `1250:26672` / `1250:26777` |
| S-48a Sam paid less (1 of 2) | `1249:26385` / `1249:26495` |
| S-48b Priya paid more (2 of 2) | `1249:26540` / `1249:26664` |
| S-48d Split card afterwards, with the Undo toast | `1250:26870` / `1250:27055` |
| S-48e Priya's ••• afterwards | `1250:27228` / `1250:27332` |
| S-14u5 Owed to you / You owe | `1250:27424` / `1250:27490` |
| **S-47f2** Settle up, tapping a locked row (new) | `1253:27150` / `1253:27206` |

S-47f2's toast says: "Priya's $40.00 is linked, so it stays. If Priya's share comes out different, Pearl asks you." Options opens Priya's •••. S-47f stays as approved for "What was your share?".

**Marked "Superseded by S-48…":**
- S-45c `1116:7844` / `1116:7922`
- S-45e `1116:8138` / `1116:8222`
- S-45c2 `1239:25426` / `1239:25532`
- S-45c3 `1239:25626` / `1239:25734`
- S-45c4 `1244:25980` / `1244:26078`

On Settle up, every method now works over everyone. Payers stay locked at what they paid until S-48a/b's answer, so the "only what's left" maths from S-45c2–c4 is replaced, along with S-45e's extra step.

The coordinator is pasting the THL-303 wording into Jira (my entry above).


### [engBOT → testingBOT] 2026-11-10 · T-01r2 and S-47's four methods · Built in 94e8389
This is on `feat/not-sure-yet-you-row`, after testingBOT's round-2 commit 1307951.
- **T-01r2:** Cash flow's split note is now one of three:
  - "Split with Priya +2 · $87.50 to come back" while people owe (two people are named, "Priya and Sam"; with three or more it's "Priya +2"). The amount drops as each payback comes in.
  - "Your share of $59.33 · all paid back" once everyone has paid.
  - "Split 5 ways · not sure yet · $45.00 still counts" while it's Not sure yet (you count among the ways when you're in it).
  - Tests: the `TestCashFlowNote` pytest cases in `tests/test_split_rule_a.py`; `test_splits` and `test_what_was_this` now expect the new words.
- **S-47c** (S-47c2 rejected): "What was your share?" with several people unpaid offers Evenly, Amounts, % and Shares.
  - % is of the whole purchase, and only the unpaid rows take input.
  - Shares divide only what's left across the unpaid.
  - Payers show as locked rows.
  - UI check: `testSetYourShareOnNotSureYet` switches through all four, and each must add up.

### [engBOT → testingBOT] 2026-11-10 · TEST-18b · Built in 8788188 (server) and 9452db8 (app) (option C)
This is on a new branch, `feat/settle-mismatch`, stacked on `feat/not-sure-yet-you-row`.
- **Server:** on Settle up a payer's share may differ from what they paid, but only as she answered.
  - A share over what they paid saves only with `ask` ("Ask Sam for $13.33").
  - A share under what they paid saves only with `extra`: "they overpaid" (You owe) or a gift (a gift part on the deposit, THL-291's parts model).
  - Otherwise the server refuses: "Sam paid $20.00. Ask Sam for $13.33, or make Sam's share $20.00." / "Say what Priya's extra $6.67 is."
  - "What was your share?" (S-47) still never asks: payers stay exactly as paid.
  - Everything saves with one Undo back to Not sure yet.
- **App** (S-48c, S-48a, S-48b, S-48d, S-47f2):
  - On Settle up › Type amounts, Evenly and Shares run over everyone. A payer's row shows what they paid as text, with "locked · even share $33.33, Pearl asks next".
  - The button reads "Next · check Sam and Priya" and the line "2 to check: Sam and Priya".
  - Pearl asks one person at a time (S-48a / S-48b, "Back to amounts" leaves without saving). Each answer recalculates, and anyone who then matches is skipped.
  - The toast reads "Settled · Sam owes $13.33 · you owe Priya $6.67", with Undo.
  - Tapping a payer shows S-47f2's toast ("…is linked, so it stays. If Priya's share comes out different, Pearl asks you.") with Options.
  - On Amounts and %, payers stay at what they paid, so nothing differs. On %, a payer's percent is what they paid.
- **Tests:**
  - `tests/test_settle_mismatch.py` covers the $100 example: Ask Sam + I owe Priya (Sam owes $13.33, You owe Priya $6.67, Allowance −$6.67, Undo back to Not sure yet); Sam's share $20.00 (Priya then matches and isn't asked; Allowance unchanged); Priya's share $40.00 + Ask Sam (unchanged); It's a gift; unanswered differences refused; Use what each paid never asks.
  - The S-45e tests that the lock had replaced are back as TEST-18b cases. The S-47 lock test still holds.
  - UI check: `testSettleUpAsksWhenAPayersShareDiffers`.
- **Not built yet:** S-48e, changing an answer later from the person's •••. It needs a way to swap an existing gift or overpaid part on a saved split, which the server can't do yet; I'll build it next if you want it. S-14u5 uses the existing Owed to you lists (Sam under owes you, Priya under You owe).

### [engBOT → designBOT] 2026-11-10 · TEST-18b · "It's a gift" moves the Allowance
**Severity:** Minor
**Jira:** THL-303, THL-291   **Figma:** S-48b `1249:26540`   **Code:** `finance/api.py` (_settle_extra), `tests/test_settle_mismatch.py::test_its_a_gift`
**Problem:** S-48b's callout says only "I owe Priya" changes the Allowance. As built, "It's a gift" lowers it $6.67 too. The purchase counts $46.67 (your $33.34 and Sam's $13.33) instead of $40.00. The $6.67 becomes Gift income on Priya's deposit, and the Allowance is worked out from take-home pay, so Gift income doesn't add to it. Example: $100 dinner, Sam $20, Priya $40 → the Allowance goes from $3,600.00 to $3,593.33 after "Ask Sam" + "It's a gift".
**Ask:** should a gift on a payback add to the Allowance (a server change), or should the callout say both answers lower it? Until then the test expects what's built.

### [designBOT → engBOT] 2026-11-10 · TEST-18b · "It's a gift" lowers the Allowance too
**Status:** Redesigned · Approved — build (product owner's decision)
**Jira:** THL-303, THL-291   **Figma:** S-48b `1249:26540` / dark `1249:26664`, note `1250:27544`
The product owner decided that "It's a gift" lowers the Allowance by the difference, the same as "I owe Priya": $6.67 in the example. The Allowance comes from take-home pay, so gift income doesn't add to it.

- **S-48b's callout now reads:** "“I owe Priya” and “It’s a gift” lower your Allowance by $6.67. “Priya’s share is $40.00” doesn’t change it."
- **The section 19 note** now says the same.
- **This corrects my TEST-18b entry above.** There I said a gift doesn't move the Allowance.
- **For the THL-303 wording:** the Allowance line should read: "I owe Priya" and "It's a gift" lower it by the overpaid amount; the other answers don't move it until money arrives.

Nothing else changes. The gift is still a part on the deposit (Gift income kind), and section 19 stays Approved — build.

---

### [testingBOT] 2026-11-10 · Round 2 start
- **Builds:** two detached worktrees of my own, Debug, Xcode 26.6.
  - **A** = `43ca9b0` (`feat/sort-now-cashflow`): the round-1 fixes, Rule A, the Pearl confirmation sheets, the round-1 redesigns, Sort now and the Cash flow summary. Used for TEST-01 to TEST-17.
  - **B** = `1307951` (`feat/not-sure-yet-you-row`): the round-1 fixes, Rule A and TEST-18 with its follow-ups. Used for TEST-18. (engBOT's later commits 94e8389, 8788188 and 9452db8 are not in B, so S-47's four methods, T-01r2 and TEST-18b are not tested here.)
- **Simulator:** one at a time, as the product owner asked: the stock iPhone 16 (iOS 26.5). A and B ran one after the other on it, on my own ports (5061 and 5071), so engBOT's runs on 5051 were never touched. Early runs on two new simulators were thrown away: the machine was overloaded and taps didn't land.
- **Data:** demo data only, `DATABASE_URL` removed, a fresh temp database per journey. On top of Round 1's seed: **Pizza Nova $120.00** on the Amex and three **$25.00 e-Transfers** in (Priya Shah, Sam Lee, Jo Park). Alex never pays.
- **Journeys:** `ios/PearlUITests/Round2JourneysUITests.swift` (new; the Pizza Nova journeys, the Rule A journey with the Allowance checked at every step, and the re-tests), plus Round 1's `PersonJourneysUITests.swift` for the regressions. Both are in each worktree, made with `make_project.py`. The runner is `ios/tools/run_journeys.py` with `PEARL_TBOT_PORT` and `PEARL_TBOT_SIM`, and the Pizza Nova seed.
- **Server checks:** the same steps with `curl` against a throwaway demo server on each commit: `round2/curl-a-ruleA.txt` and `round2/curl-b-test18.txt`.
- **Screenshots:** `/private/tmp/claude-501/-Users-mariapapadimitriou-GitHub-finance/47dab3d8-05be-4db9-b3fc-84667327b935/scratchpad/testing-run/round2/`. Paths below are relative to it: `a/`, `a2/`, `a3/`, `a4/` and `a-ax/` are commit A, `b/`, `b-ax2/` and `b-pretick-run/` are commit B, and `a-probe/` is the reopen check for TEST-19. Each `.png` has its accessibility tree in a `.txt` beside it.
- **Not tested, as asked:** the Cash flow split note (T-01r2), % and Shares on "What was your share?", and the lock rule for payers who paid more or less than their share.

### [testingBOT] 2026-11-10 · TEST-01 · Fixed
In dark mode the Quick sort card is dark with light words, Skip is a dark circle, and Needs a look's chosen chip "All · 9" is a light capsule with dark words. Everything on the card reads. (`a/testQuickSortAndNeedsALookInDark-04-dark-quick-sort.png`, `a/testQuickSortAndNeedsALookInDark-03-dark-needs-a-look-scrolled.png`)

### [testingBOT] 2026-11-10 · TEST-02 · Fixed
Settle up › Type amounts opens on "Settle up · type amounts" with Gusto **−$127.50**, the method segments, "I had some too", and Priya "Paid $42.50 so far". "Who was it with?" never appears. (`a2/testNotSureYetThenSettleUpByTyping-07-light-type-amounts.png`)

### [testingBOT] 2026-11-10 · TEST-03 · Fixed (Rule A)
Gusto $127.50 split by amounts (Priya $42.50, Sam $30.00, Jo $15.00, you $40.00). The Allowance was read from the server after each step, in the app journey and again with curl:

| Step | Allowance | Moved | Rule A says |
|---|---|---|---|
| Before | $15,073.58 | | |
| Split saved | $15,073.58 | 0 | The whole $127.50 still counts |
| Priya's $42.50 e-Transfer linked | $15,116.08 | +$42.50 | Up by the payback |
| Sam's $30.00 cash | $15,146.08 | +$30.00 | Up by the payback |
| Let Jo's $15.00 go | $15,146.08 | 0 | No change |
| Undo let it go | $15,146.08 | 0 | No change |

The purchase's `amount` goes 127.50 → 55.00 as the paybacks come in, and Owed to you ends at Jo $15.00, with Sam (cash) and Priya under PAID BACK THIS MONTH. The page's hero is the whole −$127.50 with "Your share $40.00" under it. (`a/testRuleAWhenFriendsPayBackForDinner-*.png`, `a/testRuleAWhenFriendsPayBackForDinner-11-light-owed-to-you.png`, `curl-a-ruleA.txt`)

### [testingBOT] 2026-11-10 · TEST-04 · Fixed
Home has the card icon, "9 to sort", "About 2 minutes. Pearl sorted 184 by itself.", the bar, a filled **Sort now** and **See the list**. Sort now opens Quick sort straight away, and See the list opens Needs a look. "Review one by one" is gone. (`a/testSortFromHomeWithSortNow-01-light-home.png`, `a/testSortFromHomeWithSortNow-02-light-quick-sort-first-card.png`)

### [testingBOT] 2026-11-10 · TEST-05 · Fixed (as designed), one thing for designBOT
Spending is in ink everywhere I went: Cash flow rows, the transaction hero and the Quick sort card. T-01r's summary is built: November with "Came in $0" on the right, the headline, the bar, "Spent $2,099 · Saved $0 · Over $2,099", and "9 need a look · Sort". (`a/testCashFlowSummaryAndLeaveOut-01-light-cash-flow.png`)
Still worth a look (designBOT): early in the month, before pay has come in, the headline is a red **Over $2,099** while Home's orb says **$15,074 left in November**. The red is what T-01r specifies, but these are the two biggest numbers in the app and they disagree. Maybe "Over" should wait until the expected pay has arrived, or the headline could compare against expected pay as the Allowance does. Not filed as a new finding.

### [testingBOT] 2026-11-10 · TEST-06 · Fixed (on the sheets I could reach)
No stock alert or action sheet appeared anywhere in Round 2. The accessibility trees list no `Alert` or `Sheet` elements. Sign out is a Pearl sheet: "SIGN OUT · Sign out on this iPhone?", "Pearl stays as it is. To come back, you'll sign in again.", Sign out and Stay signed in (`a2/testCashFlowSummaryAndLeaveOut-07-light-sign-out-sheet.png`). Cash flow › Select › Spotify › Leave out opens T-77c as a Pearl sheet: "LEAVE OUT · 1 SELECTED · Leave out 1 transaction?", "It's left out of all your numbers. You can put it back from its page.", a Why? field and Cancel (`a4/testCashFlowSummaryAndLeaveOut-05-light-leave-out-sheet.png`).
I didn't reach Delete (manual transactions only), Reset Pearl, the device sheets, the rule and tag sheets, Nickname/Name or IB-03.

### [testingBOT] 2026-11-10 · TEST-07 · Fixed
With the Why? field empty, **Leave out** is off, and "Say why, so you can tell later." sits right under the field (`a4/testCashFlowSummaryAndLeaveOut-05-light-leave-out-sheet.png`). My journey couldn't type into the sheet's field, so I didn't see a save go through in the app. engBOT's pytest covers the server side.

### [testingBOT] 2026-11-10 · TEST-08 · Fixed
"I had some too" sits under the people on How to split. On Amounts with Priya $40 and Sam $30:
- **On:** "$57.50 left · stays yours", and Save is on.
- **Off:** your row goes, the line says "$57.50 left to assign", and Save is off.
- **On again:** your row comes back.

(`a/testIHadSomeTooAndTheNumberPad-04-light-short-stays-yours.png`, `-05-light-i-had-some-too-off.png`, `-07-light-rest-evenly.png`)

### [testingBOT] 2026-11-10 · TEST-09 · Still broken
Once a split page scrolls, the content still runs under the clock and the Back chevron with nothing behind them, and the new inline title is drawn on top of the content, so the two overlap:
- "Split with 2 · Not sure yet" is crossed by "Gusto" and the chevron (`a-probe/testNotSureYetCardAfterReopening-05-light-reopened-scrolled.png`).
- The "What was this?" row reads "What was thiGusto" under the clock (`a/testRuleAWhenFriendsPayBackForDinner-08-light-let-jo-go-sheet.png`).
- At the largest text size, "Nopa Restaurant" sits over Priya's row (`a-ax/testSplitADinnerAtTheLargestTextSize-06-light-split-card.png`).
- In dark mode it's the same (`b/testPizzaNovaThreePaidAndISetMyShare-26-dark-card-dark.png`).

The title appears, but the scroll-edge backing S-04r v2s draws behind it does not. My guess is that the page's custom background or the ScrollView sits outside the navigation bar's scroll-edge effect.

### [testingBOT] 2026-11-10 · TEST-10 · Fixed (two of three, as agreed)
Quick sort and every list say **Corner Store** and **Northshop** (they were "Corner" and "Unknown"). I accept "Blue" as engBOT's won't-fix. (`a/testSortFromHomeWithSortNow-02-light-quick-sort-first-card.png`)

### [testingBOT] 2026-11-10 · TEST-11 · Fixed
On a Not sure yet split, Priya's ••• reads "Remove Priya · Nothing to unlink", and That's everything? has "Sam · Won't show as owing" with nothing on the right. (`a2/testNotSureYetThenSettleUpByTyping-03-light-S-40u2-options.png`, `a2/testNotSureYetThenSettleUpByTyping-08-light-thats-everything-sheet.png`)

### [testingBOT] 2026-11-10 · TEST-12 · Fixed
An "Other" guess is now a question: NEEDS A LOOK, "What was this?", "Pearl couldn't place this one. Answer opens What was this?", with Skip and Answer. Needs a look has no "Other?" chip. (`a/testSortFromHomeWithSortNow-02-light-quick-sort-first-card.png`)
Small leftover: Cash flow's list still shows the **"Other?"** chip on Corner Store, and VoiceOver hears "Pearl's guess: Other" on Gusto, Corner Store, Northshop and Makersmkt (`a4/testCashFlowSummaryAndLeaveOut-04-light-spotify-selected.png`, `a3/testCashFlowSummaryAndLeaveOut-03-light-spotify-found.txt`). T-93n says the chip should go there too.

### [testingBOT] 2026-11-10 · TEST-13 · Fixed (see TEST-20)
"Which payment was it?" names the sender as Cash flow does ("Priya Shah · Nov 9"). The joint card's page shows "—" and "Owing". But that same sheet now suggests the wrong people's payments; that's TEST-20. (`a/testRuleAWhenFriendsPayBackForDinner-05-light-which-payment-Priya.png`)

### [testingBOT] 2026-11-10 · TEST-14 · Partly fixed
- **Fixed:** the Cash flow tab's value is "9 to sort", and VoiceOver hears it. The hit-region audit found no small tap areas on the transaction page, How to split, the split card, Person options, S-40y, S-47c or S-04u7.
- **Still flagged:** OPTIONS and DETAILS say "Dynamic Type font sizes are partially unsupported" on every split page (A and B). On B, S-40y's overline "PIZZA NOVA · NOT SURE YET" is **Text clipped**.
- **New flag:** "Label not human-readable" on the hero amounts ("−$127.50", "−$120.00") and on How to split's amount fields ("$42.50"). I think it's the U+2212 minus and the field values having no label. An `accessibilityLabel` such as "spent 127 dollars 50" would fix both.
- **Couldn't check:** the audit on Home and Cash flow timed out ("Audit failed to complete in time"), so I can't confirm Calendar's 44 pt there.
- **Waiting:** `Pearl.link` isn't applied yet. "See everyone who owes you" still reads "Contrast nearly passed" / "failed".

(`run-a.log` and `run-b.log`, lines `JOURNEY note: AUDIT`)

### [testingBOT] 2026-11-10 · TEST-15 · Fixed
"Let Jo's $15.00 go?" says "Your Allowance doesn't change.", and now it doesn't: the server shows $15,146.08 before and after, and again after Undo. (`a/testRuleAWhenFriendsPayBackForDinner-08-light-let-jo-go-sheet.png`)

### [testingBOT] 2026-11-10 · TEST-16 · Partly fixed
- **Fixed:** the Done bar is on the number pad (Amounts, Change share, S-47). The split meter and "$87.50 of $127.50" are there. The status line is ink. Change Sam's share shows "That's $70.00 too much". Your field shows the amount it will save.
- **Still broken:** while the pad is up on How to split, the disabled **Save** is drawn on top of the "I had some too" card, and the meter and status line are behind the keyboard. A person typing "100" for Priya can't see "too much" until she taps Done. At the largest text size, Save covers the meter, and the "$59.33" total sits under the button. (`a/testIHadSomeTooAndTheNumberPad-02-light-too-much-with-the-pad-up.png`, `a-ax/testSplitADinnerAtTheLargestTextSize-05-light-S-03-header.png`)

### [testingBOT] 2026-11-10 · TEST-17 · Fixed
At accessibility-extra-large, How to split drops the initials circle, "Nopa Restaurant" is whole, and the method row becomes "How to split · Evenly ›". (`a-ax/testSplitADinnerAtTheLargestTextSize-05-light-S-03-header.png`) Note that B doesn't have this fix, so its header still shows "P…" (`b-ax/testPizzaNovaInDarkMode-03-dark-S-03u2-not-sure-with-you.png`). A new problem at this size is TEST-22.

### [testingBOT] 2026-11-10 · TEST-18 · Works end to end, with three bugs (TEST-19, TEST-20, TEST-23)
The product owner's Pizza Nova story on B, with real taps: $120.00 split five ways, Priya, Sam and Jo pay $25.00 each by e-Transfer, she sets $17.00, and Alex owes $28.00. The server agrees at every step (`curl-b-test18.txt`).

| What | Seen | Result |
|---|---|---|
| S-03u2 You row | "You · Your share · set it any time, or never", with "I had some too" on by default | ✓ `b/testPizzaNovaThreePaidAndISetMyShare-03` |
| S-04u6 card | "Split 5 ways · Not sure yet", You first ("Your share · not set yet" with •••), then Priya, Sam, Jo and Alex "Nothing yet" | ✓ but only after reopening the page (TEST-19) `-05`, `-12` |
| Allowance while Not sure yet | $15,073.58 → +25 → +25 → +25 → $15,148.58 | ✓ |
| S-14u4 Owed to you | "$0.00 · 1 split not settled", "Pizza Nova · You and 4 · $75.00 paid · your share not set", "Not in the total until settled" | ✓ `-13` |
| S-40y | "You · Your share isn't set" → Set your share | ✓ `-14` |
| S-47a | empty field, "You can leave it and set it later.", Save off | ✓ `-15` |
| S-47e, too big | $50 → "Your share can be up to $45.00", Save off | ✓ `-16` |
| S-47b | $17 → WHAT'S LEFT $120.00 − $75.00 (Priya, Sam and Jo · linked, locked) − $17.00, "Alex owes you $28.00", "Save · Alex owes $28.00", the Rule A note | ✓ matches Figma S-47b `-17` |
| Tapping the locked line (three payers) | nothing happens | ✗ see below |
| Save | toast "Alex owes you $28.00" with Undo; set split You $17, Alex $28; Allowance unchanged | ✓ `-19`, `-22` |
| Undo | back to Not sure yet, "not set yet", Allowance unchanged | ✓ `-20` |
| S-14u3 Owed to you | Alex $28.00, in the total | ✓ `-23` |
| Alex pays $28.00 cash | Allowance +$28.00; $17.00 stays counted | ✓ `-25` |
| Two unpaid (Jo, Alex), S-47c | Evenly $26.50 each, "Adds up to $120.00 ✓"; Priya and Sam each a locked row | ✓ `b/testPizzaNovaTwoStillOwe-07` |
| S-47d | Jo 20, Alex 20 → "$13.00 left to assign", Save off; Alex 40 → "That's $7.00 too much", Save off | ✓ `-08`, `-09` |
| S-47f | tap Priya's locked row → toast "Priya's $25.00 is linked. Unlink the payback to change Priya's share." with Options → Priya's S-40u with View the e-Transfer and **Unlink…** | ✓ `-10`, `-11` |
| Settle up, two unpaid, every method | Evenly: you $23.34, Jo and Alex $23.33, payers locked at $25.00. Amounts, % and Shares open with the payers as text | ✓ but Shares says "53 shares" (TEST-23) `-15`…`-18` |
| "I had some too" off | no You row on S-03u3, the card, S-40 or anywhere; no "Options for you" | ✓ `b/testPizzaNovaWithoutMe-04`, `-06` |
| S-45a2 | "Alex owes what's left · $45.00 · the purchase less what's been paid back" leads; "Use what each paid · Alex pays nothing; the $45.00 stays yours"; tap → toast "Alex owes you $45.00" with Undo; Owed to you Alex $45.00; Allowance unchanged | ✓ `b/testPizzaNovaWithoutMe-11`, `-13`, `-14` |
| Everyone pays, share never set, S-46a3 | That's everything? "Everyone has paid. $17.00 stays yours.", You $17.00 · what's left, "Priya, Sam, Jo and Alex · Paid back $103.00", Dining $17.00, Allowance No change | ✓ `b/testPizzaNovaEveryonePaidThenThatsEverything-11` |
| Dark mode | S-03u2, the card, S-40y, S-47c, the S-47f toast and S-04u7 all read well | ✓ `b/testPizzaNovaInDarkMode-*` |
| Largest text | With the methods behind "How to split · Evenly ›" (S-03u), Not sure → the You row → link → S-40y → S-47 all work at accessibility-extra-large in dark. Two problems: the toast's words outgrow it ("Sam paid back $25.00" spills over the page, TEST-22), and on B the header initials still read "P…" (TEST-17's fix isn't on B) | ✓ mostly `b-ax2/testPizzaNovaInDarkMode-*` |
| Audit | no hit-region problems; see TEST-14 for the rest | ✓ |

**Differences from the frames (Minor):**
- **The locked line doesn't respond (S-47f).** With three payers and one unpaid, WHAT'S LEFT folds them into one row ("Priya, Sam and Jo · linked, locked"). Tapping it does nothing, so the way to Unlink that S-47f promises is missing in her exact case (`b/testPizzaNovaThreePaidAndISetMyShare-18`). engBOT's note says this is deliberate. I'd still open a small chooser (or each person's S-40u) rather than nothing.
- **S-04u8 isn't there once everyone has paid.** After Alex's cash, the card still says "You · Your share · not set yet" with no amount, and That's everything has no "Everyone has paid. $17.00 stays yours." under it (`b/testPizzaNovaEveryonePaidThenThatsEverything-10`). Figma S-04u8 `1237:24579` has both. The sheet itself (S-46a3) is right.
- **The S-47e error state contradicts itself.** "Alex owes you $0.00" and "When Alex pays, your $17.00 is what stays counted" stay on screen while the field says the share is too big (`b-pretick-run/testPizzaNovaThreePaidAndISetMyShare-17`).

### [testingBOT → engBOT] 2026-11-10 · TEST-19 · After Save split on Not sure yet, the page still shows the purchase unsplit
**Kind:** Bug   **Severity:** Major
**Where:** T-03 transaction page after S-03u / S-03u2 › Save split, and after S-46a That's everything   **Figma:** S-04u6 `1237:23743`   **Jira:** THL-303   **Code:** `ios/Pearl/Views/Transactions/TransactionDetailView.swift` (the page's reload after `SplitSheet` saves with mode "unknown")
**Steps:**
1. Gusto (A) or Pizza Nova (B) → Split with others → Priya, Sam (and Jo, Alex) → Not sure → Save split.
2. Look at the page.
3. Go back to Cash flow and open the purchase again.
**Saw:**
- After Save split, the toast says "Split with 4 · not sure yet.", but the page still offers **Split with others**. There's no split card, no You row and no •••. It stays like this for as long as I waited (15 s).
- The server has the split (`PUT …/split` 200, and the next `GET` returns `splitting.mode = "unknown"`).
- Going back and opening the purchase again shows the card. It happens on both commits and in every Pizza Nova journey (the journeys now reopen the page to carry on; `run-b.log` says "STALE page after Save split" six times).
- That's everything has the same problem: after "Split closed · Undo", the page still shows Settle up and That's everything.

(`a/testNotSureYetThenSettleUpByTyping-03-light-S-40u2-options.png`, `a-probe/testNotSureYetCardAfterReopening-02-light-saved.png` vs `-04-light-reopened.png`, `b-stale-first-run/testPizzaNovaThreePaidAndISetMyShare-05-light-S-04u6-card-with-you-first.png`, `b/testPizzaNovaEveryonePaidThenThatsEverything-13-light-closed-card.png`)
**Expected:** S-04u6 right after Save split, as an amount split already does. A person who just split a dinner and sees "Split with others" again will split it a second time.
**Advice:** refresh `t` from the server reply (or reload) on the Not sure yet save and close paths, the way the amount path does. A UI check that taps "Options for Priya" within 3 s of Save split, without reopening, would catch it. I'm not sure why `testSetYourShareOnNotSureYet` passes; it may be timing, since my runs were on a busy machine with the 0.3 s proxy.

### [testingBOT → engBOT] 2026-11-10 · TEST-20 · "Which payment was it?" suggests and pre-ticks someone else's money
**Kind:** Bug   **Severity:** Major
**Where:** S-06rb Which payment was it?   **Figma:** S-06rb `1091:2219`   **Jira:** THL-291 (paybacks), THL-122 (names), THL-303 (locked once linked)   **Code:** `finance/api.py` `list_paybacks` (the candidates' order and `likely`), the sheet's default selection in `SplitFlow.swift`
**Steps:**
1. Pizza Nova Not sure yet with Priya, Sam, Jo and Alex. Priya's ••• → Mark paid back → Bank or e-Transfer.
2. Gusto split by amounts: Priya's ••• → Mark paid back → Bank or e-Transfer.
**Saw:**
- **On Not sure yet ("From Priya, any amount"):** the only SUGGESTED row is **Sam Lee · Nov 8 · Amount matches · +$30.00, already ticked**. Priya's own $25.00 is under OTHER MONEY IN, and the button reads **Link $55.00**. A person who taps Link credits Sam's $30.00 to Priya. Under the lock rule she then can't fix the split without unlinking. That run went on to "Paid back $105.00" and "Your share can be up to $15.00" (`b-pretick-run/testPizzaNovaThreePaidAndISetMyShare-06-light-which-payment-Priya.png`, `-17`).
- **The same with Jo:** Sam Lee's $30.00 is pre-ticked again (`run-b.log`, "PRE-TICKED for Jo").
- **On an amount split ("From Priya, $42.50"):** Sam Lee $25.00 and Jo Park $25.00 are SUGGESTED with "**Amount matches**", which they don't (`a/testRuleAWhenFriendsPayBackForDinner-05-light-which-payment-Priya.png`, `b/testFriendsPayBackForDinner-07-light-priya-payment-picked.png`).
**Expected:** suggestions lead with the person's own payments (their name is on the e-Transfer). "Amount matches" only when it does. Nothing pre-ticked unless it's that person's and the amount fits.
**Advice:** rank by sender name first, then amount. On Not sure yet there's no amount to match, so say "From Priya" instead of "Amount matches". Pre-tick only a row whose `party` matches the person. Add a pytest with two senders sending the same amount.

### [testingBOT → both] 2026-11-10 · TEST-21 · Raising one person's share can't be saved: your share doesn't give way
**Kind:** Confusion   **Severity:** Minor
**Where:** S-03re Change Sam's share (A and B), on a plain split and on Split my part   **Figma:** S-03re `1092:2360`   **Jira:** THL-291
**Steps:**
1. Costco $100 joint (her part $50.00), split evenly three ways: you $16.68, Priya $16.66, Sam $16.66.
2. Sam's ••• → Change Sam's share → 20.
**Saw:** "That's $3.34 too much" and Save is off. Your field stays at 16.68. To give Sam $20 she has to work out and type her own $13.34 (`a/testSplitMyPartOfAJointPurchase-20-light-joint-share-changed.png`, `b/testSplitMyPartOfAJointPurchase-20-light-joint-share-changed.png`). The same happens on Gusto with Sam at 100 (`a/testIHadSomeTooAndTheNumberPad-09-light-change-sam-too-much.png`).
**Expected:** the sheet is called "Change Sam's share", so changing Sam should be enough, as long as your share can absorb it. Lowering Sam already works that way ("$x left · stays yours").
**Advice:** on Change their share, treat your row as what's left (shown, not typed) unless she edits it. Only say "too much" when your share would go below zero.

### [testingBOT → both] 2026-11-10 · TEST-22 · At the largest text size, amounts break in the middle, Save covers the total and the toast spills
**Kind:** Bug   **Severity:** Minor
**Where:** S-04r split card and S-03 How to split at accessibility-extra-large (A)   **Jira:** designBOT rules: Dynamic Type
**Steps:**
1. Text size accessibility-extra-large. Nopa → Split with others → Priya, Sam → Save.
**Saw:**
- On the card, Priya's and Sam's amounts wrap as "$19." over "77" (`a-ax/testSplitADinnerAtTheLargestTextSize-06-light-split-card.png`).
- On How to split, Save sits on the meter, and the "$59.33" total peeks out under the button (`a-ax/testSplitADinnerAtTheLargestTextSize-05-light-S-03-header.png`).
- A toast's words outgrow it: "Sam paid back $25.00 · Undo" spills over DETAILS and Add a note (B, dark: `b-ax2/testPizzaNovaInDarkMode-08-dark-card-dark.png`).
- The rest holds up: the header wraps, the method row works, and S-40a and S-47 scroll.
**Expected:** an amount never breaks inside the number, and the status line stays readable above Save.
**Advice:** `lineLimit(1)` + `minimumScaleFactor` on amounts (or move the amount under the name at AX sizes, as S-03ax does for the header), and keep the meter in the scroll content above the footer.

### [testingBOT → engBOT] 2026-11-10 · TEST-23 · Settle up › Shares says "53 shares" for three shares
**Kind:** Bug   **Severity:** Minor
**Where:** S-45c4 Settle up › Type amounts › Shares, with locked payers (B)   **Figma:** S-45c4 `1244:25980`   **Jira:** THL-303
**Steps:**
1. Pizza Nova Not sure yet, five ways. Priya and Sam linked at $25.00 each.
2. Settle up → Type amounts → Shares.
**Saw:** You, Jo and Alex have 1 share each ($23.34, $23.33, $23.33), and Priya and Sam are "locked · not in the shares". The line under them says "**53 shares** · adds up to $120.00 ✓" (`b/testPizzaNovaTwoStillOwe-18-light-settle-Shares.png`).
**Expected:** "3 shares · adds up to $120.00 ✓".
**Advice:** the count seems to include the locked rows' amounts (25 + 25 + 3). Count only the unlocked rows' shares.

### [testingBOT] 2026-11-10 · Round 2 regressions: Quick sort, Needs a look, joint Split my part
- **Quick sort on B** (pre-T-93n): Yes, Undo puts the same card back, Skip works, a category tile gives "YOUR CHOICE · Northshop · Groceries?", and "9 to sort" goes to 6 with the tab value "6 to sort". No regression. (`b/testSortWhatPearlGuessedFromHome-*`)
- **Quick sort on A:** all nine cards are now NEEDS A LOOK questions (T-93n). Even the e-Transfers ask "What was this?". Answer opens What was this?, and Skip moves on ("9 left" → "8 left"). Nothing in the demo seed has a real guess any more, so Yes and Undo weren't exercised on A. That comes from the data, not a bug. (`a/testSortFromHomeWithSortNow-*`)
- **Needs a look,** light and dark, on A and B: the chips, the list, the Quick sort card and What was this? from the card all work. No regression. (`a/testQuickSortAndNeedsALookInDark-*`, `b/testLookThroughNeedsALook-*`)
- **Joint Split my part,** on A and B: Shared with → Alex 50/50, then Costco $100 → Split my part three ways gives **$16.68 / $16.66 / $16.66** with "Alex's $50.00 stays theirs · joint 50/50", as in Round 1. On B the set split now has You first ("You · Your share · $16.68", S-04r v3). No regression, apart from TEST-21. (`a/testSplitMyPartOfAJointPurchase-*`, `b/testSplitMyPartOfAJointPurchase-17-light-joint-split-card.png`)
- **Round 1's paybacks journey on B** stopped at the payment picker because of TEST-20. The same steps on A (the Rule A journey) all passed.

### [testingBOT] 2026-11-10 · Round 2 · What worked well (please keep)
- **Rule A's numbers are exact.** They're the same on the server, in the app and with curl, at every step, for an amount split, Not sure yet, Set your share, "Alex owes what's left" and Let it go.
- **Set your share is clear.** S-47b reads like the product owner's own sentence: "Type what you had. Pearl gives what's left to Alex, who hasn't paid yet." The WHAT'S LEFT sum makes the $28.00 obvious, and "Save · Alex owes $28.00" says exactly what will happen.
- **The lock explains itself.** "Priya's $25.00 is linked. Unlink the payback to change Priya's share." with Options going straight to Unlink is the right amount of help.
- **"I had some too" off is respected everywhere.** No You row, no ••• for you, and Settle up offers "Alex owes what's left".
- **Undo** on Set your share and on "Alex owes what's left" goes back exactly, with the Allowance untouched.
- **Dark mode** on every new screen, and the Pearl sheets (Sign out, Let it go, That's everything) all look the part.

### [testingBOT] 2026-11-10 · Round 2 summary

**Round 1 findings, re-tested**

| ID | Title | Commit | Round 2 |
|---|---|---|---|
| TEST-01 | Quick sort's card unreadable in dark | A | **Fixed** |
| TEST-02 | Settle up › Type amounts opened "Who was it with?" | A | **Fixed** |
| TEST-03 | A split counted only your share (Rule A) | A | **Fixed** (app and curl) |
| TEST-04 | No Sort now on Home | A | **Fixed** |
| TEST-05 | Red spending, old Cash flow summary | A | **Fixed** (red "Over" early in the month: a note for designBOT) |
| TEST-06 | Stock alerts and action sheets | A | **Fixed** for every sheet I reached (Leave out, Sign out, Let it go, That's everything). Not all 14 were reached |
| TEST-07 | Leave out without a reason did nothing | A | **Fixed** (the save itself not seen in the app) |
| TEST-08 | "I had some too" missing on How to split | A | **Fixed** |
| TEST-09 | Floating Back over the scrolled page | A, B | **Still broken** (no backing; the title overlaps the content) |
| TEST-10 | Shop names cut short | A | **Fixed** (2 of 3, as agreed) |
| TEST-11 | "$0.00 goes back", "Sam · Done" | A | **Fixed** |
| TEST-12 | "Other?" as a guess with Yes | A | **Fixed** in Quick sort and Needs a look; the "Other?" chip is still on Cash flow rows |
| TEST-13 | Names and "no balance" | A | **Fixed** (the payment picker has a new problem: TEST-20) |
| TEST-14 | Accessibility audit | A, B | **Partly fixed** (the tab value and tap areas are fixed; the overlines, an "unreadable" amount label, a clipped overline on S-40y and the link colour remain) |
| TEST-15 | Let it go said the Allowance doesn't change | A | **Fixed** |
| TEST-16 | The number pad hid what's wrong | A | **Partly fixed** (the Done bar is fixed; with the pad up, Save sits over "I had some too" and the status line is hidden) |
| TEST-17 | Initials became "…" at AX sizes | A | **Fixed** (on A; B doesn't have it) |
| TEST-18 | Not sure yet with you in it (product owner) | B | **Works end to end**: Pizza Nova $120, you $17, Alex $28, every number right in the app and on the server. Open: TEST-19, TEST-20, TEST-23, and three small differences from the frames (the locked line with three payers, S-04u8's lines, S-47e's note) |

**New in Round 2**

| ID | Kind | Severity | To | Title |
|---|---|---|---|---|
| TEST-19 | Bug | Major | engBOT | After Save split on Not sure yet, the page still shows the purchase unsplit |
| TEST-20 | Bug | Major | engBOT | "Which payment was it?" suggests and pre-ticks someone else's money |
| TEST-21 | Confusion | Minor | both | Raising one person's share can't be saved: your share doesn't give way |
| TEST-22 | Bug | Minor | both | At the largest text size, amounts break in the middle, Save covers the total and the toast spills |
| TEST-23 | Bug | Minor | engBOT | Settle up › Shares says "53 shares" for three shares |

**Not covered in Round 2:**
- Delete a transaction, Reset Pearl, the device, rule and tag sheets, Nickname/Name and IB-03 (TEST-06's other sheets).
- The audit on Home and Cash flow (it timed out).
- Leave out actually saving in the app.
- Yes and Undo in Quick sort on A (the seed has no real guesses left).
- Round 1's paybacks journey on B (blocked by TEST-20; covered on A).
- engBOT's later commits (94e8389 S-47 four methods and T-01r2, 8788188/9452db8 TEST-18b), which aren't in B.
- Offline and error states, and Reduce Motion.

---

### [designBOT → testingBOT] 2026-11-11 · Round 2 · designBOT's replies
New frames are in section 20 on the Design refresh page (`1266:27288`, note `1266:28323`). They're built from Pearl Design System components, in light and dark, and stay **Awaiting product owner** until she picks.

### [designBOT → both] 2026-11-11 · TEST-21 · Your share gives way when you raise someone else's
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-291, THL-289, THL-303   **Figma:** S-03rg `1266:27289` / `1266:27383`, S-03rh `1266:27464` / `1266:27560`, S-03ri `1266:27643` / `1266:27739`
You're right. On a sheet called "Change Sam's share", changing Sam should be enough. Lowering Sam already works that way; raising him should too. The rule I propose, on How to split, Change their share and Settle up › Type amounts:
- **S-03rg:** until you type in your own field, your row is what's left. Its sub-line reads "Your share · gives way · what's left". Raise Sam to $60.00 and your share drops to $24.12, so it adds up and Save is on.
- **S-03rh:** only when your share would go below $0.00 does the line say "That's $5.88 too much, even with your share at $0.00", with Save off.
- **S-03ri:** once you've typed your own share, it's pinned ("Your share · you typed it"). Raising Sam then shows "That's $15.88 too much" and a text button, **Take $15.88 from your share**. One tap unpins your share and makes it add up. It sits where "Split the rest evenly" sits.
- **"What was your share?" (S-47)** is the exception. Your share never moves there, because it's the number you just typed. The unpaid rows you haven't touched give way instead.
- **"I had some too" off:** there's no row of yours to give way, so the "$x left to assign" / "too much" rules stay as they are.

**Recommendation: build S-03rg/rh/ri.** It's what a person expects, and it never changes a share they typed without asking.

### [designBOT → both] 2026-11-11 · TEST-05 · Cash flow says "Over $2,099" while Home says "$15,074 left"
**Status:** Redesigned · Awaiting product owner
**Jira:** THL-122, THL-123, THL-125   **Figma:** T-01r3 `1266:27822` / `1266:27927` (T-01r `1074:356` unchanged)
It's confusing, so I've redesigned it. T-01r's "Over" compares spending with the money that has already come in. Before payday that's $0, so the month looks overspent on day 10. Home's Allowance plans with the expected pay, so the two biggest numbers in the app disagree, and the red one is the false alarm.

T-01r3 changes the summary only until this month's expected pay has come in:
- the headline is **"Spent so far $2,099"**, in ink
- the top right says **"Pay expected Nov 15"** instead of "Came in $0"
- the line under the bar reads "Spent $2,099 · Saved $0 · Pay to come $5,200"

Once the expected pay arrives (or the month ends), the T-01r summary comes back: Leftover, with red "Over" only if spending really is more than what came in.

**Recommendation: build T-01r3.** engBOT: the expected pay date and amount are the ones the Allowance already uses (THL-127 income).

### [designBOT → both] 2026-11-11 · TEST-18 · The three differences from the frames
**Status:** Clarified in Figma · S-47g Awaiting product owner
**Jira:** THL-303, THL-291   **Figma:** section 18 note `1238:25742`, S-47g `1266:28020` / `1266:28160`
I checked testingBOT's screenshots against the frames.

1. **The folded locked line ("Paid back · Priya, Sam and Jo · linked, locked") does nothing when tapped.**
   - S-47b didn't say what it should do, so this one was ambiguous. With one payer, it opens that person's S-40u (S-47f).
   - With several payers, I've drawn **S-47g, "Who paid you back"**. It lists each payer as a locked row ("Paid back · Nov 14 · locked · $25.00 ›"), and each row opens that person's S-40u, where Unlink is.
   - It's Awaiting product owner because it's a new small sheet. Until she picks it, engBOT can open the first payer's S-40u, or leave the line as is.
2. **S-04u8's lines are missing.** The frame is clear, so this is a build difference. I've added the trigger to the section 18 note so it can't be missed:
   - S-04u8 applies as soon as everyone except you has at least one linked or cash payment and your share was never set.
   - Your row then reads "Your share · what's left after paybacks" with the amount ($17.00).
   - That's everything gets the sub-line "Everyone has paid. $17.00 stays yours."

   In testingBOT's shot, Alex had paid $28.00 cash, so it should have switched.
3. **S-47e's "Alex owes you $0.00" and the Rule A note.** Also a build difference: S-47e `1237:25668` has neither. I've spelled it out in the note:
   - While the field is in error, WHAT'S LEFT shows only Pizza Nova, Paid back and "Left for you and Alex · Your share can be up to this · $45.00".
   - There's no "Your share" row, no "Alex owes you" row and no Rule A callout.
   - They come back once the share fits.

### [designBOT → both] 2026-11-11 · TEST-22 · Amounts at the largest text size
**Status:** Agree with testingBOT's advice (no new frame)
**Jira:** designBOT rules (Dynamic Type)   **Figma:** S-03ax `1231:21270`
- **Amounts never wrap.** Use `lineLimit(1)` and `minimumScaleFactor(0.7)`. At AX sizes, if a row's amount still doesn't fit beside the name, it moves under the name, as the header does in S-03ax.
- **The split meter and status line** sit in the scroll content, above the pinned Save, so Save never covers them.
- **Toasts at AX sizes** grow to two or three lines, with Undo on its own line under the words, and never spill.

### [designBOT → engBOT] 2026-11-11 · Round 2 · Section 20 approved — build
**Status:** Approved — build
**Jira:** THL-291, THL-289, THL-303, THL-122, THL-123   **Figma:** section 20 `1266:27288`, note `1266:28323`
The product owner picked all five frames in section 20. The section, its note and all 10 frames (light and dark) are now marked "Approved — build":

| Frame | Finding | Light / dark | Jira |
|---|---|---|---|
| S-03rg | TEST-21 | `1266:27289` / `1266:27383` | THL-291, THL-289 |
| S-03rh | TEST-21 | `1266:27464` / `1266:27560` | THL-291, THL-289 |
| S-03ri | TEST-21 | `1266:27643` / `1266:27739` | THL-291, THL-289 |
| T-01r3 | TEST-05 | `1266:27822` / `1266:27927` | **THL-122**, with THL-123 |
| S-47g | TEST-18 | `1266:28020` / `1266:28160` | THL-303, THL-291 |

**T-01r3's ticket:** it's the Cash flow summary card, so it belongs to **THL-122** ("Design: transactions list and detail"), which T-01r and TEST-05 are filed under. THL-123 is also on T-01r's label. The expected pay it shows ("Pay expected Nov 15 · Pay to come $5,200") is the same figure the Allowance uses (THL-125 Home, THL-127 income). That's a source of data only; it adds no work to either ticket.

### [engBOT] 2026-11-11 · Round 2 replies · where the fixes are
Two local branches, nothing pushed:
- **B stack** `fix/testing-round-2` (off `feat/settle-mismatch` ddc24b0): `6ef1260` round 2 fixes (TEST-18, 19, 20, 22, 23, 14's S-40y overline), `8ec40b0` section 20 (TEST-21's S-03rg/rh/ri and S-47g).
- **A stack** `fix/testing-round-2-a` (off `feat/sort-now-cashflow` 43ca9b0): `fe2c8c2` round 2 fixes that live in the round-1 redesigns and Cash flow code (TEST-09, 12, 14, 16, 22's Save and meter, and TEST-19's cause, which is in shared code), `ddaa159` T-01r3 (TEST-05).
- ddc24b0 (S-48e) was complete: `tests/test_settle_mismatch.py` 10 passed, and its UI check `testSettleUpAsksWhenAPayersShareDiffers` passes.
- `run_journeys.py` now takes `PEARL_SIM_UDID` to reuse a booted simulator rather than booting "Pearl journeys" too. All my runs used the one booted iPhone 16 Pro (iOS 18.3).

### [engBOT → testingBOT] 2026-11-11 · TEST-19 · Fixed in 6ef1260 (B) and fe2c8c2 (A)
Reproduced with That's everything: the toast said "Split closed", the server returned `closed_at`, and the page still offered Settle up. The cause was `Transaction.==`, which compares only what a list row shows (category, chip, amount and so on) and not the split. The page keeps the purchase in `@State`, and SwiftUI skips the redraw when the new value compares equal. Under Rule A, saving a Not sure yet split or closing one changes none of those fields, so the page stayed as it was. An amount split usually changed something else, which is why it looked fine. `==` now also compares `split` and `splitting`. The UI checks `testNotSureYetCardRightAfterSaveAndNoOneElsesMoneyTicked` (Options for Priya within 4 s of Save split, and no Split with others) and `testThatsEverythingClosesTheCardAtOnce` (Reopen split within 4 s) fail before the fix and pass after it. My Save split check passed even before the fix on this machine, so it depends on timing; the close check fails every time without the fix.

### [engBOT → testingBOT] 2026-11-11 · TEST-20 · Fixed in 6ef1260
Reproduced on the server: for Priya on Pizza Nova (Not sure yet), Sam's $30.00 was first and `likely`, because a quarter of $120.00 "looked even". The sheet now asks for that person's payments (`GET …/paybacks?person=Priya`). Payments that name them come first. Only one of theirs is `likely` (pre-ticked), and only if it fits: on a set split it has to be what they owe, and on Not sure yet it has to fit what still counts as hers. The new `match: "amount"` is the only thing that shows "Amount matches". Otherwise the row shows the account, as the S-06rb note says. The app also pre-ticks only a row whose sender is that person. Without `person`, nothing changes. pytest `tests/test_testing_round_2.py`: Not sure yet suggests only Priya's; Jo gets nothing ticked; on an amount split, Sam's $30.00 isn't ticked for Priya and nothing matches for Jo; two senders with the same $30.00 each get only their own. UI: Jo's sheet has nothing ticked, no "Suggested" and no "Amount matches", and Link is off.

### [engBOT → testingBOT] 2026-11-11 · TEST-23 · Fixed in 6ef1260
The count added up every row's number, and a locked payer's number is the dollars they paid. Only rows in the shares are counted now. UI: Settle up › Shares on Gusto with Priya linked says "3 shares · adds up to".

### [engBOT → testingBOT] 2026-11-11 · TEST-18 · Fixed in 6ef1260 and 8ec40b0
Built from designBOT's note `1238:25742` and section 20:
- **S-04u8:** once everyone but you has a linked or cash payment and your share was never set, your row reads "Your share · what's left after paybacks" with the amount, and That's everything has "Everyone has paid. $55.00 stays yours." (`testEveryoneHasPaidShowsWhatStaysYours`).
- **S-47e:** while the share is too big, WHAT'S LEFT shows only the purchase, Paid back and "Left for you and Sam · Your share can be up to this". There's no Your share row, no "owes you" row and no Allowance note. The words under the field are the frame's: "That's more than what's left. Paybacks cover $42.50, so your share can be up to $85.00." (`testYourShareTooBigShowsOnlyWhatsLeft`).
- **The folded locked line (S-47g, 8ec40b0):** with two or more payers it opens "Who paid you back". Each row ("Paid back · Nov 10 · locked", "· cash ·" for cash) opens that person's S-40u, where Unlink is. With one payer it still opens S-47f. (`testWhoPaidYouBackOpensTheirOptions`.)

### [engBOT → testingBOT] 2026-11-11 · TEST-21 · Fixed in 8ec40b0 (section 20, approved)
S-03rg/rh/ri apply on How to split, Change their share and Settle up › Type amounts. Until she types her own share, it's what's left ("Your share · gives way · what's left"), so raising Sam adds up and her share saves as what's left. It's only too much when hers would go below $0.00 ("That's $x too much, even with your share at $0.00", Save off). Once she types it, it's pinned ("you typed it"), and "Take $x from your share" unpins it. A split opened again leaves her share unpinned, which fixes the Costco case (Sam to $20.00 adds up). S-47 is unchanged. UI `testYourShareGivesWayUntilYouTypeIt`: Sam $80 adds up with $7.50 yours; Sam $90 is too much even at $0.00; your typed $20 then Take $12.50; it saves as $7.50.
Note: with her share giving way, typing only Priya now reads "Adds up to $127.50 ✓" rather than "$87.50 left · stays yours", and "Split the rest evenly" shows only once she has typed her own share. That follows S-03rg. Please re-test TEST-08's wording with that in mind.

### [engBOT → testingBOT] 2026-11-11 · TEST-22 · Fixed in 6ef1260 (B) and fe2c8c2 (A)
Following designBOT's answer: split card amounts are one line, shrink to fit (`minimumScaleFactor(0.7)`) and move under the name at AX sizes. At AX sizes the toast's words wrap and Undo goes on its own line (B). On How to split (A), Save is no longer an inset over the scroll view. It sits below it, so the meter and status line scroll above Save and Save never covers them. AX check: `testTheNumberPadGoesAwayAndTheStatusStaysInView` at accessibility-extra-large keeps the status line above Save and the pad.

### [engBOT → testingBOT] 2026-11-11 · TEST-09 · Fixed in fe2c8c2
The app's navigation bars are see-through (`PearlApp` sets a transparent appearance for every bar), so iOS had no scroll-edge material to draw. Once the hero is under the bar, the transaction page now shows S-04r v2s's solid bar (Figma `--surface-page`, `1231:21486`) behind Back, the title and the clock. `testTheBarTakesTheMerchantOnceItScrolls` now also checks that the bar strip next to Back is one flat colour after scrolling. It's on A only, because S-04r v2s's inline title is in the round-1 redesigns.

### [engBOT → testingBOT] 2026-11-11 · TEST-16 · Fixed in fe2c8c2
Two causes on A: Save was a `safeAreaInset` on the scroll view, which didn't make room under the number pad, and typing changes the status line and the rows under it, which pushed it out of view. Save is now the scroll view's sibling, and the status line is scrolled back into view as she types. UI: the status line is hittable and above Save, and Save doesn't overlap "I had some too", at the default size and at accessibility-extra-large.

### [engBOT → testingBOT] 2026-11-11 · TEST-14 · Fixed in fe2c8c2 (and 6ef1260 for S-40y)
- OPTIONS and DETAILS use the sheets' section label (footnote, grows with Dynamic Type) instead of the fixed 11 pt caption, and wrap.
- Sheet overlines wrap instead of clipping ("PIZZA NOVA · NOT SURE YET" on S-40y), on both stacks.
- The hero amount reads "spent $127.50" to VoiceOver, and How to split's header reads "Gusto, spent $127.50" (U+2212 isn't read).
- The link colour still waits on the library, as you said, so I've left it.

### [engBOT → testingBOT] 2026-11-11 · TEST-12 · Fixed in fe2c8c2
On Cash flow a best guess of Other is now a "What was this?" chip that asks rather than confirms, as Needs a look and Quick sort do. VoiceOver hears "What was this?" and "Pearl couldn't place this one", not "Pearl's guess: Other". UI `testCashFlowRowsHaveNoOtherGuess`.

### [engBOT → testingBOT] 2026-11-11 · TEST-05 · T-01r3 built in ddaa159
Before this month's pay is in, Cash flow's summary reads "Spent so far" in ink, "Pay expected Nov 15" on the right and "Spent · Saved · Pay to come $11,700" under the bar, and never a red Over. The figures are the Allowance's: what its income row still expects this month, and its first unpaid payday. `month_totals.pay` is only on the current month and goes once the pay has all come in, which brings T-01r back. pytest `tests/test_cash_flow_pay_to_come.py`; UI `testCashFlowLeadsWithLeftover` checks T-01r3 while pay is to come. Two things for designBOT: when the income is a figure she typed, with no payday, there's no date, so the top right keeps "Came in"; and with two paydays a month, "Spent so far" stays until both have come in.

### [engBOT → designBOT] 2026-11-11 · TEST-05 · T-01r3 questions
**Severity:** Minor
**Jira:** THL-122   **Figma:** T-01r3 `1266:27822`   **Code:** `ios/Pearl/Views/Transactions/TransactionsView.swift` (summaryCard), `finance/api.py` `_pay_to_come`
**Problem:** (1) When her income is a figure she typed or her usual month, the Allowance has no payday, so "Pay expected <date>" has no date. I kept "Came in $X" on the right in that case and show "Pay to come" under the bar. (2) The demo pay is twice a month (Nov 15 and Nov 30). I keep T-01r3 until all of this month's expected pay has come in, so after Nov 15 it still says "Spent so far" and "Pay expected Nov 30".
**Ask:** confirm both, or draw the no-date case and say whether one payday arriving should bring back T-01r.

---

### [testingBOT] 2026-11-11 · Round 3 start
- **Builds:** my two detached worktrees, checked out at **A' = `ddaa159`** (`fix/testing-round-2-a`) and **B' = `8ec40b0`** (`fix/testing-round-2`). Debug, Xcode 26.6.
- **Simulator:** one only, the stock iPhone 16 (`5C99309E…`, iOS 26.5), passed in with `PEARL_SIM_UDID`. A' ran first, then B', never in parallel, and I shut the simulator down at the end. I used my own ports (5061 and 5071).
- **Data:** demo only, with `DATABASE_URL` removed. On top of Round 2's seed: the TEST-18b dinner, **Bar Isabel $100.00**, with Sam Lee $20.00 and Priya Shah $40.00 e-Transfers in.
- **Journeys:** a new `ios/PearlUITests/Round3JourneysUITests.swift` (option C, S-48e, section 20, the four methods on S-47, S-47g, T-01r2, T-01r3, and the re-tests), plus the Round 2 and Round 1 journeys as regressions.
- **Curl checks:** the same steps against a throwaway B' server: `round3/curl-b-optionC.txt` and `round3/curl-b-cashflow-notes.txt`.
- **Screenshots:** `/private/tmp/claude-501/-Users-mariapapadimitriou-GitHub-finance/47dab3d8-05be-4db9-b3fc-84667327b935/scratchpad/testing-run/round3/`. `a/` and `a-ax/` are A'. `b/`, `b2/` (re-runs after fixing my journeys) and `b-ax/` are B'.

### [testingBOT] 2026-11-11 · TEST-05 (T-01r3) · Fixed
Before payday, Cash flow reads "November · **Pay expected Nov 15**", "**Spent so far $2,247**" in ink, and "Spent $2,247 · Saved $0 · Pay to come $11,700". There's no red Over and no "Came in $0", in light and dark (`a/testR3CashFlowBeforePayday-01-light-cash-flow-summary.png`, `-04-dark-…`). It now agrees with Home. engBOT's two questions (no payday date; two paydays) are still with designBOT.

### [testingBOT] 2026-11-11 · TEST-09 · Fixed
Once the hero scrolls away, the split page has a solid bar behind Back, the clock and "Gusto", and nothing runs under it, in light and dark and at the largest text size (`a/testR3SplitPageBarPadAndNotSure-03-light-scrolled-split-page-bar.png`, `-07-dark-…`, `a-ax/testR3LargestTextSplit-04-light-split-card-large-scrolled.png`). This fix is only on A'. B' still has the floating Back over the content (`b2/testR3OptionCAnswers-09-light-S-48d-card.png`, "Split 3 ways" under the clock), which will go away when the stacks merge.

### [testingBOT] 2026-11-11 · TEST-12 · Fixed (on A')
Cash flow rows ask instead of guessing: Corner Store and Makersmkt show a dashed "What was this?" chip, and VoiceOver hears "What was this?" (`a/testR3CashFlowBeforePayday-06-dark-corner-store-row.png`). B' (without the redesign stack) still shows "Other?", which is expected until the stacks merge.

### [testingBOT] 2026-11-11 · TEST-14 · Partly fixed
- **Fixed on A':** OPTIONS and DETAILS grow with Dynamic Type (`a-ax/testR3LargestTextSplit-04`), and the hero reads "**spent $127.50**" to VoiceOver. The A' audit no longer flags OPTIONS, DETAILS or the hero.
- **Still flagged on A':** How to split's amount fields ("$42.50", Label not human-readable).
- **Still flagged on B':**
  - S-40y's overline "PIZZA NOVA · NOT SURE YET" (**Text clipped**), although engBOT lists that fix in 6ef1260.
  - OPTIONS and DETAILS (B' doesn't have the A' fix).
  - The −$120.00 hero.
  - S-47's unpaid amount fields ("$26.00").

  (`run-b.log`, `AUDIT` lines)
- **Waiting:** the link colour.

### [testingBOT] 2026-11-11 · TEST-16 · Fixed
With the pad up on How to split, the meter, "That's $22.50 too much · $150.00 of $127.50" and Save sit above the Done bar. "I had some too" is clear of Save, and the status line can be tapped (`a/testR3SplitPageBarPadAndNotSure-02-light-pad-up-too-much.png`). At the largest size, the meter and status are in the scroll content above Save.

### [testingBOT] 2026-11-11 · TEST-18 (the three differences) · Fixed
- **S-47g:** with three payers, the folded "Paid back · linked, locked" line opens **Who paid you back**. It lists Priya, Sam and Jo "Paid back · Nov 9 · locked · $25.00 ›", explains "These payments are linked, so they're locked…", and has "Back to your share". Tapping Sam opens Sam's S-40u with **Unlink…** (`b/testR3WhoPaidYouBackAndEveryonePaid-08-light-S-47g-who-paid-you-back.png`, `-09`).
- **S-04u8:** once Alex pays $28.00 cash without your share set, That's everything reads "Everyone has paid. $17.00 stays yours." Your row reads "what's left after paybacks", and S-46a3 matches (`b/testPizzaNovaEveryonePaidThenThatsEverything-10-light-S-04u8-scrolled.png`).
- **S-47e:** at $50, the field says "That's more than what's left. Paybacks cover $75.00, so your share can be up to $45.00." There's no "Alex owes you $0.00" and no Rule A note (`b2/testPizzaNovaThreePaidAndISetMyShare-16-light-S-47e-too-big.png`).
- The rest of the Pizza Nova story still holds on B': you set $17, Alex owes $28, Undo, Owed to you, and the Allowance at every step (`run-b2.log`).

### [testingBOT] 2026-11-11 · TEST-19 · Fixed
Right after Save split on Not sure yet, the card is there (Options for Priya within 4 s, and no "Split with others"), on every Pizza Nova and Bar Isabel run on B'. After That's everything, the page shows **Reopen split** at once (`b/testPizzaNovaEveryonePaidThenThatsEverything-13-light-closed-card.png`). On A' I couldn't run the Not sure yet half (my journey typed the names into Cash flow's search; my mistake, `a/testR3SplitPageBarPadAndNotSure-05`), so that half is checked on B' only.

### [testingBOT] 2026-11-11 · TEST-20 · Fixed
- **Jo on Not sure yet:** the only SUGGESTED row is **Jo Park · Nov 10 · $25.00**, ticked, and it's hers. Sam's and Priya's money sits under OTHER MONEY IN, unticked. There's no "Amount matches" (`b/testR3WhatWasYourShareFourMethods-07-light-jo-which-payment.png`).
- **Priya on a $42.50 amount split:** only her own $42.50 is suggested with "Amount matches", and Sam's $25.00 is no longer suggested (`b/testFriendsPayBackForDinner-06-light-which-payment.png`). engBOT's note said Jo would get nothing ticked; with her own matching e-Transfer in my seed, ticking it is right.

### [testingBOT] 2026-11-11 · TEST-21 · Fixed (section 20)
On How to split, Gusto $127.50, Amounts:
- **S-03rg:** Priya $40, Sam $80 → "You · Your share · gives way · what's left · $7.50", "Adds up to $127.50 ✓", and Save is on (`b2/testR3YourShareGivesWay-03`).
- **S-03rh:** Sam $90 → "That's $2.50 too much, even with your share at $0.00", and Save is off (`-04`).
- **S-03ri:** you type $20 → "you typed it". Sam $80 → "Take $12.50 from your share". One tap and Save is on, and it saves as you $7.50, Priya $40 and Sam $80 (`-05`, `-06`).
- **Change Sam's share to $85** gives way too ($2.50 yours), and it saves.
- **The Costco case:** joint Split my part, Sam to $20 → "You · gives way · $13.34", "Adds up to $50.00 ✓", Save on (`b/testSplitMyPartOfAJointPurchase-19-light-sam-20-on-joint.png`). Note that the card then still showed $16.66 for Sam (`-20`). The joint save wasn't confirmed, so I'll recheck it next round.

### [testingBOT] 2026-11-11 · TEST-08 wording after S-03rg · Fixed, as engBOT describes
Typing only Priya now reads "**Adds up to $127.50 ✓**" with your row "gives way · what's left", and there's no "stays yours". "Split the rest evenly" only comes back once you've typed your own share. That matches S-03rg (`b2/testR3YourShareGivesWay-02-light-TEST-08-wording-priya-only.png`).

### [testingBOT] 2026-11-11 · TEST-22 · Partly fixed
- **Fixed on B':** split card amounts stay on one line and move under the name ("Your share $17.00", "Paid back · Nov 9 · $25.00"). The toast wraps with **Undo** on its own line and doesn't spill (`b-ax/testPizzaNovaInDarkMode-13-dark-S-04u7-dark.png`).
- **Still broken on A':** at accessibility-extra-large, Priya's and Sam's amounts on the card still break as "$19." over "77" (`a-ax/testR3LargestTextSplit-03-light-split-card-large.png`). The amount fix is only on B', so it should go away on merge. Please confirm.
- **Fixed on A':** How to split's Save no longer covers the meter or the total (`a-ax/testR3LargestTextSplit-02`).

### [testingBOT] 2026-11-11 · TEST-23 · Fixed
Settle up › Shares no longer says "53 shares". With the payers locked, the line reads "3 to check: Priya, Sam and Jo" and the button "Next · check Priya, Sam and Jo" (option C). The payers show "Paid $25.00 · locked · share $24.00, Pearl asks next" (`b/testR3WhoPaidYouBackAndEveryonePaid-10-light-settle-shares-count.png`).

### [testingBOT] 2026-11-11 · Option C / TEST-18b, the $100 example · Works, except "It's a gift" (TEST-24)
Bar Isabel $100.00, Not sure yet with Sam and Priya. Linking Sam's $20.00 and Priya's $40.00 raises the Allowance by $60.00. Then Settle up → Type amounts → Evenly:
- **S-48c:** You $33.34. Sam "Paid $20.00 · locked · even share $33.33, Pearl asks next", and Priya the same. "2 to check: Sam and Priya", with "Next · check Sam and Priya".
- **S-48a (1 of 2):** "Sam paid $20.00", with Ask Sam for $13.33 or Sam's share is $20.00.
- **S-48b (2 of 2):** "Priya paid $6.67 more", with I owe Priya $6.67, Priya's share is $40.00, or It's a gift (`b2/testR3OptionCAnswers-06-light-S-48b-priya.png`).
- **After answering:** the sheet comes back with each payer's answer ("ask Sam for $13.33", "you owe Priya $6.67"), "Adds up to $100.00 ✓" and **Settle up** (`-07`).
- **Settle up:** toast "Settled · Sam owes $13.33 · you owe Priya $6.67" with Undo. The card shows You $33.34, Sam "Paid $20.00 of $33.33" $13.33, and Priya "Paid back" $40.00 (`-08`, `-09`).
- **Allowance:** **−$6.67** ✓.
- **S-14u5:** Owed to you is $13.33 (Sam) under OWES YOU, with Priya $6.67 "Overpaid for Bar Isabel Toronto" under **YOU OWE** ✓ (`-10`).
- **Sam's share is $20.00:** Priya then matches and isn't asked ✓. The Allowance doesn't move ✓. **Undo** goes back to Not sure yet ✓ (`b2/testR3OptionCSamsShareAndUndo-*`, and curl).
- **"Ask Sam" + "It's a gift": the Allowance doesn't move (expected −$6.67).** This is TEST-24.
- **S-48e:** Priya's ••• shows "Change what the extra $6.67 is · Now: you owe Priya · or Priya's share, or a gift". It asks again and saves (`-11`, `-12`, `-13`). Changing from "I owe Priya" to a gift raised the Allowance by $6.67. That's consistent with TEST-24's bug, not a separate one. Changing back to I owe brought it to −$6.67 (curl).
- **Unanswered:** the server refuses a settle that leaves an answer out ("Sam paid $20.00. Ask Sam for $13.33, or make Sam's share $20.00.").

### [testingBOT] 2026-11-11 · "What was your share?" with four methods · Works
Pizza Nova, Priya and Sam paid $25.00 each, and you $17:
- **Evenly:** Jo and Alex $26.50 each.
- **Amounts, %, Shares:** all reach "Adds up to $120.00 ✓". % shows Jo as "22.08%" of the whole purchase, and the payers stay locked rows in WHAT'S LEFT (`b/testR3WhatWasYourShareFourMethods-08`…`-13`).
- **One for designBOT:** the method segments sit inside the WHAT'S LEFT card, below your share and above the unpaid rows. That's a fine place, but at the default size the rows they change are below the fold.

### [testingBOT → engBOT] 2026-11-11 · TEST-24 · "It's a gift" doesn't lower the Allowance
**Kind:** Bug   **Severity:** Major
**Where:** S-48b, S-48e   **Figma:** S-48b `1249:26540`   **Jira:** THL-303 (designBOT's wording: "'I owe Priya' and 'It's a gift' lower it by the overpaid amount")   **Code:** `finance/api.py` (`_settle_extra`, the gift part)
**Steps:**
1. Bar Isabel $100.00 Not sure yet. Sam's $20.00 and Priya's $40.00 linked.
2. Settle up → Type amounts → Evenly → Ask Sam → **It's a gift** → Settle up.
**Saw:**
- The Allowance stays at $15,002.27, a 0.00 move, in the app (`run-b2.log`, "Ask Sam + It's a gift … WRONG") and with curl (`curl-b-optionC.txt`, "ask Sam + gift: allowance 15002.27").
- S-48e from "I owe" to "gift" raised it by $6.67.
- S-48b's callout still says "**Only** 'I owe Priya' changes your Allowance" (`b2/testR3OptionCAnswers-06-light-S-48b-priya.png`). That's designBOT's old wording, so the words and the numbers both say a gift is free.
**Expected:** the product owner decided (designBOT, 2026-11-10) that "It's a gift" lowers the Allowance by $6.67, the same as "I owe Priya". engBOT's entry said that's how it was built, but this commit doesn't do it.
**Advice:** count the gift part against the purchase as "I owe" does (or exclude it from the payback), and change S-48b's callout to "'I owe Priya' and 'It's a gift' lower your Allowance by $6.67. 'Priya's share is $40.00' doesn't change it." Add a pytest: ask + gift → −6.67.

### [testingBOT → engBOT] 2026-11-11 · TEST-25 · Cash flow's split note (T-01r2) never reaches the app
**Kind:** Bug   **Severity:** Major
**Where:** T-01r Cash flow list, B'   **Figma:** T-01r2 `1244:26496`   **Jira:** THL-122, THL-291 (Rule A)   **Code:** `ios/Pearl/API/Models.swift:1274-1276` (the client builds "Your share of …"), `finance/txlist.py:334-342`
**Steps:**
1. Gusto $127.50 split by amounts. Link Priya's $42.50.
2. Cash flow, and scroll to Gusto (not search).
3. Pizza Nova Not sure yet, three paid, then Alex pays.
**Saw:**
- The server's `/api/transactions/list` has the right notes: "Split with Priya +2 · $87.50 to come back" → "$45.00 to come back" → "$15.00" → "Your share of $127.50 · all paid back" (`curl-b-cashflow-notes.txt`).
- The app shows **"Your share of $127.50 · −$85.00"** for Gusto, and "Your share of $120 · −$45.00" then "−$17.00" for Pizza Nova (`b2/testR3CashFlowSplitNotes-03-light-cash-flow-gusto-note.png`, `run-b2.log`).
- So the row uses the client's own line, and the amount is what's still counting, not the whole purchase that T-01r2 and Rule A put on the row.
**Expected:** T-01r2: −$127.50 with "Split with Priya +2 · $45.00 to come back", and for Pizza Nova "Split 5 ways · not sure yet · $45.00 still counts".
**Advice:** show the server's `note` on list rows (and the whole amount until all paid), and drop the client's "Your share of" fallback for split rows. A UI check on the row text (not just the pytest) would catch it.

### [testingBOT → both] 2026-11-11 · TEST-26 · A' and B' each have half the fixes; the merge needs a check
**Kind:** Suggestion   **Severity:** Minor
**Where:** split pages on both stacks
**Saw:**
- **Only on A':** the solid bar (TEST-09), the "What was this?" chip on Cash flow (TEST-12), OPTIONS/DETAILS growing (TEST-14), spending in ink and T-01r3.
- **Only on B':** the AX amounts and toast (TEST-22), S-40y's overline, T-01r2, option C and section 20.
- So neither build has all of TEST-09, 14 and 22. On B' the floating Back still covers "Split 3 ways" (`b2/testR3OptionCAnswers-09`). On A' the AX amounts still break ("$19." / "77", `a-ax/testR3LargestTextSplit-03`).
**Advice:** when the stacks merge, re-run my Round 3 journeys on the merged build. The Round 3 suite already covers both halves. engBOT's merge note named `SplitFlow.swift`, but `TransactionDetailView.swift` and `Models.swift` also changed on both stacks.

### [testingBOT] 2026-11-11 · Round 3 regressions
- **Quick sort:** on B', Yes, Undo, Skip and the tile work, and "11 to sort" goes to 8, with the tab saying "8 to sort". On A', Sort now opens the T-93n questions as in Round 2. Round 1's Home and Needs a look journeys expect "Review one by one", so they stopped on A'; that's the old journey, not the app (A' has Sort now and See the list, checked in Round 2).
- **Needs a look on A' in dark:** checked in Round 2. Not re-run here.
- **Joint Split my part** on A' and B': $16.68 / $16.66 / $16.66, "Alex's $50.00 stays theirs", and the gives-way on Change Sam's share (B'), with one note in TEST-21.
- **Paybacks:**
  - Round 1's journey on B' linked Priya, but then stopped. Its old Unlink step expects a separate button, and with TEST-20's picker the next sheet pre-ticked Jo's $25.00 for "Priya, $42.50" under OTHER MONEY IN (`b/testFriendsPayBackForDinner-09`).
  - That's the S-06rb sheet reopened by my journey after linking, which shouldn't normally happen. But a pre-tick on someone else's money under OTHER MONEY IN goes against TEST-20's fix. I'll look again next round. Not filed yet.
- **Rule A** on B' holds for Pizza Nova at every step. Undo on Set your share, Settle up and the Settled toast all go back exactly.

### [testingBOT] 2026-11-11 · Round 3 summary

**Re-tests**

| ID | Round 3 | Build |
|---|---|---|
| TEST-05 (T-01r3) | **Fixed** | A' |
| TEST-08 wording | **Fixed** (follows S-03rg) | B' |
| TEST-09 | **Fixed** on A' (B' still floating until merge, TEST-26) | A' |
| TEST-12 | **Fixed** on A' | A' |
| TEST-14 | **Partly fixed** (A': overlines and hero fixed. Still flagged: amount fields; S-40y overline still clipped on B') | A', B' |
| TEST-16 | **Fixed** | A' |
| TEST-18 (three differences) | **Fixed** (S-47g, S-04u8, S-47e) | B' |
| TEST-19 | **Fixed** (Save split and That's everything, B'; A' half not run) | B' |
| TEST-20 | **Fixed** | B' |
| TEST-21 | **Fixed** (S-03rg/rh/ri, Change share, Costco) | B' |
| TEST-22 | **Fixed** on B'; **still broken** on A' (card amounts at AX) | B', A' |
| TEST-23 | **Fixed** | B' |

**New in Round 3**

| ID | Kind | Severity | To | Title |
|---|---|---|---|---|
| TEST-24 | Bug | Major | engBOT | "It's a gift" doesn't lower the Allowance (and S-48b's callout says it shouldn't) |
| TEST-25 | Bug | Major | engBOT | Cash flow's split note (T-01r2) never reaches the app; rows show "Your share of …" and the remaining amount |
| TEST-26 | Suggestion | Minor | both | A' and B' each have half the fixes; check the merged build |

**New features:**
- Option C works for Ask, I owe, Sam's share, skipping Priya, one Undo, S-14u5 and S-48e, except for the gift (TEST-24).
- The four methods on "What was your share?" work.
- Section 20 and S-47g work.

**Not covered:**
- TEST-19's Not sure yet half on A' (my journey's mistake).
- Changing Sam's share on a joint split actually saving (TEST-21 note).
- The audit on Home and Cash flow.
- The two T-01r3 edge cases that are waiting on designBOT.
- Offline and error states.
- engBOT's own UI checks.

### [engBOT] 2026-11-11 · Round 3 replies · where the fixes are
Pushed to the open PRs (no new PRs, no merge, no rebase):
- **#326** `fix/testing-round-2`: `11757fe` (TEST-24, TEST-25, TEST-26's halves for this stack, TEST-14, the link colour).
- **#330** `fix/testing-round-2-a`: `8041f62` (TEST-25, TEST-22's card amounts, TEST-14's amount labels, the link colour).
I used one simulator (iPhone 16 Pro, iOS 18.3) and shut it down at the end.

### [engBOT → testingBOT] 2026-11-11 · TEST-24 · Fixed in 11757fe
Reproduced on the demo ledger: after Ask Sam + It's a gift, the Allowance didn't move. My pytest planned with a typed income, and a typed income ignores what has arrived, so it passed. On the demo ledger the pay is detected, so what arrives counts. The gift part on Priya's deposit (Income · Gifts) counted as $6.67 received and cancelled the −$6.67. The Allowance's income now leaves out a split's extra that she called a gift: the gift part beside a payback to a split purchase on the same deposit (S-48b; Dad's $172 gift beside a $428 flight that isn't split is still income), and a cash or app gift row (S-11c). Ask + gift, ask + I owe, and I owe → gift later (S-48e) all lower it by $6.67, and Priya's share is $40.00 leaves it. S-48b's callout now reads "“I owe Priya” and “It’s a gift” lower your Allowance by $6.67. “Priya’s share is $40.00” doesn’t change it." (1249:26540).
pytest: `tests/test_testing_round_2.py` on the demo ledger with detected pay (the gift and I owe cases fail without the fix). UI: `testItsAGiftLowersTheAllowance` (Gusto, four ways: the callout's words, then a gift lowers the Allowance by Priya's extra).

### [engBOT → testingBOT] 2026-11-11 · TEST-25 · Fixed in 11757fe (and 8041f62)
The Cash flow row made its own "Your share of $128" and showed what still counts. That was `TransactionRow.extra` in `TransactionsView.swift`. `Models.swift:1274` (`shareNote`) is only used on the sorting cards. A split row now shows the server's note in place of the category line ("Split with Priya +2 · $45.00 to come back", "Split 5 ways · not sure yet · $45.00 still counts"). While the note is a "Split …" one, the row shows the whole purchase (−$127.50). Once it's "Your share of … · all paid back", it shows her share. On #330 the server's notes are the older ones ("Split with Priya, Sam"), and the row shows those. UI: `testCashFlowRowSaysWhatsStillToComeBack` (#326) and `testCashFlowRowUsesTheServersSplitNote` (#330) read the row itself.

### [engBOT → testingBOT] 2026-11-11 · TEST-26 · Both halves on each stack
- **TEST-09 on #326:** the split stack now has S-04r v2s's inline title and the solid bar once the hero scrolls away, the same code as #330. `testTheBarTakesTheMerchantOnceItScrolls` runs on both.
- **TEST-22 on #330:** card amounts stay on one line, shrink to fit, and go under the name at AX sizes, the same code as #326. I checked a screenshot at accessibility-extra-large (no "$19." over "77").
- **TEST-14 on #326:** OPTIONS and DETAILS, the hero ("spent $120.00") and How to split's header are the same as on #330.
The two stacks still conflict where both changed the same lines (`SplitFlow.swift`, `TransactionDetailView.swift`, `Models.swift`, `SplitMenus.swift`, `Theme.swift` and the UI test file). Where I ported a fix, I made the edit identical on both branches to keep the merge small. Please run Round 3 again on the merged build.

### [engBOT → testingBOT] 2026-11-11 · TEST-14 · Fixed in 11757fe and 8041f62
- **How to split's amounts:** on Evenly, each amount is a bare "$42.50" text. It now reads "Priya, $42.50". A payer's locked amount reads "Priya, paid $42.50, locked". S-47's Evenly amounts read "Jo owes $26.00".
- **S-40y's overline:** the header wraps its overline (6ef1260). The audit on my simulator (iOS 18.3) finds no clipped text on S-40y (`testS40yAndHowToSplitPassTheAudit`, the textClipped audit). Your flag was on iOS 26.5, so please re-run it there.
- **Link colour:** `color/text/link` is now published (Pearl Design System: light rose/800 #9C1F4B, dark rose/300 #FF8FB1). Text links and text buttons use it on both stacks: See everyone who owes you, Edit split, Add someone new, Split the rest evenly, Take $x from your share, Sort, Select, Add and the rest. Filled buttons keep the action colour, as the variable's note says.

### [engBOT → testingBOT] 2026-11-11 · TEST-20 · Reopened sheet checked, no change needed
I couldn't make the app pre-tick someone else's money on a reopened sheet. The server marks only the person's own payment as likely (after Priya's $42.50 is linked, her list has Jo's $25.00 and Sam's $30.00, neither likely), and the app ticks only a likely row that names her. The sheet is a new one each time it opens. Your `testFriendsPayBackForDinner-09` shows "Link $25.00" with Jo selected and "Paid back $25.00 of Priya's $42.50". That looks like the journey's tap landing on Jo's row after Priya's row left the list, not a pre-tick. `testAReopenedPaymentSheetTicksNoOneElse` covers it: Priya on $50.00, her $42.50 linked, then her sheet again, and nothing of Sam's or Jo's is ticked.

### [engBOT → designBOT] 2026-11-11 · TEST-05 · T-01r3 · Product owner's decision
The product owner decided to keep T-01r3 as built:
1. When the Allowance has no payday (her income is a figure she typed, or her usual month), the summary keeps "Came in $X" on the right, with "Pay to come $X" under the bar.
2. "Spent so far" stays until all of the month's expected pay is in. With two paydays (Nov 15 and Nov 30), the first one arriving doesn't bring back Leftover / Over. "Pay expected" moves to the next payday.
Please note both cases on T-01r3 (1266:27822) so the frame matches what's built.

---

### [testingBOT] 2026-11-11 · Round 4 start
- **Builds:** my two detached worktrees at **A'' = `8041f62`** (`fix/testing-round-2-a`, PR #330) and **B'' = `11757fe`** (`fix/testing-round-2`, PR #326). Debug, Xcode 26.6.
- **Simulator:** one only, the stock iPhone 16 (`5C99309E…`, iOS 26.5), passed in with `PEARL_SIM_UDID`. A'' ran first, then B'', never in parallel. I shut it down after the main run and again after a short probe run.
- **Data and ports:** demo data only, with `DATABASE_URL` removed. My own ports (5061, 5071, and 5092 for curl). The seed is Round 3's (Pizza Nova and the Bar Isabel $100 dinner).
- **Journeys:**
  - The Round 3 suite plus four Round 4 tests in `Round3JourneysUITests.swift`: the link colour (sampled from the screenshot), the reopened payment sheet checked without tapping a row, joint Change Sam's share with a relaunch, and a How to split / S-40y probe.
  - Round 2's Rule A and Pizza Nova journeys and Round 1's Quick sort journey as regressions.
- **Curl checks:** `round4/curl-b-gift.txt`.
- **Screenshots:** `/private/tmp/claude-501/-Users-mariapapadimitriou-GitHub-finance/47dab3d8-05be-4db9-b3fc-84667327b935/scratchpad/testing-run/round4/`. `a/`, `a-ax/` and `probe-a/` are A''. `b/`, `b-ax/` and `probe-b/` are B''.

### [testingBOT] 2026-11-11 · TEST-24 · Fixed
On Bar Isabel, Sam's $20.00 and Priya's $40.00 are linked. In the app:
- **Ask Sam + It's a gift:** the Allowance moves **−$6.67**, from $15,002.27 to $14,995.60.
- **Ask Sam + I owe Priya:** −$6.67.
- **S-48e from I owe to a gift:** no further move.
- **Sam's share is $20.00:** no move.
- **Undo:** back to Not sure yet, with no move.

S-48b's callout now reads "“I owe Priya” and “It’s a gift” lower your Allowance by $6.67. “Priya’s share is $40.00” doesn’t change it." (`run-b.log`, `b/testR3OptionCSamsShareAndUndo-*`, `b/testR3OptionCAnswers-*`). Curl agrees: ask + gift 14,995.60; S-48e to I owe 14,995.60; to a gift 14,995.60; to Priya's share $40 15,002.27; Undo 15,002.27 (`curl-b-gift.txt`).

### [testingBOT] 2026-11-11 · TEST-25 · Fixed
**B'':** Cash flow rows now carry the server's note and the whole purchase:
- "Gusto · Split with Priya +2 · $45.00 to come back · −$127.50"
- "Pizza Nova · Split 5 ways · not sure yet · $45.00 still counts · −$120.00"
- after Alex pays: "… $17.00 still counts · −$120.00"

(`b/testR3CashFlowSplitNotes-11-light-cash-flow-pizza-note.png`, `run-b.log`)

**A'':** the row follows the server too ("Gusto · Priya paid you back · −$85.00", `run-a.log`). The A stack's server still has the pre-T-01r2 notes, which engBOT expected. The merged build will have T-01r2 on both.

### [testingBOT] 2026-11-11 · TEST-26 · Fixed
- **TEST-09 on B'':** the solid bar with the merchant ("Costco Wholesale") sits behind Back and the clock once the page scrolls (`b/testR4JointChangeSamSaves-05-light-joint-card-after-relaunch.png`).
- **TEST-22 on A'':** at accessibility-extra-large, the card amounts sit under the name on one line ("$19.77"), with no "$19." / "77" (`a-ax/testR3LargestTextSplit-03-light-split-card-large.png`).
- **TEST-14's labels on both:** the hero reads "spent $127.50", and How to split's amounts read "Priya, $42.50".
- Each stack still keeps the other's server-side words until merge, as noted under TEST-25. Please re-run the Round 3 and 4 suites on the merged build.

### [testingBOT] 2026-11-11 · TEST-14 · Fixed (the audit still reports "Text clipped", but nothing is clipped on screen)
- **Link colour:** the dominant text colour sampled from the screenshot:

  | Link | A'' light | A'' dark | B'' light | B'' dark |
  |---|---|---|---|---|
  | Add someone new | #9C1F4B | #FF8FB1 | #9C1F4B | #FFC2D4 (see note) |
  | Edit split | #9C1F4B | #FF8FB1 | #9C1F4B | #FF8FB1 |
  | See everyone who owes you | #9C1F4B | #FF8FB1 | #9C1F4B | #FF8FB1 |

  On B'' dark, "Add someone new" is the same pink as the other links in the screenshot (`probe-b/testR4ProbeHowToSplitAndS40y-04-dark-how-to-split-evenly-dark.png`). My sample there was taken over the whole row, which includes B'' dark's pink card outline, so #FFC2D4 is the outline, not the text.
- **S-40y on iOS 26.5:** the overline "PIZZA NOVA · NOT SURE YET" is whole on screen (`probe-b/testR4ProbeHowToSplitAndS40y-09-light-S-40y-light.png`), but `performAccessibilityAudit` still reports **Text clipped** for it.
- **The new amount labels:** "Priya, $42.50" on How to split and "Jo owes $26.00" on S-47 are also reported as Text clipped on both builds. The text field is 55 pt wide and shows "$42.50" in full (`probe-a/…-02`), so the audit is comparing the longer spoken label with the shorter text on screen. That's TEST-27.
- **Contrast:** the audit still flags muted text on the see-through background. designBOT judged those false alarms in Round 1.

### [testingBOT] 2026-11-11 · The reopened payment sheet · Not a bug (engBOT is right)
Gusto split by amounts, Priya's $42.50 linked, then Priya's ••• opened twice by hand, with no row tapped. Her sheet reads "Paid back in full · Nov 10" with View the e-Transfer and Unlink…. There's **no Mark paid back**, so a payment sheet for Priya can't be reopened to tick anyone else's money (`a/testR4ReopenedPaymentSheetByHand-04-light-priya-options-1.png`; the same on B''). The Round 3 shot was my Round 1 journey tapping on after Priya's row had gone.

### [testingBOT] 2026-11-11 · TEST-19 (A'' half) · Fixed
On A'', Nopa → Not sure yet → Save split: the card is there within 4 s ("Options for Priya", and no "Split with others"). After That's everything, **Reopen split** shows at once (`run-a.log`, "TEST-19 Nopa: card at once true", "Reopen split shown true").

### [testingBOT] 2026-11-11 · Joint "Change Sam's share" · Saves (B'')
On B'', Costco joint $50.00 Split my part evenly, then Sam → $20:
- your share gives way to $13.34
- the server has you $13.34, Priya $16.66 and Sam $20.00
- after relaunching, the card shows Sam $20.00 (`b/testR4JointChangeSamSaves-05`, `run-b.log`)

On A'', raising Sam still shows "That's $3.34 too much" (`a/testR4JointChangeSamSaves-02`), because section 20 (S-03rg) is only on the B stack. That's expected before the merge, not a new finding.

### [testingBOT → engBOT] 2026-11-11 · TEST-27 · The audit reports "Text clipped" for the new spoken labels
**Kind:** Suggestion   **Severity:** Minor
**Where:** How to split (Evenly), S-47, S-40y, on both builds, iOS 26.5   **Code:** the `accessibilityLabel` on the amount `Text` views (TEST-14's change) and S-40y's header overline
**Steps:**
1. Run `performAccessibilityAudit` on How to split (Evenly), S-47c and S-40y.
**Saw:** "Text clipped · Priya, $42.50", "Jo owes $26.00" and "PIZZA NOVA · NOT SURE YET". On screen nothing is cut (`probe-a/testR4ProbeHowToSplitAndS40y-02-light-how-to-split-evenly-light.png`, `probe-b/…-09-light-S-40y-light.png`).
**Expected:** a clean audit, so that real clipping isn't hidden among false alarms.
**Advice:** put the spoken label on the combined row (`.accessibilityElement(children: .combine)` with the label on the row) rather than on the short amount text. Or tell `testS40yAndHowToSplitPassTheAudit` to ignore textClipped for these elements and say why. I can't see what makes S-40y's overline trigger it on 26.5 and not on 18.3. It isn't visible to a person, so this doesn't block the merge.

### [testingBOT] 2026-11-11 · Round 4 regressions
- **Option C (B''):** Ask, I owe, Sam's share (Priya skipped), one Undo, Owed to you, S-48e, and the Allowance at every step all match.
- **Rule A (A'' and B''):** the split doesn't move the Allowance, then +$42.50, +$30.00, Let it go 0, Undo 0. Owed to you ends at Jo $15.00.
- **The You row (B''):** Pizza Nova end to end, five ways: three pay, you set $17, Alex owes $28, Undo, Alex pays cash +$28.00.
- **Quick sort:**
  - On B'': Yes, Undo and the tile work, and "11 to sort" goes to 8.
  - On A'': Sort now opens the T-93n questions, and Cash flow says "Spent so far · Pay expected Nov 15" (T-01r3) in light and dark.
- **TEST-16 (A''):** with the pad up, the status line sits above Save and the Done bar.
- **The link colour** looks right in light and dark on every screen I opened.
- I found no regressions on either build.

### [testingBOT] 2026-11-11 · Round 4 summary

| ID | Round 4 | Build |
|---|---|---|
| TEST-24 | **Fixed** (app and curl: a gift −$6.67, new S-48b wording) | B'' |
| TEST-25 | **Fixed** (the row uses the server's note; T-01r2 words on B'', the older notes on A'' until merge) | A'', B'' |
| TEST-26 | **Fixed** (TEST-09 bar on B'', TEST-22 amounts on A'', TEST-14 labels on both) | A'', B'' |
| TEST-14 | **Fixed** (link colour #9C1F4B / #FF8FB1 on both, overlines, hero and amount labels). The audit still says "Text clipped" though nothing is clipped on screen: TEST-27 | A'', B'' |
| Reopened payment sheet | **Not a bug**: Priya has no Mark paid back once paid in full | A'', B'' |
| TEST-19 (A'' half) | **Fixed** | A'' |
| Joint Change Sam's share | **Saves** on B'' (survives a relaunch); A'' lacks section 20 until merge | B'' |

| New | Kind | Severity | To | Title |
|---|---|---|---|---|
| TEST-27 | Suggestion | Minor | engBOT | The audit reports "Text clipped" for the new spoken labels |

**Verdict: clean.**
- Every re-test is Fixed.
- No new Bug, Major or Blocker. The one new finding, TEST-27, is a Minor Suggestion about audit noise; nothing a person sees.
- Two things to know before merging:
  1. A'' and B'' each still miss the other stack's half (the T-01r2 notes, section 20, the Done bar on B''), so the merge needs care.
  2. Please re-run Rounds 3 and 4 on the merged build.

**Not covered:** the merged build, which doesn't exist yet. Offline and error states. The audit on Home and Cash flow, which timed out in earlier rounds and wasn't re-run.
