import XCTest

/// engBOT's checks of the consolidation follow-ups (CONSOLIDATE-01): Cash
/// flow by day (T-01r), Quick sort's "Other?" with Yes and Skip (T-93o),
/// split cards with the bar only (1284:230, S-44b–i) and the Transactions ·
/// Calendar switch in dark (TEST-32). Real taps against the demo ledger. Run
/// with `python3 ios/tools/run_journeys.py --suite PearlUITests/ConsolidationUITests …`.
final class ConsolidationUITests: XCTestCase {
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

    // MARK: T-01r · Cash flow by day

    /// T-01r (1074:356): under Newest, a header per day ("TODAY",
    /// "YESTERDAY", "WED, NOV 12") over that day's card; Select on the first
    /// header; nothing else on the right; no day on the rows.
    func testCashFlowIsGroupedByDay() {
        launch()
        openCashFlow()
        let headers = app.staticTexts.matching(NSPredicate(format: "identifier == 'day-header' OR label == 'TODAY' OR label == 'YESTERDAY'"))
        XCTAssertTrue(headers.firstMatch.waitForExistence(timeout: 10), "No day header on Cash flow")
        app.swipeUp(velocity: .slow)
        step("T-01r day headers")
        let labels = app.staticTexts.allElementsBoundByIndex.map(\.label)
        let days = labels.filter { $0 == "TODAY" || $0 == "YESTERDAY"
            || $0.range(of: "^[A-Z]{3}, [A-Z]{3} \\d{1,2}$", options: .regularExpression) != nil }
        note("day headers: \(days)")
        XCTAssertGreaterThan(days.count, 1, "T-01r: expected more than one day header")
        XCTAssertEqual(Set(days).count, days.count, "T-01r: a day should have one card, under one header")
        app.swipeDown(velocity: .fast)
        app.swipeDown(velocity: .fast)
        XCTAssertTrue(app.buttons["Select"].waitForExistence(timeout: 4), "T-01r: Select belongs on the first day header")
        XCTAssertFalse(element(containing: " transactions").exists, "T-01r: the day header replaces “n transactions”")
        // The rows under a day header don't repeat the day.
        let yesterday = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'Corner Store'")).firstMatch
        if yesterday.waitForExistence(timeout: 4) {
            note("Corner Store row: \(yesterday.label)")
            XCTAssertFalse(yesterday.label.contains("Yesterday"), "T-01r: the row repeats the day: \(yesterday.label)")
        }
        // T-01r dark (1074:497).
        launch("dark")
        openCashFlow()
        app.swipeUp(velocity: .slow)
        step("T-01r dark day headers")
    }

    // MARK: TEST-32 · the switch in dark

    /// TEST-32: the chosen segment of Transactions · Calendar is
    /// color/surface/card, #151B44 in dark, not white under white words.
    func testTheSwitchReadsInDark() {
        for scheme in ["dark", "light"] {
            launch(scheme)
            openCashFlow()
            let on = app.buttons["Transactions"]
            XCTAssertTrue(on.waitForExistence(timeout: 8), "No Transactions segment")
            step("TEST-32 switch \(scheme)")
            // Sample just inside the pill's left end, clear of the word.
            let f = on.frame
            let c = colour(at: CGPoint(x: f.minX + 14, y: f.midY))
            let light = (c.0 + c.1 + c.2) / 3
            note("TEST-32 \(scheme) pill colour \(c)")
            if scheme == "dark" {
                XCTAssertLessThan(light, 110, "TEST-32: the chosen segment is still light in dark: \(c)")
            } else {
                XCTAssertGreaterThan(light, 200, "The chosen segment should be white in light: \(c)")
            }
        }
    }

    // MARK: T-93o · Quick sort "Other?"

