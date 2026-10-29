import Foundation

/// Talks to the Pearl server (the same one the web app uses).
///
/// Signing in works the way it does in a browser: the server sets a session
/// cookie and a device cookie, and `HTTPCookieStorage.shared` keeps both
/// between launches, so the iPhone stays signed in and stays a device you've
/// confirmed.
final class APIClient {
    static let defaultServer = "https://ledger-six-lac.vercel.app"
    private static let serverKey = "pearl.server"

    /// Where Pearl's server is. Changeable on the sign-in screen, for running
    /// against a copy on your Mac (http://localhost:5050) while developing.
    var baseURL: URL {
        didSet { UserDefaults.standard.set(baseURL.absoluteString, forKey: Self.serverKey) }
    }

    private let session: URLSession
    private let decoder = JSONDecoder()

    init() {
        let saved = UserDefaults.standard.string(forKey: Self.serverKey) ?? Self.defaultServer
        baseURL = URL(string: saved) ?? URL(string: Self.defaultServer)!
        let config = URLSessionConfiguration.default
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.httpCookieAcceptPolicy = .always
        config.httpShouldSetCookies = true
        config.timeoutIntervalForRequest = 30
        config.httpAdditionalHeaders = ["User-Agent": Self.userAgent, "Accept": "application/json"]
        session = URLSession(configuration: config)
    }

    /// "PearlApp/1.0 (iPhone; iOS 17.4)": your other devices see
    /// "Pearl app on iPhone" when this one asks to be approved.
    static var userAgent: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let system = ProcessInfo.processInfo.operatingSystemVersion
        return "PearlApp/\(version) (iPhone; iOS \(system.majorVersion).\(system.minorVersion))"
    }

    // MARK: Requests

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        try await send("GET", path, query: query, body: nil)
    }

    func post<T: Decodable>(_ path: String, _ body: [String: Any] = [:]) async throws -> T {
        try await send("POST", path, query: [:], body: body)
    }

    func put<T: Decodable>(_ path: String, _ body: [String: Any] = [:]) async throws -> T {
        try await send("PUT", path, query: [:], body: body)
    }

    func patch<T: Decodable>(_ path: String, _ body: [String: Any] = [:]) async throws -> T {
        try await send("PATCH", path, query: [:], body: body)
    }

    private func send<T: Decodable>(_ method: String, _ path: String, query: [String: String],
                                    body: [String: Any]?) async throws -> T {
        guard var parts = URLComponents(url: baseURL.appendingPathComponent(path),
                                        resolvingAgainstBaseURL: false) else {
            throw APIError.message("That server address doesn't look right.")
        }
        if !query.isEmpty {
            parts.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = parts.url else { throw APIError.message("That server address doesn't look right.") }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.message("Pearl couldn't reach the server. Check your connection and try again.")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 {
            throw APIError.signedOut
        }
        if !(200..<300).contains(status) {
            let problem = (try? decoder.decode(ServerProblem.self, from: data))?.error
            throw APIError.message(problem ?? "Something went wrong (\(status)). Try again.")
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            #if DEBUG
            print("Pearl: couldn't read \(path): \(error)")
            #endif
            throw APIError.message("Pearl got an answer it couldn't read. Try again.")
        }
    }

    /// Forget the session and the device, as signing out does.
    func clearCookies() {
        let storage = HTTPCookieStorage.shared
        for cookie in storage.cookies(for: baseURL) ?? [] where cookie.name == "session" {
            storage.deleteCookie(cookie)
        }
    }
}

enum APIError: LocalizedError, Equatable {
    case signedOut
    case message(String)

    var errorDescription: String? {
        switch self {
        case .signedOut: return "You've been signed out. Sign in again."
        case .message(let text): return text
        }
    }
}

private struct ServerProblem: Decodable {
    let error: String?
}

/// For calls whose answer we don't need beyond "it worked".
struct OK: Decodable {
    let ok: Bool?
}
