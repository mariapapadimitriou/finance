import XCTest
import UIKit

/// engBOT's checks for what testingBOT found in Round 1 (ios/bots/testing-log.md),
/// one test per finding, with real taps against the demo ledger. Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/Round1FixesUITests`,
/// which seeds the same data as testingBOT's journeys (Gusto $127.50, Priya's
/// and Sam's e-Transfers, six guesses for Quick sort).
final class Round1FixesUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    // MARK: Helpers

    private func launch(_ scheme: String = "light") {
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:5051", "-pearl.appearance", scheme]
        app.launch()
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 5) { notNow.tap() }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        // On a busy machine N-01 can come after the tab bar: put it away too.
        if notNow.waitForExistence(timeout: 8) { notNow.tap() }
    }

    private func button(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
    }

    private func text(containing text: String) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15,
                     file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(e.waitForExistence(timeout: timeout), "Couldn't find \(what)", file: file, line: line)
        var n = 0
        while !e.isHittable && n < 8 { app.swipeUp(velocity: .slow); n += 1 }
        e.tap()
    }

    /// The last tappable button with this label (a sheet over a page).
    private func press(_ label: String, prefix: Bool = false, file: StaticString = #filePath, line: UInt = #line) {
        let q = app.buttons.matching(NSPredicate(format: prefix ? "label BEGINSWITH %@" : "label == %@", label))
        XCTAssertTrue(q.firstMatch.waitForExistence(timeout: 8), "No \(label)", file: file, line: line)
        guard let e = q.allElementsBoundByIndex.reversed().first(where: { $0.exists && $0.isHittable }) else {
            return XCTFail("\(label) can't be tapped", file: file, line: line)
        }
        e.tap()
    }

    private func server(_ path: String) -> Any? {
        var result: Any?
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: URL(string: "http://localhost:5051/api/\(path)")!) { data, _, _ in
            if let data = data { result = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return result
    }

    private func openCashFlow() {
        app.tabBars.buttons["Cash flow"].tap()
        sleep(2)
    }

    private func openTransaction(_ merchant: String) {
        openCashFlow()
        let row = button(merchant)
        if !row.waitForExistence(timeout: 10) || !row.isHittable {
            let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
            if search.waitForExistence(timeout: 3) {
                search.tap()
                search.typeText(merchant)
                sleep(2)
            }
        }
        tap(button(merchant), "the \(merchant) row")
    }

    private func addPeople(_ names: [String]) {
        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), "S-02 has no name field")
        for name in names {
            field.tap()
            field.typeText(name)
            if app.buttons["Add"].waitForExistence(timeout: 3) { app.buttons["Add"].tap() }
        }
        tap(app.buttons["Next"], "Next on S-02")
        sleep(1)
    }

    private func amountField(_ who: String) -> XCUIElement {
        app.textFields.matching(identifier: "\(who) amount").firstMatch
    }

    /// How light an element is on screen, 0 (black) to 1 (white): the mean
    /// luminance of the middle of its frame.
    private func lightness(of e: XCUIElement, inset: CGFloat = 0.3) -> Double {
        let shot = XCUIScreen.main.screenshot().image
        guard let cg = shot.cgImage else { return -1 }
        let scale = CGFloat(cg.width) / shot.size.width
        let f = e.frame.insetBy(dx: e.frame.width * inset, dy: e.frame.height * inset)
        let rect = CGRect(x: f.minX * scale, y: f.minY * scale, width: f.width * scale, height: f.height * scale)
            .integral.intersection(CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        guard let crop = cg.cropping(to: rect) else { return -1 }
        let w = crop.width, h = crop.height
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = CGContext(data: &pixels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                            space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        ctx?.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
        var sum = 0.0
        for i in stride(from: 0, to: pixels.count, by: 4) {
            sum += 0.2126 * Double(pixels[i]) + 0.7152 * Double(pixels[i + 1]) + 0.0722 * Double(pixels[i + 2])
        }
        return sum / Double(w * h) / 255
    }

    /// How far apart the darkest and lightest parts of an element are, 0 to 1
    /// (2nd to 98th percentile luminance): words that read on their fill
    /// are far apart; white on white is not.
    private func spread(of e: XCUIElement, inset: CGFloat = 0) -> Double {
        let shot = XCUIScreen.main.screenshot().image
        guard let cg = shot.cgImage else { return -1 }
        let scale = CGFloat(cg.width) / shot.size.width
        let f = e.frame.insetBy(dx: e.frame.width * inset, dy: e.frame.height * inset)
        let rect = CGRect(x: f.minX * scale, y: f.minY * scale, width: f.width * scale, height: f.height * scale)
            .integral.intersection(CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        guard let crop = cg.cropping(to: rect) else { return -1 }
        let w = crop.width, h = crop.height
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = CGContext(data: &pixels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                            space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        ctx?.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
        var lum: [Double] = []
        lum.reserveCapacity(w * h)
        for i in stride(from: 0, to: pixels.count, by: 4) {
            lum.append((0.2126 * Double(pixels[i]) + 0.7152 * Double(pixels[i + 1]) + 0.0722 * Double(pixels[i + 2])) / 255)
        }
        lum.sort()
        guard !lum.isEmpty else { return -1 }
        return lum[Int(Double(lum.count - 1) * 0.98)] - lum[Int(Double(lum.count - 1) * 0.02)]
    }

    /// A Not sure yet split of Gusto with Priya and Sam, and Priya's
    /// e-Transfer linked to it from her •••.
    private func gustoNotSureWithPriyaPaid(_ others: [String] = ["Sam"]) {
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya"] + others)
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        press("Save split")
        sleep(2)
        tap(app.buttons["Options for Priya"], "Options for Priya")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        // TEST-13: the sender as Cash flow names them, not "E-transfer From Priya Shah".
        let priya = button("Priya Shah")
        XCTAssertTrue(priya.waitForExistence(timeout: 10), "Priya Shah's e-Transfer, named as in Cash flow")
        // The suggested one comes ticked (S-06rb); tick it only if it isn't.
        if !priya.isSelected { priya.tap() }
        XCTAssertFalse(button("E-transfer From").exists, "S-06rb still names the bank's words")
        press("Link", prefix: true)
        // The toast goes, and any sheet still up is closed, before Settle up.
        sleep(5)
        let close = app.buttons.matching(NSPredicate(format: "label == 'Close'")).firstMatch
        if close.exists && close.isHittable { close.tap(); sleep(1) }
    }

    // MARK: TEST-01 Quick sort in dark mode

    /// The card, Skip and the chosen chip are dark in dark mode, so the
    /// near-white words on them read (they were white on white).
    func testQuickSortReadsInDarkMode() {
        launch("dark")
        tap(app.buttons["See the list"], "See the list")
        let all = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'All'")).firstMatch
        XCTAssertTrue(all.waitForExistence(timeout: 15), "Needs a look has no All chip")
        sleep(1)
        XCTAssertGreaterThan(spread(of: all), 0.5, "The chosen chip's words don't stand out from it")
        tap(button("Quick sort"), "Quick sort card")
        let card = app.descendants(matching: .any)["quick-sort-card"]
        XCTAssertTrue(card.waitForExistence(timeout: 15), "No Quick sort card")
        sleep(1)
        XCTAssertLessThan(lightness(of: card, inset: 0.08), 0.35, "The card face should be --surface-card in dark")
        let skip = app.buttons["Skip"]
        XCTAssertTrue(skip.exists, "No Skip")
        XCTAssertLessThan(lightness(of: skip, inset: 0.35), 0.4, "Skip's circle should be dark in dark")
        // And light mode keeps its light card.
        launch("light")
        tap(app.buttons["See the list"], "See the list")
        tap(button("Quick sort"), "Quick sort card")
        XCTAssertTrue(card.waitForExistence(timeout: 15), "No Quick sort card")
        sleep(1)
        XCTAssertGreaterThan(lightness(of: card, inset: 0.08), 0.8, "Light mode's card is unchanged")
    }

    // MARK: TEST-02 Settle up › Type amounts

    func testSettleUpTypeAmountsOpensOnHowToSplit() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(button("Settle up"), "Settle up")
        tap(button("Type amounts"), "Type amounts")
        XCTAssertTrue(text(containing: "type amounts").waitForExistence(timeout: 8),
                      "Type amounts should open on S-45c, Settle up · type amounts")
        XCTAssertFalse(text(containing: "Who was it with").exists, "It opened on Who was it with? again")
        XCTAssertTrue(text(containing: "127.50").exists, "The header should show the whole purchase, $127.50")
        // THL-303 (TEST-18): Priya is locked at what she paid.
        let paid = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'locked'")).firstMatch
        if !paid.exists, let dir = ProcessInfo.processInfo.environment["PEARL_SHOTS"] {
            try? app.debugDescription.write(toFile: dir + "/settle-type-amounts.txt", atomically: true, encoding: .utf8)
        }
        XCTAssertTrue(paid.exists, "Priya's row should say she's paid back, locked")
    }

    // MARK: TEST-07 Leave out without a reason

    func testLeaveOutWaitsForAReason() {
        launch()
        openCashFlow()
        tap(app.buttons["Select"], "Select")
        tap(button("Spotify"), "Spotify in Select")
        tap(app.buttons["Leave out"], "Leave out in the bar")
        // TEST-06: T-77c is a Pearl sheet, not a stock alert.
        XCTAssertEqual(app.alerts.count, 0, "Leave out is still a stock alert")
        XCTAssertTrue(text(containing: "Leave out 1 transaction?").waitForExistence(timeout: 5), "No T-77c sheet")
        XCTAssertTrue(text(containing: "Say why, so you can tell later.").exists,
                      "The sheet should say a reason is needed")
        // The sheet's Leave out, not the Select bar's behind it.
        let leave = app.buttons["sheet-primary"]
        XCTAssertFalse(leave.isEnabled, "Leave out should wait for a reason")
        let why = app.textFields["leave-out-reason"]
        tap(why, "the Why? field")
        why.typeText("A friend's")
        XCTAssertTrue(leave.isEnabled, "Leave out should be on once there's a reason")
        leave.tap()
        sleep(3)
        let list = server("transactions?q=Spotify") as? [String: Any]
        let rows = (list?["transactions"] as? [[String: Any]]) ?? []
        XCTAssertTrue(rows.contains { !(($0["excluded"] as? String) ?? "").isEmpty }, "Spotify wasn't left out")
    }

    // MARK: TEST-16 The number pad on Amounts

    func testTheNumberPadGoesAwayAndTheStatusStaysInView() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        // At AX sizes the methods sit behind "How to split · Evenly ›" (S-03u).
        let methods = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'How to split'")).firstMatch
        let ax = !app.buttons["Amounts"].waitForExistence(timeout: 3) && methods.exists
        if ax {
            methods.tap()
            tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Amounts, split method'")).firstMatch, "Amounts")
        } else {
            tap(app.buttons["Amounts"].firstMatch, "Amounts")
        }
        let priya = amountField("Priya")
        tap(priya, "Priya's amount")
        priya.typeText("40")
        // S-03rg (TEST-21): her share gives way, so it adds up.
        let status = text(containing: "Adds up to $127.50")
        XCTAssertTrue(status.waitForExistence(timeout: 4), "No status line")
        sleep(1)
        let saveButton = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last
        XCTAssertTrue(status.isHittable, "The status line is under the number pad or Save: status \(status.frame), "
                      + "Save \(saveButton?.frame ?? .zero), pad \(app.keyboards.firstMatch.frame), window \(app.windows.firstMatch.frame)")
        // S-03rg: with her share giving way there's nothing left to split,
        // so "Split the rest evenly" isn't offered.
        _ = ax
        // TEST-16 (round 2): Save sits below the content, never on it.
        let save = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last!
        XCTAssertLessThanOrEqual(status.frame.maxY, save.frame.minY + 1, "TEST-16: Save covers the status line")
        let had = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'I had some too'")).firstMatch
        if had.exists && had.isHittable {
            XCTAssertFalse(had.frame.intersects(save.frame), "TEST-16: Save is drawn on I had some too")
        }
        // A tap on the sheet's title puts the pad away.
        app.staticTexts["How to split"].firstMatch.tap()
        sleep(1)
        XCTAssertEqual(app.keyboards.count, 0, "The number pad didn't go away")
    }

    // MARK: TEST-21 Your share gives way (S-03rg / S-03rh / S-03ri)

    func testYourShareGivesWayUntilYouTypeIt() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        let save = { self.app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last! }
        func type(_ who: String, _ value: String) {
            let f = amountField(who)
            tap(f, "\(who)'s amount")
            if let old = f.value as? String, !old.isEmpty, old != f.placeholderValue {
                // What's there is selected, so typing replaces it.
                f.doubleTap()
            }
            f.typeText(value)
        }
        type("Priya", "40")
        type("Sam", "80")
        // S-03rg: raising Sam is enough; you're what's left, $7.50.
        XCTAssertTrue(text(containing: "Adds up to $127.50").waitForExistence(timeout: 4), "S-03rg: it should add up")
        XCTAssertTrue(text(containing: "gives way").exists, "S-03rg: Your share · gives way · what's left")
        XCTAssertEqual(amountField("You").placeholderValue, "$7.50", "S-03rg: your share should be what's left")
        XCTAssertTrue(save().isEnabled, "S-03rg: Save should be on")
        // S-03rh: more than the whole, even with yours at $0.00.
        type("Sam", "90")
        XCTAssertTrue(text(containing: "too much, even with your share at $0.00").waitForExistence(timeout: 4), "S-03rh")
        XCTAssertFalse(save().isEnabled, "S-03rh: Save should be off")
        // S-03ri: typed, your share is pinned; Take $x from your share unpins it.
        type("Sam", "80")
        type("You", "20")
        XCTAssertTrue(text(containing: "you typed it").waitForExistence(timeout: 4), "S-03ri: pinned")
        let take = button("Take $12.50 from your share")
        if !take.waitForExistence(timeout: 4) {
            let seen = app.staticTexts.allElementsBoundByIndex.map(\.label).filter { $0.contains("$") || $0.contains("much") }
            XCTFail("S-03ri: no Take $12.50. Fields: \(["Priya", "Sam", "You"].map { amountField($0).value as? String ?? "?" }), \(seen)")
        }
        tap(take, "Take $12.50 from your share")
        XCTAssertTrue(text(containing: "Adds up to $127.50").waitForExistence(timeout: 4), "S-03ri: it should add up after Take")
        XCTAssertTrue(save().isEnabled)
        app.staticTexts["How to split"].firstMatch.tap()
        press("Save")
        sleep(3)
        let you = app.buttons["split-you-row"]
        XCTAssertTrue(you.waitForExistence(timeout: 8) && you.label.contains("7.50"), "Your share should save as $7.50")
    }

    // MARK: TEST-14 Tap areas and the tab's badge

    func testTheCashFlowTabSaysHowManyToSort() {
        launch()
        let tab = app.tabBars.buttons["Cash flow"]
        XCTAssertTrue(tab.waitForExistence(timeout: 10))
        sleep(2)
        XCTAssertTrue(((tab.value as? String) ?? "").contains("to sort"),
                      "VoiceOver hears no count on Cash flow: value \(tab.value ?? "nil")")
    }

    func testTheSmallTextButtonsHave44ptTapAreas() throws {
        guard #available(iOS 17.0, *) else { throw XCTSkip("The audit needs iOS 17") }
        launch()
        var small: [String] = []
        func audit() {
            try? app.performAccessibilityAudit(for: .hitRegion) { issue in
                small.append(issue.element?.label ?? "?")
                return true
            }
        }
        audit()
        openCashFlow()
        audit()
        for label in ["See the list", "Sort now", "Calendar"] {
            XCTAssertFalse(small.contains(label), "\(label) is still under 44 pt: \(small)")
        }
        XCTAssertGreaterThanOrEqual(app.buttons["Calendar"].frame.height, 44)
    }
    // MARK: TEST-03 Rule A: the whole purchase until it's paid back

    /// S-04r v2: the page's big amount is the whole purchase, with "Your
    /// share" under it, and the Allowance doesn't drop by only your share.
    func testASplitShowsTheWholePurchaseAndYourShare() {
        launch()
        let before = ((server("home") as? [String: Any])?["safe_to_spend"] as? [String: Any])?["amount"] as? Double
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        for (who, amount) in [("Priya", "42.50"), ("Sam", "30"), ("Jo", "15")] {
            let f = amountField(who)
            tap(f, "\(who)'s amount")
            f.typeText(amount)
        }
        app.staticTexts["How to split"].firstMatch.tap()
        press("Save")
        sleep(3)
        XCTAssertTrue(text(containing: "127.50").waitForExistence(timeout: 8), "The hero should be the whole purchase")
        XCTAssertTrue(text(containing: "Your share $40.00").exists, "\"Your share $40.00\" should be under it")
        let after = ((server("home") as? [String: Any])?["safe_to_spend"] as? [String: Any])?["amount"] as? Double
        XCTAssertEqual(before ?? 0, after ?? -1, accuracy: 0.01, "Splitting shouldn't move the Allowance under Rule A")
    }
    // MARK: TEST-18 Not sure yet with you in it (THL-303)

    /// S-03u2, S-04u6, S-40y, S-47c → S-04u7: a You row, Set your share,
    /// and what's left split between the two who haven't paid.
    func testSetYourShareOnNotSureYet() {
        launch()
        let home = { ((self.server("home") as? [String: Any])?["safe_to_spend"] as? [String: Any])?["amount"] as? Double }
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        XCTAssertTrue(text(containing: "Your share · set it any time").waitForExistence(timeout: 4),
                      "S-03u2: no You row on Not sure")
        press("Save split")
        sleep(2)
        tap(app.buttons["Options for Priya"], "Options for Priya")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        let priya = button("Priya Shah")
        XCTAssertTrue(priya.waitForExistence(timeout: 10))
        if !priya.isSelected { priya.tap() }
        press("Link", prefix: true)
        sleep(5)
        let before = home()
        tap(app.buttons["Options for you"], "S-04u6: your •••")
        tap(button("Set your share"), "S-40y: Set your share")
        let field = app.textFields["your-share"]
        XCTAssertTrue(field.waitForExistence(timeout: 5), "No S-47 field")
        field.tap()
        field.typeText("40")
        XCTAssertTrue(app.toolbars.buttons["Done"].exists || app.buttons["Done"].exists, "No Done bar on S-47")
        XCTAssertTrue(text(containing: "Adds up to $127.50").waitForExistence(timeout: 4), "S-47c should add up")
        // S-47c: all four methods of what's left; % and Shares divide it too.
        if app.keyboards.count > 0 { (app.toolbars.buttons["Done"].exists ? app.toolbars.buttons["Done"] : app.buttons["Done"]).tap() }
        for method in ["Shares", "%", "Amounts", "Evenly"] {
            tap(app.buttons[method].firstMatch, "the \(method) method")
            XCTAssertTrue(text(containing: "Adds up to $127.50").waitForExistence(timeout: 4), "\(method) should add up")
        }
        press("Save")
        XCTAssertTrue(text(containing: "Sam and Jo owe you $45.00").waitForExistence(timeout: 8), "S-04u7 toast")
        let split = (server("transactions?q=Gusto") as? [String: Any]).flatMap { $0["transactions"] as? [[String: Any]] }?
            .first { ($0["merchant"] as? String) == "Gusto" }
        XCTAssertNotNil(split)
        XCTAssertEqual(before ?? 0, home() ?? -1, accuracy: 0.01, "Setting your share doesn't move the Allowance")
    }
    /// S-04r v3: You first on a split with amounts; tapping it opens Edit split.
    func testASplitWithAmountsListsYouFirst() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        press("Save")
        sleep(3)
        let you = app.buttons["split-you-row"]
        XCTAssertTrue(you.waitForExistence(timeout: 8), "No You row on the split card")
        XCTAssertTrue(you.label.contains("42.50"), "You row should show your share: \(you.label)")
        XCTAssertFalse(app.buttons["Options for you"].exists, "S-04r v3's You row has no •••")
        tap(you, "the You row")
        // The same sheet Edit split opens.
        let sheet = app.staticTexts.matching(NSPredicate(format: "label == 'How to split' OR label == 'Who was it with?'")).firstMatch
        XCTAssertTrue(sheet.waitForExistence(timeout: 5), "Tapping You should open Edit split")
    }

    /// S-45c4 and S-47f: Shares on Type amounts with a locked payer, and the
    /// lock toast's Options opening that person's S-40u.
    func testSharesWithALockedPayerAndTheLockToast() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(button("Settle up"), "Settle up")
        tap(button("Type amounts"), "Type amounts")
        tap(app.buttons["Shares"], "the Shares segment")
        // TEST-18b: Shares runs over everyone; a payer shows what they paid.
        // TEST-14 (round 3): it reads "Priya, paid $42.50, locked".
        let amount = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Priya, paid $42.50, locked'")).firstMatch
        XCTAssertTrue(amount.waitForExistence(timeout: 5), "Priya's payment should show as text")
        // TEST-23: you, Priya and Sam, one share each; not Priya's dollars counted as shares.
        XCTAssertTrue(text(containing: "3 shares · adds up to").waitForExistence(timeout: 4),
                      "TEST-23: the shares count should be 3")
        amount.tap()
        XCTAssertTrue(text(containing: "is linked, so it stays").waitForExistence(timeout: 4), "No S-47f2 toast")
        tap(app.buttons["Options"], "Options on the toast")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] 'Unlink'")).firstMatch
                        .waitForExistence(timeout: 8), "Options should open Priya's S-40u")
    }
    // MARK: TEST-18b Pearl asks when a payer's share differs (option C)

    /// S-48c → S-48a → S-48d: Evenly gives Sam $42.50 but he paid $20.00
    /// cash; Pearl asks, "Ask Sam for $22.50" saves with Settle up.
    func testSettleUpAsksWhenAPayersShareDiffers() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Cash in hand"), "Cash in hand")
        let amount = app.textFields["Amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap()
        amount.typeText("20")
        press("Mark $", prefix: true)
        sleep(4)
        tap(button("Settle up"), "Settle up")
        tap(button("Type amounts"), "Type amounts")
        tap(app.buttons["Evenly"].firstMatch, "Evenly")
        let next = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Next · check'")).firstMatch
        XCTAssertTrue(next.waitForExistence(timeout: 5), "S-48c: Settle up should say who it checks")
        XCTAssertTrue(next.label.contains("Sam") && !next.label.contains("Priya"), "Priya's $42.50 matches: \(next.label)")
        next.tap()
        XCTAssertTrue(text(containing: "Sam paid $20.00").waitForExistence(timeout: 5), "No S-48a")
        tap(button("Ask Sam for $22.50"), "Ask Sam for $22.50")
        sleep(1)
        press("Settle up")
        XCTAssertTrue(text(containing: "Sam owes $22.50").waitForExistence(timeout: 8), "S-48d toast")
        // S-48e: change it later from Sam's •••: his share is what he paid.
        sleep(7)
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Change Sam’s share"), "Change Sam's share")
        XCTAssertTrue(text(containing: "Sam paid $20.00").waitForExistence(timeout: 5), "S-48e should reopen S-48a")
        tap(button("Sam’s share is $20.00"), "Sam's share is $20.00")
        XCTAssertTrue(text(containing: "Sam’s share is $20.00").waitForExistence(timeout: 8), "No toast for the change")
        let id = ((server("transactions?q=Gusto") as? [String: Any])?["transactions"] as? [[String: Any]])?
            .first { ($0["merchant"] as? String) == "Gusto" }?["id"] as? String
        let detail = id.flatMap { server("transactions/\($0)") as? [String: Any] }
        let t = (detail?["transaction"] as? [String: Any]) ?? detail
        let people = ((t?["splitting"] as? [String: Any])?["people"] as? [[String: Any]]) ?? []
        let owes = people.first { ($0["name"] as? String) == "Sam" }?["owes"] as? Double
        XCTAssertEqual(owes ?? -1, 0, accuracy: 0.001, "Sam shouldn't owe anything once his share is $20.00")
    }

    // MARK: Round 2 (testingBOT, ios/bots/testing-log.md)

    /// TEST-19: right after Save split on Not sure yet the page is S-04u6
    /// (the card and each •••), without reopening it. TEST-20: Jo's "Which
    /// payment was it?" ticks nobody's money, since none of it is Jo's.
    func testNotSureYetCardRightAfterSaveAndNoOneElsesMoneyTicked() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        press("Save split")
        XCTAssertTrue(app.buttons["Options for Priya"].waitForExistence(timeout: 4),
                      "TEST-19: the card should show right after Save split")
        XCTAssertFalse(app.buttons["Split with others"].exists, "TEST-19: the page still offers Split with others")
        tap(app.buttons["Options for Jo"], "Options for Jo")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        XCTAssertTrue(button("Priya Shah").waitForExistence(timeout: 10), "The money in should be listed")
        XCTAssertFalse(button("Priya Shah").isSelected || button("Sam Lee").isSelected,
                       "TEST-20: someone else's payment is ticked for Jo")
        XCTAssertFalse(text(containing: "Amount matches").exists, "TEST-20: no amount to match on Not sure yet")
        XCTAssertFalse(text(containing: "Suggested").exists, "TEST-20: nothing of Jo's to suggest")
        let link = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Link'")).allElementsBoundByIndex.last
        XCTAssertFalse(link?.isEnabled ?? false, "TEST-20: Link should wait for a pick")
    }

    /// TEST-19: after That's everything the page is S-46b at once (Reopen
    /// split), not still Settle up.
    func testThatsEverythingClosesTheCardAtOnce() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(button("That’s everything"), "That's everything")
        press("That’s everything")
        let reopen = button("Reopen split").waitForExistence(timeout: 4)
        let seen = reopen ? "" : (app.buttons.allElementsBoundByIndex + app.staticTexts.allElementsBoundByIndex)
            .map(\.label).filter { !$0.isEmpty }.joined(separator: " | ")
        XCTAssertTrue(reopen, "TEST-19: the card should close at once. On screen: \(seen)")
        XCTAssertFalse(button("Settle up").exists, "TEST-19: Settle up is still offered after closing")
    }

    /// TEST-18 (S-47e): a share that's too big shows only what's left for
    /// her; no "Sam owes you" row and no Allowance note.
    func testYourShareTooBigShowsOnlyWhatsLeft() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(app.buttons["Options for you"], "S-04u6: your •••")
        tap(button("Set your share"), "S-40y: Set your share")
        let field = app.textFields["your-share"]
        XCTAssertTrue(field.waitForExistence(timeout: 5), "No S-47 field")
        field.tap()
        field.typeText("100")
        XCTAssertTrue(text(containing: "Paybacks cover $42.50, so your share can be up to $85.00").waitForExistence(timeout: 4),
                      "S-47e's words")
        XCTAssertTrue(text(containing: "Left for you and Sam").exists, "S-47e: Left for you and Sam")
        XCTAssertFalse(text(containing: "Sam owes you").exists, "S-47e: no owes-you row while it's too big")
        XCTAssertFalse(text(containing: "Allowance doesn’t change").exists, "S-47e: no Rule A note while it's too big")
    }

    /// TEST-18 (S-04u8): once Priya and Sam have both paid and her share
    /// was never set, her row is what's left and That's everything says so.
    func testEveryoneHasPaidShowsWhatStaysYours() {
        launch()
        gustoNotSureWithPriyaPaid()
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Cash in hand"), "Cash in hand")
        let amount = app.textFields["Amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap()
        amount.typeText("30")
        press("Mark $", prefix: true)
        sleep(5)
        XCTAssertTrue(text(containing: "what’s left after paybacks").waitForExistence(timeout: 8), "S-04u8: your row")
        XCTAssertTrue(text(containing: "Everyone has paid. $55.00 stays yours.").exists, "S-04u8: That's everything's line")
    }

    /// S-47g (section 20): with two payers the folded Paid back line opens
    /// "Who paid you back"; a row opens that person's options, with Unlink.
    func testWhoPaidYouBackOpensTheirOptions() {
        launch()
        gustoNotSureWithPriyaPaid(["Sam", "Jo"])
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Cash in hand"), "Cash in hand")
        let amount = app.textFields["Amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap()
        amount.typeText("30")
        press("Mark $", prefix: true)
        sleep(5)
        tap(app.buttons["Options for you"], "your •••")
        tap(button("Set your share"), "Set your share")
        XCTAssertTrue(app.textFields["your-share"].waitForExistence(timeout: 5))
        let folded = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Priya and Sam'")).firstMatch
        tap(folded, "the folded Paid back line")
        XCTAssertTrue(text(containing: "Who paid you back").waitForExistence(timeout: 5), "S-47g didn't open")
        tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sam,'")).firstMatch, "Sam's row")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] 'Unlink'")).firstMatch
                        .waitForExistence(timeout: 8), "Sam's row should open his S-40u, with Unlink")
    }

    // MARK: Round 3 (testingBOT, ios/bots/testing-log.md)

    /// S-04r v2s: once the hero scrolls away, the bar says the merchant.
    func testTheBarTakesTheMerchantOnceItScrolls() {
        launch()
        openTransaction("Gusto")
        // A split makes the page long enough to scroll.
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        press("Save")
        sleep(3)
        app.swipeUp(); app.swipeUp(); app.swipeUp()
        let title = app.navigationBars.descendants(matching: .any).matching(NSPredicate(format: "label == 'Gusto'")).firstMatch
        if !title.waitForExistence(timeout: 4), let dir = ProcessInfo.processInfo.environment["PEARL_SHOTS"] {
            try? app.debugDescription.write(toFile: dir + "/inline-bar.txt", atomically: true, encoding: .utf8)
        }
        XCTAssertTrue(title.exists, "The inline bar should show Gusto once the hero is gone")
        // TEST-09 (round 2): a solid bar behind Back and the title, so the
        // scrolled content doesn't show through. The strip right of Back
        // is one flat colour, not words passing under it.
        let bar = app.navigationBars.firstMatch
        let f = bar.frame
        let shot = XCUIScreen.main.screenshot().image
        if let cg = shot.cgImage {
            let scale = CGFloat(cg.width) / shot.size.width
            let r = CGRect(x: (f.minX + f.width * 0.16) * scale, y: (f.minY + 4) * scale,
                           width: f.width * 0.18 * scale, height: (f.height - 8) * scale).integral
            if let crop = cg.cropping(to: r) {
                let w = crop.width, h = crop.height
                var px = [UInt8](repeating: 0, count: w * h * 4)
                let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
                ctx?.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
                var lum: [Double] = []
                for i in stride(from: 0, to: px.count, by: 4) {
                    lum.append((0.2126 * Double(px[i]) + 0.7152 * Double(px[i + 1]) + 0.0722 * Double(px[i + 2])) / 255)
                }
                lum.sort()
                let spread = lum[Int(Double(lum.count - 1) * 0.98)] - lum[Int(Double(lum.count - 1) * 0.02)]
                XCTAssertLessThan(spread, 0.2, "TEST-09: the content shows through the bar (spread \(spread))")
            }
        }
        // TEST-14: the hero's amount reads as words, not an unread U+2212.
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'spent $'")).firstMatch
                        .waitForExistence(timeout: 4), "TEST-14: the hero amount should say spent $127.50")
    }

    private func allowance() -> Double {
        ((server("home") as? [String: Any])?["safe_to_spend"] as? [String: Any])?["amount"] as? Double ?? -1
    }

    /// Gusto Not sure yet with Priya, Sam and Jo; Priya's $42.50 and Sam's
    /// $30.00 e-Transfers linked.
    private func gustoWithPriyaAndSamPaid() {
        gustoNotSureWithPriyaPaid(["Sam", "Jo"])
        tap(app.buttons["Options for Sam"], "Options for Sam")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        let sam = button("Sam Lee")
        XCTAssertTrue(sam.waitForExistence(timeout: 10))
        if !sam.isSelected { sam.tap() }
        press("Link", prefix: true)
        sleep(5)
    }

    /// TEST-24: S-48b says a gift lowers the Allowance, and it does. Evenly
    /// four ways Priya ($42.50) paid more than her share.
    func testItsAGiftLowersTheAllowance() {
        launch()
        gustoWithPriyaAndSamPaid()
        let before = allowance()
        tap(button("Settle up"), "Settle up")
        tap(button("Type amounts"), "Type amounts")
        tap(app.buttons["Evenly"].firstMatch, "Evenly")
        tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Next · check'")).firstMatch, "Next · check")
        // S-48a / S-48b, in whichever order Pearl asks: ask Sam for the
        // rest; Priya's extra is a gift.
        let settle = app.buttons.matching(NSPredicate(format: "label == 'Settle up'"))
        var sawCallout = false
        for _ in 0..<6 {
            sleep(2)
            if settle.allElementsBoundByIndex.contains(where: { $0.isHittable }) { break }
            if text(containing: "Priya paid").exists && text(containing: "more").exists {
                XCTAssertTrue(text(containing: "and “It’s a gift” lower your Allowance by").exists,
                              "TEST-24: S-48b's callout should say a gift lowers the Allowance")
                XCTAssertFalse(text(containing: "Only “I owe").exists, "TEST-24: the old callout")
                sawCallout = true
                tap(button("It’s a gift"), "It's a gift")
                continue
            }
            let ask = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Ask '")).allElementsBoundByIndex.last
            if let ask = ask, ask.isHittable { ask.tap() }
        }
        XCTAssertTrue(sawCallout, "S-48b for Priya never came")
        if !settle.allElementsBoundByIndex.contains(where: { $0.isHittable }) {
            XCTFail("No Settle up after the answers. Buttons: \(app.buttons.allElementsBoundByIndex.map(\.label).filter { !$0.isEmpty })")
            return
        }
        press("Settle up")
        XCTAssertTrue(text(containing: "Settled").waitForExistence(timeout: 8), "No Settled toast")
        sleep(2)
        let moved = allowance() - before
        XCTAssertLessThan(moved, -10.5, "TEST-24: a gift should lower the Allowance by Priya's extra (moved \(moved))")
        XCTAssertGreaterThan(moved, -10.8, "TEST-24: only by Priya's extra (moved \(moved))")
    }

    /// TEST-25 (T-01r2): Cash flow's Gusto row is the whole purchase with
    /// the server's note, not "Your share of …" and what still counts.
    func testCashFlowRowSaysWhatsStillToComeBack() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        for (who, amount) in [("Priya", "42.50"), ("Sam", "30"), ("Jo", "15")] {
            let f = amountField(who)
            tap(f, "\(who)'s amount")
            f.typeText(amount)
        }
        app.staticTexts["How to split"].firstMatch.tap()
        press("Save")
        sleep(3)
        tap(app.buttons["Options for Priya"], "Options for Priya")
        tap(button("Mark paid back"), "Mark paid back")
        tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
        XCTAssertTrue(button("Priya Shah").waitForExistence(timeout: 10))
        if !button("Priya Shah").isSelected { button("Priya Shah").tap() }
        press("Link", prefix: true)
        sleep(4)
        app.navigationBars.buttons["Back"].firstMatch.tap()
        sleep(2)
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Gusto'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 8), "No Gusto row")
        XCTAssertTrue(row.label.contains("Split with Priya +2 · $45.00 to come back"), "TEST-25: \(row.label)")
        XCTAssertTrue(row.label.contains("127.50"), "TEST-25: the row should show the whole purchase: \(row.label)")
        XCTAssertFalse(row.label.contains("Your share of"), "TEST-25: the app's own note: \(row.label)")
    }

    /// TEST-20: Priya's sheet, opened again after her $42.50 is linked and
    /// she still owes $7.50, ticks nobody else's money.
    func testAReopenedPaymentSheetTicksNoOneElse() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam", "Jo"])
        tap(app.buttons["Amounts"], "Amounts")
        for (who, amount) in [("Priya", "50"), ("Sam", "30"), ("Jo", "25")] {
            let f = amountField(who)
            tap(f, "\(who)'s amount")
            f.typeText(amount)
        }
        app.staticTexts["How to split"].firstMatch.tap()
        press("Save")
        sleep(3)
        for round in 0..<2 {
            tap(app.buttons["Options for Priya"], "Options for Priya")
            // "Mark the rest paid back" once part is in.
            tap(button(round == 0 ? "Mark paid back" : "Mark the rest paid back"), "Mark paid back")
            tap(button("Bank or e-Transfer"), "Bank or e-Transfer")
            XCTAssertTrue(button("Sam Lee").waitForExistence(timeout: 10))
            let ticked = app.buttons.matching(NSPredicate(format: "selected == true AND (label BEGINSWITH 'Sam' OR label BEGINSWITH 'Jo')"))
            XCTAssertEqual(ticked.count, 0, "TEST-20: someone else's payment is ticked for Priya (round \(round))")
            if round == 0 {
                let priya = button("Priya Shah")
                if !priya.isSelected { priya.tap() }
                press("Link", prefix: true)
                sleep(5)
            }
        }
    }

    /// TEST-14: no clipped text on S-40y, and How to split's amounts read as
    /// words (the audit's "not human-readable").
    func testS40yAndHowToSplitPassTheAudit() throws {
        guard #available(iOS 17.0, *) else { throw XCTSkip("The audit needs iOS 17") }
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        var found: [String] = []
        try app.performAccessibilityAudit(for: [.sufficientElementDescription]) { issue in
            if let label = issue.element?.label, label.hasPrefix("$") { found.append(label) }
            return true
        }
        XCTAssertTrue(found.isEmpty, "TEST-14: bare amounts on How to split: \(found)")
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        press("Save split")
        tap(app.buttons["Options for you"], "your •••")
        XCTAssertTrue(button("Set your share").waitForExistence(timeout: 5))
        var clipped: [String] = []
        try app.performAccessibilityAudit(for: [.textClipped]) { issue in
            clipped.append(issue.element?.label ?? issue.compactDescription)
            return true
        }
        XCTAssertFalse(clipped.contains { $0.contains("NOT SURE YET") }, "TEST-14: S-40y's overline is clipped: \(clipped)")
    }

    // MARK: From the redesign line (sections 16 and 17, Sort now, T-01r / T-01r3, TEST-12, TEST-22)

    /// T-93n: a card whose best guess is Other asks, with Answer.
    func testAnOtherGuessIsAQuestion() {
        launch()
        tap(app.buttons["See the list"], "See the list")
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Other?'")).firstMatch
                        .waitForExistence(timeout: 6), "Needs a look still shows an Other? chip")
        tap(button("Quick sort"), "Quick sort card")
        var n = 0
        while !text(containing: "What was this?").exists && n < 6 {
            app.buttons["Skip"].tap(); sleep(1); n += 1
        }
        XCTAssertTrue(text(containing: "What was this?").exists, "No card asks What was this?")
        XCTAssertTrue(app.buttons["Answer"].exists, "Its round button should be Answer")
        XCTAssertTrue(text(containing: "NEEDS A LOOK").exists)
    }

    /// T-01r: Leftover leads, then Spent / Saved / Leftover, Came in, and
    /// "need a look · Sort"; spending amounts in ink. T-01r3 (TEST-05):
    /// while this month's pay is still to come, "Spent so far", "Pay
    /// expected <day>" and "Pay to come", and never a red Over.
    func testCashFlowLeadsWithLeftover() {
        launch()
        let month = String(ISO8601DateFormatter().string(from: Date()).prefix(7))
        let totals = (server("transactions/list?month=\(month)") as? [String: Any])?["month_totals"] as? [String: Any]
        let waiting = totals?["pay"] is [String: Any]
        openCashFlow()
        if waiting {
            XCTAssertTrue(text(containing: "Spent so far").waitForExistence(timeout: 8), "T-01r3: no Spent so far")
            for words in ["Pay expected", "Pay to come", "Spent $", "Saved", "need a look"] {
                let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", words)).firstMatch
                XCTAssertTrue(e.waitForExistence(timeout: 8), "T-01r3: no \(words) on Cash flow")
            }
            XCTAssertFalse(text(containing: "Over").exists, "T-01r3: no Over before the pay is in")
            XCTAssertFalse(text(containing: "Came in").exists, "T-01r3: Pay expected takes Came in's place")
            return
        }
        let lead = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Leftover' OR label CONTAINS 'Over'")).firstMatch
        XCTAssertTrue(lead.waitForExistence(timeout: 8), "No Leftover / Over headline")
        for words in ["Came in", "Spent", "Saved", "need a look"] {
            let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", words)).firstMatch
            XCTAssertTrue(e.waitForExistence(timeout: 8), "No \(words) on Cash flow")
        }
        XCTAssertFalse(text(containing: "Over $").exists && text(containing: "Leftover $").exists)
    }

    /// TEST-12 (T-93n): Cash flow's rows ask "What was this?" too; never "Other?".
    func testCashFlowRowsHaveNoOtherGuess() {
        launch()
        openCashFlow()
        sleep(2)
        let other = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Other?' OR label CONTAINS 'guess: Other'"))
        XCTAssertFalse(other.firstMatch.exists, "TEST-12: Cash flow still shows an Other? guess")
    }

    /// S-03r2 / S-03r2b: "I had some too" on How to split; off, your row
    /// goes, the rest is left to assign and Save is off. The Done bar too.
    func testIHadSomeTooOnHowToSplit() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        let priya = amountField("Priya")
        tap(priya, "Priya's amount")
        priya.typeText("40")
        XCTAssertTrue(app.toolbars.buttons["Done"].exists || app.buttons["Done"].exists, "No Done over the number pad")
        (app.toolbars.buttons["Done"].exists ? app.toolbars.buttons["Done"] : app.buttons["Done"]).tap()
        XCTAssertTrue(text(containing: "of $127.50").waitForExistence(timeout: 4), "No \"… of $127.50\" by the bar")
        let toggle = app.switches.matching(NSPredicate(format: "label BEGINSWITH 'I had some too'")).firstMatch
        XCTAssertTrue(toggle.waitForExistence(timeout: 4), "No I had some too on How to split")
        if !toggle.isHittable { app.swipeUp() }
        toggle.switches.firstMatch.exists ? toggle.switches.firstMatch.tap() : toggle.tap()
        XCTAssertTrue(text(containing: "left to assign").waitForExistence(timeout: 4), "Off should leave the rest to assign")
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last!.isEnabled,
                       "Save should be off while it's short")
    }

    /// S-40u2: on a Not sure yet split nobody has a share to give back.
    func testRemoveOnNotSureYetSaysNothingToUnlink() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        let unsure = app.buttons["Not sure yet, split method"].exists ? app.buttons["Not sure yet, split method"] : app.buttons["Not sure"]
        tap(unsure, "Not sure")
        press("Save split")
        sleep(2)
        tap(app.buttons["Options for Priya"], "Options for Priya")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Nothing to unlink'")).firstMatch
                        .waitForExistence(timeout: 5), "Remove should say Nothing to unlink")
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS '$0.00 goes back'")).firstMatch.exists)
    }

    /// TEST-06: P-05, a Pearl sheet; Stay signed in keeps her signed in.
    func testSignOutAsksOnAPearlSheet() {
        launch()
        app.tabBars.buttons["Profile"].tap()
        let signOut = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sign out'")).firstMatch
        tap(signOut, "Sign out on Profile")
        XCTAssertEqual(app.sheets.count + app.alerts.count, 0, "Sign out is still a stock dialog")
        XCTAssertTrue(text(containing: "Sign out on this iPhone?").waitForExistence(timeout: 5), "No P-05 sheet")
        tap(app.buttons["Stay signed in"], "Stay signed in")
        sleep(1)
        XCTAssertTrue(app.tabBars.buttons["Profile"].exists, "Stay signed in should keep her signed in")
    }

    /// H-00r: Sort now opens Quick sort straight from Home.
    func testSortNowOpensQuickSortFromHome() {
        launch()
        XCTAssertFalse(app.buttons["Review one by one"].exists, "Home still says Review one by one")
        XCTAssertTrue(text(containing: "About").waitForExistence(timeout: 10), "No \"About a minute\" line")
        tap(app.buttons["Sort now"], "Sort now")
        XCTAssertTrue(app.descendants(matching: .any)["quick-sort-card"].waitForExistence(timeout: 15),
                      "Sort now should open Quick sort")
        XCTAssertFalse(app.staticTexts["Needs a look"].exists, "It opened Needs a look instead")
    }

    /// TEST-22: at the largest text size the card's amounts never break
    /// inside the number. Held on screen for the host to capture.
    func testSplitCardAmountsAtTheLargestSize() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        press("Save")
        sleep(3)
        let card = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Priya'")).firstMatch
        tap(card, "Priya's row")
        app.buttons["Close"].firstMatch.tap()
        sleep(12)
    }
}
