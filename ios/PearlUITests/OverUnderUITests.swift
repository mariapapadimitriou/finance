import XCTest

/// REFRESH-18 (2026-11-25): overpaid and underpaid shares, with real taps on
/// a purchase of their own (ios/tools/run_journeys.py `seed_over`). Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/OverUnderUITests testOver…`.
final class OverUnderUITests: XCTestCase {
    private var app: XCUIApplication!
    private var n = 0
    private var scheme = "light"
    private var shots: String { ProcessInfo.processInfo.environment["PEARL_SHOTS"] ?? NSTemporaryDirectory() }
    private var port: String { ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051" }

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    // MARK: Helpers

    private func launch(_ look: String = "light") {
        scheme = look
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(port)", "-pearl.appearance", look]
        app.launch()
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 6) { notNow.tap() }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        sleep(2)
        let deny = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Don’t Allow"]
        if deny.exists { deny.tap() }
        if notNow.exists && notNow.isHittable { notNow.tap() }
    }

    private func step(_ name: String) {
        sleep(1)
        n += 1
        let method = self.name.components(separatedBy: " ").last?.replacingOccurrences(of: "]", with: "") ?? "test"
        let base = "\(shots)/\(method)-\(String(format: "%02d", n))-\(scheme)-\(name.replacingOccurrences(of: " ", with: "-"))"
        FileManager.default.createFile(atPath: base + ".png", contents: XCUIScreen.main.screenshot().pngRepresentation)
        print("JOURNEY \(base).png")
    }

    private func see(_ text: String, _ where_: String = "", timeout: TimeInterval = 8) {
        let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
        let ok = e.waitForExistence(timeout: timeout)
        if !ok { step("NOT SEEN") }
        XCTAssertTrue(ok, "Not seen: \(text) \(where_)")
    }

    private func gone(_ text: String) {
        let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
        let end = Date().addingTimeInterval(6)
        while e.exists && Date() < end { usleep(300_000) }
        XCTAssertFalse(e.exists, "Still there: \(text)")
    }

    /// The last button with that label that can be tapped (a sheet over a page).
    private func press(_ label: String, exact: Bool = false) {
        let q = app.buttons.matching(NSPredicate(format: exact ? "label == %@" : "label BEGINSWITH %@", label))
        let there = q.firstMatch.waitForExistence(timeout: 10)
        if !there { step("NO BUTTON") }
        XCTAssertTrue(there, "No button \(label)")
        for attempt in 0..<6 {
            for e in q.allElementsBoundByIndex.reversed() where e.exists && e.isHittable {
                e.tap()
                sleep(1)
                return
            }
            if attempt > 1 { app.swipeUp(velocity: .slow) } else { sleep(1) }
        }
        step("CANNOT TAP")
        XCTFail("Can't tap \(label)")
    }

