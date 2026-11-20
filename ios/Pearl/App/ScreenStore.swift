import CryptoKit
import Foundation
import SwiftUI

/// The last answer to every read a screen makes, kept on the iPhone
/// (perf rehaul, 2026-11-19).
///
/// A screen shows its last answer the moment it appears, then asks the
/// server with the answer's ETag (`If-None-Match`). When nothing changed
/// the server says `304` after one statement and the screen keeps what it
/// shows; when something did, the new answer eases in. Offline, the last
/// answer stays and nothing is said about it unless there's none at all.
///
/// Answers are kept as the server's own bytes (`Transaction` and the rest
/// only decode), under Application Support/PearlCache/<account>/, each
/// file protected until the iPhone is unlocked (`.completeFileProtection`).
/// Another account never sees a previous one's answers: its folder is its
/// own, and signing out, deleting the account and Start over remove it.
/// A missing or unreadable file only means "nothing kept yet".
@MainActor
final class ScreenStore {
    private let api: APIClient
    private(set) var account = "owner"
    /// What's been read this launch, decoded, by key.
    private var memory: [String: Entry] = [:]
    /// Keys looked for on disk and not found, so they aren't looked for twice.
    private var missing: Set<String> = []
    /// Reads and writes of the files, off the main thread, in order.
    private let io = DispatchQueue(label: "pearl.screens", qos: .userInitiated)

    private struct Entry {
        let value: Any
        let etag: String?
        let savedAt: Date
    }

    private struct Meta: Codable {
        let key: String
        let etag: String?
        let savedAt: Date
    }

    init(api: APIClient) {
        self.api = api
    }

    // MARK: Where

    static var root: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("PearlCache", isDirectory: true)
    }

    var directory: URL { Self.root.appendingPathComponent(account, isDirectory: true) }

    /// Whose answers these are: the signed-in account's id, or "owner"
    /// before one is known. Changing it forgets what's in memory.
    func use(account id: String?) {
        let next = id.flatMap { $0.isEmpty ? nil : $0 } ?? "owner"
        guard next != account else { return }
        account = next
        memory = [:]
        missing = []
    }

    /// Everything kept for this account, gone (signing out, Start over).
    func clear() {
        memory = [:]
        missing = []
        let dir = directory
        io.async { try? FileManager.default.removeItem(at: dir) }
    }

    /// One answer forgotten: the next appear asks for it afresh.
    func forget(_ path: String, query: [String: String] = [:]) {
        let key = Self.key(path, query)
        memory[key] = nil
        missing.insert(key)
        let dir = directory
        io.async {
            for name in Self.names(for: key) { try? FileManager.default.removeItem(at: dir.appendingPathComponent(name)) }
        }
    }

    // MARK: Reading

    /// The last answer, from memory or the files, without asking the server.
    func cached<T: Decodable>(_ type: T.Type, _ path: String, query: [String: String] = [:]) async -> T? {
        let key = Self.key(path, query)
        if let entry = memory[key] { return entry.value as? T }
        if missing.contains(key) { return nil }
        let dir = directory
        let api = self.api
        let found: (T, Meta)? = await withCheckedContinuation { done in
            io.async {
                let names = Self.names(for: key)
                guard let data = try? Data(contentsOf: dir.appendingPathComponent(names[0])),
                      let metaData = try? Data(contentsOf: dir.appendingPathComponent(names[1])),
                      let meta = try? Self.reader.decode(Meta.self, from: metaData), meta.key == key,
                      let value: T = try? api.decode(data, path: path) else {
                    done.resume(returning: nil)
                    return
                }
                done.resume(returning: (value, meta))
            }
        }
        // The account may have changed while the file was read.
        guard dir == directory else { return nil }
        guard let (value, meta) = found else {
            missing.insert(key)
            return nil
        }
        if memory[key] == nil { memory[key] = Entry(value: value, etag: meta.etag, savedAt: meta.savedAt) }
        return value
    }

    /// Asks the server, with the last answer's ETag. `fresh` is false when
    /// it said `304` and `value` is the answer already shown.
    func fetch<T: Decodable>(_ type: T.Type, _ path: String, query: [String: String] = [:]) async throws -> (value: T, fresh: Bool) {
        let key = Self.key(path, query)
        let have: T? = await cached(type, path, query: query)
        let etag = have == nil ? nil : memory[key]?.etag
        guard let raw = try await api.getRaw(path, query: query, ifNoneMatch: etag) else {
            guard let have = have else { throw APIError.message("Pearl got an answer it couldn't read. Try again.") }
            return (have, false)
        }
        let api = self.api
        let value: T = try await Task.detached(priority: .userInitiated) { try api.decode(raw.data, path: path) }.value
        try Task.checkCancellation()
        save(key: key, data: raw.data, etag: raw.etag, value: value)
        return (value, true)
    }

    /// A screen's load: the last answer shown at once, the server asked
    /// with its ETag, a changed answer eased in. Offline with a last answer
    /// keeps it quietly; offline with none throws, as the plain GET did. A
    /// cancelled load (the screen went away) does nothing. Returns whether
    /// anything was shown. `fresh` runs only for the server's own answer,
    /// after `apply`, for what mustn't be set back from a kept one.
    @discardableResult
    func load<T: Decodable>(_ path: String, query: [String: String] = [:], as type: T.Type,
                            apply: @escaping @MainActor (T) -> Void,
                            fresh: (@MainActor (T) -> Void)? = nil) async throws -> Bool {
        let have: T? = await cached(type, path, query: query)
        if let have = have {
            // SwiftUI's Transaction, not Pearl's: shown without animation.
            var quiet = SwiftUI.Transaction()
            quiet.disablesAnimations = true
            withTransaction(quiet) { apply(have) }
        }
        do {
            let (value, isFresh) = try await fetch(type, path, query: query)
            if isFresh {
                withAnimation(.easeInOut(duration: 0.2)) { apply(value) }
                fresh?(value)
            }
            return true
        } catch is CancellationError {
            return have != nil
        } catch let error as APIError where error == .offline && have != nil {
            return true
        }
    }

    // MARK: Files

    private func save<T>(key: String, data: Data, etag: String?, value: T) {
        let savedAt = Date()
        memory[key] = Entry(value: value, etag: etag, savedAt: savedAt)
        missing.remove(key)
        let dir = directory
        let meta = Meta(key: key, etag: etag, savedAt: savedAt)
        io.async {
            do {
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true,
                                                        attributes: [.protectionKey: FileProtectionType.complete])
                let names = Self.names(for: key)
                try data.write(to: dir.appendingPathComponent(names[0]), options: [.atomic, .completeFileProtection])
                try Self.coder.encode(meta).write(to: dir.appendingPathComponent(names[1]),
                                                  options: [.atomic, .completeFileProtection])
            } catch {
                // Nothing kept this time; the screen still has its answer.
            }
        }
    }

    private static let coder = JSONEncoder()
    private static let reader = JSONDecoder()

    static func key(_ path: String, _ query: [String: String]) -> String {
        let q = query.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: "&")
        return q.isEmpty ? path : path + "?" + q
    }

    /// The answer's file and its ETag's, named by the key's hash.
    private static func names(for key: String) -> [String] {
        let digest = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
        return [digest + ".json", digest + ".meta.json"]
    }
}
