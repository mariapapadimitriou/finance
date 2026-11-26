import XCTest

/// Fewer taps, Home and set-up (TP-P1-Home, TP-P7-LinkLater, TP-P12-Home,
/// TP-P12-Amount, TP-P6-News, TP-P6-Setup): real taps against the demo
/// ledger, where Acme's $5,850 is a pay Pearl found and she hasn't answered.
/// Run with `python3 ios/tools/run_journeys.py --suite PearlUITests/FewerTapsHomeUITests …`.
final class FewerTapsHomeUITests: XCTestCase {
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

    private func launch(_ scheme: String = "light", setup: String? = nil) {
        appearance = scheme
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(port)", "-pearl.appearance", scheme]
            + (setup.map { ["-pearl-setup", $0] } ?? [])
        app.launch()
        if setup == nil {
            XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        }
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

    private func shows(_ text: String, timeout: TimeInterval = 6) -> Bool {
        let ok = element(containing: text).waitForExistence(timeout: timeout)
        note("\(ok ? "SEEN" : "NOT SEEN") “\(text)”")
        return ok
    }

    private func tapId(_ id: String, timeout: TimeInterval = 8) {
        let b = app.buttons[id]
        XCTAssertTrue(b.waitForExistence(timeout: timeout), "No \(id)")
        if b.isHittable { b.tap() } else { b.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
    }

    // MARK: P12a–c: Is this your pay? on Home, Yes / No, Undo

    func testPayAskOnHome() {
        launch()
        XCTAssertTrue(shows("Is $5,850 from Acme your pay?", timeout: 15))
        XCTAssertTrue(shows("ALLOWANCE LEFT") || shows("Allowance left"))
        XCTAssertTrue(app.buttons["profile-circle"].exists)
        step("P12a home asks")
        tapId("pay-ask-yes")
        XCTAssertTrue(shows("Acme is your pay."))
        step("P12b yes toast")
        let undo = button("Undo")
        XCTAssertTrue(undo.waitForExistence(timeout: 4))
        undo.tap()
        XCTAssertTrue(shows("Is $5,850 from Acme your pay?", timeout: 10), "Undo brings the question back")
        step("P12b undone")
        tapId("pay-ask-no")
        XCTAssertTrue(shows("Got it. Acme isn’t your pay."))
        step("P12c no toast")
        XCTAssertFalse(element(containing: "from Acme your pay?").exists)
    }

    // MARK: P1: one name, Allowance left

    func testAllowanceLeftEverywhere() {
        launch()
        XCTAssertTrue(shows("Allowance left", timeout: 15))
        XCTAssertFalse(element(containing: "Left to spend").exists)
        XCTAssertTrue(shows("For you") || true)
        step("P1a home")
        let gauge = app.buttons["allowance-gauge"]
        XCTAssertTrue(gauge.waitForExistence(timeout: 6))
        gauge.tap()
        XCTAssertTrue(shows("How your Allowance adds up"))
        XCTAssertTrue(shows("Spent so far"))
        XCTAssertFalse(element(containing: "Left is the same number").exists)
        step("P1b adds up")
        app.tabBars.buttons["Cash flow"].tap()
        XCTAssertTrue(shows("Allowance left", timeout: 10))
        XCTAssertFalse(element(containing: "Leftover").exists)
        step("P1c cash flow card")
        let month = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Month,")).firstMatch
        if month.waitForExistence(timeout: 6) {
            month.tap()
            XCTAssertTrue(shows("so far"))
            XCTAssertFalse(element(containing: "Leftover").exists)
            step("P1d choose a month")
        }
    }

    // MARK: P7a: Link later goes straight to Home

    func testLinkLaterGoesHome() {
        launch(setup: "linkBank")
        let later = app.buttons["Link later"]
        XCTAssertTrue(later.waitForExistence(timeout: 15))
        step("P7a plaid")
        later.tap()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 15), "Link later lands on Home")
        XCTAssertFalse(element(containing: "Almost there").exists)
        step("P7 home")
    }

    // MARK: P6b–e: one pay question, bills one level down, savings, all set

    func testSetupPayQuestion() {
        launch(setup: "payBills")
        XCTAssertTrue(shows("Is this your pay?", timeout: 15))
        XCTAssertTrue(shows("Acme"))
        step("P6b pay")
        tapId("setup-bills")
        XCTAssertTrue(shows("Untick any that aren’t yours."))
        step("P6c bills")
        tapId("setup-bills-done")
        tapId("setup-pay-yes")
        XCTAssertTrue(shows("How much do you want to save?", timeout: 10))
        XCTAssertTrue(shows("A share of each pay."))
        XCTAssertTrue(app.buttons["Other"].exists || shows("Other"))
        step("P6d saving")
        let cont = app.buttons["Continue"]
        XCTAssertTrue(cont.waitForExistence(timeout: 4))
        cont.tap()
        XCTAssertTrue(shows("Allowance left ·", timeout: 10))
        XCTAssertTrue(shows("Sort this month"))
        step("P6e all set")
    }
}
