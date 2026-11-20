import Foundation

/// Writes that are safe to send twice (perf rehaul, 2026-11-19).
///
/// Every edit a screen shows before the server has it goes through here.
/// Each gets an op id and the ledger version the phone had (`X-Op-Id`,
/// `X-Base-Version`, finance/changed.py): the server answers a repeat of
/// the same id from its first attempt and does nothing twice, so a retry
/// is always safe. An edit that can't reach the server stays queued, in a
/// file under the account's protected cache folder, with what she sees
/// already changed; the queue is sent again in order when Pearl comes back
/// to the front or the next read gets through. `409 {"retry": true}` means
/// the first attempt is still running: the same op goes again in 2 s. A
/// refusal (`400 {"error": …}`) drops the edit; the screen that sent it
/// puts things back and says why, or the app's toast does if that screen
/// has gone.
@MainActor
final class Outbox {
    /// One write, as it will be sent.
    struct Op: Codable, Identifiable {
        let id: String
        let seq: Int
        let method: String
        let path: String
        let query: [String: String]
        let body: Data?
        let baseVersion: Int?
        let madeAt: Date
    }

    /// A write's answer: its own fields, and what it changed.
    struct Sent<T> {
        let body: T
        let changed: Changed?
        /// The server had already done this op (a retry landed twice).
        let replayed: Bool
    }

    private let api: APIClient
    weak var app: AppModel?
    /// Writes waiting for the network, oldest first.
    private(set) var queue: [Op] = []
    /// What to put back on screen if a queued write is refused, while the
    /// screen that sent it is still around.
    private var rollbacks: [String: () -> Void] = [:]
    private var replaying = false
    private var seq = 0
    private var directory: URL?
    private let io = DispatchQueue(label: "pearl.outbox", qos: .userInitiated)

    init(api: APIClient) {
        self.api = api
    }

    var isEmpty: Bool { queue.isEmpty }

    /// Where this account's queue lives (ScreenStore's folder, `outbox/`);
    /// ops left from the last launch are read back in.
    func use(directory: URL) {
        let dir = directory.appendingPathComponent("outbox", isDirectory: true)
        guard dir != self.directory else { return }
        self.directory = dir
        queue = []
        rollbacks = [:]
        Task {
            let ops: [Op] = await withCheckedContinuation { done in
                io.async {
                    let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
                    let decoder = JSONDecoder()
                    let ops = names.compactMap { name -> Op? in
                        guard let data = try? Data(contentsOf: dir.appendingPathComponent(name)) else { return nil }
                        return try? decoder.decode(Op.self, from: data)
                    }
                    done.resume(returning: ops.sorted { $0.seq < $1.seq })
                }
            }
            guard dir == self.directory else { return }
            queue = ops + queue
            seq = max(seq, (ops.map(\.seq).max() ?? 0) + 1)
            if !queue.isEmpty { await replay() }
        }
    }

    /// The queue forgotten (signing out, Start over): nothing of hers is sent later.
    func clear() {
        queue = []
        rollbacks = [:]
        if let dir = directory { io.async { try? FileManager.default.removeItem(at: dir) } }
    }

    // MARK: Sending

    /// Sends a write, or queues it when the server can't be reached: nil
    /// then, and the screen keeps showing the change. Any other failure
    /// throws, and the screen puts things back.
    func send<T: Decodable>(_ method: String, _ path: String, query: [String: String] = [:],
                            _ body: [String: Any]? = nil, rollback: (() -> Void)? = nil) async throws -> Sent<T>? {
        seq += 1
        let op = Op(id: UUID().uuidString, seq: seq, method: method, path: path, query: query,
                    body: try JSONBody.data(body), baseVersion: app?.ledgerVersion, madeAt: Date())
        keep(op)
        // Earlier edits go first, so the server sees them in her order.
        if !queue.isEmpty { await replay() }
        if !queue.isEmpty {
            enqueue(op, rollback: rollback)
            return nil
        }
        do {
            let reply = try await perform(op)
            drop(op)
            return try read(reply, path: path)
        } catch let error as APIError where error == .offline {
            enqueue(op, rollback: rollback)
            return nil
        } catch {
            drop(op)
            throw error
        }
    }

    private func read<T: Decodable>(_ reply: APIClient.Reply, path: String) throws -> Sent<T> {
        let body: T = try api.decode(reply.data, path: path)
        let changed = (try? api.decode(reply.data, path: path) as ChangedOnly)?.changed
        return Sent(body: body, changed: changed, replayed: reply.replayed)
    }

    /// The request itself, with the op's headers; a 409 "still running"
    /// is tried again in 2 s, a few times.
    private func perform(_ op: Op) async throws -> APIClient.Reply {
        var tries = 0
        while true {
            tries += 1
            do {
                return try await api.request(op.method, op.path, query: op.query, body: op.body,
                                             headers: APIClient.writeHeaders(opId: op.id, baseVersion: op.baseVersion))
            } catch let error as APIError {
                guard error.problem?.retry == true, tries < 6 else { throw error }
                try await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }

    private func enqueue(_ op: Op, rollback: (() -> Void)?) {
        queue.append(op)
        if let rollback = rollback { rollbacks[op.id] = rollback }
    }

    /// Sends what's waiting, in order, with the same op ids. Stops at the
    /// first that can't reach the server. Once anything went through, every
    /// screen checks its answer again (an ETag each, 304 when nothing
    /// relevant changed).
    func replay() async {
        guard !replaying, !queue.isEmpty else { return }
        replaying = true
        defer { replaying = false }
        var went = false
        while let op = queue.first {
            do {
                let reply = try await perform(op)
                queue.removeFirst()
                rollbacks[op.id] = nil
                drop(op)
                went = true
                if let changed = (try? api.decode(reply.data, path: op.path) as ChangedOnly)?.changed {
                    app?.apply(changed, by: nil, bump: false)
                }
            } catch let error as APIError where error == .offline {
                break
            } catch {
                // Refused, or signed out: this edit isn't happening.
                queue.removeFirst()
                drop(op)
                rollbacks.removeValue(forKey: op.id)?()
                if let words = app?.handle(error) { app?.say(words) }
            }
        }
        if went { app?.changed() }
    }

    // MARK: Files

    private func keep(_ op: Op) {
        guard let dir = directory else { return }
        io.async {
            do {
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true,
                                                        attributes: [.protectionKey: FileProtectionType.complete])
                try JSONEncoder().encode(op).write(to: dir.appendingPathComponent(Self.name(op)),
                                                   options: [.atomic, .completeFileProtection])
            } catch {
                // Not kept across a relaunch; it's still sent now.
            }
        }
    }

    private func drop(_ op: Op) {
        guard let dir = directory else { return }
        io.async { try? FileManager.default.removeItem(at: dir.appendingPathComponent(Self.name(op))) }
    }

    private static func name(_ op: Op) -> String { String(format: "%08d-", op.seq) + op.id + ".json" }
}
