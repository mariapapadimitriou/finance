import XCTest

/// The fewer-taps boards (P2, P3, P4, P10, P14, P15; Pearl redesign canvas
/// v100), with real taps against the journeys' demo ledger, where Corner
/// Store, Makersmkt and Northshop have no real guess (Pearl's best is Other).
/// Run with `python3 ios/tools/run_journeys.py --suite PearlUITests/FewerTapsUITests …`.
final class FewerTapsUITests: XCTestCase {
    private var app: XCUIApplication!
    private var stepNumber = 0
    private var appearance = "light"

    private var shots: String { ProcessInfo.processInfo.environment["PEARL_SHOTS"] ?? NSTemporaryDirectory() }
    private var port: String { ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051" }

    override func setUp() {
        continueAfterFailure = true
        app = XCUIApplication()
    }

    // MARK: Helpers

    private func launch(_ scheme: String = "light") {
        appearance = scheme
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(port)", "-pearl.appearance", scheme]
        app.launch()
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 8) { notNow.tap() }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        sleep(2)
        clearInterruptions()
    }

    /// N-01 ("Want a heads-up?") and iOS's notification prompt can come up
    /// late, over whatever is on screen: put them away first.
    private func clearInterruptions() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let deny = springboard.buttons["Don’t Allow"]
        if deny.exists { deny.tap(); note("dismissed iOS notification prompt"); sleep(1) }
        let notNow = app.buttons["Not now"]
        if notNow.exists && notNow.isHittable && app.staticTexts["Want a heads-up?"].exists {
            notNow.tap(); note("dismissed N-01 late"); sleep(1)
        }
    }

    @discardableResult
    private func step(_ name: String, settle: UInt32 = 1) -> String {
        sleep(settle)
        clearInterruptions()
        stepNumber += 1
        let test = String(name.prefix(60)).replacingOccurrences(of: " ", with: "-")
        let method = self.name.components(separatedBy: " ").last?.replacingOccurrences(of: "]", with: "") ?? "test"
        let base = "\(shots)/\(method)-\(String(format: "%02d", stepNumber))-\(appearance)-\(test)"
        FileManager.default.createFile(atPath: base + ".png", contents: XCUIScreen.main.screenshot().pngRepresentation)
        try? app.debugDescription.write(toFile: base + ".txt", atomically: true, encoding: .utf8)
        print("JOURNEY \(base).png")
        return base
    }

    private func note(_ s: String) { print("JOURNEY note: \(s)") }

    private func button(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
    }

    private func anyButton(containing text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func element(containing text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func shows(_ text: String, timeout: TimeInterval = 4) -> Bool {
        let ok = element(containing: text).waitForExistence(timeout: timeout)
        note("\(ok ? "SEEN" : "NOT SEEN") “\(text)”")
        return ok
    }

    /// Whether `e` is inside the window (hittable or not: sheets' rows often aren't).
    private func onScreen(_ e: XCUIElement) -> Bool {
        let f = e.frame, w = app.windows.firstMatch.frame
        return !f.isEmpty && w.contains(CGPoint(x: f.midX, y: f.midY)) && f.midY < w.maxY - 90
    }

    /// Taps by coordinate, which reaches controls XCUI calls not hittable.
    @discardableResult
    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15) -> Bool {
        guard e.waitForExistence(timeout: timeout) else { XCTFail("Couldn't find \(what)"); note("MISSING \(what)"); return false }
        var n = 0
        while !onScreen(e) && n < 6 { app.swipeUp(velocity: .slow); n += 1 }
        e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        return true
    }

    @discardableResult
    private func tapIf(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 8) -> Bool {
        guard e.waitForExistence(timeout: timeout) else { note("MISSING \(what)"); return false }
        var n = 0
        while !e.isHittable && n < 8 { app.swipeUp(velocity: .slow); n += 1 }
        e.tap()
        return true
    }

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

    private func lastButton(_ label: String, prefix: Bool = false) -> XCUIElement? {
        let q = app.buttons.matching(NSPredicate(format: prefix ? "label BEGINSWITH %@" : "label == %@", label))
        return q.allElementsBoundByIndex.reversed().first { $0.exists && $0.isHittable }
    }

    private func server(_ path: String) -> Any? {
        var result: Any?
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: URL(string: "http://localhost:\(port)/api/\(path)")!) { data, _, _ in
            if let data = data { result = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return result
    }

    private func allowance() -> Double {
        ((server("home") as? [String: Any])?["safe_to_spend"] as? [String: Any])?["amount"] as? Double ?? .nan
    }

    private func openCashFlow() {
        clearInterruptions()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
    }

    private func openTransaction(_ merchant: String) {
        openCashFlow()
        let row = button(merchant)
        if !row.waitForExistence(timeout: 8) || !row.isHittable {
            let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
            if search.waitForExistence(timeout: 3) {
                search.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                sleep(1)
                app.typeText(merchant)
                sleep(2)
            }
        }
        tap(button(merchant), "the \(merchant) row")
        sleep(1)
    }

    private func transactionJSON(_ merchant: String) -> [String: Any]? {
        let q = merchant.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? merchant
        guard let list = server("transactions?q=\(q)") as? [String: Any],
              let rows = list["transactions"] as? [[String: Any]] else { return nil }
        return rows.first { ($0["merchant"] as? String ?? "").localizedCaseInsensitiveContains(merchant) }
    }

    private func detail(_ merchant: String) -> [String: Any]? {
        guard let id = transactionJSON(merchant)?["id"] as? String,
              let d = server("transactions/\(id)") as? [String: Any] else { return nil }
        return (d["transaction"] as? [String: Any]) ?? d
    }

    /// P3 / P4: the four tiles for this purchase, as the server works them
    /// out (finance/likely.py, Needs a look's `likely`), else her most used.
    private func likeliest(for merchant: String) -> [String] {
        if let review = server("review") as? [String: Any],
           let items = review["unsure_category"] as? [[String: Any]],
           let item = items.first(where: { (($0["txn"] as? [String: Any])?["merchant"] as? String ?? "")
               .localizedCaseInsensitiveContains(merchant) }),
           let four = item["likely"] as? [String], !four.isEmpty {
            return Array(four.prefix(4))
        }
        return likeliest()
    }

    /// Her four most used spending categories, as the app works them out.
    private func likeliest() -> [String] {
        guard let body = server("categories") as? [String: Any],
              let cats = body["categories"] as? [[String: Any]] else { return [] }
        let spending = cats.filter { ["essentials", "lifestyle"].contains($0["group"] as? String ?? "lifestyle")
            && $0["hidden"] as? Bool != true && $0["name"] as? String != "Unsorted transfers" }
        let ordered = ["essentials", "lifestyle"].flatMap { g in spending.filter { ($0["group"] as? String ?? "lifestyle") == g } }
        let ranked = ordered.enumerated().sorted { a, b in
            let ua = a.element["uses"] as? Int ?? 0, ub = b.element["uses"] as? Int ?? 0
            return ua != ub ? ua > ub : a.offset < b.offset
        }
        return ranked.prefix(4).compactMap { $0.element["name"] as? String }
    }

    /// Home's Needs a look card: See the list.
    private func openNeedsALook() {
        tap(app.buttons["See the list"].firstMatch, "See the list")
        sleep(2)
    }

    private func toast(_ text: String, timeout: TimeInterval = 8) -> Bool {
        let ok = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
            .waitForExistence(timeout: timeout)
        note("\(ok ? "SEEN" : "NOT SEEN") toast “\(text)”")
        return ok
    }

    private func undo() {
        let undo = app.buttons["Undo"]
        if undo.waitForExistence(timeout: 5) {
            undo.tap()
        } else {
            // The toast's Undo is an accessibility action on the toast.
            XCTFail("No Undo on the toast")
        }
        sleep(2)
    }

    // MARK: P3 · No "Other?" guesses

    /// P3a–c: Needs a look › Corner Store › What was this? with four tiles;
    /// one tap sorts it, the list closes up, the toast has Undo.
    func testFewerTapsP3NeedsALookTile() {
        launch()
        openNeedsALook()
        tap(button("Corner Store"), "Corner Store in Needs a look")
        step("what was this, no guess")
        XCTAssertFalse(element(containing: "Other?").exists, "P3: no “Other?” guess")
        let four = likeliest(for: "Corner Store")
        note("likeliest \(four)")
        guard let first = four.first else { return XCTFail("No categories") }
        tap(app.buttons[first].firstMatch, "the \(first) tile")
        XCTAssertTrue(toast("Corner Store is \(first)."), "P3c toast")
        step("sorted, toast with undo")
        undo()
        step("after undo")
        XCTAssertTrue(shows("Undone"), "P10c: Undone after Undo")
    }

    /// P3d: an unsorted purchase from Cash flow shows the same tiles on its
    /// page; a tile sorts at once, with Undo.
    func testFewerTapsP3PageTiles() {
        launch()
        openTransaction("Northshop")
        step("northshop page, tiles")
        XCTAssertTrue(shows("What was this?"), "P3d heading")
        XCTAssertTrue(app.buttons["More"].exists, "P2: More row")
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Yes, Other'")).firstMatch.exists,
                       "P3d: no Yes, Other")
        let four = likeliest(for: "Northshop")
        guard let first = four.first else { return XCTFail("No categories") }
        tap(app.buttons[first].firstMatch, "the \(first) tile")
        XCTAssertTrue(toast("Northshop is \(first)."), "P3d toast")
        step("sorted on the page")
    }

    // MARK: P4 · Quick sort

    /// P4a–c: a card with no guess has the tiles and only Skip; a tile sorts
    /// and moves on, the toast's Undo brings the card back.
    func testFewerTapsP4QuickSortTile() {
        launch()
        tap(app.buttons["Sort now"].firstMatch, "Sort now")
        sleep(3)
        var found = false
        for _ in 0..<10 {
            step("quick sort card")
            if element(containing: "What was this?").exists { found = true; break }
            tap(app.buttons["Skip"].firstMatch, "Skip")
            sleep(2)
        }
        guard found else { return XCTFail("No card without a guess") }
        XCTAssertFalse(app.buttons["Yes"].exists, "P4a: no Yes on a tiles card")
        let name = ["Corner Store", "Makersmkt", "Northshop"].first { element(containing: $0).exists } ?? "?"
        let four = likeliest(for: name)
        guard let first = four.first else { return XCTFail("No categories") }
        tap(app.buttons[first].firstMatch, "the \(first) tile on the card")
        XCTAssertTrue(toast("\(name) is \(first)."), "P4c toast")
        step("next card, toast")
        undo()
        step("card back after undo")
        XCTAssertTrue(shows(name), "P4c: Undo brings the card back")
    }

    // MARK: P2 / P14 / P9 · More

    /// P2b, P14a–c, P9a–c: More holds the rest; One-off toasts in the sheet
    /// and shows as a pill; I pay this every month adds a bill with Undo.
    func testFewerTapsP2MoreOneOffAndMonthly() {
        launch()
        openTransaction("Bar Isabel")
        step("purchase page")
        XCTAssertFalse(element(containing: "OPTIONS").exists, "P2a: no Options group")
        XCTAssertTrue(app.buttons["Split with others"].exists || app.buttons["Edit"].exists, "P2a: Split")
        tap(app.buttons["More"], "More")
        step("more sheet")
        for row in ["Someone paid me back", "I pay this every month", "Moved between my accounts", "Add a note"] {
            XCTAssertTrue(element(containing: row).exists, "More has \(row)")
        }
        let oneOff = app.switches["One-off"]
        XCTAssertTrue(oneOff.waitForExistence(timeout: 8), "More has One-off")
        // The switch itself, at the row's right.
        oneOff.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        XCTAssertTrue(toast("One-off. Your usual month stays the same."), "P14b toast")
        step("one-off on, toast in the sheet")
        tap(app.buttons["Close"].firstMatch, "close More")
        sleep(1)
        XCTAssertTrue(element(containing: "One-off").waitForExistence(timeout: 5), "P14c: the One-off pill")
        step("one-off pill")
        tap(app.buttons["More"], "More again")
        tap(button("I pay this every month"), "I pay this every month")
        step("filled in from the purchase")
        tap(app.buttons["Add to my bills"], "Add to my bills")
        XCTAssertTrue(toast("Bar Isabel Toronto is one of your bills now."), "P9c toast")
        XCTAssertTrue(element(containing: "Every month").waitForExistence(timeout: 8), "P9c pill")
        step("every month pill")
        undo()
        step("bill undone")
    }

    // MARK: P10 / P15 · Category, with Undo

    /// P10a–c: a category change toasts with Undo; after Undo, "Undone.
    /// Loblaws is Groceries again." with none.
    func testFewerTapsP10CategoryUndo() {
        launch()
        openTransaction("Loblaws")
        let was = (detail("Loblaws")?["category"] as? String) ?? "Groceries"
        tap(button("Change").exists ? button("Change") : button(was), "Change")
        step("category picker")
        XCTAssertTrue(app.textFields["Search categories"].exists, "P15a: search")
        XCTAssertTrue(shows("Most used"), "P15a: Most used")
        let pick = likeliest().first { $0 != was } ?? "Dining"
        tap(app.buttons[pick].firstMatch, "the \(pick) tile")
        XCTAssertTrue(toast("Loblaws is \(pick) now."), "P10a toast")
        step("changed, toast")
        undo()
        XCTAssertTrue(toast("Undone. Loblaws is \(was) again."), "P10c")
        step("undone")
    }

    /// P15b–c: search a few letters, results as rows with the group; All
    /// categories has the plain groups.
    func testFewerTapsP15Search() {
        launch()
        openTransaction("Loblaws")
        tap(button("Groceries"), "Change")
        tap(app.buttons["All categories"], "All categories")
        step("all categories")
        XCTAssertTrue(shows("Everyday"), "P15c Everyday")
        XCTAssertTrue(shows("Not really spending"), "P15c Not really spending")
        XCTAssertTrue(shows("Someone else’s purchase"), "P15c plain names")
        tap(app.buttons["Back"].firstMatch, "Back")
        let search = app.textFields["Search categories"]
        tap(search, "search")
        sleep(1)
        app.typeText("pet")
        step("search pet")
        XCTAssertTrue(app.buttons["Pets"].waitForExistence(timeout: 5), "P15b: Pets row")
        tap(app.buttons["Pets"], "Pets")
        XCTAssertTrue(toast("Loblaws is Pets now."), "P15b toast")
        step("picked pets")
        undo()
    }

    // MARK: P5h · No clear name

    /// P5h: the seeded "INTERAC E-TRANSFER" $60.00 is half of Pai Northern
    /// Thai, which Sam owes $60.00 on. The card guesses the purchase, never
    /// who; Yes asks Who sent this? with Sam first, a field to type a name,
    /// and Sam's pick pays it back.
    func testFewerTapsP5hNameless() {
        launch()
        tap(app.buttons["Sort now"].firstMatch, "Sort now")
        sleep(3)
        var found = false
        for _ in 0..<16 {
            if element(containing: "of Pai Northern Thai?").exists { found = true; break }
            // A payback guess has Not this / Yes, no Skip: a swipe left skips it.
            if app.buttons["Skip"].exists {
                tap(app.buttons["Skip"].firstMatch, "Skip")
            } else {
                app.descendants(matching: .any)["quick-sort-card"].firstMatch.swipeLeft()
            }
            sleep(2)
        }
        guard found else { step("no p5h card"); return XCTFail("P5h: no card for the nameless e-Transfer") }
        step("p5h card")
        XCTAssertTrue(shows("Exactly half of $120.00"), "P5h: the plain consequence")
        tap(app.buttons["Yes"].firstMatch, "Yes")
        XCTAssertTrue(shows("Who sent this?", timeout: 8), "P5h: asks who")
        XCTAssertTrue(shows("On Pai Northern Thai"), "P5h: everyone on the split")
        XCTAssertTrue(app.textFields["who-sent-name"].exists, "P5h: type a name")
        step("who sent this")
        tap(button("Sam"), "Sam")
        XCTAssertTrue(toast("Sam paid back $60.00"), "P5h: Sam paid back")
        step("sam paid back, toast")
        undo()
    }
}
