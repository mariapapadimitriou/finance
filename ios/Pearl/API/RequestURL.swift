import Foundation

/// Builds a request's URL from the server address, a path and its query.
///
/// This is the only place a path is percent-encoded (TEST-33). Callers pass
/// ids as they are, "2026-10-28:2026-10-30" or "PG&E Electric", never already
/// encoded: encoding them first sent "%253A" and the server answered 404.
/// tests/test_request_url.py checks it with swiftc.
enum RequestURL {
    static func make(base: URL, path: String, query: [String: String] = [:]) -> URL? {
        guard var parts = URLComponents(url: base.appendingPathComponent(path),
                                        resolvingAgainstBaseURL: false) else { return nil }
        if !query.isEmpty {
            parts.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
            // The server reads "+" as a space; a search for "+5850" keeps it.
            parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        return parts.url
    }
}
