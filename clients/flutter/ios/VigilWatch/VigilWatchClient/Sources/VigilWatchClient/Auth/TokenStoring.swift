import Foundation

/// Storage for the watch's session tokens. Implementations: the Keychain on
/// watchOS (production) and an in-memory store for tests and previews.
public protocol TokenStoring: AnyObject, Sendable {
    func load() -> SessionTokens?
    func save(_ tokens: SessionTokens)
    func clear()
}

/// Thread-safe in-memory store — tests, previews, and the Linux suite.
public final class InMemoryTokenStore: TokenStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var tokens: SessionTokens?

    public init() {}

    public func load() -> SessionTokens? {
        lock.lock()
        defer { lock.unlock() }
        return tokens
    }

    public func save(_ tokens: SessionTokens) {
        lock.lock()
        defer { lock.unlock() }
        self.tokens = tokens
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }
        self.tokens = nil
    }
}

#if canImport(Security)
import Security

/// Keychain-backed store for the tokens handed over from the paired iPhone.
/// The pair lives in a generic-password item scoped to this app; nothing
/// token-shaped ever touches UserDefaults, files, or logs. The Keychain's
/// default accessibility applies — the data stays on this device.
public final class KeychainTokenStore: TokenStoring {
    private let service: String

    public init(service: String = "ai.deeptempo.vigil.watch") {
        self.service = service
    }

    public func load() -> SessionTokens? {
        var query = baseQuery
        query[kSecReturnData as String] = kCFBooleanTrue as Any
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(SessionTokens.self, from: data)
    }

    public func save(_ tokens: SessionTokens) {
        guard let data = try? JSONEncoder().encode(tokens) else { return }
        var query = baseQuery
        let attributes: [String: Any] = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            query[kSecValueData as String] = data
            SecItemAdd(query as CFDictionary, nil)
        }
    }

    public func clear() {
        SecItemDelete(baseQuery as CFDictionary)
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "session",
        ]
    }
}
#endif