    private func tapWords(_ text: String) {
        let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text))
        XCTAssertTrue(e.firstMatch.waitForExistence(timeout: 10), "Nothing says \(text)")
        for x in e.allElementsBoundByIndex.reversed() where x.isHittable { x.tap(); sleep(1); return }
        XCTFail("Can't tap \(text)")
    }

    /// N-01 and iOS's own prompt can come up late, over whatever is on screen.
    private func clearInterruptions() {
        let deny = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Don’t Allow"]
        if deny.exists { deny.tap(); sleep(1) }
        let notNow = app.buttons["Not now"]
        if notNow.exists && notNow.isHittable { notNow.tap(); sleep(1) }
    }

    /// Drag until it's between the bar and the tabs.
    private func bring(_ e: XCUIElement) {
        var k = 0
        while e.exists, e.frame.midY > 660 || e.frame.midY < 160, k < 10 {
            let down = e.frame.midY < 160
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.45 : 0.7))
                .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.7 : 0.45)),
                       withVelocity: .slow, thenHoldForDuration: 0.3)
            k += 1
        }
    }

    private func openBistro() { openPurchase("Corner Bistro") }

    private func openPurchase(_ merchant: String) {
        sleep(2)
        clearInterruptions()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        clearInterruptions()
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", merchant)).firstMatch
        // The list builds its rows as it scrolls.
        for _ in 0..<8 where !row.waitForExistence(timeout: 3) { app.swipeUp(velocity: .slow) }
        if !row.waitForExistence(timeout: 15) { step("NO ROW"); XCTFail("No \(merchant)") }
        bring(row)
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.5)).tap()
        sleep(2)
        app.swipeUp(velocity: .slow)
        sleep(1)
    }

    /// A row's options: Mark paid back or Add another payment → Bank or e-Transfer.
    private func addPayment(_ name: String, first: Bool) {
        press(name + ",")
        press(first ? "Mark paid back" : "Add another payment")
        press("Bank or e-Transfer")
        see("Which payment was it?")
    }

    private func undoToast() { press("Undo", exact: true); sleep(2) }

    private func server(_ path: String) -> Any? {
        var out: Any?
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: URL(string: "http://localhost:\(port)/api/\(path)")!) { data, _, _ in
            if let data = data { out = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return out
    }

    // MARK: Journeys

    /// $59.54 split three ways: Georgia Klev owes $19.77 and sends $20.00.
    func testOverRoundedUp() {
        launch()
        openBistro()
        addPayment("Georgia Klev", first: true)
        step("which payment")
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label == 'Link'")).firstMatch.isEnabled, "Nothing is ticked")
        press("Georgia Klev")
        see("$0.23 extra")
        press("Link $20.00")
        see("Georgia Klev paid back $19.77 · $0.23 extra")
        step("toast")
        sleep(7)
        see("$0.23 extra")
        gone("What’s the extra $0.23?")
        step("card")
        press("Georgia Klev,")
        see("Paid $20.00 · $0.23 extra")
        see("What’s the extra $0.23?")
        step("options")
        XCTAssertEqual(((server("owed") as? [String: Any])?["you_owe"] as? [Any])?.count, 0)
    }

    /// Priya owes $20.00 and sends $19.00; Undo takes both back, and Undo let
    /// it go makes the share hers.
    func testOverRoundedDown() {
        launch()
        openBistro()
        addPayment("Priya", first: true)
        press("Priya")
        see("$1.00 let go")
        step("said before link")
        press("Link $19.00")
        see("Priya paid back $19.00 · $1.00 let go")
        step("toast")
        undoToast()
        see("Priya, owes you $20.00")
        step("undone")
        addPayment("Priya", first: true)
        press("Priya")
        press("Link $19.00")
        sleep(8)
        step("card")
        press("Priya,")
        see("Paid $19.00 · $1.00 let go")
        step("options")
        press("Undo let it go")
        see("Priya owes you $1.00 again")
        step("undo let it go")
        undoToast()
        see("$1.00 let go")
        step("let go back")
    }

    /// $55.00 on a $40.00 share, linked and said from the purchase.
    func testOverSaidFromThePurchase() {
        launch()
        openBistro()
        addPayment("Georgia Klev", first: true)
        press("Georgia Klev")
        see("$15.00 extra")
        step("which payment")
        press("Link $55.00")
        sleep(8)
        step("card asks")
        press("Georgia Klev,")
        see("Paid $55.00 · $15.00 extra")
        see("Change Georgia Klev’s share")
        step("options")
        press("Close")
        sleep(1)
        press("What’s the extra $15.00?")
        see("How much of it?")
        see("Georgia Klev’s share is $40.00.")
        step("whats the extra")
        press("Pays back something else")
        see("What did the $15.00 pay back?")
        step("pays back something else")
        press("Back")
        press("I owe it back")
        see("You owe Georgia Klev $15.00")
        step("said")
        sleep(7)
        see("You owe $15.00 back")
        step("card said")
        press("Georgia Klev,")
        see("you owe $15.00 back")
        see("Change what the extra is")
        step("options said")
        press("Change what the extra is")
        press("A gift")
        see("$15.00 from Georgia Klev is a gift")
        sleep(1)
        undoToast()
        press("Everyone who owes you")
        // P17b: You owe is one row under Also; its page lists who (P17g).
        press("You owe")
        see("Overpaid for Corner Bistro")
        step("owed to you")
        press("Georgia Klev")
        see("Open Corner Bistro")
        step("you owe opens it")
    }

    /// $25.00 then $15.00.
    func testOverTwoPayments() {
        launch()
        openBistro()
        addPayment("Georgia Klev", first: true)
        tapWords("+$25.00")
        press("Link $25.00")
        sleep(8)
        see("left")
        step("underpaid")
        press("Georgia Klev,")
        see("Paid $25.00 · $15.00 left")
        see("Let the $15.00 go")
        step("options")
        press("Add another payment")
        see("$15.00 left on Corner Bistro")
        step("how")
        press("Bank or e-Transfer")
        tapWords("+$15.00")
        press("Link $15.00")
        sleep(8)
        see("paid back")
        step("paid by two")
        press("Georgia Klev,")
        see("Paid with")
        step("both payments")
    }

    /// $25.00, the rest let go, then $15.00 from Quick sort's question.
    func testOverLetGoThenPaid() {
        launch()
        openBistro()
        addPayment("Georgia Klev", first: true)
        tapWords("+$25.00")
        press("Link $25.00")
        sleep(8)
        press("Georgia Klev,")
        press("Let the $15.00 go")
        see("becomes your spending")
        step("let the rest go")
        press("Let $15.00 go")
        see("Let go · $15.00")
        sleep(8)
        step("let go card")
        press("Georgia Klev,")
        see("$15.00 let go")
        step("let go options")
        press("Add another payment")
        see("You let $15.00 go on Corner Bistro")
        press("Bank or e-Transfer")
        tapWords("+$15.00")
        press("Link $15.00")
        see("Georgia Klev paid back the $15.00 you let go")
        step("toast")
        undoToast()
        see("let go")
        step("let go back")
        // Needs a look asks it; nothing was done for her.
        app.terminate()
        launch("dark")
        openBistro()
        step("card dark")
    }

    /// Georgia Klev and Georgia Pappas on one split: each payment is its own.
    func testOverTwoGeorgias() {
        launch()
        openBistro()
        addPayment("Georgia Pappas", first: true)
        step("pappas payments")
        press("Georgia Pappas")
        press("Link $25.00")
        sleep(8)
        addPayment("Georgia Klev", first: true)
        press("Georgia Klev")
        press("Link $55.00")
        sleep(8)
        see("What’s the extra $15.00?")
        step("card")
        press("What’s the extra $15.00?")
        press("I sent it back")
        sleep(8)
        see("You sent $15.00 back")
        step("card said")
        press("Georgia Pappas,")
        see("Paid $25.00 · $15.00 left")
        step("pappas options")
    }

    /// Needs a look: S-21o's row opens S-11e; PQ-03o says the extra first.
    func testOverNeedsALook() {
        launch()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        let chip = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'need a look' OR label CONTAINS[c] 'Needs a look'")).firstMatch
        clearInterruptions()
        XCTAssertTrue(chip.waitForExistence(timeout: 8))
        chip.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        let money = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Money in'")).firstMatch
        if money.waitForExistence(timeout: 4) { money.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        sleep(1)
        let row = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Georgia Klev'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 8), "No row for Georgia Klev")
        bring(row)
        step("needs a look")
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.4, dy: 0.5)).tap()
        sleep(2)
        see("$40.00 of $55.00 · $15.00 extra")
        step("is she paying you back")
        press("Yes, Corner Bistro")
        sleep(3)
        step("answered")
        let extra = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS '$15.00 extra'")).firstMatch
        XCTAssertTrue(extra.waitForExistence(timeout: 8), "No extra row")
        sleep(6)
        bring(extra)
        step("the extra")
        extra.coordinate(withNormalizedOffset: CGVector(dx: 0.4, dy: 0.5)).tap()
        sleep(2)
        see("What’s the extra $15.00?")
        step("whats the extra")
        press("A gift")
        sleep(2)
        gone("$15.00 extra")
        step("gone")
    }

    /// PB-41o: the deposit's own page, its extra said there.
    func testOverDeposit() {
        launch()
        openBistro()
        addPayment("Georgia Klev", first: true)
        press("Georgia Klev")
        press("Link $55.00")
        sleep(8)
        press("Back")
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Georgia Klev'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "No deposit row")
        bring(row)
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.5)).tap()
        sleep(3)
        see("Georgia Klev’s share")
        step("the deposit")
        press("What’s the extra $15.00?")
        see("Georgia Klev’s share is $40.00.")
        press("Something else…")
        step("something else")
        press("Back")
        press("I owe it back")
        sleep(3)
        step("said on the deposit")
        press("Unlink")
        see("Unlink")
        step("unlink")
    }

    /// Split my part is a row in Options, as Split with others is (product
    /// owner, 2026-11-25): on "All mine", with none of it hers, and at 50/50,
    /// where it opens the split.
    /// P16a: "Everyone who owes you" under the split card opens Owed to you
    /// (P17a: one list, biggest first; P17b: Also); Paid back this month opens
    /// its own page (P17h). Then the same page from Home's card.
    func testOverOwedOrganized() {
        launch()
        openBistro()
        see("Everyone who owes you")
        let button = app.buttons["Everyone who owes you"].firstMatch
        bring(button)
        step("split purchase")
        button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        see("Owed to you")
        see("people owe you")
        see("Georgia Klev")
        step("owed to you")
        app.swipeUp(velocity: .slow)
        sleep(1)
        see("Also")
        step("also")
        let paid = app.buttons["owed-also-paidBack"].firstMatch
        XCTAssertTrue(paid.waitForExistence(timeout: 6), "No Paid back this month row")
        bring(paid)
        paid.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        see("this month")
        see("Priya")
        step("paid back")
        // From Home.
        app.tabBars.buttons["Home"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        app.tabBars.buttons["Home"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        let card = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", "owe you")).firstMatch
        for _ in 0..<6 where !(card.exists && card.frame.midY < 660) { app.swipeUp(velocity: .slow); sleep(1) }
        XCTAssertTrue(card.waitForExistence(timeout: 6), "No Owed card on Home")
        bring(card)
        step("home card")
        card.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        see("Owed to you")
        see("Georgia Klev")
        step("owed from home")
    }

    /// P17a–d on the simulator (board gaps, 2026-11-27): Owed to you from the
    /// split purchase, in light and dark, with a frame mid count-up. Run at
    /// `--text accessibility-extra-extra-extra-large` too.
    private func owedLooks(_ what: String, expect: [String], paidBack: Bool = true) {
        for look in ["light", "dark"] {
            launch(look)
            openBistro()
            let button = app.buttons["Everyone who owes you"].firstMatch
            XCTAssertTrue(button.waitForExistence(timeout: 8), "No Everyone who owes you")
            bring(button)
            button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            // P17a motion: the total counting up, the rows settling in.
            usleep(150_000)
            n += 1
            let method = self.name.components(separatedBy: " ").last?.replacingOccurrences(of: "]", with: "") ?? "test"
            let base = "\(shots)/\(method)-\(String(format: "%02d", n))-\(scheme)-\(what)-opening"
            FileManager.default.createFile(atPath: base + ".png", contents: XCUIScreen.main.screenshot().pngRepresentation)
            print("JOURNEY \(base).png")
            sleep(2)
            see("Owed to you")
            for text in expect { see(text) }
            step(what)
            app.swipeUp(velocity: .slow)
            sleep(1)
            if paidBack {
                XCTAssertTrue(app.buttons["owed-also-paidBack"].firstMatch.waitForExistence(timeout: 6),
                              "No Paid back this month")
            }
            step(what + "-end")
        }
    }

    func testOverOwedLooksMany() {
        owedLooks("many", expect: ["people owe you", "Georgia Klev", "Sam"])
    }

    func testOverOwedLooksOne() {
        owedLooks("one", expect: ["Georgia Klev owes you"])
        XCTAssertFalse(app.staticTexts["Sam"].exists, "P17c: only Georgia")
    }

    func testOverOwedLooksNobody() {
        owedLooks("nobody", expect: ["Nobody owes you anything."])
    }

    func testJointSplitInOptions() {
        launch()
        for (merchant, label) in [("Lantern Books", "Split with others"), ("Harbour Furniture", "Split my part"),
                                  ("Corner Bistro", "Split my part")] {
            openPurchase(merchant)
            step(merchant)
            let rows = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", label))
            XCTAssertTrue(rows.firstMatch.waitForExistence(timeout: 8), "\(merchant): no \(label)")
            XCTAssertEqual(rows.count, 1, "\(merchant): \(label) more than once")
            XCTAssertFalse(app.buttons["Split it with friends"].exists, merchant)
            XCTAssertTrue(rows.firstMatch.isEnabled, merchant)
            let options = app.staticTexts.matching(NSPredicate(format: "label ==[c] 'Options'")).firstMatch
            XCTAssertTrue(options.exists, "\(merchant): no Options")
            XCTAssertLessThan(options.frame.minY, rows.firstMatch.frame.minY, "\(merchant): not under Options")
            if merchant == "Harbour Furniture" {
                // Marked Sam's on its page: the row stays, dimmed, and says why.
                let bar = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Half each'")).firstMatch
                XCTAssertTrue(bar.exists, "No share bar")
                bar.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.2)).tap()
                let theirs = app.buttons["whose-theirs"]
                XCTAssertTrue(theirs.waitForExistence(timeout: 8), "No Whose was it?")
                theirs.tap()
                sleep(3)
                step("all Sams")
                see("None of it is yours to split.")
                XCTAssertFalse(rows.firstMatch.isEnabled, "None of it is hers")
            }
            if merchant != "Corner Bistro" { press("Back", exact: true) }
        }
        press("Split my part")
        sleep(2)
        clearInterruptions()
        step("split my part")
        // The joint account's other owner is never listed, and refused typed.
        XCTAssertTrue(app.buttons["Priya"].waitForExistence(timeout: 5), "No Priya")
        XCTAssertFalse(app.buttons["Sam"].exists, "Sam is on the joint account")
        let field = app.textFields.firstMatch
        field.tap()
        field.typeText("Sam")
        see("Sam’s part is already off.")
        XCTAssertFalse(app.buttons["Add"].isEnabled, "Add takes Sam")
        XCTAssertFalse(app.buttons["Next"].isEnabled, "Next goes on without anyone")
        step("sam refused")
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 3))
        gone("Sam’s part is already off.")
        press("Priya")
        press("Next", exact: true)
        step("how to split")
        press("Save")
        sleep(3)
        see("Priya")
        step("saved")
        gone("Split my part")
    }

    // MARK: 2026-11-26 fixes

    /// A card payment has its ⇄; a tapped calendar day is ringed and its
    /// purchases sit right under the grid; money in's What was this? shows
    /// every answer, with no Something else… step.
    func testCalendarDayCardPaymentAndMoneyIn() {
        launch()
        clearInterruptions()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        clearInterruptions()

        // The calendar: tap the 15th. The list can open part way down; the
        // status bar takes it to the top, where the switch is.
        let calendarTab = app.buttons.matching(NSPredicate(format: "label == 'Calendar'")).firstMatch
        for _ in 0..<4 where !(calendarTab.exists && calendarTab.frame.minY > 100) {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.01)).tap()
            sleep(1)
        }
        step("top of cash flow")
        // XCUI calls the switch's buttons not hittable; a finger's tap works.
        calendarTab.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(3)
        step("calendar")
        let f = DateFormatter()
        f.dateFormat = "MMMM d"
        var c = Calendar.current.dateComponents([.year, .month], from: Date())
        c.day = 15
        let fifteenth = Calendar.current.date(from: c)!
        let cell = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", ", " + f.string(from: fifteenth))).firstMatch
        XCTAssertTrue(cell.waitForExistence(timeout: 10), "No 15th in the grid")
        // A finger on the day: if anything covered the grid, this wouldn't reach it.
        cell.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(3)
        step("day tapped")
        XCTAssertTrue(cell.isSelected, "The tapped day isn't marked")
        let f2 = DateFormatter()
        f2.dateFormat = "EEE, MMM d"
        let header = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH[c] %@",
                                                          f2.string(from: fifteenth).uppercased())).firstMatch
        XCTAssertTrue(header.waitForExistence(timeout: 8), "No list for the 15th")
        XCTAssertLessThan(header.frame.maxY, app.frame.maxY - 90, "The day's list is off screen")
        XCTAssertLessThan(header.frame.minY, cell.frame.maxY + 300, "The day's list is far from the grid")

        // ⇄ on a card payment: VoiceOver reads a move between accounts as "Moved …".
        let listTab = app.buttons.matching(NSPredicate(format: "label == 'Transactions'")).firstMatch
        for _ in 0..<4 where !(listTab.exists && listTab.frame.minY > 100) {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.01)).tap()
            sleep(1)
        }
        listTab.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        let payment = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Online Payment'")).firstMatch
        for _ in 0..<10 where !payment.waitForExistence(timeout: 2) { app.swipeUp(velocity: .slow) }
        XCTAssertTrue(payment.exists, "No card payment in the list")
        bring(payment)
        step("card payment row")
        XCTAssertTrue(payment.label.localizedCaseInsensitiveContains("moved"), "No ⇄ on the card payment: \(payment.label)")

        // Money in's What was this?: every answer, no Something else….
        launch()
        clearInterruptions()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        let name = app.staticTexts["Northwind Ltd Expenses"].firstMatch
        for _ in 0..<8 where !name.waitForExistence(timeout: 2) { app.swipeUp(velocity: .slow) }
        bring(name)
        name.tap()
        sleep(2)
        step("deposit page")
        // Its "What was this?" (the category card, or the chip when it's asked).
        let ask = app.staticTexts["Other?"].firstMatch
        XCTAssertTrue(ask.waitForExistence(timeout: 6), "No guess card")
        ask.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
        step("what was this")
        see("INCOME")
        see("NOT INCOME")
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Something else'")).firstMatch.exists,
                       "Something else… is still a step")
    }
}
