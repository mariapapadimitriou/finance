// Prints the URL RequestURL.make builds for each path given on the command
// line, one per line (tests/test_request_url.py compiles the two together and
// checks them, TEST-33). 2026-11-19.
import Foundation

let base = URL(string: "http://127.0.0.1:5001")!
for path in CommandLine.arguments.dropFirst() {
    guard let url = RequestURL.make(base: base, path: path) else {
        print("NIL")
        continue
    }
    print(url.absoluteString)
}
