import XCTest

/// Real taps from the app's real root, against a seeded local server. Run with
/// `python3 ios/tools/run_ui_tests.py`, which starts that server.
///
/// A harness that loads the data itself can't catch what these catch: the
/// blank category sheet (2026-11-06) came from how a real screen handed its
/// categories to Quick sort, and tiles drew fine once they arrived.
final class QuickSortCategoryUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-pearl.server", "http://localhost:5051"]
    }

    private func launch() {
        app.launch()
        // N-01 covers Home on a first launch.
        let notNow = app.buttons["Not now"]
        if notNow.waitForExistence(timeout: 4) { notNow.tap() }
    }

    /// Have the test server's proxy refuse the categories, or stop refusing.
    private func categories(_ state: String) {
        var request = URLRequest(url: URL(string: "http://localhost:5051/__test/categories/\(state)")!)
        request.httpMethod = "POST"
        let done = expectation(description: "proxy told")
        URLSession.shared.dataTask(with: request) { _, _, _ in done.fulfill() }.resume()
        wait(for: [done], timeout: 5)
    }

    private func button(startingWith text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", text)).firstMatch
    }

    private func openNeedsALook() {
        app.tabBars.buttons["Cash flow"].tap()
        let link = app.buttons.matching(NSPredicate(format: "label CONTAINS 'a look'")).firstMatch
        XCTAssertTrue(link.waitForExistence(timeout: 15), "Cash flow has no Needs a look link")
        link.tap()
    }

    private func assertTheCategoriesShow(_ context: String) {
        XCTAssertTrue(app.buttons["Groceries"].waitForExistence(timeout: 10),
                      "No category tiles on the sheet \(context)")
    }

    /// Needs a look → the Quick sort card → Let me choose → the category.
    func testTheCategoriesShowFromTheQuickSortCard() {
        launch()
        openNeedsALook()
        let card = button(startingWith: "Quick sort")
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Needs a look has no Quick sort card")
        // A person reads the list first: everything has loaded and the screen
        // has settled by the time they tap. The blank sheet needed that.
        sleep(5)
        card.tap()
        let choose = app.buttons["Let me choose"]
        XCTAssertTrue(choose.waitForExistence(timeout: 15), "Quick sort has no Let me choose")
        choose.tap()
        let category = button(startingWith: "Dining")
        XCTAssertTrue(category.waitForExistence(timeout: 15), "T-96 has no category row")
        category.tap()
        assertTheCategoriesShow("opened from the Quick sort card")
    }

    /// Let me choose → another category comes back to the deck, on the next card.
    func testAnsweringStaysInQuickSort() {
        launch()
        openNeedsALook()
        let card = button(startingWith: "Quick sort")
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Needs a look has no Quick sort card")
        sleep(3)
        card.tap()
        let choose = app.buttons["Let me choose"]
        XCTAssertTrue(choose.waitForExistence(timeout: 15), "Quick sort has no Let me choose")
        choose.tap()
        let category = button(startingWith: "Dining")
        XCTAssertTrue(category.waitForExistence(timeout: 15), "T-96 has no category row")
        category.tap()
        assertTheCategoriesShow("opened from the Quick sort card")
        // A tile answers at once: there is no Save.
        app.buttons["Groceries"].tap()
        let tapped = Date()
        // Stays in Quick sort: the header, and an answer on the next card, for a while.
        sleep(4)
        XCTAssertTrue(app.staticTexts["Quick sort"].waitForExistence(timeout: 10),
                      "The answer left Quick sort (\(Date().timeIntervalSince(tapped))s after tapping)")
        XCTAssertTrue(app.buttons["Let me choose"].exists, "No card to answer after the tile")
        XCTAssertTrue(app.buttons["Undo"].exists, "No Undo after the tile")
    }

    /// The same from Home's card, a different parent to Needs a look.
    func testTheCategoriesShowFromHome() {
        launch()
        let link = app.buttons["Review one by one"]
        XCTAssertTrue(link.waitForExistence(timeout: 15), "Home has no Needs a look card")
        link.tap()
        let card = button(startingWith: "Quick sort")
        XCTAssertTrue(card.waitForExistence(timeout: 15), "Needs a look has no Quick sort card")
        sleep(5)
        card.tap()
        let choose = app.buttons["Let me choose"]
        XCTAssertTrue(choose.waitForExistence(timeout: 15), "Quick sort has no Let me choose")
        choose.tap()
        let category = button(startingWith: "Dining")
        XCTAssertTrue(category.waitForExistence(timeout: 15), "T-96 has no category row")
        category.tap()
        assertTheCategoriesShow("opened from Home")
    }

    /// Needs a look → a row → the category: the same page, reached the other way.
    func testTheCategoriesShowFromARow() {
        launch()
        openNeedsALook()
        let row = button(startingWith: "Uber Eats")
        XCTAssertTrue(row.waitForExistence(timeout: 15), "Needs a look has no Uber Eats row")
        row.tap()
        let category = button(startingWith: "Dining")
        XCTAssertTrue(category.waitForExistence(timeout: 15), "T-96 has no category row")
        category.tap()
        assertTheCategoriesShow("opened from a row")
    }

    /// The categories can't load: the sheet says so, and Try again brings the tiles.
    func testTheSheetOffersTryAgainWhenTheCategoriesFail() {
        categories("fail")
        addTeardownBlock { [self] in categories("ok") }
        launch()
        openNeedsALook()
        let row = button(startingWith: "Uber Eats")
        XCTAssertTrue(row.waitForExistence(timeout: 15), "Needs a look has no Uber Eats row")
        row.tap()
        let category = button(startingWith: "Dining")
        XCTAssertTrue(category.waitForExistence(timeout: 15), "T-96 has no category row")
        category.tap()
        let again = app.buttons["Try again"]
        XCTAssertTrue(again.waitForExistence(timeout: 10), "The sheet doesn't offer Try again")
        categories("ok")
        again.tap()
        assertTheCategoriesShow("after Try again")
    }
}
