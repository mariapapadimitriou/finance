import XCTest

/// engBOT's check of H-00r v2 (the Allowance gauge on Home, n-home-gauge) and
/// T-01r (Cash flow's month card with the meter, n-cf-meter), light and
/// dark, with How it adds up from each. Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/GaugeUITests testGaugeBusy`
/// (the demo ledger) or `… testGaugeCalm` (a ledger with nothing to do).
final class GaugeUITests: XCTestCase {
    private var app: XCUIApplication!
    private var stepNumber = 0
    private var appearance = "light"

    private var shots: String { ProcessInfo.processInfo.environment["PEARL_SHOTS"] ?? NSTemporaryDirectory() }
    private var port: String { ProcessInfo.processInfo.environment["PEARL_PORT"] ?? "5051" }

    override func setUp() {
        continueAfterFailure = true
        app = XCUIApplication()
    }

    private func launch(_ scheme: String) {
        appearance = scheme
        app.terminate()
        app.launchArguments = ["-pearl.server", "http://localhost:\(port)", "-pearl.appearance", scheme]
        app.launch()
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 8) { notNow.tap() }
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 20), "No tab bar")
        sleep(3)
        clearInterruptions()
    }

    private func clearInterruptions() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let deny = springboard.buttons["Don’t Allow"]
        if deny.exists { deny.tap(); sleep(1) }
        let notNow = app.buttons["Not now"]
        if notNow.exists && notNow.isHittable && app.staticTexts["Want a heads-up?"].exists { notNow.tap(); sleep(1) }
    }

    private func step(_ name: String) {
        sleep(1)
        clearInterruptions()
        stepNumber += 1
        let method = self.name.components(separatedBy: " ").last?.replacingOccurrences(of: "]", with: "") ?? "test"
        let base = "\(shots)/\(method)-\(String(format: "%02d", stepNumber))-\(appearance)-\(name.replacingOccurrences(of: " ", with: "-"))"
        FileManager.default.createFile(atPath: base + ".png", contents: XCUIScreen.main.screenshot().pngRepresentation)
        try? app.debugDescription.write(toFile: base + ".txt", atomically: true, encoding: .utf8)
        print("JOURNEY \(base).png")
    }

    private func back() {
        let b = app.buttons["Back"].firstMatch
        if b.waitForExistence(timeout: 3) { b.tap(); sleep(1) }
    }

    private func shoot() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            let gauge = app.buttons["allowance-gauge"]
            XCTAssertTrue(gauge.waitForExistence(timeout: 10), "No gauge")
            print("JOURNEY note: gauge says “\(gauge.label)”")
            step("home")
            // A real tap at its centre (XCUI's hittable check is unsure of it).
            gauge.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            sleep(2)
            print("JOURNEY note: How it adds up open \(app.staticTexts["How your Allowance adds up"].exists)")
            step("adds up from home")
            back()
            app.swipeUp()
            step("home scrolled")
            app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            sleep(3)
            step("cash flow card")
            let addsUp = app.buttons["cf-adds-up"]
            XCTAssertTrue(addsUp.waitForExistence(timeout: 6), "No How it adds up row")
            addsUp.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            sleep(2)
            step("adds up from cash flow")
            back()
        }
    }

    func testGaugeBusy() { shoot() }

    func testGaugeCalm() { shoot() }
}
