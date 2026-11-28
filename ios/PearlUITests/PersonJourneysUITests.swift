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
        if notNow.waitForExistence(timeout: 5), notNow.isHittable { notNow.tap() }
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
        // Since #466 some rows on screen report not hittable (B's tests tap
        // by coordinate too), so tap the middle of what was found.
        if e.isHittable { e.tap() } else { e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
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
        // Since #466 some on-screen buttons report not hittable: tap the
        // last one on screen by its middle, as FewerTapsUITests does.
        let screen = app.windows.firstMatch.frame
        if let e = q.allElementsBoundByIndex.reversed().first(where: {
            $0.exists && !$0.frame.isEmpty && screen.contains(CGPoint(x: $0.frame.midX, y: $0.frame.midY))
        }) {
            e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
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
                // P15 (#466): the field isn't hittable as an element, so tap its middle.
                search.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                sleep(1)
                app.typeText(merchant)
                sleep(2)
            } else {
                _ = scrollToFind(row, max: 14)
            }
        }
        // The first match can sit under the search bar, so take the first row
        // below it and tap its middle (since #466 rows report not hittable).
        let rows = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", merchant))
        _ = rows.firstMatch.waitForExistence(timeout: 10)
        let screen = app.windows.firstMatch.frame
        if let r = rows.allElementsBoundByIndex.first(where: {
            $0.exists && $0.frame.minY > 140 && $0.frame.maxY < screen.maxY - 100
        }) {
            r.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            sleep(1)
        } else {
            tap(button(merchant), "the \(merchant) row")
        }
    }

    // MARK: Split helpers

    /// P11 (fewer taps): one sheet. A chip for someone she has split with,
    /// else Add › type the name › Add "Name"; then, for an uneven split,
    /// Other ways › the method (S-03 on it).
    private func addPeople(_ names: [String], way: String? = nil) {
        XCTAssertTrue(app.buttons["Add someone new"].waitForExistence(timeout: 10), "P11 has no Add chip")
        for name in names {
            let chip = app.buttons.matching(NSPredicate(format: "label == %@", name)).firstMatch
            if chip.exists && chip.isHittable && !chip.isSelected {
                chip.tap()
                continue
            }
            tap(app.buttons["Add someone new"], "Add for \(name)")
            let field = app.textFields["split-add-name"]
            XCTAssertTrue(field.waitForExistence(timeout: 6), "Add someone new has no field")
            if (field.value(forKey: "hasKeyboardFocus") as? Bool) != true { field.tap() }
            field.typeText(name)
            tap(button("Add “\(name)”"), "Add “\(name)”")
            sleep(1)
        }
        step("who was it with")
        if let way = way {
            tap(app.buttons["split-other-ways"], "Other ways")
            tap(app.buttons["split-way-\(way)"], "the \(way) way")
            sleep(1)
        }
    }

    /// P11a's button, "Split", or Save on a method's screen.
    @discardableResult
    private func saveSplit() -> Bool {
        press("Split", timeout: 3) || press("Save", timeout: 3)
    }

    /// Someone paid me back: under More (P2), or Options' row before it.
    private func openPaidBack() {
        if app.buttons["Mark as paid back"].waitForExistence(timeout: 3) {
            tap(app.buttons["Mark as paid back"], "Mark as paid back")
        } else {
            // The page's More row by its identifier: a split card's ••• is labelled More too.
            tap(app.buttons.matching(NSPredicate(format: "identifier == 'More'")).firstMatch, "More")
            tap(anyButton(containing: "Someone paid me back"), "Someone paid me back")
        }
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

    // MARK: 2b Also 8 older ones? (REFRESH-17)

    private func olderSheet() -> XCUIElement { app.staticTexts["Also 8 older ones?"] }

    /// Where it is on screen: the glass bars make a visible row "not hittable".
    private func press(_ e: XCUIElement) {
        e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
    }

    private func openNeedsALook() {
        step("home")
        let list = app.buttons["See the list"].firstMatch
        XCTAssertTrue(list.waitForExistence(timeout: 15), "No See the list")
        press(list)
    }

    /// Needs a look: the newest Maple Court is Utilities; Yes, all 8, then Undo.
    func testOlderOnesFromNeedsALook() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            openNeedsALook()
            let chip = button("Where it went")
            XCTAssertTrue(chip.waitForExistence(timeout: 15), "No Where it went chip")
            press(chip)
            step("needs a look")
            XCTAssertTrue(button("Maple Court").waitForExistence(timeout: 8), "No Maple Court row")
            press(button("Maple Court"))
            step("maple court asked")
            if !app.buttons["Utilities"].exists { tapIf(anyButton(containing: "Something else"), "Something else") }
            step("every answer")
            tap(button("Utilities"), "Utilities")
            if scheme == "light" {
                XCTAssertTrue(olderSheet().waitForExistence(timeout: 12), "OT-01 didn't come")
                step("OT-01")
                tap(app.buttons["Yes, all 8"], "Yes, all 8")
                XCTAssertTrue(text(containing: "8 more moved to Utilities").waitForExistence(timeout: 8), "No OT-02 toast")
                step("OT-02")
                tap(app.buttons["Undo"], "Undo")
                XCTAssertTrue(text(containing: "Undone").waitForExistence(timeout: 8), "Undo didn't answer")
                XCTAssertTrue(app.buttons["Undo"].waitForNonExistence(timeout: 2), "Undone. kept an Undo that does nothing")
                step("after undo")
            } else {
                // The older waiting one, sorted: the same 8 are asked about again.
                XCTAssertTrue(olderSheet().waitForExistence(timeout: 12), "OT-01 didn't come again")
                step("OT-01")
                tap(app.buttons["Leave them in Transfers"], "Leave them")
                XCTAssertTrue(olderSheet().waitForNonExistence(timeout: 6), "OT-01 stayed")
                step("after leave them")
            }
        }
    }

    /// Quick sort: the card's answer, the sheet, then "Undo 8".
    func testOlderOnesFromQuickSort() {
        launch()
        openNeedsALook()
        press(button("Quick sort"))
        let card = app.descendants(matching: .any)["quick-sort-card"]
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Quick sort has no card")
        var n = 0
        while !card.label.contains("Maple Court") && n < 25 {
            press(app.buttons["Skip"].firstMatch)
            sleep(2)
            n += 1
        }
        note("card: \(card.label)")
        step("maple court card")
        press(card)
        step("answers")
        if !app.buttons["Utilities"].exists { tapIf(anyButton(containing: "Something else"), "Something else") }
        tap(button("Utilities"), "Utilities")
        step("picked")
        if !olderSheet().exists { press(app.buttons["Yes"].firstMatch) }
        XCTAssertTrue(olderSheet().waitForExistence(timeout: 12), "OT-01q didn't come")
        step("OT-01q")
        tap(app.buttons["Yes, all 8"], "Yes, all 8")
        XCTAssertTrue(app.buttons["Undo the 8"].waitForExistence(timeout: 8), "No Undo 8")
        step("OT-02q")
        tap(app.buttons["Undo the 8"], "Undo 8")
        XCTAssertTrue(app.buttons["Undo the last answer"].waitForExistence(timeout: 8), "Her own Undo isn't next")
        step("undo again")
    }

    /// The page, with ✕: nothing moves, and it asks again.
    func testOlderOnesFromThePage() {
        launch()
        press(app.tabBars.buttons["Cash flow"])
        let field = app.textFields["Search"].firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 15), "No Search")
        press(field)
        field.typeText("Maple")
        XCTAssertTrue(button("Maple Court").waitForExistence(timeout: 10), "No Maple Court")
        press(button("Maple Court"))
        step("page")
        tapIf(button("Not sorted yet"), "the category row")
        step("what was this")
        if !app.buttons["Utilities"].exists { tapIf(anyButton(containing: "Something else"), "Something else") }
        tap(button("Utilities"), "Utilities")
        XCTAssertTrue(olderSheet().waitForExistence(timeout: 12), "OT-01p didn't come")
        step("OT-01p")
        tap(app.buttons["Close"].firstMatch, "Close")
        XCTAssertTrue(olderSheet().waitForNonExistence(timeout: 6), "OT-01p stayed")
        step("after close")
    }

    /// T-03r: a name too common for a rule; no switch, and the line instead.
    func testOlderOnesCommonName() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            press(app.tabBars.buttons["Cash flow"])
            let field = app.textFields["Search"].firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 15), "No Search")
            press(field)
            field.typeText("Internet")
            XCTAssertTrue(button("Internet").waitForExistence(timeout: 10), "No Internet Withdrawal")
            press(button("Internet"))
            step("page")
            if scheme == "light" {
                tapIf(button("Not sorted yet"), "the category row")
                if !app.buttons["Utilities"].exists { tapIf(anyButton(containing: "Something else"), "Something else") }
                XCTAssertFalse(app.staticTexts["This name is too common for a rule"].exists, "The sheet says nothing")
                tap(button("Utilities"), "Utilities")
                sleep(3)
                XCTAssertFalse(app.buttons["Leave them in Transfers"].exists, "OT-01 asked for a common name")
            }
            XCTAssertTrue(app.staticTexts["This name is too common for a rule"].waitForExistence(timeout: 8), "No line")
            XCTAssertFalse(app.switches["Always for this merchant"].exists, "A switch that does nothing")
            step("T-03r", settle: 5)
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
        saveSplit()
        step("split saved")
        let s = split(of: "Nopa")
        note("server split: \(s ?? [:])")
        app.swipeUp()
        step("split card")
        tapIf(app.buttons["Everyone who owes you"], "Everyone who owes you", timeout: 4)
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
        addPeople(["Priya", "Sam"], way: "amount")
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
        addPeople(["Priya"])
        let toggle = app.switches.firstMatch
        if toggle.waitForExistence(timeout: 3) { toggle.tap() } else { note("MISSING I’m paying a share") }
        step("all for them")
        saveSplit()
        step("saved all for them")
        note("server split: \(split(of: "Lucky") ?? [:])")
    }

    /// Not sure yet → Priya's e-Transfer comes in and is linked → Settle up →
    /// That's everything → Reopen.
    func testSplitNotSureYetThenSettleUp() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"], way: "unknown")
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
        addPeople(["Priya", "Sam", "Jo"], way: "amount")
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
        tapIf(app.buttons["Everyone who owes you"], "Everyone who owes you", timeout: 4)
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
        app.buttons["profile-circle"].firstMatch.tap()
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

    // MARK: Fewer taps (P5, P8, P11; TP-P5-FromPurchase, TP-P8-CardPay, TP-P11-Split)

    private func toastSays(_ words: String, timeout: TimeInterval = 8) -> Bool {
        element(containing: words).waitForExistence(timeout: timeout)
    }

    private func paidBackRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier == 'paid-back-row' AND label BEGINSWITH %@", name)).firstMatch
    }

    /// P11: one sheet. Add Priya and Sam, Evenly is done, "I’m paying a
    /// share" off and on, "Split with Priya and Sam", then the toast's Undo.
    func testFewerSplitInOneSheet() {
        launch()
        openTransaction("Nopa")
        tap(app.buttons["Split with others"], "Split with others")
        XCTAssertTrue(text(containing: "Split $").waitForExistence(timeout: 8), "P11a: no “Split $…” title")
        step("P11a one sheet")
        addPeople(["Priya", "Sam"])
        XCTAssertTrue(text(containing: "Adds up to").exists, "P11a: no Adds up to line")
        let share = app.switches.firstMatch
        XCTAssertTrue(share.waitForExistence(timeout: 4), "P11b: no I’m paying a share")
        share.tap()
        step("P11b paying a share off")
        share.tap()
        tap(app.buttons["split-other-ways"], "Other ways")
        XCTAssertTrue(app.buttons["split-way-amount"].waitForExistence(timeout: 4), "P11c: no Amounts")
        step("P11c other ways")
        tap(app.buttons["Back"].firstMatch, "Back from Other ways")
        sleep(1)
        XCTAssertTrue(press("Split"), "P11a: no Split button")
        XCTAssertTrue(toastSays("Split with Priya and Sam."), "P10b: no split toast")
        step("P10b split toast")
        let s = split(of: "Nopa")
        note("server split: \(s ?? [:])")
        XCTAssertEqual((s?["people"] as? [[String: Any]])?.count, 2, "split with two people")
        tap(app.buttons["Undo"], "Undo on the split toast")
        sleep(3)
        let after = transactionJSON(merchant: "Nopa")
        note("after undo: \(after?["split"] ?? "nil")")
        XCTAssertNotEqual(after?["split"] as? Bool, true, "Undo kept the split")
        step("split undone")
    }

    /// P11d: Add someone new; typing always works and nothing asks for Contacts.
    func testFewerAddSomeoneNewTyping() {
        launch()
        openTransaction("Lucky")
        tap(app.buttons["Split with others"], "Split with others")
        tap(app.buttons["Add someone new"], "Add")
        let field = app.textFields["split-add-name"]
        XCTAssertTrue(field.waitForExistence(timeout: 6), "P11d: no name field")
        if (field.value(forKey: "hasKeyboardFocus") as? Bool) != true { field.tap() }
        field.typeText("Jo")
        XCTAssertTrue(app.buttons["split-contacts"].exists, "P11d: no Choose from Contacts")
        XCTAssertFalse(app.alerts.firstMatch.exists, "P11d: an alert asked for Contacts")
        step("P11d add someone new")
        tap(anyButton(containing: "Add “Jo”"), "Add “Jo”")
        XCTAssertTrue(app.buttons["Jo"].waitForExistence(timeout: 4), "P11d: Jo isn't a chip")
        step("Jo added")
        saveSplit()
        XCTAssertTrue(toastSays("Split with Jo."), "no split toast")
    }

    /// P5a / P5b: a split's person pays part of their share. From the purchase,
    /// Which money paid this back? lists their money first with how it
    /// compares; one tap saves; the rest is still owed.
    func testFewerPaybackFromThePurchase() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya"])
        saveSplit()
        sleep(3)
        openPaidBack()
        XCTAssertTrue(text(containing: "Which money paid this back?").waitForExistence(timeout: 8), "P5a: no title")
        let priya = paidBackRow("Priya")
        XCTAssertTrue(priya.waitForExistence(timeout: 10), "P5a: no money from Priya")
        note("Priya's row: \(priya.label)")
        XCTAssertTrue(priya.label.contains("less than"), "P5a: no compare line")
        step("P5a which money")
        priya.tap()
        XCTAssertTrue(toastSays("Priya paid back $"), "P5b: no toast")
        step("P5b paid back toast")
        let s = split(of: "Gusto")
        note("split after: \(s ?? [:])")
        let p = (s?["people"] as? [[String: Any]])?.first
        XCTAssertGreaterThan(p?["owes"] as? Double ?? 0, 0.005, "P5b: the rest was forgiven")
    }

    /// P5c / P5d: a purchase nobody split. A clear name saves at once; money
    /// with no name asks Who sent this? once.
    func testFewerPaybackWithAndWithoutAName() {
        launch()
        openTransaction("Gusto")
        openPaidBack()
        XCTAssertTrue(text(containing: "Money in since").waitForExistence(timeout: 10), "P5c: no Money in since")
        step("P5c money in since")
        let priya = paidBackRow("Priya")
        XCTAssertTrue(priya.waitForExistence(timeout: 8), "P5c: no Priya Shah")
        priya.tap()
        XCTAssertTrue(toastSays("Priya paid back $42.50."), "P5c: no toast")
        step("P5c saved")
        sleep(4)
        openPaidBack()
        // Pearl tidies the nameless INTERAC E-TRANSFER to "E-transfer".
        let nameless = paidBackRow("E-transfer")
        XCTAssertTrue(nameless.waitForExistence(timeout: 10), "P5d: the nameless e-Transfer isn't listed")
        nameless.tap()
        XCTAssertTrue(text(containing: "Who sent this?").waitForExistence(timeout: 6), "P5d: no Who sent this?")
        step("P5d who sent this")
        let field = app.textFields["who-sent-name"]
        tap(field, "Type a name")
        field.typeText("Jo")
        press("Save")
        XCTAssertTrue(toastSays("Jo paid back $"), "P5d: no toast")
        step("P5d saved")
        note("split after: \(split(of: "Gusto") ?? [:])")
    }

    /// P8a / P8b: a card payment reads "Paid off your card", grey ⇄, and its
    /// page offers no pay and one way out.
    func testFewerCardPayment() {
        launch()
        guard let list = server("transactions/list?q=payment") as? [String: Any],
              let rows = list["transactions"] as? [[String: Any]],
              let pay = rows.first(where: { ($0["card_payment"] as? Bool) == true }),
              let merchant = pay["merchant"] as? String else {
            XCTFail("No card payment in the demo ledger"); return
        }
        note("card payment: \(merchant)")
        openCashFlow()
        let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
        if search.waitForExistence(timeout: 4) {
            search.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            sleep(1); app.typeText(merchant); sleep(2)
        }
        let row = button("Paid off your card")
        XCTAssertTrue(row.waitForExistence(timeout: 10), "P8a: no Paid off your card row")
        step("P8a row")
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(text(containing: "Not spending. The purchases on the card already count.").waitForExistence(timeout: 8),
                      "P8b: no line")
        XCTAssertFalse(button("This is my regular pay").exists, "P8b: offers pay")
        XCTAssertFalse(button("Link to another transfer").exists, "P8b: offers Link")
        step("P8b page")
        tap(app.buttons["not-a-card-payment"], "Not a card payment?")
        step("P8b what was this")
    }

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
        step("P11 large text")
        saveSplit()
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
        app.buttons["profile-circle"].firstMatch.tap()
        step("profile")
    }

    /// THL-308, Ask Pearl on every iPhone (PC-20 to PC-26, CN-06): Before
    /// you ask, Not now, off, Turn on, Try asking, the answers, couldn't
    /// answer, and the switch in Profile › Privacy. The journeys' server has
    /// no key, so the answers are Pearl's built-in ones; no model is called.
    func testAskPearl() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            tap(app.tabBars.buttons["Pearl"], "the Pearl tab")
            if scheme == "light" {
                XCTAssertTrue(app.buttons["ask-turn-on"].waitForExistence(timeout: 15), "No Before you ask")
                XCTAssertFalse(app.textFields["chat-composer"].exists, "The field shows before Turn on")
                step("PC-24 before you ask")
                tap(app.buttons["ask-not-now"], "Not now")
                step("PC-25 ask pearl is off")
                tap(app.buttons["ask-turn-on"], "Turn on Ask Pearl")
            }
            XCTAssertTrue(app.buttons["ask-example-0"].waitForExistence(timeout: 15), "No Try asking")
            step("PC-21 try asking")
            tap(app.buttons["ask-example-0"], "How's this month going?")
            step("PC-22 this month", settle: 3)
            ask("When are my cards due?")
            step("PC-26d cards", settle: 3)
            if scheme == "dark" { break }
            tap(app.buttons["chat-new"].firstMatch, "New chat")
            tap(app.buttons.matching(NSPredicate(format: "label == 'New chat' AND identifier != 'chat-new'")).firstMatch,
                "the sheet's New chat")
            tap(app.buttons["ask-example-1"], "a shop this year")
            step("PC-26a a shop", settle: 3)
            let last = Calendar.current.date(byAdding: .month, value: -1, to: Date())!
            let month = DateFormatter().monthSymbols[Calendar.current.component(.month, from: last) - 1]
            ask("How did \(month) go?")
            step("PC-26b a month", settle: 3)
            app.swipeUp()
            step("PC-26b a month scrolled")
            ask("Any subscriptions I forgot?")
            step("subscriptions", settle: 3)
            ask("Can I afford a trip to Lisbon?")
            step("PC-23 couldn't answer", settle: 3)
            app.buttons["profile-circle"].firstMatch.tap()
            tap(anyButton(containing: "Privacy"), "Privacy and consent")
            XCTAssertTrue(element(containing: "Uses Claude, by Anthropic").waitForExistence(timeout: 15),
                          "No Ask Pearl switch")
            step("CN-06 privacy")
            tap(app.switches.matching(NSPredicate(format: "label == 'Ask Pearl'")).firstMatch, "the Ask Pearl switch")
            step("CN-06 turn off ask pearl")
            tap(button("Keep it on"), "Keep it on")
        }
    }

    /// Ask Pearl in the composer, and send.
    private func ask(_ words: String) {
        let field = app.textFields["chat-composer"]
        tap(field, "the composer")
        field.typeText(words)
        tap(app.buttons["chat-send"], "Send")
    }

    /// AI Phase 4, part 1 (THL-309; run_journeys.py's seed_ai): WL-20's price
    /// rise and WL-21's forgotten subscription on Home, each sheet and its
    /// answer; then Quick sort's TR-30 pair card and TR-20's past trip.
    func testAIDetections() {
        launch("light")
        let rise = app.buttons["worth-sheet-price_rise"]
        if !rise.waitForExistence(timeout: 10) { app.swipeUp() }
        XCTAssertTrue(rise.waitForExistence(timeout: 15), "No price rise in For you")
        scrollTo(rise)
        step("WL-20 WL-21 for you")
        tap(rise, "the price rise")
        XCTAssertTrue(text(containing: "more a year").waitForExistence(timeout: 10), "No price rise sheet")
        step("WL-20 the sheet")
        tap(app.buttons["sheet-primary"], "Got it")
        step("WL-20 got it")
        let forgot = app.buttons["worth-sheet-forgotten"]
        tap(forgot, "the forgotten subscription")
        XCTAssertTrue(text(containing: "Pearl can’t cancel for you").waitForExistence(timeout: 10),
                      "No forgotten sheet")
        step("WL-21 the sheet")
        tap(button("Not mine anymore"), "Not mine anymore")
        step("WL-21 not mine anymore")
        app.swipeDown()
        tap(button("Sort now"), "Sort now")
        let pair = app.descendants(matching: .any)["quick-sort-pair"]
        var tries = 0
        while !pair.exists && tries < 40 {
            if !button("Skip").waitForExistence(timeout: 5) { break }
            button("Skip").tap()
            sleep(1)
            tries += 1
        }
        XCTAssertTrue(pair.waitForExistence(timeout: 10), "No pair card")
        step("TR-30 pair")
        tap(button("Yes"), "Yes on the pair")
        step("TR-30 linked", settle: 3)
        tries = 0
        while !text(containing: "PAST TRIP").exists && tries < 40 {
            if !button("Skip").waitForExistence(timeout: 5) { break }
            button("Skip").tap()
            sleep(1)
            tries += 1
        }
        XCTAssertTrue(text(containing: "PAST TRIP").waitForExistence(timeout: 10), "No past trip card")
        step("TR-20 past trip")
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
