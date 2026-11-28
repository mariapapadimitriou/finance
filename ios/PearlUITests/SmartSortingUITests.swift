import XCTest

/// THL-309 (AI Phase 4, Pearl redesign canvas, Pearl page): Pearl sorts for
/// you, Off · Rules · Smart (CN-07), Turn on Smart? (CN-08), a Smart reason
/// on a Quick sort card and in Why Pearl sorted this (AI-03s), stepping down
/// (CN-09), and Profile › AI usage (AU-01). Run by run_journeys.py
/// (`--suite PearlUITests/SmartSortingUITests testSmartSorting`), whose
/// seed_smart gives a pattern Smart sorted and Smart's picks for the
/// guesses, made with a fake model. No model is called.
final class SmartSortingUITests: XCTestCase {
    private var app: XCUIApplication!
    private var stepNumber = 0

    private var shots: String { ProcessInfo.processInfo.environment["PEARL_SHOTS"] ?? NSTemporaryDirectory() }
    private var port: String { ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051" }

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    private func launch() {
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(port)", "-pearl.appearance", "light"]
        app.launch()
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 5) {
            sleep(1)
            notNow.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        // Whatever a stray tap opened on Home, back out of it.
        for _ in 0..<3 where !app.buttons["profile-circle"].firstMatch.waitForExistence(timeout: 3) {
            let back = app.buttons["Back"].firstMatch
            if back.exists { back.tap() } else { app.tabBars.buttons["Home"].tap() }
        }
    }

    private func step(_ name: String, settle: UInt32 = 1) {
        sleep(settle)
        stepNumber += 1
        let base = "\(shots)/testSmartSorting-\(String(format: "%02d", stepNumber))-\(name.replacingOccurrences(of: " ", with: "-"))"
        FileManager.default.createFile(atPath: base + ".png", contents: XCUIScreen.main.screenshot().pngRepresentation)
        try? app.debugDescription.write(toFile: base + ".txt", atomically: true, encoding: .utf8)
        print("JOURNEY \(base).png")
    }

    private func element(_ text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    private func button(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
    }

    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15) {
        XCTAssertTrue(e.waitForExistence(timeout: timeout), "Couldn't find \(what)")
        var n = 0
        while !e.isHittable && n < 6 { app.swipeUp(velocity: .slow); n += 1 }
        if e.isHittable { e.tap() } else { e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
    }

    private func see(_ text: String, _ what: String) {
        XCTAssertTrue(element(text).waitForExistence(timeout: 15), "No \(what): \(text)")
    }

    private func openPrivacy() {
        tap(app.buttons["profile-circle"].firstMatch, "the profile circle")
        tap(app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Privacy and consent'")).firstMatch,
            "Privacy and consent")
        XCTAssertTrue(app.otherElements["privacy-sorting"].waitForExistence(timeout: 15)
                      || element("Pearl sorts for you").waitForExistence(timeout: 5), "No sorting row")
    }

    private func backHome() {
        for _ in 0..<3 {
            let back = app.buttons["profile-back"].firstMatch
            if back.waitForExistence(timeout: 2) && back.isHittable { back.tap() } else { break }
        }
        tap(app.tabBars.buttons["Home"], "Home")
    }

    func testSmartSorting() {
        launch()
        step("home")
        // CN-07: Rules, the old switch mapped across.
        openPrivacy()
        see("Sorts the ways you said yes to.", "Rules' line")
        step("CN-07 rules")
        // CN-08: Smart the first time asks, in Pearl's words.
        tap(app.buttons["Smart"].firstMatch, "Smart")
        see("Turn on Smart?", "CN-08")
        see("shop names only", "the privacy line")
        step("CN-08 turn on smart")
        tap(app.buttons["Turn on Smart"].firstMatch, "Turn on Smart")
        see("Smart is on.", "the toast")
        see("Rules, plus Claude for reasons and harder cases.", "Smart's line")
        step("CN-08 smart is on")
        backHome()

        // AI-03s: a guess worded by Claude, one quiet grey line, no badge.
        sleep(6)                                     // the toast goes
        tap(app.buttons["See the list"].firstMatch, "See the list")
        step("needs a look")
        tap(app.buttons.matching(NSPredicate(format: "label == 'Quick sort'")).firstMatch, "Quick sort")
        sleep(3)
        step("quick sort opened")
        // The deck starts with the category guesses' first card that Claude worded.
        var n = 0
        while !element("Looks like").exists && n < 8 && app.buttons["Skip"].firstMatch.exists {
            app.buttons["Skip"].firstMatch.tap()
            sleep(2)
            n += 1
        }
        see("Looks like", "Claude's reason on the card")
        step("AI-03s quick sort", settle: 2)
        let later = app.buttons["Later"].firstMatch
        if later.waitForExistence(timeout: 3) { later.tap() }
        sleep(1)
        // AI-03s: Why Pearl sorted this, with "Reason worded by Claude."
        step("after quick sort")
        let chip = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label BEGINSWITH 'Pearl sorted'")).firstMatch
        if !chip.waitForExistence(timeout: 5) {
            tap(app.buttons["See the list"].firstMatch, "See the list")
        }
        if !chip.isHittable { app.scrollViews.firstMatch.swipeLeft() }
        tap(chip, "Pearl sorted")
        step("pearl sorted")
        // The first row under SORTED FOR YOU (the one Smart sorted).
        let row = app.staticTexts["Northside Pantry"].firstMatch
        if row.waitForExistence(timeout: 5) && row.isHittable { row.tap() }
        else { app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.397)).tap() }
        see("Your usual groceries, like your last 5 at Northside Pantry.", "Claude's reason")
        see("Reason worded by Claude.", "the byline")
        step("AI-03s why pearl sorted this")
        tap(app.buttons["Close"].firstMatch, "Close")
        let back = app.buttons["Back"].firstMatch
        if back.waitForExistence(timeout: 3) { back.tap() }
        tap(app.tabBars.buttons["Home"], "Home")

        // CN-09: Smart → Rules at once, with Undo; Off asks first.
        openPrivacy()
        tap(app.buttons["Rules"].firstMatch, "Rules")
        see("Back to Rules.", "the toast")
        see("keeps sorting", "the step-down line")
        step("CN-09 back to rules")
        tap(app.buttons["Off"].firstMatch, "Off")
        see("Stop Pearl sorting for you?", "CN-09's sheet")
        step("CN-09 stop pearl sorting")
        tap(app.buttons["Keep it on"].firstMatch, "Keep it on")
        sleep(1)

        // AU-01: the owner's AI usage (a local ledger is the owner's own).
        let profileBack = app.buttons["profile-back"].firstMatch
        if profileBack.waitForExistence(timeout: 3) { profileBack.tap() }
        tap(app.buttons["profile-ai-usage"].firstMatch, "AI usage")
        see("Only you see this.", "AU-01")
        see("Needed the bigger model", "the Sonnet row")
        step("AU-01 ai usage")
    }
}