    /// T-93o (1284:103): Pearl's best guess of Other is a card like any
    /// other: PEARL’S GUESS, “Other?”, Skip and Yes. Yes sorts this one as
    /// Other and saves no rule.
    func testQuickSortOtherIsYesOrSkip() {
        launch()
        tap(app.buttons["See the list"], "See the list")
        tap(button("Quick sort"), "Quick sort card")
        var n = 0
        while !element(containing: "Other?").exists && n < 8 {
            tap(app.buttons["Skip"], "Skip"); sleep(1); n += 1
        }
        XCTAssertTrue(element(containing: "Other?").exists, "T-93o: no card reads “Other?”")
        step("T-93o other card")
        XCTAssertTrue(element(containing: "PEARL’S GUESS").exists, "T-93o: Other is Pearl’s guess")
        XCTAssertFalse(element(containing: "What was this?").exists, "T-93o: the card no longer asks")
        XCTAssertTrue(app.buttons["Yes"].exists, "T-93o: Yes")
        XCTAssertTrue(app.buttons["Skip"].exists, "T-93o: Skip")
        XCTAssertFalse(app.buttons["Answer"].exists, "T-93o: no Answer")
        XCTAssertTrue(element(containing: "Yes sorts this one as Other").exists, "T-93o: the line above the buttons")
        let card = app.descendants(matching: .any)["quick-sort-card"]
        let merchant = ["Corner Store", "Makersmkt", "Northshop", "City Parking", "Lucky Noodle", "Bright Dental"]
            .first { card.label.localizedCaseInsensitiveContains($0) } ?? ""
        note("Other card: \(card.label)")
        tap(app.buttons["Yes"], "Yes")
        sleep(3)
        step("T-93o after Yes")
        guard !merchant.isEmpty, let row = rows(merchant).first else { XCTFail("Couldn't find the Other card's row"); return }
        note("after Yes: \(row["category"] ?? "-") suggested=\(row["suggested"] ?? "-") rule=\(row["rule"] ?? "-")")
        XCTAssertEqual(row["category"] as? String, "Other", "T-93o: Yes sorts it as Other")
        XCTAssertEqual(row["suggested"] as? Bool, false, "T-93o: no longer a guess")
        XCTAssertEqual((row["rule"] as? [String: Any])?["has_rule"] as? Bool, false,
                       "T-93o: Yes on Other saves no always rule")
    }

    /// T-93o in dark, and Skip leaves the card in Needs a look.
    func testQuickSortOtherSkipInDark() {
        launch("dark")
        tap(app.buttons["See the list"], "See the list")
        tap(button("Quick sort"), "Quick sort card")
        var n = 0
        while !element(containing: "Other?").exists && n < 8 {
            tap(app.buttons["Skip"], "Skip"); sleep(1); n += 1
        }
        XCTAssertTrue(element(containing: "Other?").exists, "T-93o: no card reads “Other?”")
        step("T-93o other card dark")
        tap(app.buttons["Skip"], "Skip")
        sleep(2)
        let review = call("GET", "review") as? [String: Any]
        let open = (review?["unsure_category"] as? [[String: Any]])?.compactMap { ($0["txn"] as? [String: Any])?["merchant"] as? String } ?? []
        note("still in Needs a look: \(open)")
        XCTAssertTrue(open.contains { $0.localizedCaseInsensitiveContains("Corner Store") },
                      "T-93o: Skip leaves the Other card in Needs a look")
    }

    // MARK: Bar only (1284:230, S-44b–i)

    /// A paid-back person's row shows "✓ Paid back · <day>" and the bar, and no
    /// longer "$40.00 · paid back Pizza Nova and Bar Isabel" under it.
    func testSplitCardsShowOnlyTheBar() {
        launch()
        guard let pizza = rows("Pizza Nova").first?["id"] as? String,
              let bar = rows("Bar Isabel").first?["id"] as? String,
              let priya = rows("Priya").first(where: { abs(($0["amount"] as? Double) ?? 0) == 40 })?["id"] as? String
        else { XCTFail("Couldn't find Pizza Nova, Bar Isabel and Priya's $40.00"); return }
        // Priya owes $20.00 on each, and one $40.00 e-Transfer pays both back.
        for (id, total) in [(pizza, 120.0), (bar, 100.0)] {
            _ = call("PUT", "transactions/\(id)/split",
                     ["mode": "amount", "include_me": true, "people": [["name": "Priya", "amount": 20]], "you": total - 20])
            let r = call("POST", "transactions/\(id)/paybacks/\(priya)", ["person": "Priya", "amount": 20]) as? [String: Any]
            note("payback on \(id): \(r?["toast"] ?? r?["error"] ?? "-")")
        }
        openCashFlow()
        let search = app.textFields.matching(NSPredicate(format: "placeholderValue == 'Search'")).firstMatch
        if search.waitForExistence(timeout: 4) { search.tap(); search.typeText("Pizza Nova"); sleep(2) }
        tap(button("Pizza Nova"), "the Pizza Nova row")
        sleep(2)
        app.swipeUp(velocity: .slow)
        step("bar only Pizza Nova")
        XCTAssertTrue(element(containing: "✓ Paid back").waitForExistence(timeout: 6), "No ✓ Paid back on Priya's row")
        XCTAssertFalse(element(containing: "paid back Pizza Nova").exists, "Bar only: the payment line is still there")
        XCTAssertFalse(element(containing: "paid back Bar Isabel").exists, "Bar only: the payment line is still there")
        XCTAssertFalse(element(containing: "still cash").exists)
    }
}
