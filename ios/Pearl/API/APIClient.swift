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

    /// Every ETag a read came back with (perf rehaul, 2026-11-19): the
    /// ledger's version is in it, and AppModel keeps the latest for the
    /// outbox's `X-Base-Version`. Called off the main thread.
    var sawETag: ((String) -> Void)?

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        try await send("GET", path, query: query, body: nil)
    }

    /// A read the screen already has an answer to (ScreenStore): with the
    /// answer's ETag as `If-None-Match`, the server says `304` after one
    /// statement when nothing changed, and nothing is decoded or redrawn.
    func get<T: Decodable>(_ path: String, query: [String: String] = [:],
                           ifNoneMatch: String?) async throws -> Cached<T> {
        guard let raw = try await getRaw(path, query: query, ifNoneMatch: ifNoneMatch) else { return .unchanged }
        return .fresh(try decode(raw.data, path: path), etag: raw.etag)
    }

    /// The bytes of a read, with its ETag, for the on-device cache to keep;
    /// nil when the server said `304 Not Modified`.
    func getRaw(_ path: String, query: [String: String] = [:], ifNoneMatch: String?) async throws -> RawReply? {
        var headers: [String: String] = [:]
        if let tag = ifNoneMatch, !tag.isEmpty { headers["If-None-Match"] = tag }
        let reply = try await request("GET", path, query: query, body: nil, headers: headers)
        if reply.status == 304 { return nil }
        return RawReply(data: reply.data, etag: reply.etag)
    }

    func post<T: Decodable>(_ path: String, _ body: [String: Any] = [:],
                            opId: String? = nil, baseVersion: Int? = nil) async throws -> T {
        try await send("POST", path, query: [:], body: body, opId: opId, baseVersion: baseVersion)
    }

    func put<T: Decodable>(_ path: String, _ body: [String: Any] = [:],
                           opId: String? = nil, baseVersion: Int? = nil) async throws -> T {
        try await send("PUT", path, query: [:], body: body, opId: opId, baseVersion: baseVersion)
    }

    func patch<T: Decodable>(_ path: String, _ body: [String: Any] = [:],
                             opId: String? = nil, baseVersion: Int? = nil) async throws -> T {
        try await send("PATCH", path, query: [:], body: body, opId: opId, baseVersion: baseVersion)
    }

    func delete<T: Decodable>(_ path: String, query: [String: String] = [:],
                              opId: String? = nil, baseVersion: Int? = nil) async throws -> T {
        try await send("DELETE", path, query: query, body: nil, opId: opId, baseVersion: baseVersion)
    }

    /// A file's bytes rather than an answer to read (Your data's .zip).
    func download(_ path: String) async throws -> Data {
        try await request("GET", path, query: [:], body: nil, headers: [:]).data
    }

    /// What a request came back with, before it's read.
    struct Reply {
        let data: Data
        let status: Int
        let etag: String?
        /// `X-Replayed: 1`: the server had already done this op (Outbox).
        let replayed: Bool
    }

    struct RawReply {
        let data: Data
        let etag: String?
    }

    /// Headers the outbox puts on a write (finance/changed.py): the op's id,
    /// so a repeat is answered from the first attempt and done once, and the
    /// ledger version the phone had.
    static func writeHeaders(opId: String?, baseVersion: Int?) -> [String: String] {
        var h: [String: String] = [:]
        if let id = opId { h["X-Op-Id"] = id }
        if let v = baseVersion { h["X-Base-Version"] = String(v) }
        return h
    }

    private func send<T: Decodable>(_ method: String, _ path: String, query: [String: String],
                                    body: [String: Any]?, opId: String? = nil, baseVersion: Int? = nil) async throws -> T {
        let data = try JSONBody.data(body)
        let reply = try await request(method, path, query: query, body: data,
                                      headers: Self.writeHeaders(opId: opId, baseVersion: baseVersion))
        return try decode(reply.data, path: path)
    }

    /// An answer's JSON as `T`; a reply that can't be read says so once.
    func decode<T: Decodable>(_ data: Data, path: String) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            #if DEBUG
            print("Pearl: couldn't read \(path): \(error)")
            #endif
            throw APIError.message("Pearl got an answer it couldn't read. Try again.")
        }
    }

    /// One request, with the answer's status and headers: everything above
    /// and the outbox go through here. Throws for anything but 2xx and 304.
    func request(_ method: String, _ path: String, query: [String: String],
                 body: Data?, headers: [String: String]) async throws -> Reply {
        // Paths come in plain; RequestURL encodes them once (TEST-33).
        guard let url = RequestURL.make(base: baseURL, path: path, query: query) else {
            throw APIError.message("That server address doesn't look right.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
        let data: Data
        let response: URLResponse
        #if DEBUG
        let began = Date()
        var timed: HTTPURLResponse?
        defer {
            // Server-Timing says what the server spent (finance/timing.py);
            // the difference from the wall time is the network and the phone.
            let ms = Int(Date().timeIntervalSince(began) * 1000)
            let server = timed?.value(forHTTPHeaderField: "Server-Timing") ?? "-"
            print("Pearl: \(method) \(path) \(timed?.statusCode ?? 0) \(ms) ms wall; server \(server)")
        }
        #endif
        do {
            (data, response) = try await session.data(for: request)
            #if DEBUG
            timed = response as? HTTPURLResponse
            #endif
        } catch {
            // A screen that reloaded or went away cancels its request: not a
            // connection problem, so it isn't reported as one.
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                throw CancellationError()
            }
            throw APIError.offline
        }
        let http = response as? HTTPURLResponse
        let status = http?.statusCode ?? 0
        let etag = http?.value(forHTTPHeaderField: "ETag")
        if let etag = etag { sawETag?(etag) }
        if status == 401 {
            // Signing in with a wrong password is a 401 too: say what the
            // server said rather than "signed out".
            if path.hasPrefix("api/auth/") {
                if let problem = try? decoder.decode(ServerProblem.self, from: data), problem.error != nil {
                    throw APIError.server(problem)
                }
                throw APIError.message("That didn't work. Try again.")
            }
            throw APIError.signedOut
        }
        if status != 304 && !(200..<300).contains(status) {
            if let problem = try? decoder.decode(ServerProblem.self, from: data),
               problem.error != nil || problem.needsConfirmation == true || problem.retry == true {
                throw APIError.server(problem)
            }
            throw APIError.message("Something went wrong (\(status)). Try again.")
        }
        return Reply(data: data, status: status, etag: etag,
                     replayed: http?.value(forHTTPHeaderField: "X-Replayed") == "1")
    }

    /// A non-2xx answer to a streamed request, before any line came.
    struct StreamRefused: Error {
        let status: Int
        let problem: ServerProblem?
    }

    /// A streamed answer, one line at a time (Ask Pearl, THL-308: POST
    /// /api/ask answers in application/x-ndjson). No connection, before or
    /// part way through, is `APIError.offline`; 401 is `.signedOut`; any
    /// other refusal is `StreamRefused` with the server's words.
    func lines(_ path: String, _ body: [String: Any]) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = RequestURL.make(base: baseURL, path: path, query: [:]) else {
                        throw APIError.message("That server address doesn't look right.")
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("application/x-ndjson", forHTTPHeaderField: "Accept")
                    request.httpBody = try JSONBody.data(body)
                    request.timeoutInterval = 60
                    let bytes: URLSession.AsyncBytes
                    let response: URLResponse
                    do {
                        (bytes, response) = try await session.bytes(for: request)
                    } catch {
                        if error is CancellationError || (error as? URLError)?.code == .cancelled {
                            throw CancellationError()
                        }
                        throw APIError.offline
                    }
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    if status == 401 { throw APIError.signedOut }
                    if !(200..<300).contains(status) {
                        var data = Data()
                        for try await byte in bytes { data.append(byte) }
                        throw StreamRefused(status: status, problem: try? decoder.decode(ServerProblem.self, from: data))
                    }
                    do {
                        for try await line in bytes.lines { continuation.yield(line) }
                    } catch let error as URLError where error.code != .cancelled {
                        throw APIError.offline
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
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
    case offline
    case message(String)
    /// What the server said went wrong, with its flags (a wrong code, a pause…).
    case server(ServerProblem)

    var errorDescription: String? {
        switch self {
        case .signedOut: return "You've been signed out. Sign in again."
        case .offline: return "Pearl couldn't reach the server. Check your connection and try again."
        case .message(let text): return text
        case .server(let problem): return problem.error
        }
    }

    var problem: ServerProblem? {
        if case .server(let problem) = self { return problem }
        return nil
    }
}

/// An error reply: the words, and what kind of problem it was.
struct ServerProblem: Decodable, Equatable {
    let error: String?
    var taken: Bool? = nil
    var weak: Bool? = nil
    var wrong: Bool? = nil
    var left: Int? = nil
    var paused: Bool? = nil
    var retryIn: Int? = nil
    var expired: Bool? = nil
    /// Adding by hand (T-23): something like it is already there.
    var needsConfirmation: Bool? = nil
    var duplicate: Bool? = nil
    var matches: [Match]? = nil
    /// 409 from the outbox's op id: the first attempt is still running;
    /// send the same op again in 2 s (finance/changed.py `claim`).
    var retry: Bool? = nil
    /// A payback onto a split she set up, from a sender Pearl can't place on
    /// it (409, finance/marks_api.py `_who_paid`): ask who with PP-01.
    var whoPaid: WhoPaidAsk? = nil

    struct Match: Decodable, Equatable, Identifiable {
        let id: String
        let date: String
        let merchant: String
        let amount: Double
    }

    enum CodingKeys: String, CodingKey {
        case error, taken, weak, wrong, left, paused, expired, duplicate, matches, retry
        case retryIn = "retry_in"
        case whoPaid = "who_paid"
        case needsConfirmation = "needs_confirmation"
    }
}

/// "Who paid you back?" for a payback onto a split she set up (2026-11-16,
/// "it adds another person instead of crediting the friend on it"): the
/// sender ("PAPAS A") couldn't be placed on the split and more than one
/// person could have sent it. Nothing was saved. PP-01 (`WhoPaidPicker`)
/// lists only `people`; her tap sends the payback again as that person.
struct WhoPaidAsk: Decodable, Equatable, Identifiable {
    let charge: String
    let merchant: String
    let sender: String
    let amount: Double
    /// The money in it's from (the pair card's row too), and its day for
    /// PB-30's header.
    let deposit: String?
    var date: String? = nil
    let people: [Person]

    struct Person: Decodable, Equatable {
        let name: String
        /// Nil on a Not sure yet split.
        let owes: Double?
    }

    var id: String { charge + "|" + sender }

    /// The same payback, from `name` on the split, with PQ-03c's toast.
    func answer(_ name: String) -> ReviewAnswer? {
        guard let deposit = deposit else { return nil }
        return .payback(deposit, charge: charge,
                        toast: "\(name) paid back \(Format.amount(amount)) for \(merchant)", person: name)
    }
}

extension Error {
    /// The server's problem behind an error, if there was one.
    var serverProblem: ServerProblem? { (self as? APIError)?.problem }
    /// A payback the server wants to know who sent (`WhoPaidAsk`).
    var whoPaid: WhoPaidAsk? { serverProblem?.whoPaid }
}

/// For calls whose answer we don't need beyond "it worked".
struct OK: Decodable {
    let ok: Bool?
}

/// A conditional read's answer (perf rehaul, 2026-11-19).
enum Cached<T> {
    case fresh(T, etag: String?)
    /// `304 Not Modified`: what the screen shows is still right.
    case unchanged
}

/// A request body as bytes, once, so the outbox can keep it for a retry.
enum JSONBody {
    static func data(_ body: [String: Any]?) throws -> Data? {
        guard let body = body else { return nil }
        return try JSONSerialization.data(withJSONObject: body)
    }
}
