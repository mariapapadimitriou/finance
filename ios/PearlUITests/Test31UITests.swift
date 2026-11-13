import XCTest

/// engBOT's checks of TEST-31 (product owner, 2026-11-13): work reimbursing your
/// own share of a split purchase. Pai Northern Thai $120.00 split with Sam, and
/// Northwind's $60.00 in the journeys' demo data. Run with
/// `python3 ios/tools/run_journeys.py --suite PearlUITests/Test31UITests …`.
final class Test31UITests: XCTestCase {
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

    private func clearInterruptions() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let deny = springboard.buttons["Don’t Allow"]
        if deny.exists { deny.tap(); sleep(1) }
        let notNow = app.buttons["Not now"]
        if notNow.exists && notNow.isHittable && app.staticTexts["Want a heads-up?"].exists {
            notNow.tap(); sleep(1)
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
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] %@", text)).firstMatch
    }

    private func element(containing text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
    }

    @discardableResult
    private func tap(_ e: XCUIElement, _ what: String, timeout: TimeInterval = 15) -> Bool {
        guard e.waitForExistence(timeout: timeout) else { XCTFail("Couldn't find \(what)"); return false }
        var n = 0
        while !e.isHittable && n < 8 { app.swipeUp(velocity: .slow); n += 1 }
        e.tap()
        return true
    }

    private func call(_ method: String, _ path: String, _ body: [String: Any]? = nil) -> Any? {
        var result: Any?
        var request = URLRequest(url: URL(string: "http://localhost:\(port)/api/\(path)")!)
        request.httpMethod = method
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        let done = expectation(description: path)
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data = data { result = try? JSONSerialization.jsonObject(with: data) }
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 15)
        return result
    }

    private func rows(_ q: String) -> [[String: Any]] {
        let q = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q
        return ((call("GET", "transactions/list?q=\(q)&limit=50") as? [String: Any])?["transactions"]
                as? [[String: Any]]) ?? []
    }

    private func openCashFlow() {
        clearInterruptions()
        app.tabBars.buttons["Cash flow"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(2)
    }

    /// The average colour of a few points around `p` (in points) on screen.
    private func colour(at p: CGPoint) -> (Double, Double, Double) {
        let shot = XCUIScreen.main.screenshot().image
        guard let cg = shot.cgImage else { return (-1, -1, -1) }
        let scale = CGFloat(cg.width) / shot.size.width
        let r = CGRect(x: (p.x - 2) * scale, y: (p.y - 1) * scale, width: 4 * scale, height: 2 * scale).integral
        guard let crop = cg.cropping(to: r) else { return (-1, -1, -1) }
        let w = crop.width, h = crop.height
        var px = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        ctx?.draw(crop, in: CGRect(x: 0, y: 0, width: w, height: h))
        var t = (0.0, 0.0, 0.0)
        for i in stride(from: 0, to: px.count, by: 4) { t.0 += Double(px[i]); t.1 += Double(px[i + 1]); t.2 += Double(px[i + 2]) }
        let n = Double(w * h)
        return (t.0 / n, t.1 / n, t.2 / n)
    }

    // MARK: TEST-31

    private func id(_ q: String, amount: Double? = nil) -> String? {
        rows(q).first { amount == nil || abs(abs(($0["amount"] as? Double) ?? 0) - amount!) < 0.01 }?["id"] as? String
    }

    private func mine(_ charge: String) -> [String: Any]? {
        let d = call("GET", "transactions/\(charge)") as? [String: Any]
        let t = (d?["transaction"] as? [String: Any]) ?? d
        return (t?["splitting"] as? [String: Any])?["mine"] as? [String: Any]
    }

    private func openRow(_ name: String) {
        openCashFlow()
        let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
        if search.waitForExistence(timeout: 4) { search.tap(); search.typeText(name); sleep(2) }
        tap(button(name), "the \(name) row")
        sleep(2)
    }

    /// T-09w → S-04w → S-40w → T-41w: work's $60.00 for her share of Pai
    /// Northern Thai, from the deposit's What was this?, in light and dark.
    func testReimburseYourShare() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            guard let pai = id("Pai Northern Thai"), let work = id("Northwind", amount: 60) else {
                XCTFail("No Pai Northern Thai or Northwind in the demo"); return
            }
            // Start from nothing linked, whichever scheme runs first.
            _ = call("DELETE", "transactions/\(pai)/paybacks/\(work)")
            openRow("Northwind")
            step("northwind before")
            // The deposit's own answer: What was this? › Work paying me back.
            // Its card: "Other · Pearl’s guess" (or the kind of income once sorted).
            let card = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Pearl’s guess' OR label BEGINSWITH 'Other' OR label CONTAINS[c] 'income'")).firstMatch
            tap(card, "the deposit's card")
            sleep(2)
            tap(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Work paying me back'")).firstMatch, "Work paying me back")
            sleep(2)
            step("T-09w what did this pay back")
            let share = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Your share of Pai Northern Thai'")).firstMatch
            XCTAssertTrue(share.waitForExistence(timeout: 6), "T-09w: no “Your share of Pai Northern Thai” match")
            XCTAssertTrue(element(containing: "all of it").exists, "T-09w: “all of it” should stay beside it")
            share.tap()
            sleep(1)
            step("T-09w your share picked")
            if let save = app.buttons.matching(NSPredicate(format: "label == 'Save'")).allElementsBoundByIndex
                .last(where: { $0.isHittable }) { save.tap() }
            sleep(3)
            let m = mine(pai)
            note("mine after T-09w: \(String(describing: m))")
            XCTAssertEqual(m?["reimbursed"] as? Double, 60, "Her share should be reimbursed")
            // S-04w: the split card in two parts.
            app.terminate(); launch(scheme)
            openRow("Pai Northern Thai")
            app.swipeUp(velocity: .slow)
            step("S-04w split card")
            let you = app.buttons["split-you-row"]
            XCTAssertTrue(you.waitForExistence(timeout: 6))
            note("you row: \(you.label)")
            XCTAssertTrue(you.label.hasPrefix("You, reimbursed by"), "S-04w: \(you.label)")
            XCTAssertTrue(element(containing: "Owes you").exists, "S-04w: Sam still owes")
            XCTAssertTrue(element(containing: "reimbursed").exists)
            // S-40w.
            tap(app.buttons["Options for you"].firstMatch, "Options for you")
            sleep(2)
            step("S-40w your options")
            XCTAssertTrue(element(containing: "REIMBURSED BY").exists || element(containing: "Reimbursed by").exists)
            XCTAssertTrue(app.buttons["View the deposit"].exists, "S-40w: View the deposit")
            XCTAssertTrue(app.buttons["Unlink…"].exists, "S-40w: Unlink…")
            XCTAssertTrue(button("Change your share").exists, "S-40w: Change your share")
            XCTAssertFalse(button("Remove").exists, "S-40w: no Remove")
            app.buttons["View the deposit"].tap()
            sleep(3)
            // T-41w: the deposit's page.
            step("T-41w deposit page")
            let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Paid back, your share of Pai Northern Thai'")).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 6), "T-41w: no PAID BACK row")
            note("T-41w row: \(row.label)")
            XCTAssertEqual(row.label, "Paid back, your share of Pai Northern Thai, $60.00")
            // T-41w's top: the answer, a "Paid back" chip, a green amount.
            XCTAssertTrue(button("Work paying me back").exists, "T-41w: the card reads Work paying me back")
            XCTAssertTrue(element(containing: "Paid back").exists, "T-41w: Paid back chip")
            XCTAssertFalse(element(containing: "Not counted").exists, "T-41w: not Not counted")
        }
    }

    /// T-41w's rule for a friend's payback: "Paying me back", the Paid back
    /// chip and a green amount, in light and dark.
    func testAFriendsPaybackReadsPaidBack() {
        for scheme in ["light", "dark"] {
            launch(scheme)
            guard let pizza = id("Pizza Nova"),
                  let priya = rows("Priya").first(where: { abs(($0["amount"] as? Double) ?? 0) == 40 })?["id"] as? String
            else { XCTFail("No Pizza Nova or Priya's $40.00"); return }
            _ = call("PUT", "transactions/\(pizza)/split",
                     ["mode": "amount", "include_me": true, "people": [["name": "Priya", "amount": 40]], "you": 80])
            _ = call("POST", "transactions/\(pizza)/paybacks/\(priya)", ["person": "Priya"])
            openCashFlow()
            let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
            if search.waitForExistence(timeout: 4) { search.tap(); search.typeText("Priya"); sleep(2) }
            let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Priya' AND label CONTAINS '40.00'")).firstMatch
            tap(row, "Priya's $40.00")
            sleep(2)
            step("T-41w friend payback")
            XCTAssertTrue(button("Paying me back").waitForExistence(timeout: 6), "The card reads Paying me back")
            XCTAssertTrue(element(containing: "Paid back").exists, "Paid back chip")
            // The green amount, sampled from the hero.
            let hero = app.staticTexts.matching(NSPredicate(format: "label CONTAINS '40'")).firstMatch
            note("hero: \(hero.label) \(hero.frame)")
        }
    }

    /// S-04w3 and S-04w2 from the server: Sam pays his $60.00 too ("Costs you
    /// $0.00"), then the share link goes and a $45.00 part stands in.
    func testBothPaidAndPartial() {
        launch()
        guard let pai = id("Pai Northern Thai"), let work = id("Northwind", amount: 60) else {
            XCTFail("No Pai Northern Thai or Northwind in the demo"); return
        }
        _ = call("POST", "transactions/\(work)/mark", ["case": "reimbursement", "charge": pai, "share": true])
        // Sam's two e-Transfers in the demo ($25.00 and $20.00) aren't $60.00:
        // mark his share paid in cash so the card has both parts full.
        _ = call("POST", "transactions/\(pai)/split/cash", ["name": "Sam", "amount": 60])
        openRow("Pai Northern Thai")
        app.swipeUp(velocity: .slow)
        step("S-04w3 both paid")
        XCTAssertTrue(element(containing: "Costs you $0.00").waitForExistence(timeout: 6), "S-04w3: Costs you $0.00")
        // Partial: the deposit split as a $45.00 reimbursement and $15.00 extra pay.
        let d = call("GET", "transactions/\(pai)") as? [String: Any]
        let people = (((d?["transaction"] as? [String: Any]) ?? d)?["splitting"] as? [String: Any])?["people"] as? [[String: Any]]
        for cash in (people?.first?["cash_ids"] as? [Int]) ?? [] {
            _ = call("DELETE", "transactions/\(pai)/split/cash/\(cash)")
        }
        _ = call("DELETE", "transactions/\(pai)/paybacks/\(work)")
        let r = call("POST", "transactions/\(work)/parts", ["parts": [
            ["kind": "reimbursement", "amount": 45, "charge": pai],
            ["kind": "income", "amount": 15, "income_kind": "bonus"]]]) as? [String: Any]
        note("parts: \(r?["title"] ?? r?["error"] ?? "-")")
        app.terminate(); launch()
        openRow("Pai Northern Thai")
        app.swipeUp(velocity: .slow)
        step("S-04w2 partial")
        XCTAssertTrue(element(containing: "stays yours").waitForExistence(timeout: 6), "S-04w2: $15.00 stays yours")
        // Put the deposit back as it was, so a suite run on one database
        // (run_journeys.py with no journey names) can still find it.
        _ = call("DELETE", "transactions/\(work)/parts")
    }
}
