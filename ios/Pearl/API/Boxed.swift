import Foundation

/// A value kept on the heap, with value semantics: reading it never copies
/// the whole thing onto the stack.
///
/// Why (2026-11-14, a crash on the product owner's iPhone): `Transaction`
/// holds its split, its refund and the purchase it repays inline, each with
/// nested link sheets and people, so the struct grew to kilobytes. A Debug
/// build copies it into a fresh stack slot for every `t.` in a SwiftUI body,
/// and TransactionDetailView's body ran out of stack ("Thread stack size
/// exceeded" in `___chkstk_darwin`). Boxing the big, rarely-read parts keeps
/// `Transaction` small; the values themselves never change after decoding.
@propertyWrapper
struct Boxed<Value: Hashable>: Hashable {
    private final class Storage {
        let value: Value
        init(_ value: Value) { self.value = value }
    }

    private var storage: Storage

    init(wrappedValue: Value) { storage = Storage(wrappedValue) }

    var wrappedValue: Value {
        get { storage.value }
        set { storage = Storage(newValue) }
    }

    static func == (a: Boxed, b: Boxed) -> Bool { a.storage === b.storage || a.wrappedValue == b.wrappedValue }
    func hash(into hasher: inout Hasher) { hasher.combine(wrappedValue) }
}

extension Boxed: Decodable where Value: Decodable {
    init(from decoder: Decoder) throws {
        self.init(wrappedValue: try Value(from: decoder))
    }
}

extension KeyedDecodingContainer {
    /// A boxed optional is optional in the JSON too: missing or null is nil.
    func decode<T: Decodable & Hashable>(_ type: Boxed<T?>.Type, forKey key: Key) throws -> Boxed<T?> {
        Boxed(wrappedValue: try decodeIfPresent(T.self, forKey: key))
    }
}
