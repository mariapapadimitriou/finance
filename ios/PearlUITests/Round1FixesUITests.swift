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
    private func gustoNotSureWithPriyaPaid() {
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
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
        tap(app.buttons["Review one by one"], "Review one by one")
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
        tap(app.buttons["Review one by one"], "Review one by one")
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
        let paid = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Paid $42.50 so far'")).firstMatch
        if !paid.exists, let dir = ProcessInfo.processInfo.environment["PEARL_SHOTS"] {
            try? app.debugDescription.write(toFile: dir + "/settle-type-amounts.txt", atomically: true, encoding: .utf8)
        }
        XCTAssertTrue(paid.exists, "Priya's row should say what she's paid")
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
        let leave = app.buttons.matching(NSPredicate(format: "label == 'Leave out'")).allElementsBoundByIndex.last!
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

    // MARK: TEST-16 The number pad on Amounts

    func testTheNumberPadGoesAwayAndTheStatusStaysInView() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        tap(app.buttons["Amounts"], "Amounts")
        let priya = amountField("Priya")
        tap(priya, "Priya's amount")
        priya.typeText("40")
        let status = text(containing: "stays yours")
        XCTAssertTrue(status.waitForExistence(timeout: 4), "No status line")
        sleep(1)
        XCTAssertTrue(status.isHittable, "The status line is under the number pad or Save")
        XCTAssertTrue(app.buttons["Split the rest evenly"].isHittable, "Split the rest evenly is hidden")
        // A tap on the sheet's title puts the pad away.
        app.staticTexts["How to split"].firstMatch.tap()
        sleep(1)
        XCTAssertEqual(app.keyboards.count, 0, "The number pad didn't go away")
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
        for label in ["Review one by one", "Calendar"] {
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
}
