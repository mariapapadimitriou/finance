import XCTest

/// testingBOT's journeys: what a person does with Pearl, with real taps from
/// the app's real root, against the demo ledger. Run with
/// `python3 ios/tools/run_journeys.py [journey…]`, which starts that server
/// (demo data, a TD chequing account with two e-Transfers in, a Scotiabank
/// card with a $100.00 Costco purchase, and six guesses for Quick sort).
///
/// Each step saves a screenshot and the accessibility tree to the folder the
/// runner names, so a person can look at what the journey saw.
final class PersonJourneysUITests: XCTestCase {
    private var app: XCUIApplication!
    private var stepNumber = 0
    private var appearance = "light"

    private var shots: String {
        ProcessInfo.processInfo.environment["PEARL_SHOTS"] ?? NSTemporaryDirectory()
    }

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    // MARK: Helpers

    private func launch(_ scheme: String = "light") {
        appearance = scheme
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051")", "-pearl.appearance", scheme]
        app.launch()
        // N-01 asks about notifications once the Allowance has a number.
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 5) { notNow.tap() }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
    }

    /// A screenshot and the accessibility tree, named for the step.
    @discardableResult
    private func step(_ name: String, settle: UInt32 = 1) -> String {
        sleep(settle)
        stepNumber += 1
        let test = String(name.prefix(60)).replacingOccurrences(of: " ", with: "-")
        let method = self.name.components(separatedBy: " ").last?.replacingOccurrences(of: "]", with: "") ?? "test"
        let base = "\(shots)/\(method)-\(String(format: "%02d", stepNumber))-\(appearance)-\(test)"
        let png = XCUIScreen.main.screenshot().pngRepresentation
        FileManager.default.createFile(atPath: base + ".png", contents: png)
        try? app.debugDescription.write(toFile: base + ".txt", atomically: true, encoding: .utf8)
        let attach = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attach.name = name
        attach.lifetime = .keepAlways
        add(attach)
        print("JOURNEY \(base).png")
        return base
    }

    private func button(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
    }

    private func anyButton(containing text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func text(containing text: String) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func element(containing text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    @discardableResult
    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15,
                     file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        XCTAssertTrue(e.waitForExistence(timeout: timeout), "Couldn't find \(what)", file: file, line: line)
        if !e.isHittable { scrollTo(e) }
        e.tap()
        return e
    }

    private func scrollTo(_ e: XCUIElement, max: Int = 8) {
        var n = 0
        while !e.isHittable && n < max {
            app.swipeUp(velocity: .slow)
            n += 1
        }
    }

    private func scrollToFind(_ e: XCUIElement, max: Int = 10) -> Bool {
        var n = 0
        while !(e.exists && e.isHittable) && n < max {
            app.swipeUp(velocity: .slow)
            n += 1
        }
        return e.exists
    }

    /// A GET from the local server (the proxy), parsed.
    private func server(_ path: String) -> Any? {
        var result: Any?
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: URL(string: "http://localhost:\(ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051")/api/\(path)")!) { data, _, _ in
            if let data = data { result = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return result
    }

    private func send(_ method: String, _ path: String, _ body: [String: Any] = [:]) -> Any? {
        var request = URLRequest(url: URL(string: "http://localhost:\(ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051")/api/\(path)")!)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        var result: Any?
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data = data { result = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return result
    }

    private func note(_ s: String) { print("JOURNEY note: \(s)") }

    /// Tap it if it's there; say so in the log if not, and carry on.
    @discardableResult
    private func tapIf(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 8) -> Bool {
        guard e.waitForExistence(timeout: timeout) else {
            note("MISSING \(what)")
            return false
        }
        if !e.isHittable { scrollTo(e) }
        e.tap()
        return true
    }

    /// The button a person would tap when a label is on screen more than once
    /// (a sheet over a page): the last one that can be tapped.
    @discardableResult
    private func press(_ label: String, prefix: Bool = false, timeout: TimeInterval = 8) -> Bool {
        let q = app.buttons.matching(NSPredicate(format: prefix ? "label BEGINSWITH %@" : "label == %@", label))
        guard q.firstMatch.waitForExistence(timeout: timeout) else { note("MISSING \(label)"); return false }
        for e in q.allElementsBoundByIndex.reversed() where e.exists && e.isHittable {
            e.tap()
            return true
        }
        note("NOT HITTABLE \(label)")
        return false
    }

    private func reviewCount() -> Int {
        ((server("home") as? [String: Any])?["review_count"] as? Int) ?? -1
    }

    private func openCashFlow() {
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
    }

    /// Cash flow → search for a merchant → open its row.
    private func openTransaction(_ merchant: String) {
        openCashFlow()
        let row = button(merchant)
        if !row.waitForExistence(timeout: 10) || !row.isHittable {
            let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
            if search.waitForExistence(timeout: 3) {
                search.tap()
                search.typeText(merchant)
                sleep(2)
            } else {
                _ = scrollToFind(row, max: 14)
            }
        }
        tap(button(merchant), "the \(merchant) row")
    }

    // MARK: Split helpers

    /// S-02: type each name and Add, then Next.
    private func addPeople(_ names: [String]) {
        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), "S-02 has no name field")
        for name in names {
            field.tap()
            field.typeText(name)
            tapIf(app.buttons["Add"], "Add for \(name)", timeout: 3)
        }
        step("who was it with")
        tapIf(app.buttons["Next"], "Next on S-02")
        sleep(1)
    }

    private func amountField(_ who: String) -> XCUIElement {
        app.textFields.matching(identifier: "\(who) amount").firstMatch
    }

    private func type(_ value: String, into field: XCUIElement, _ what: String) {
        guard field.waitForExistence(timeout: 6) else { note("MISSING \(what)"); return }
        field.tap()
        if let old = field.value as? String, !old.isEmpty, old != field.placeholderValue {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))
        }
        field.typeText(value)
    }

    /// The number pad has no Done: tap the sheet's title, as a person would.
    private func dismissKeyboard() {
        if app.keyboards.count > 0 {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.12)).tap()
            sleep(1)
        }
    }

    private func saveEnabled() -> Bool {
        app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last?.isEnabled ?? false
    }

    private func transactionJSON(merchant: String) -> [String: Any]? {
        guard let list = server("transactions?q=\(merchant)") as? [String: Any],
              let rows = (list["transactions"] as? [[String: Any]]) else { return nil }
        return rows.first { ($0["merchant"] as? String ?? "").localizedCaseInsensitiveContains(merchant) }
    }

    private func split(of merchant: String) -> [String: Any]? {
        guard let id = transactionJSON(merchant: merchant)?["id"] as? String,
              let detail = server("transactions/\(id)") as? [String: Any] else { return nil }
        let t = (detail["transaction"] as? [String: Any]) ?? detail
        return (t["splitting"] as? [String: Any]) ?? ["split": t["split"] ?? "none", "parts": t["parts"] ?? "none"]
    }

    // MARK: 1–2 Home, Quick sort, Needs a look

    /// Home's Allowance and "to sort", then Quick sort: Yes, Skip, a category
    /// tile, Undo, and on to the end; the counts after, everywhere.
    func testSortWhatPearlGuessedFromHome() {
        launch()
        let home = server("home") as? [String: Any]
        let allowance = (home?["safe_to_spend"] as? [String: Any])?["amount"] as? Double ?? -1
        let before = reviewCount()
        note("server Allowance \(allowance), review_count \(before)")
        step("home")
        let orb = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Allowance,'")).firstMatch
        XCTAssertTrue(orb.waitForExistence(timeout: 10), "No Allowance orb")
        let shown = String(format: "$%@", NumberFormatter.localizedString(from: NSNumber(value: allowance.rounded()), number: .decimal))
        XCTAssertTrue(orb.label.contains(shown), "Orb says \(orb.label), server \(shown)")
        XCTAssertTrue(app.staticTexts["\(before) to sort"].exists, "Home's card doesn't say \(before) to sort")
        // H-00r: Sort now opens Quick sort; See the list opens Needs a look.
        if app.buttons["Sort now"].exists {
            app.buttons["Sort now"].tap()
        } else {
            note("MISSING Sort now on Home (H-00r)")
            tap(app.buttons["Review one by one"], "Review one by one")
            step("needs a look")
            tap(button("Quick sort"), "the Quick sort card on Needs a look")
        }
        let card = app.descendants(matching: .any)["quick-sort-card"]
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Quick sort has no card")
        step("quick sort first card")
        note("card 1: \(card.label)")
        tap(app.buttons["Yes"], "Yes")
        step("after yes")
        tapIf(app.buttons["Undo"], "Undo after Yes", timeout: 4)
        step("after undo")
        note("card after undo: \(card.label)")
        tap(app.buttons["Yes"], "Yes again")
        sleep(2)
        tap(app.buttons["Skip"], "Skip")
        step("after skip")
        // Tap the card for other answers: the shared What was this? page.
        card.tap()
        step("other answers")
        // The page's category row opens the tiles (T-96).
        if tapIf(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Other'")).firstMatch, "the category row", timeout: 6) {
            step("category tiles")
            if tapIf(button("Groceries"), "Groceries tile", timeout: 6) { step("groceries picked") }
        }
        tapIf(app.buttons["Back"].firstMatch, "Back to the card", timeout: 4)
        step("card shows choice")
        note("card after the tile: \(card.label)")
        tapIf(app.buttons["Yes"], "Yes on the edited card")
        sleep(2)
        // On to the end: Yes, or Answer's first choice.
        var n = 0
        while n < 12 && !app.buttons["Done"].exists {
            if app.buttons["Yes"].exists && app.buttons["Yes"].isHittable {
                app.buttons["Yes"].tap()
            } else if app.buttons["Skip"].exists && app.buttons["Skip"].isHittable {
                step("question card \(n)")
                app.buttons["Skip"].tap()
            } else { break }
            sleep(2)
            n += 1
        }
        step("end of quick sort")
        let after = reviewCount()
        note("review_count after \(after) (was \(before))")
        tapIf(app.buttons["Done"], "Done", timeout: 4)
        step("after done")
        // Back to Home: the count, the tab badge.
        var back = 0
        while !app.tabBars.buttons["Home"].exists && back < 4 {
            tapIf(app.buttons["Back"].firstMatch, "Back out of Quick sort", timeout: 3)
            back += 1
        }
        app.tabBars.buttons["Home"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        tapIf(app.buttons["Back"].firstMatch, "Back to Home", timeout: 2)
        step("home after sorting")
        note("Cash flow tab value: \(String(describing: app.tabBars.buttons["Cash flow"].value))")
        openCashFlow()
        step("cash flow after sorting")
        launch("dark")
        step("home dark after sorting")
    }

    /// Needs a look itself, light and dark, and Quick sort's card in dark.
    func testLookThroughNeedsALook() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            tap(app.buttons["Review one by one"], "Review one by one")
            step("needs a look")
            app.swipeUp()
            step("needs a look scrolled")
            app.swipeDown()
            tap(button("Quick sort"), "Quick sort card")
            step("quick sort")
            app.descendants(matching: .any)["quick-sort-card"].tap()
            step("what was this from the card")
        }
    }

    // MARK: 3 What was this? and Leave out

    /// A transaction's category, changed on its page; then Leave out from Select.
    func testChangeACategoryAndLeaveOneOut() {
        launch()
        openTransaction("Starbucks")
        step("starbucks detail")
        tap(button("Coffee"), "the category row")
        step("category page")
        tapIf(button("Dining"), "Dining")
        step("dining picked")
        let tx = transactionJSON(merchant: "Starbucks")
        note("server category now \(tx?["category"] ?? "?")")
        tapIf(app.buttons["Back"].firstMatch, "Back")
        step("detail after category")
        // Leave out, from Select on Cash flow.
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        tap(app.buttons["Select"], "Select")
        step("select mode")
        tapIf(button("Spotify"), "Spotify row in Select")
        step("one selected")
        tapIf(app.buttons["Leave out"], "Leave out in the bar")
        step("leave out confirm")
        note("alerts on screen: \(app.alerts.count), sheets: \(app.sheets.count)")
        if app.alerts.count > 0 { tapIf(app.alerts.buttons["Leave out"], "Leave out in the alert") }
        step("after leave out", settle: 4)
        let spotify = transactionJSON(merchant: "Spotify")
        note("Spotify excluded: \(spotify?["excluded"] ?? "?")")
        // Delete on a transaction's page.
        openTransaction("Nopa")
        app.swipeUp(); app.swipeUp()
        if tapIf(app.buttons["Delete transaction"], "Delete transaction", timeout: 4) {
            step("delete confirm")
            note("delete: alerts \(app.alerts.count), sheets \(app.sheets.count)")
        }
    }

    // MARK: 4 Split a purchase

    /// Dinner at Nopa split evenly with Priya and Sam.
    func testSplitADinnerEvenlyWithTwoFriends() {
        launch()
        openTransaction("Nopa")
        let total = abs(transactionJSON(merchant: "Nopa")?["amount"] as? Double ?? 0)
        note("Nopa total \(total)")
        tap(app.buttons["Split with others"], "Split with others")
        step("split sheet opens")
        addPeople(["Priya", "Sam"])
        step("how to split evenly")
        press("Save")
        step("split saved")
        let s = split(of: "Nopa")
        note("server split: \(s ?? [:])")
        app.swipeUp()
        step("split card")
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("owed to you")
        note("owed: \(server("owed") ?? "nil")")
        launch("dark")
        openTransaction("Nopa")
        app.swipeUp()
        step("split card dark")
    }

    /// Typed amounts that don't add up: too much, too little, "I had some
    /// too" off, then Split the rest evenly.
    func testSplitWithAmountsThatDontAddUp() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        step("amounts empty")
        type("100", into: amountField("Priya"), "Priya amount")
        type("50", into: amountField("Sam"), "Sam amount")
        dismissKeyboard()
        step("too much")
        note("Save enabled with too much: \(saveEnabled())")
        type("40", into: amountField("Priya"), "Priya amount")
        type("30", into: amountField("Sam"), "Sam amount")
        dismissKeyboard()
        step("short, stays yours")
        note("Save enabled when short with me: \(saveEnabled())")
        // Off: there's no "you" to keep the rest.
        let toggle = app.switches.firstMatch
        if toggle.waitForExistence(timeout: 3) {
            scrollTo(toggle)
            toggle.tap()
            step("i had some too off")
            note("Save enabled when short without me: \(saveEnabled())")
        } else {
            note("MISSING I had some too on How to split")
        }
        tapIf(app.buttons["Split the rest evenly"], "Split the rest evenly", timeout: 4)
        step("rest split evenly")
        press("Save")
        step("saved")
        note("server split: \(split(of: "Gusto") ?? [:])")
    }

    /// "I had some too" off on S-02: it was all for them.
    func testSplitSomethingThatWasAllForThem() {
        launch()
        openTransaction("Lucky")
        tap(app.buttons["Split with others"], "Split with others")
        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap(); field.typeText("Priya")
        tapIf(app.buttons["Add"], "Add")
        let toggle = app.switches.firstMatch
        if toggle.waitForExistence(timeout: 3) { toggle.tap() } else { note("MISSING I had some too on S-02") }
        step("all for them")
        tapIf(app.buttons["Next"], "Next")
        step("how to split all for them")
        press("Save")
        step("saved all for them")
        note("server split: \(split(of: "Lucky") ?? [:])")
    }

    /// Not sure yet → Priya's e-Transfer comes in and is linked → Settle up →
    /// That's everything → Reopen.
    func testSplitNotSureYetThenSettleUp() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        step("not sure yet")
        press("Save split")
        step("not sure yet saved")
        app.swipeUp()
        step("S-04u card")
        // Priya's payment, from her ••• (S-40u2).
        tap(app.buttons["Options for Priya"], "Options for Priya")
        step("S-40u2 options")
        tap(button("Mark paid back"), "Mark paid back")
        step("how did priya pay")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        step("which payment")
        tapIf(button("Priya Shah"), "Priya's e-Transfer", timeout: 8)
        step("payment picked")
        press("Link", prefix: true)
        step("payment linked")
        note("split after link: \(split(of: "Gusto") ?? [:])")
        app.swipeUp()
        step("card after link")
        tap(app.buttons["Options for Priya"], "Options for Priya again")
        step("S-40u options paid")
        tapIf(app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'close' OR label == 'Close'")).firstMatch, "Close", timeout: 3)
        // Settle up.
        tap(button("Settle up"), "Settle up")
        step("settle up")
        tapIf(button("Type amounts"), "Type amounts", timeout: 4)
        step("settle type amounts")
        app.swipeDown(velocity: .fast)
        sleep(1)
        // That's everything, then Reopen.
        if tapIf(button("That’s everything"), "That's everything") {
            step("thats everything confirm")
            press("That’s everything")
            step("closed")
            note("split after close: \(split(of: "Gusto") ?? [:])")
            sleep(5) // the toast goes
            if tapIf(button("Reopen split"), "Reopen split") {
                step("reopen", settle: 2)
                press("Reopen", prefix: true, timeout: 3)
                step("reopened", settle: 3)
                note("split after reopen: \(split(of: "Gusto") ?? [:])")
            }
        }
    }

    // MARK: 5–6 Paybacks and person options

    /// Gusto $127.50: Priya $42.50, Sam $30.00, Jo $15.00, you the rest.
    private func splitGustoByAmounts() {
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        type("42.50", into: amountField("Priya"), "Priya amount")
        type("30", into: amountField("Sam"), "Sam amount")
        type("15", into: amountField("Jo"), "Jo amount")
        dismissKeyboard()
        step("gusto amounts")
        press("Save")
        sleep(2)
    }

    /// Priya's e-Transfer linked, checked on Owed to you, unlinked with Undo;
    /// Sam pays cash; Jo's let go and back; Remind Jo.
    func testFriendsPayBackForDinner() {
        launch()
        splitGustoByAmounts()
        step("split card")
        note("owed before: \(server("owed") ?? "nil")")
        tap(app.buttons["Options for Priya"], "Options for Priya")
        step("S-40a priya")
        tap(button("Mark paid back"), "Mark paid back")
        step("S-06 how did priya pay")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        step("which payment")
        tapIf(button("Priya Shah"), "Priya's e-Transfer", timeout: 8)
        step("priya payment picked")
        press("Link", prefix: true)
        step("priya linked")
        note("owed after link: \(server("owed") ?? "nil")")
        // Unlink, then Undo.
        tap(app.buttons["Options for Priya"], "Options for Priya after paying")
        step("S-40 priya paid")
        if tapIf(anyButton(containing: "Unlink"), "Unlink", timeout: 4) {
            step("unlink confirm")
            if app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Unlink'")).count > 0 {
                app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Unlink'")).allElementsBoundByIndex.last?.tap()
            }
            step("unlinked toast")
            note("owed after unlink: \(server("owed") ?? "nil")")
            tapIf(app.buttons["Undo"], "Undo the unlink", timeout: 4)
            step("unlink undone")
            note("owed after undo: \(server("owed") ?? "nil")")
        }
        // Sam pays cash.
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back for Sam")
        tap(button("Cash in hand"), "Cash in hand")
        step("cash for sam")
        press("Mark $", prefix: true, timeout: 5)
        step("sam paid cash")
        // Jo: let it go, then undo it.
        tap(app.buttons["Options for Jo"], "Options for Jo")
        step("S-40a jo")
        tap(button("Let it go"), "Let it go")
        step("let jo go confirm")
        let letGo = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Let'"))
        letGo.allElementsBoundByIndex.last?.tap()
        step("jo let go")
        note("split after let go: \(split(of: "Gusto") ?? [:])")
        if !tapIf(app.buttons["Undo"], "Undo on the let-go toast", timeout: 3) {
            tap(app.buttons["Options for Jo"], "Options for Jo after let go")
            step("jo options after let go")
            tapIf(button("Undo let it go"), "Undo let it go")
        }
        step("jo back")
        // Remind Jo.
        tap(app.buttons["Options for Jo"], "Options for Jo to remind")
        tap(button("Remind Jo"), "Remind Jo")
        step("remind jo")
        app.swipeDown(velocity: .fast)
        // Owed to you.
        app.swipeUp()
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("owed to you")
        app.swipeUp()
        step("owed to you scrolled")
        note("owed at end: \(server("owed") ?? "nil")")
        launch("dark")
        openTransaction("Gusto")
        app.swipeUp()
        step("split card dark")
        tap(app.buttons["Options for Priya"], "Options for Priya dark")
        step("S-40 dark")
    }

    /// Change Sam's share and remove Jo, from their •••.
    func testChangeAShareAndRemoveSomeone() {
        launch()
        splitGustoByAmounts()
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Change Sam"), "Change Sam's share")
        step("change sam share")
        type("35", into: amountField("Sam"), "Sam amount")
        dismissKeyboard()
        step("sam 35")
        if !press("Save", timeout: 3) { press("Update", prefix: true, timeout: 3) }
        step("share changed")
        note("split after change: \(split(of: "Gusto") ?? [:])")
        tap(app.buttons["Options for Jo"], "Options for Jo")
        tap(button("Remove Jo"), "Remove Jo")
        step("remove jo")
        if app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Remove'")).count > 0 {
            app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Remove'")).allElementsBoundByIndex.last?.tap()
        }
        step("jo removed")
        note("split after remove: \(split(of: "Gusto") ?? [:])")
    }

    // MARK: 7 Joint

    /// The Scotiabank card set to joint with Alex at 50/50, then Costco's
    /// $100.00: Split my part three ways, and change a share.
    func testSplitMyPartOfAJointPurchase() {
        launch()
        app.tabBars.buttons["Profile"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        step("profile")
        tap(button("Accounts"), "Accounts")
        step("accounts")
        tap(button("Scotiabank"), "Scotiabank account")
        step("scotiabank account")
        let joint = app.switches["Joint account"].exists ? app.switches["Joint account"] : app.switches.firstMatch
        tapIf(joint, "Joint account toggle")
        step("joint on")
        if tapIf(button("Shared with"), "Shared with", timeout: 4) {
            step("shared with page")
            tapIf(button("Add who"), "Add who it's shared with", timeout: 4)
            // AM-08p1: iOS asks for Contacts on open; she says no (AM-08p2).
            let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
            let deny = springboard.buttons["Don’t Allow"]
            if deny.waitForExistence(timeout: 5) { deny.tap() }
            step("shared with picker")
            tapIf(button("Type a name"), "Type a name")
            let field = app.textFields.matching(NSPredicate(format: "placeholderValue CONTAINS[c] 'name'")).firstMatch
            if field.waitForExistence(timeout: 4) { field.tap(); field.typeText("Alex") }
            step("alex typed")
            press("Add", prefix: true, timeout: 4)
            step("alex picked")
            press("Add", prefix: true, timeout: 4)
            step("shared with alex")
            press("Save", timeout: 4)
            step("joint saved")
            tapIf(app.buttons["Back"].firstMatch, "Back to accounts", timeout: 3)
        }
        note("accounts: \((server("accounts") as? [String: Any])?["accounts"].map { "\($0)".prefix(1) } ?? "")")
        let scotia = ((server("accounts") as? [String: Any])?["accounts"] as? [[String: Any]])?.first { ($0["account_id"] as? String) == "scotia_visa_8830" }
        note("scotia joint: \(scotia?["joint"] ?? "nil"), share \(scotia?["joint_share"] ?? "nil"), people \(scotia?["joint_people"] ?? "nil")")
        openTransaction("Costco")
        step("costco joint detail")
        app.swipeUp()
        step("costco joint detail scrolled")
        if !tapIf(app.buttons["Split my part"], "Split my part") {
            tapIf(app.buttons["Split with others"], "Split with others on a joint purchase")
        }
        step("split my part sheet")
        addPeople(["Priya", "Sam"])
        step("split my part three ways")
        press("Save")
        step("joint split saved")
        note("costco split: \(split(of: "Costco") ?? [:])")
        app.swipeUp()
        step("joint split card")
        if tapIf(app.buttons["Options for Sam"], "Options for Sam on joint") {
            tap(button("Change Sam"), "Change Sam's share")
            step("change share on joint")
            type("20", into: amountField("Sam"), "Sam amount")
            dismissKeyboard()
            step("sam 20 on joint")
            if !press("Save", timeout: 3) { press("Update", prefix: true, timeout: 3) }
            step("joint share changed")
            note("costco split after change: \(split(of: "Costco") ?? [:])")
        }
    }

    // MARK: Conditions

    /// Even split at the largest accessibility text size.
    func testSplitADinnerAtTheLargestTextSize() {
        launch()
        step("home large text")
        openCashFlow()
        step("cash flow large text")
        openTransaction("Nopa")
        step("detail large text")
        tap(app.buttons["Split with others"], "Split with others")
        step("S-02 large text")
        addPeople(["Priya", "Sam"])
        step("S-03u large text")
        tapIf(button("How to split"), "the method row", timeout: 3)
        step("pick a method large text")
        app.swipeDown(velocity: .fast)
        press("Save")
        app.swipeUp()
        step("split card large text")
        tapIf(app.buttons["Options for Priya"], "Options for Priya")
        step("S-40a large text")
    }

    /// The accessibility audit on Home, Cash flow, a split and its options.
    func testAccessibilityAuditOnTheMainScreens() throws {
        guard #available(iOS 17.0, *) else { throw XCTSkip("The audit needs iOS 17") }
        launch()
        var issues: [String] = []
        func audit(_ screen: String) {
            do {
                try app.performAccessibilityAudit { issue in
                    issues.append("\(screen): \(issue.auditType) · \(issue.compactDescription) · \(issue.element?.label ?? "")")
                    return true
                }
            } catch {
                issues.append("\(screen): audit failed \(error)")
            }
        }
        audit("Home")
        openCashFlow()
        audit("Cash flow")
        openTransaction("Gusto")
        audit("Transaction")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        audit("How to split")
        press("Save")
        sleep(2)
        app.swipeUp()
        audit("Split card")
        if tapIf(app.buttons["Options for Priya"], "Options for Priya") {
            sleep(1)
            audit("Person options")
        }
        for i in issues { note("AUDIT \(i)") }
    }

    // MARK: Explore

    /// Cash flow, a transaction and its menus, to learn the screens.
    func testLookAround() {
        launch()
        openCashFlow()
        step("cash flow")
        app.swipeUp()
        step("cash flow scrolled")
        openTransaction("Costco")
        step("costco detail")
        app.swipeUp()
        step("costco detail scrolled")
        app.tabBars.buttons["Profile"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        step("profile")
    }

    /// Home in light and dark, with the tree, to learn the screen.
    func testLookAtHome() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            step("home")
            app.swipeUp()
            step("home scrolled")
        }
    }
}
