import XCTest

/// testingBOT's Round 2 journeys (ios/bots/testing-log.md): re-tests of the
/// Round 1 fixes and TEST-18 (a You row on Not sure yet, Set your share, the
/// lock), with real taps against the demo ledger plus Pizza Nova $120.00 and
/// three $25.00 e-Transfers (Priya Shah, Sam Lee, Jo Park). Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/Round2JourneysUITests …`.
final class Round3JourneysUITests: XCTestCase {
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


    // MARK: - Round 3

    /// Opens the purchase's split sheet and adds people; stops on How to split.
    private func startSplit(_ merchant: String, _ people: [String]) {
        openTransaction(merchant)
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(people)
    }

    private func chooseNotSure() {
        if !notSureSegment().exists {
            tapIf(button("How to split"), "the How to split row", timeout: 4)
            tapIf(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Not sure'")).firstMatch, "Not sure in the picker", timeout: 4)
            sleep(1)
        } else {
            tap(notSureSegment(), "Not sure")
        }
    }

    /// TEST-19 re-test: the card must be there without reopening.
    private func cardAppearsAtOnce(_ who: String, _ label: String) {
        let ok = app.buttons["Options for \(who)"].waitForExistence(timeout: 4)
        note("TEST-19 \(label): card at once \(ok); Split with others still offered \(app.buttons["Split with others"].exists)")
        if !ok { reopenIfStale(label) }
    }

    // MARK: A' (ddaa159)

    /// T-01r3 (TEST-05) and TEST-12's chip on Cash flow, light and dark.
    func testR3CashFlowBeforePayday() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            openCashFlow()
            step("cash flow summary")
            for words in ["Spent so far", "Pay expected", "Pay to come", "Over", "Came in", "Other?"] { _ = shows(words, timeout: 1) }
            app.swipeUp()
            step("cash flow rows")
            let corner = button("Corner Store")
            var n = 0
            while !(corner.exists && corner.isHittable) && n < 6 { app.swipeUp(velocity: .slow); n += 1 }
            note("Corner Store row: \(corner.exists ? corner.label : "not found")")
            step("corner store row")
        }
    }

    /// TEST-09 (bar), TEST-16 (pad), TEST-19 (Not sure yet card) on A'.
    func testR3SplitPageBarPadAndNotSure() {
        launch()
        startSplit("Gusto", ["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        type("100", into: amountField("Priya"), "Priya")
        type("50", into: amountField("Sam"), "Sam")
        step("pad up too much")
        let save = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last
        let toggle = app.switches.matching(NSPredicate(format: "label CONTAINS[c] 'had some'")).firstMatch
        let status = element(containing: "too much")
        note("pad up: status hittable \(status.exists && status.isHittable) frame \(status.frame); Save frame \(save?.frame ?? .zero); toggle frame \(toggle.frame)")
        _ = doneBar()
        type("40", into: amountField("Priya"), "Priya")
        type("30", into: amountField("Sam"), "Sam")
        _ = doneBar()
        press("Save")
        sleep(3)
        app.swipeUp(); app.swipeUp()
        step("scrolled split page bar")
        // Not sure yet on Nopa: the card at once (TEST-19).
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        startSplit("Nopa", ["Priya", "Sam"])
        chooseNotSure()
        press("Save split")
        sleep(2)
        step("not sure saved")
        cardAppearsAtOnce("Priya", "Nopa")
        app.swipeUp()
        step("not sure card scrolled")
        if tapIf(button("That’s everything"), "That's everything", timeout: 4) {
            press("That’s everything")
            sleep(2)
            step("closed at once")
            note("TEST-19 close: Reopen split shown \(button("Reopen split").waitForExistence(timeout: 4)); Settle up still \(button("Settle up").exists)")
        }
        launch("dark")
        openTransaction("Gusto")
        app.swipeUp(); app.swipeUp()
        step("scrolled split page bar dark")
    }

    /// TEST-14 on A': audit the transaction page, split card and options.
    func testR3AuditOnA() throws {
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
        openTransaction("Gusto")
        note("hero label: \(app.staticTexts.matching(NSPredicate(format: "label CONTAINS '127.50'")).firstMatch.label)")
        audit("Transaction")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        audit("How to split")
        press("Save")
        sleep(3)
        app.swipeUp()
        audit("Split card scrolled")
        for i in issues { note("AUDIT \(i)") }
    }

    /// TEST-22 and TEST-16 at the largest text size (run with
    /// --text accessibility-extra-large).
    func testR3LargestTextSplit() {
        launch()
        startSplit("Nopa", ["Priya", "Sam"])
        step("how to split large")
        let save = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last
        let status = element(containing: "Adds up")
        note("AX: status frame \(status.frame) hittable \(status.exists && status.isHittable); Save frame \(save?.frame ?? .zero)")
        press("Save")
        sleep(3)
        app.swipeUp()
        step("split card large")
        app.swipeUp()
        step("split card large scrolled")
    }

    /// A Cash flow row found by scrolling, not by search (search rows are
    /// drawn differently).
    private func rowWithoutSearch(_ merchant: String, _ shot: String) {
        let cancel = app.buttons["Cancel"]
        if cancel.exists && cancel.isHittable { cancel.tap(); sleep(1) }
        openCashFlow()
        let row = button(merchant)
        var n = 0
        while !(row.exists && row.isHittable) && n < 12 { app.swipeUp(velocity: .slow); n += 1 }
        app.swipeUp(velocity: .slow)
        note("\(merchant) row (no search): \(row.exists ? row.label : "not found")")
        step(shot)
    }

    // MARK: B' (8ec40b0)

    /// T-01r2: Cash flow's split notes, while people owe, Not sure yet,
    /// and once everyone has paid.
    func testR3CashFlowSplitNotes() {
        launch()
        startSplit("Gusto", ["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        type("42.50", into: amountField("Priya"), "Priya")
        type("30", into: amountField("Sam"), "Sam")
        type("15", into: amountField("Jo"), "Jo")
        _ = doneBar()
        press("Save")
        sleep(3)
        linkETransfer("Priya", "42.50")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        rowWithoutSearch("Gusto", "cash flow gusto note")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        // Not sure yet, Pizza Nova with three paid.
        pizzaNovaNotSure()
        for who in ["Priya", "Sam", "Jo"] { linkETransfer(who) }
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        openCashFlow()
        let pizza = button("Pizza Nova")
        note("Pizza Nova row: \(pizza.waitForExistence(timeout: 6) ? pizza.label : "?")")
        step("cash flow pizza note")
        // Alex pays: everyone has paid.
        openTransaction("Pizza Nova")
        tap(app.buttons["Options for Alex"], "Options for Alex")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Cash in hand"), "Cash in hand")
        if let f = app.textFields.allElementsBoundByIndex.last, f.exists { type("28", into: f, "cash"); _ = doneBar() }
        press("Mark $", prefix: true, timeout: 5)
        sleep(3)
        app.swipeUp()
        step("S-04u8 everyone paid")
        _ = shows("what’s left after paybacks"); _ = shows("Everyone has paid")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        openCashFlow()
        note("Pizza Nova row after all paid: \(button("Pizza Nova").waitForExistence(timeout: 6) ? button("Pizza Nova").label : "?")")
        step("cash flow pizza all paid")
    }

    /// "What was your share?" with all four methods, and the locked payers;
    /// TEST-20 (nothing of anyone else's ticked) on the way.
    func testR3WhatWasYourShareFourMethods() {
        launch()
        pizzaNovaNotSure()
        cardAppearsAtOnce("Priya", "Pizza Nova")
        for who in ["Priya", "Sam"] { linkETransfer(who) }
        // Jo's sheet: nothing ticked, no Amount matches (TEST-20).
        tap(app.buttons["Options for Jo"], "Options for Jo")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        sleep(2)
        let ticked = app.buttons.matching(NSPredicate(format: "label CONTAINS '+$'")).allElementsBoundByIndex.filter { $0.isSelected }.map(\.label)
        note("TEST-20 Jo's sheet: ticked \(ticked); Amount matches \(element(containing: "Amount matches").exists); Suggested \(element(containing: "SUGGESTED").exists)")
        step("jo which payment")
        closeSheets()
        tap(app.buttons["Options for you"], "Options for you")
        tap(button("Set your share"), "Set your share")
        let field = app.textFields["your-share"]
        XCTAssertTrue(field.waitForExistence(timeout: 6))
        type("17", into: field, "your share")
        _ = doneBar()
        step("S-47c evenly")
        for m in ["Amounts", "%", "Shares", "Evenly"] {
            if tapIf(app.buttons[m], "\(m) on S-47", timeout: 3) {
                sleep(1)
                step("S-47 \(m)")
                for w in ["Adds up", "left to assign", "too much", "share", "%"] where element(containing: w).exists { note("S-47 \(m): \(element(containing: w).label)") }
            }
        }
        app.swipeUp()
        step("S-47 scrolled")
        // S-47e: too big.
        type("80", into: field, "your share")
        _ = doneBar()
        step("S-47e too big")
        _ = shows("can be up to"); _ = shows("Alex owes you", timeout: 1); _ = shows("Allowance doesn’t change", timeout: 1)
        closeSheets()
    }

    /// TEST-18's three differences: S-47g (who paid you back), S-04u8, and
    /// S-47e; plus TEST-23's count.
    func testR3WhoPaidYouBackAndEveryonePaid() {
        launch()
        pizzaNovaNotSure()
        cardAppearsAtOnce("Priya", "Pizza Nova")
        for who in ["Priya", "Sam", "Jo"] { linkETransfer(who) }
        tap(app.buttons["Options for you"], "Options for you")
        tap(button("Set your share"), "Set your share")
        type("17", into: app.textFields["your-share"], "your share")
        _ = doneBar()
        let line = element(containing: "linked, locked")
        if tapIf(line, "the folded Paid back line", timeout: 4) {
            step("S-47g who paid you back")
            _ = shows("Who paid you back")
            if tapIf(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sam'")).firstMatch, "Sam on S-47g", timeout: 4) {
                step("S-40u from S-47g")
                _ = shows("Unlink")
            }
        }
        closeSheets(); closeSheets()
        // Settle up › Shares count (TEST-23).
        if tapIf(button("Settle up"), "Settle up", timeout: 4) {
            tapIf(button("Type amounts"), "Type amounts", timeout: 4)
            if tapIf(app.buttons["Shares"], "Shares", timeout: 4) {
                step("settle shares count")
                _ = shows("shares · adds up")
            }
            closeSheets()
        }
    }

    /// Option C / TEST-18b, the $100 example: Ask Sam + I owe Priya, Undo;
    /// Sam's share is $20.00 (Priya skipped); Ask Sam + It's a gift; then
    /// S-48e from Priya's •••; Owed to you (S-14u5).
    func testR3OptionCAnswers() {
        launch()
        let start = allowance()
        startSplit("Bar Isabel", ["Sam", "Priya"])
        chooseNotSure()
        press("Save split")
        sleep(2)
        cardAppearsAtOnce("Sam", "Bar Isabel")
        linkETransfer("Sam", "20.00")
        linkETransfer("Priya", "40.00")
        var a = checkAllowance("Sam $20 + Priya $40 linked", was: start, moves: 60)
        func settleEvenly() {
            tap(button("Settle up"), "Settle up")
            tap(button("Type amounts"), "Type amounts")
            tapIf(app.buttons["Evenly"], "Evenly", timeout: 3)
            step("S-48c type amounts evenly")
            _ = shows("to check"); _ = shows("Pearl asks next", timeout: 1)
            press("Next", prefix: true)
            sleep(1)
        }
        // 1. Ask Sam, I owe Priya.
        settleEvenly()
        step("S-48a sam")
        _ = shows("Sam paid $20.00"); _ = shows("$33.33", timeout: 1)
        press("Ask Sam", prefix: true)
        sleep(1)
        step("S-48b priya")
        _ = shows("Priya paid $6.67 more"); _ = shows("Allowance", timeout: 1)
        for w in ["Only “I owe", "lower your Allowance"] where element(containing: w).exists { note("S-48b callout: \(element(containing: w).label)") }
        press("I owe Priya", prefix: true)
        sleep(2)
        step("S-48c answered before settle")
        press("Settle up")
        sleep(3)
        step("S-48d settled toast")
        _ = shows("Sam owes $13.33")
        a = checkAllowance("Ask Sam + I owe Priya", was: a, moves: -6.67)
        noteSplit("Bar Isabel", "ask + I owe")
        note("owed: \(owed())")
        app.swipeUp()
        step("S-48d card")
        tapIf(app.buttons["See everyone who owes you"], "See everyone who owes you", timeout: 4)
        step("S-14u5 owed to you and you owe")
        tapIf(app.buttons["Back"].firstMatch, "Back", timeout: 3)
        // S-48e: change Priya's extra to a gift, then back.
        if tapIf(app.buttons["Options for Priya"], "Options for Priya", timeout: 6) {
            step("S-48e priya options")
            if tapIf(button("Change what the extra"), "Change what the extra", timeout: 4) {
                step("S-48e asks again")
                press("It’s a gift", prefix: true)
                sleep(3)
                step("S-48e gift")
                a = checkAllowance("S-48e I owe → gift", was: a, moves: 0)
                noteSplit("Bar Isabel", "after S-48e gift")
            }
        }
        // Undo back to Not sure yet: reopen the purchase and use the card's
        // Undo isn't available now; Reopen/Edit is out of scope. Fresh start:
        launch()
        let b = allowance()
        note("ALLOWANCE relaunch \(b) (start \(start))")
    }

    /// Option C second path: Sam's share is $20.00, so Priya matches and
    /// isn't asked; Undo goes back to Not sure yet.
    func testR3OptionCSamsShareAndUndo() {
        launch()
        let start = allowance()
        startSplit("Bar Isabel", ["Sam", "Priya"])
        chooseNotSure()
        press("Save split")
        sleep(2)
        cardAppearsAtOnce("Sam", "Bar Isabel")
        linkETransfer("Sam", "20.00")
        linkETransfer("Priya", "40.00")
        var a = checkAllowance("linked", was: start, moves: 60)
        tap(button("Settle up"), "Settle up")
        tap(button("Type amounts"), "Type amounts")
        tapIf(app.buttons["Evenly"], "Evenly", timeout: 3)
        press("Next", prefix: true)
        sleep(1)
        step("S-48a sam 1 of 2")
        press("Sam’s share is", prefix: true)
        sleep(2)
        step("answered sam share")
        press("Settle up")
        sleep(3)
        step("after sams share")
        note("Priya asked after? \(element(containing: "Priya paid").exists)")
        if element(containing: "Priya paid").exists { step("priya still asked"); closeSheets() }
        a = checkAllowance("Sam's share is $20.00", was: a, moves: 0)
        noteSplit("Bar Isabel", "sam's share 20")
        if tapIf(app.buttons["Undo"], "Undo", timeout: 4) {
            sleep(3)
            step("undo settle")
            noteSplit("Bar Isabel", "after undo")
            a = checkAllowance("Undo settle", was: a, moves: 0)
        }
        // Third path: Ask Sam + It's a gift.
        tap(button("Settle up"), "Settle up again")
        tap(button("Type amounts"), "Type amounts")
        tapIf(app.buttons["Evenly"], "Evenly", timeout: 3)
        press("Next", prefix: true)
        sleep(1)
        press("Ask Sam", prefix: true)
        sleep(1)
        step("S-48b gift path")
        press("It’s a gift", prefix: true)
        sleep(2)
        press("Settle up")
        sleep(3)
        step("gift settled")
        a = checkAllowance("Ask Sam + It's a gift", was: a, moves: -6.67)
        noteSplit("Bar Isabel", "ask + gift")
        launch("dark")
        openTransaction("Bar Isabel")
        app.swipeUp()
        step("card dark after gift")
        if tapIf(app.buttons["Options for Priya"], "Options for Priya dark", timeout: 6) { step("S-48e dark") }
    }

    /// Section 20 (S-03rg/rh/ri) and TEST-08's wording; TEST-21 on joint.
    func testR3YourShareGivesWay() {
        launch()
        startSplit("Gusto", ["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        type("40", into: amountField("Priya"), "Priya")
        _ = doneBar()
        step("TEST-08 wording priya only")
        for w in ["Adds up", "stays yours", "gives way", "Split the rest evenly"] { _ = shows(w, timeout: 1) }
        type("80", into: amountField("Sam"), "Sam")
        _ = doneBar()
        step("S-03rg sam 80")
        _ = shows("gives way"); note("Save on: \(saveEnabled())")
        type("90", into: amountField("Sam"), "Sam")
        _ = doneBar()
        step("S-03rh sam 90")
        _ = shows("even with your share at $0.00"); note("Save on: \(saveEnabled())")
        type("20", into: amountField("You"), "You")
        _ = doneBar()
        step("S-03ri you typed 20")
        _ = shows("you typed it")
        type("80", into: amountField("Sam"), "Sam")
        _ = doneBar()
        step("S-03ri sam 80 with your 20 pinned")
        _ = shows("Take", timeout: 2)
        if tapIf(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Take'")).firstMatch, "Take … from your share", timeout: 3) {
            step("after take")
            note("Save on after Take: \(saveEnabled())")
        }
        press("Save")
        sleep(3)
        noteSplit("Gusto", "saved gives way")
        // "I had some too" off: no row of yours to give way.
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Change Sam"), "Change Sam's share")
        type("85", into: amountField("Sam"), "Sam")
        _ = doneBar()
        step("change sam 85 gives way")
        note("Save on: \(saveEnabled())")
        press("Save")
        sleep(3)
        noteSplit("Gusto", "change sam 85")
    }
}
