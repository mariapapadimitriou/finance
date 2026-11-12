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
        let status = text(containing: "stays yours")
        XCTAssertTrue(status.waitForExistence(timeout: 4), "No status line")
        sleep(1)
        let saveButton = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex.last
        XCTAssertTrue(status.isHittable, "The status line is under the number pad or Save: status \(status.frame), "
                      + "Save \(saveButton?.frame ?? .zero), pad \(app.keyboards.firstMatch.frame), window \(app.windows.firstMatch.frame)")
        if !app.buttons["Split the rest evenly"].isHittable, let dir = ProcessInfo.processInfo.environment["PEARL_SHOTS"] {
            try? app.debugDescription.write(toFile: dir + "/numberpad.txt", atomically: true, encoding: .utf8)
            FileManager.default.createFile(atPath: dir + "/numberpad.png", contents: XCUIScreen.main.screenshot().pngRepresentation)
        }
        // At AX sizes the pad leaves room for the status line; the button
        // under it is a scroll away.
        if !ax { XCTAssertTrue(app.buttons["Split the rest evenly"].isHittable, "Split the rest evenly is hidden") }
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
    // MARK: Section 17 (TEST-08, 09, 11, 12, 16)

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

    /// TEST-12 (T-93n): Cash flow's rows ask "What was this?" too; never "Other?".
    func testCashFlowRowsHaveNoOtherGuess() {
        launch()
        openCashFlow()
        sleep(2)
        let other = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS 'Other?' OR label CONTAINS 'guess: Other'"))
        XCTAssertFalse(other.firstMatch.exists, "TEST-12: Cash flow still shows an Other? guess")
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
    // MARK: TEST-04 / TEST-05 (REFRESH-00 decisions 1 and 2)

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

    // MARK: Round 3 (testingBOT, ios/bots/testing-log.md)

    /// TEST-25: Cash flow's split row shows the server's note, not the
    /// app's own "Your share of $128".
    func testCashFlowRowUsesTheServersSplitNote() {
        launch()
        openTransaction("Gusto")
        tap(app.buttons["Split with others"], "Split with others")
        addPeople(["Priya", "Sam"])
        press("Save")
        sleep(3)
        app.navigationBars.buttons["Back"].firstMatch.tap()
        sleep(2)
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Gusto'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 8), "No Gusto row")
        XCTAssertFalse(row.label.contains("Your share of $128"), "TEST-25: the app's own note: \(row.label)")
        let month = String(ISO8601DateFormatter().string(from: Date()).prefix(7))
        let rows = (server("transactions/list?month=\(month)&q=Gusto") as? [String: Any])?["transactions"] as? [[String: Any]]
        let note = rows?.first { ($0["merchant"] as? String) == "Gusto" }?["note"] as? String ?? "?"
        XCTAssertTrue(row.label.contains(note), "TEST-25: the row should carry the server's note \(note): \(row.label)")
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
