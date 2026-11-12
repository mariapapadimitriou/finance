import XCTest

/// testingBOT's Round 2 journeys (ios/bots/testing-log.md): re-tests of the
/// Round 1 fixes and TEST-18 (a You row on Not sure yet, Set your share, the
/// lock), with real taps against the demo ledger plus Pizza Nova $120.00 and
/// three $25.00 e-Transfers (Priya Shah, Sam Lee, Jo Park). Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/Round2JourneysUITests …`.
final class Round2JourneysUITests: XCTestCase {
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

    @discardableResult
    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15) -> Bool {
        guard e.waitForExistence(timeout: timeout) else { XCTFail("Couldn't find \(what)"); note("MISSING \(what)"); return false }
        var n = 0
        while !e.isHittable && n < 8 { app.swipeUp(velocity: .slow); n += 1 }
        e.tap()
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

    private func checkAllowance(_ label: String, was: Double, moves expected: Double) -> Double {
        let now = allowance()
        let moved = ((now - was) * 100).rounded() / 100
        note("ALLOWANCE \(label): \(now) (moved \(moved), expected \(expected)) \(abs(moved - expected) < 0.01 ? "OK" : "WRONG")")
        XCTAssertEqual(moved, expected, accuracy: 0.01, "Allowance after \(label)")
        return now
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

    private func noteSplit(_ merchant: String, _ when: String) {
        let t = detail(merchant)
        let s = t?["splitting"] as? [String: Any]
        let people = (s?["people"] as? [[String: Any]])?.map { p in
            "\(p["name"] ?? "?") share=\(p["share"] ?? p["amount"] ?? "-") paid=\(p["paid"] ?? "-") status=\(p["status"] ?? "-")"
        } ?? []
        note("SPLIT \(merchant) \(when): amount=\(t?["amount"] ?? "?") mode=\(s?["mode"] ?? "none") you=\(s?["you"] ?? "-") still=\(s?["still"] ?? "-") with_me=\(s?["with_me"] ?? s?["me"] ?? "-") people=\(people)")
    }

    private func owed() -> String {
        guard let o = server("owed") else { return "nil" }
        let d = (try? JSONSerialization.data(withJSONObject: o)) ?? Data()
        return String(String(data: d, encoding: .utf8)?.prefix(900) ?? "")
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
                search.tap()
                search.typeText(merchant)
                sleep(2)
            }
        }
        tap(button(merchant), "the \(merchant) row")
        sleep(1)
    }

    private func addPeople(_ names: [String], next: Bool = true) {
        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), "S-02 has no name field")
        for name in names {
            field.tap()
            field.typeText(name)
            tapIf(app.buttons["Add"], "Add for \(name)", timeout: 3)
        }
        if next {
            step("who was it with")
            tapIf(app.buttons["Next"], "Next on S-02")
            sleep(1)
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

    /// TEST-16: the Done bar over the number pad.
    private func doneBar() -> Bool {
        guard app.keyboards.count > 0 else { return true }
        let done = app.toolbars.buttons["Done"]
        if done.exists && done.isHittable { done.tap(); sleep(1); return true }
        note("NO Done bar over the number pad")
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.12)).tap()
        sleep(1)
        return false
    }

    private func saveEnabled(_ label: String = "Save", prefix: Bool = false) -> Bool {
        let q = app.buttons.matching(NSPredicate(format: prefix ? "label BEGINSWITH %@" : "label == %@", label))
        return q.allElementsBoundByIndex.last?.isEnabled ?? false
    }

    private func notSureSegment() -> XCUIElement {
        app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
    }

    /// TEST-19: after Save split on Not sure yet the page keeps showing
    /// the purchase unsplit; going back and opening it again shows the card.
    private func reopenIfStale(_ merchant: String) {
        if app.buttons["Split with others"].exists && !app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Options for'")).firstMatch.exists {
            note("STALE page after Save split: reopening \(merchant)")
            tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
            sleep(1)
            openTransaction(merchant)
            sleep(2)
        }
    }

    private func closeSheets() {
        for _ in 0..<2 {
            let close = app.buttons.matching(NSPredicate(format: "label == 'Close'")).allElementsBoundByIndex.last
            if let c = close, c.exists, c.isHittable { c.tap(); sleep(1) }
        }
    }

    /// From a person's •••: Mark paid back → Bank or e-Transfer → only
    /// their $25.00 e-Transfer ticked → Link.
    private func linkETransfer(_ who: String, _ amount: String = "25.00") {
        tap(app.buttons["Options for \(who)"], "Options for \(who)")
        tap(button("Mark paid back"), "Mark paid back for \(who)")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer for \(who)")
        // Untick anything Pearl ticked that isn't this person's payment
        // (TEST-20: it can suggest someone else's).
        let all = app.buttons.matching(NSPredicate(format: "label CONTAINS '+$'"))
        _ = all.firstMatch.waitForExistence(timeout: 10)
        sleep(1)
        for r in all.allElementsBoundByIndex where r.exists && r.isSelected && !r.label.contains(who) {
            note("PRE-TICKED for \(who): \(r.label) — unticking")
            r.tap()
        }
        let rows = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", who))
        _ = rows.firstMatch.waitForExistence(timeout: 10)
        sleep(1)
        var picked = false
        for r in rows.allElementsBoundByIndex where r.exists {
            let mine = r.label.contains(amount) || (r.value as? String ?? "").contains(amount)
            if mine && !picked {
                if !r.isSelected { r.tap() }
                picked = true
            } else if r.isSelected {
                r.tap()
            }
        }
        if !picked, let first = rows.allElementsBoundByIndex.first(where: { $0.exists && $0.isHittable }) {
            note("no \(who) row names \(amount); rows: \(rows.allElementsBoundByIndex.map(\.label))")
            if !first.isSelected { first.tap() }
        }
        step("which payment \(who)")
        press("Link", prefix: true)
        sleep(4)
        closeSheets()
    }

    // MARK: - A: re-tests of Round 1

    /// TEST-04, TEST-10, TEST-12; Quick sort regression: Sort now, Yes, Undo,
    /// Skip, an Other card that asks, to the end, then the counts.
    func testSortFromHomeWithSortNow() {
        launch()
        let before = (server("home") as? [String: Any])?["review_count"] as? Int ?? -1
        step("home")
        note("review_count \(before); Sort now: \(app.buttons["Sort now"].exists); See the list: \(app.buttons["See the list"].exists); Review one by one: \(app.buttons["Review one by one"].exists)")
        _ = shows("About a minute")
        if !tapIf(app.buttons["Sort now"], "Sort now") {
            tap(app.buttons["Review one by one"], "Review one by one")
            tap(button("Quick sort"), "Quick sort card")
        }
        let card = app.descendants(matching: .any)["quick-sort-card"]
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Sort now didn't open Quick sort")
        step("quick sort first card")
        note("card 1: \(card.label)")
        tapIf(app.buttons["Yes"], "Yes")
        step("after yes")
        tapIf(app.buttons["Undo"], "Undo", timeout: 4)
        step("after undo")
        note("card after undo: \(card.label)")
        var seen: [String] = []
        var n = 0
        while n < 14 && !app.buttons["Done"].exists {
            if card.exists { seen.append(card.label) }
            if app.buttons["Answer"].exists && app.buttons["Answer"].isHittable {
                step("question card \(n)")
                note("question card: \(card.label)")
                app.buttons["Answer"].tap()
                step("answer opens")
                if tapIf(button("Groceries"), "Groceries", timeout: 4) == false {
                    tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
                    if app.buttons["Skip"].exists { app.buttons["Skip"].tap() }
                }
            } else if app.buttons["Yes"].exists && app.buttons["Yes"].isHittable {
                app.buttons["Yes"].tap()
            } else if app.buttons["Skip"].exists && app.buttons["Skip"].isHittable {
                app.buttons["Skip"].tap()
            } else { break }
            sleep(2)
            n += 1
        }
        note("cards seen: \(seen)")
        for bad in ["Unknown", "Corner ·", "Other?"] where seen.contains(where: { $0.contains(bad) }) {
            note("CARD SAYS \(bad)")
        }
        step("end of quick sort")
        let after = (server("home") as? [String: Any])?["review_count"] as? Int ?? -1
        note("review_count after \(after) (was \(before))")
        tapIf(app.buttons["Done"], "Done", timeout: 4)
        app.tabBars.buttons["Home"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        step("home after sorting")
        note("Cash flow tab value: \(String(describing: app.tabBars.buttons["Cash flow"].value))")
        tapIf(app.buttons["See the list"], "See the list")
        step("needs a look via see the list")
        _ = shows("Other?", timeout: 2)
    }

    /// TEST-01; Needs a look regression, in dark and light.
    func testQuickSortAndNeedsALookInDark() {
        for scheme in ["dark", "light"] {
            launch(scheme)
            step("home")
            if !tapIf(app.buttons["See the list"], "See the list") { tapIf(app.buttons["Review one by one"], "Review one by one") }
            step("needs a look")
            app.swipeUp()
            step("needs a look scrolled")
            app.swipeDown()
            tapIf(button("Quick sort"), "Quick sort card on Needs a look")
            step("quick sort")
            if app.buttons["Skip"].exists { app.buttons["Skip"].tap(); sleep(1) }
            step("quick sort second card")
            app.descendants(matching: .any)["quick-sort-card"].tap()
            step("what was this from the card")
        }
    }

    /// TEST-05, TEST-06, TEST-07: Cash flow's summary, Leave out on a Pearl
    /// sheet that waits for a reason, Sign out and Turn off AI sorting.
    func testCashFlowSummaryAndLeaveOut() {
        launch()
        openCashFlow()
        step("cash flow")
        app.swipeUp()
        step("cash flow scrolled")
        app.swipeDown(); app.swipeDown()
        tap(app.buttons["Select"], "Select")
        tapIf(button("Spotify"), "Spotify in Select")
        tapIf(app.buttons["Leave out"], "Leave out in the bar")
        step("leave out sheet")
        note("alerts \(app.alerts.count)")
        let leave = lastButton("Leave out", prefix: true)
        note("Leave out enabled with no reason: \(leave?.isEnabled ?? false) label \(leave?.label ?? "-")")
        _ = shows("Say why")
        let field = app.textFields.allElementsBoundByIndex.last
        if let f = field, f.exists { f.tap(); f.typeText("A friend's account") }
        step("reason typed")
        note("Leave out enabled with a reason: \(lastButton("Leave out", prefix: true)?.isEnabled ?? false)")
        press("Leave out", prefix: true)
        step("after leave out", settle: 3)
        note("Spotify excluded: \(transactionJSON("Spotify")?["excluded"] ?? "nil")")
        // Sign out: a Pearl sheet; Stay signed in keeps her in.
        app.tabBars.buttons["Profile"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(1)
        if tapIf(app.buttons["Sign out"], "Sign out") {
            step("sign out sheet")
            note("alerts \(app.alerts.count)")
            tapIf(app.buttons["Stay signed in"], "Stay signed in")
        }
        step("profile after stay")
    }

    /// TEST-03 / TEST-15 (Rule A), TEST-13, TEST-09: Gusto $127.50 split by
    /// amounts; the Allowance at each step, on the server.
    func testRuleAWhenFriendsPayBackForDinner() {
        launch()
        var a = allowance()
        note("ALLOWANCE start \(a)")
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        type("42.50", into: amountField("Priya"), "Priya amount")
        type("30", into: amountField("Sam"), "Sam amount")
        type("15", into: amountField("Jo"), "Jo amount")
        _ = doneBar()
        step("gusto amounts")
        press("Save")
        sleep(3)
        step("split saved hero")
        _ = shows("127.50"); _ = shows("Your share $40.00")
        noteSplit("Gusto", "after split")
        a = checkAllowance("split (whole purchase still counts)", was: a, moves: 0)
        app.swipeUp()
        step("scrolled card bar")
        linkETransfer("Priya", "42.50")
        step("priya linked")
        a = checkAllowance("Priya's $42.50 linked", was: a, moves: 42.50)
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back for Sam")
        tap(button("Cash in hand"), "Cash in hand")
        press("Mark $", prefix: true, timeout: 5)
        step("sam cash")
        sleep(3)
        a = checkAllowance("Sam's $30.00 cash", was: a, moves: 30)
        tap(app.buttons["Options for Jo"], "Options for Jo")
        tap(button("Let it go"), "Let it go")
        step("let jo go sheet")
        _ = shows("doesn’t change")
        if let b = lastButton("Let", prefix: true) { b.tap() }
        step("jo let go", settle: 2)
        a = checkAllowance("Let Jo's $15.00 go", was: a, moves: 0)
        if !tapIf(app.buttons["Undo"], "Undo let it go toast", timeout: 3) {
            tapIf(app.buttons["Options for Jo"], "Options for Jo")
            tapIf(button("Undo let it go"), "Undo let it go")
        }
        step("jo back", settle: 2)
        a = checkAllowance("Undo let it go", was: a, moves: 0)
        noteSplit("Gusto", "end")
        app.swipeUp()
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("owed to you")
        note("owed: \(owed())")
    }

    /// TEST-02, TEST-11, TEST-13: Not sure yet, Priya's e-Transfer, Settle up
    /// › Type amounts, That's everything.
    func testNotSureYetThenSettleUpByTyping() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(notSureSegment(), "Not sure")
        step("not sure")
        press("Save split")
        sleep(2)
        reopenIfStale("Gusto")
        tap(app.buttons["Options for Priya"], "Options for Priya")
        step("S-40u2 options")
        _ = shows("Nothing to unlink"); _ = shows("$0.00 goes back", timeout: 1)
        closeSheets()
        linkETransfer("Priya", "42.50")
        step("priya linked")
        tap(button("Settle up"), "Settle up")
        step("settle up")
        tap(button("Type amounts"), "Type amounts")
        step("type amounts")
        _ = shows("127.50"); _ = shows("Who was it with", timeout: 1)
        closeSheets()
        app.swipeDown(velocity: .fast)
        if tapIf(button("That’s everything"), "That's everything") {
            step("thats everything sheet")
            press("That’s everything")
            step("closed", settle: 2)
        }
    }

    /// Is the Not sure yet card missing, or only late? Save, wait, go back
    /// and open the purchase again.
    func testNotSureYetCardAfterReopening() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(notSureSegment(), "Not sure")
        press("Save split")
        step("saved", settle: 6)
        note("card after save: Options for Priya \(app.buttons["Options for Priya"].exists), Split with others \(app.buttons["Split with others"].exists)")
        app.swipeUp()
        step("saved scrolled")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        sleep(2)
        openTransaction("Gusto")
        step("reopened", settle: 4)
        note("card after reopen: Options for Priya \(app.buttons["Options for Priya"].exists), Split with others \(app.buttons["Split with others"].exists)")
        app.swipeUp()
        step("reopened scrolled")
        launch()
        openTransaction("Gusto")
        step("relaunched", settle: 4)
        note("card after relaunch: Options for Priya \(app.buttons["Options for Priya"].exists), Split with others \(app.buttons["Split with others"].exists)")
        app.swipeUp()
        step("relaunched scrolled")
    }

    /// TEST-08, TEST-16: "I had some too" on How to split, the meter, the
    /// Done bar; then Change Sam's share past the total.
    func testIHadSomeTooAndTheNumberPad() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        type("100", into: amountField("Priya"), "Priya")
        type("50", into: amountField("Sam"), "Sam")
        step("too much with the pad up")
        note("Done bar: \(app.toolbars.buttons["Done"].exists)")
        _ = doneBar()
        step("too much")
        note("Save with too much: \(saveEnabled())")
        type("40", into: amountField("Priya"), "Priya")
        type("30", into: amountField("Sam"), "Sam")
        _ = doneBar()
        step("short stays yours")
        note("Save short with me: \(saveEnabled())")
        let toggle = app.switches.matching(NSPredicate(format: "label CONTAINS[c] 'had some'")).firstMatch
        if tapIf(toggle.exists ? toggle : app.switches.firstMatch, "I had some too", timeout: 4) {
            step("i had some too off")
            note("Save short without me: \(saveEnabled())")
            app.switches.firstMatch.tap()
            step("i had some too on again")
        }
        tapIf(app.buttons["Split the rest evenly"], "Split the rest evenly", timeout: 4)
        step("rest evenly")
        press("Save")
        sleep(3)
        noteSplit("Gusto", "saved")
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Change Sam"), "Change Sam's share")
        type("100", into: amountField("Sam"), "Sam")
        step("change sam too much pad up")
        _ = doneBar()
        step("change sam too much")
        note("Save on change share too much: \(saveEnabled())")
    }

    /// TEST-17 (run with --text accessibility-extra-large).
    func testSplitADinnerAtTheLargestTextSize() {
        launch()
        step("home")
        openTransaction("Nopa")
        step("detail")
        tap(app.buttons["Split with others"], "Split with others")
        step("S-02")
        addPeople(["Priya", "Sam"])
        step("S-03 header")
        press("Save")
        sleep(2)
        app.swipeUp()
        step("split card")
        tapIf(app.buttons["Options for Priya"], "Options for Priya")
        step("S-40a")
    }

    /// TEST-14: the audit on the main screens, and the tab's value.
    func testAccessibilityAuditRound2() throws {
        guard #available(iOS 17.0, *) else { throw XCTSkip("needs iOS 17") }
        launch()
        var issues: [String] = []
        func audit(_ screen: String) {
            do {
                try app.performAccessibilityAudit { issue in
                    issues.append("\(screen): \(issue.auditType) · \(issue.compactDescription) · \(issue.element?.label ?? "")")
                    return true
                }
            } catch { issues.append("\(screen): audit failed \(error)") }
        }
        note("Cash flow tab value: \(String(describing: app.tabBars.buttons["Cash flow"].value))")
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
        audit("Split card")
        app.swipeUp()
        audit("Split card scrolled")
        if tapIf(app.buttons["Options for Priya"], "Options for Priya") { sleep(1); audit("Person options") }
        for i in issues { note("AUDIT \(i)") }
    }

    // MARK: - B: TEST-18, Pizza Nova

    /// Pizza Nova $120.00 → Not sure yet with Priya, Sam, Jo and Alex, you in
    /// it. Returns the Allowance just before the split.
    @discardableResult
    private func pizzaNovaNotSure(withMe: Bool = true) -> Double {
        let a = allowance()
        openTransaction("Pizza Nova")
        step("pizza nova page")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo", "Alex"], next: false)
        step("who was it with")
        if !withMe {
            let toggle = app.switches.matching(NSPredicate(format: "label CONTAINS[c] 'had some'")).firstMatch
            if toggle.exists { toggle.tap(); step("S-02 i had some too off") }
        }
        tapIf(app.buttons["Next"], "Next")
        sleep(1)
        if !notSureSegment().exists {
            // S-03u at the largest text sizes: the methods are behind a row.
            tapIf(button("How to split"), "the How to split row", timeout: 4)
            step("method picker large text")
            tapIf(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Not sure'")).firstMatch, "Not sure in the picker", timeout: 4)
            sleep(1)
        } else {
            tap(notSureSegment(), "Not sure")
        }
        step(withMe ? "S-03u2 not sure with you" : "S-03u3 not sure without you")
        let toggle = app.switches.matching(NSPredicate(format: "label CONTAINS[c] 'had some'")).firstMatch
        note("I had some too switch on Not sure: exists \(toggle.exists) value \(String(describing: toggle.value))")
        if !withMe && toggle.exists && (toggle.value as? String) == "1" { toggle.tap(); step("S-03u3 toggle off") }
        _ = shows("Your share · set it any time", timeout: 2)
        press("Save split")
        sleep(3)
        step("S-04u6 saved")
        reopenIfStale("Pizza Nova")
        noteSplit("Pizza Nova", "not sure saved")
        return a
    }

    /// The main story: three pay, you set $17.00, Alex owes $28.00; Undo;
    /// Owed to you before and after; the Allowance throughout.
    func testPizzaNovaThreePaidAndISetMyShare() {
        launch()
        var a = pizzaNovaNotSure()
        a = checkAllowance("Not sure yet split", was: a, moves: 0)
        app.swipeUp()
        step("S-04u6 card with you first")
        note("You row options: \(app.buttons["Options for you"].exists)")
        for who in ["Priya", "Sam", "Jo"] {
            linkETransfer(who)
            step("\(who) linked")
            a = checkAllowance("\(who)'s $25.00 linked", was: a, moves: 25)
        }
        noteSplit("Pizza Nova", "three paid")
        app.swipeUp()
        step("card three paid")
        // Owed to you while it's open (S-14u4).
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("S-14u4 owed to you not settled")
        _ = shows("your share not set")
        note("owed: \(owed())")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        sleep(1)
        // S-40y → S-47a.
        tap(app.buttons["Options for you"], "Options for you")
        step("S-40y your options")
        tap(button("Set your share"), "Set your share")
        let field = app.textFields["your-share"]
        XCTAssertTrue(field.waitForExistence(timeout: 6), "No S-47 field")
        step("S-47a empty")
        note("Save enabled empty: \(saveEnabled("Save", prefix: true))")
        note("Done bar on S-47: \(app.toolbars.buttons["Done"].exists)")
        // S-47e: more than what's left.
        type("50", into: field, "your share")
        step("S-47e too big")
        _ = shows("can be up to $45.00")
        note("Save enabled too big: \(saveEnabled("Save", prefix: true))")
        type("17", into: field, "your share")
        _ = doneBar()
        step("S-47b 17 typed")
        _ = shows("Alex owes $28.00")
        // S-47f: the locked line.
        let locked = element(containing: "linked, locked")
        if locked.exists {
            locked.tap()
            step("tap the locked line")
            note("lock toast after tapping the three-payer line: \(element(containing: "is linked").exists)")
            if press("Back to your share", timeout: 3) { sleep(1) }
        } else { note("MISSING linked, locked line") }
        press("Save · Alex", prefix: true)
        step("S-04u7 saved toast", settle: 1)
        _ = shows("Alex owes you $28.00", timeout: 2)
        let undo = app.buttons["Undo"]
        note("Undo on toast: \(undo.exists)")
        noteSplit("Pizza Nova", "share set")
        a = checkAllowance("Set your share $17.00", was: a, moves: 0)
        if tapIf(undo, "Undo", timeout: 3) {
            step("after undo", settle: 2)
            noteSplit("Pizza Nova", "after undo")
            a = checkAllowance("Undo set your share", was: a, moves: 0)
            _ = shows("not set yet")
        }
        // Again, and on to Owed to you (S-14u3).
        tap(app.buttons["Options for you"], "Options for you again")
        tap(button("Set your share"), "Set your share again")
        type("17", into: app.textFields["your-share"], "your share")
        _ = doneBar()
        press("Save · Alex", prefix: true)
        sleep(5)
        step("S-04u7 set split")
        app.swipeUp()
        step("S-04u7 scrolled")
        _ = shows("what was left")
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("S-14u3 owed to you alex")
        note("owed after: \(owed())")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        // Alex pays cash: only your $17.00 stays counted.
        tap(app.buttons["Options for Alex"], "Options for Alex")
        step("S-40a alex")
        tap(button("Mark paid back"), "Mark paid back for Alex")
        tap(button("Cash in hand"), "Cash in hand")
        press("Mark $", prefix: true, timeout: 5)
        step("alex paid cash", settle: 3)
        a = checkAllowance("Alex's $28.00 cash", was: a, moves: 28)
        noteSplit("Pizza Nova", "everyone paid")
        launch("dark")
        openTransaction("Pizza Nova")
        app.swipeUp()
        step("card dark")
    }

    /// Two still owe (Jo and Alex): S-47c evenly, S-47d typed amounts that
    /// don't add up, the lock toast and Options → Unlink, then Settle up ›
    /// Type amounts on every method.
    func testPizzaNovaTwoStillOwe() {
        launch()
        pizzaNovaNotSure()
        for who in ["Priya", "Sam"] { linkETransfer(who) }
        tap(app.buttons["Options for you"], "Options for you")
        tap(button("Set your share"), "Set your share")
        let field = app.textFields["your-share"]
        XCTAssertTrue(field.waitForExistence(timeout: 6))
        type("17", into: field, "your share")
        _ = doneBar()
        step("S-47c evenly")
        _ = shows("Adds up to $120.00")
        note("Jo field \(String(describing: amountField("Jo").value)) placeholder \(amountField("Jo").placeholderValue ?? "-")")
        type("20", into: amountField("Jo"), "Jo")
        type("20", into: amountField("Alex"), "Alex")
        _ = doneBar()
        step("S-47d left to assign")
        _ = shows("$13.00 left to assign")
        note("Save with $13 left: \(saveEnabled())")
        type("40", into: amountField("Alex"), "Alex")
        _ = doneBar()
        step("too much on S-47")
        note("Save when too much: \(saveEnabled())")
        // S-47f: tap Priya's locked row.
        let priya = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Priya' AND label CONTAINS 'locked'")).firstMatch
        if tapIf(priya, "Priya's locked row", timeout: 3) {
            step("S-47f lock toast")
            _ = shows("Priya’s $25.00 is linked")
            if tapIf(app.buttons["Options"], "Options on the toast", timeout: 3) {
                step("S-40u from the toast", settle: 2)
                _ = shows("Unlink")
                closeSheets()
            }
        }
        step("after options")
        // Settle up › Type amounts, every method, two unpaid.
        app.swipeDown(velocity: .fast)
        if tapIf(button("Settle up"), "Settle up") {
            step("S-45a settle up two unpaid")
            if tapIf(button("Type amounts"), "Type amounts") {
                step("S-45c2 type amounts")
                for m in ["Evenly", "Amounts", "%", "Shares"] {
                    if tapIf(app.buttons[m], "\(m) segment", timeout: 3) { step("settle \(m)") }
                }
                note("Done bar: \(app.toolbars.buttons["Done"].exists)")
            }
        }
    }

    /// You're not in it: no You row anywhere; Settle up leads with "Alex owes
    /// what's left"; Owed to you.
    func testPizzaNovaWithoutMe() {
        launch()
        var a = pizzaNovaNotSure(withMe: false)
        app.swipeUp()
        step("S-04u card without you")
        note("Options for you exists: \(app.buttons["Options for you"].exists); split-you-row: \(app.buttons["split-you-row"].exists)")
        for who in ["Priya", "Sam", "Jo"] { linkETransfer(who) }
        a = allowance()
        step("three paid without you")
        tap(button("Settle up"), "Settle up")
        step("S-45a2 alex owes whats left")
        _ = shows("Alex owes what’s left"); _ = shows("$45.00")
        tapIf(button("Alex owes"), "Alex owes what's left")
        step("after alex owes", settle: 3)
        noteSplit("Pizza Nova", "alex owes the rest")
        a = checkAllowance("Alex owes what's left", was: a, moves: 0)
        app.swipeUp()
        step("card alex owes")
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("owed to you alex 45")
        note("owed: \(owed())")
    }

    /// Everyone pays without your share set (S-04u8), then That's everything
    /// (S-46a3).
    func testPizzaNovaEveryonePaidThenThatsEverything() {
        launch()
        var a = pizzaNovaNotSure()
        for who in ["Priya", "Sam", "Jo"] { linkETransfer(who) }
        a = allowance()
        tap(app.buttons["Options for Alex"], "Options for Alex")
        tap(button("Mark paid back"), "Mark paid back for Alex")
        tap(button("Cash in hand"), "Cash in hand")
        let amt = app.textFields.allElementsBoundByIndex.last
        if let f = amt, f.exists { type("28", into: f, "cash amount"); _ = doneBar() }
        step("alex cash 28")
        press("Mark $", prefix: true, timeout: 5)
        step("S-04u8 everyone paid", settle: 3)
        a = checkAllowance("Alex's $28.00 cash (not sure yet)", was: a, moves: 28)
        app.swipeUp()
        step("S-04u8 scrolled")
        _ = shows("Everyone has paid"); _ = shows("$17.00")
        app.swipeDown(velocity: .fast)
        if tapIf(button("That’s everything"), "That's everything") {
            step("S-46a3 thats everything")
            _ = shows("$17.00"); _ = shows("No change")
            press("That’s everything")
            step("closed", settle: 2)
            a = checkAllowance("That's everything", was: a, moves: 0)
            noteSplit("Pizza Nova", "closed")
            app.swipeUp()
            step("closed card")
        }
    }

    /// The new screens in dark (and, run with --text
    /// accessibility-extra-large, at the largest text size).
    func testPizzaNovaInDarkMode() {
        launch("dark")
        pizzaNovaNotSure()
        linkETransfer("Priya"); linkETransfer("Sam")
        app.swipeUp()
        step("card dark")
        tap(app.buttons["Options for you"], "Options for you")
        step("S-40y dark")
        tap(button("Set your share"), "Set your share")
        type("17", into: app.textFields["your-share"], "your share")
        _ = doneBar()
        step("S-47c dark")
        app.swipeUp()
        step("S-47c dark scrolled")
        let priya = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Priya' AND label CONTAINS 'locked'")).firstMatch
        if tapIf(priya, "Priya's locked row", timeout: 3) { step("S-47f dark toast") }
        press("Save")
        step("S-04u7 dark", settle: 2)
        app.swipeUp()
        step("S-04u7 dark scrolled")
    }

    /// The audit on the new screens.
    func testPizzaNovaAccessibilityAudit() throws {
        guard #available(iOS 17.0, *) else { throw XCTSkip("needs iOS 17") }
        launch()
        var issues: [String] = []
        func audit(_ screen: String) {
            do {
                try app.performAccessibilityAudit { issue in
                    issues.append("\(screen): \(issue.auditType) · \(issue.compactDescription) · \(issue.element?.label ?? "")")
                    return true
                }
            } catch { issues.append("\(screen): audit failed \(error)") }
        }
        pizzaNovaNotSure()
        audit("S-04u6 card")
        app.swipeUp()
        audit("S-04u6 card scrolled")
        linkETransfer("Priya")
        tap(app.buttons["Options for you"], "Options for you")
        sleep(1)
        audit("S-40y")
        tap(button("Set your share"), "Set your share")
        type("17", into: app.textFields["your-share"], "your share")
        _ = doneBar()
        audit("S-47c")
        press("Save")
        sleep(3)
        audit("S-04u7")
        for i in issues { note("AUDIT \(i)") }
    }
}
