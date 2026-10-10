import Foundation

/// The payload the paired iPhone hands the watch over WatchConnectivity at
/// phone-login time (and the cleared sentinel the watch wipes on sign-out).
///
/// This is the watch's OWN session — minted by a second login performed by
/// the phone carrying the watch's fixed User-Agent (`vigilWatchUserAgent`),
/// never the phone's live tokens and never the password. Single-use refresh
/// rotation therefore never contends between the two devices.
///
/// The phone writes these exact keys into the WatchConnectivity application
/// context (`clients/flutter/ios/Runner/WatchHandoffBridge.swift`); the watch
/// decodes the same keys here. One wire shape, two hand-written ends, both
/// covered by tests.
public struct SessionHandoff: Codable, Equatable, Sendable {
    public var serverBaseUrl: String
    public var accessToken: String
    public var refreshToken: String
    public var username: String?

    public init(
        serverBaseUrl: String,
        accessToken: String,
        refreshToken: String,
        username: String? = nil
    ) {
        self.serverBaseUrl = serverBaseUrl
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.username = username
    }

    /// Decodes the dictionary-shaped WatchConnectivity context. Missing or
    /// empty tokens mean the phone has not completed the handoff (or has
    /// cleared it) — the watch stays on its "open Vigil on your iPhone"
    /// state rather than failing a network call later.
    public init?(context: [AnyHashable: Any]) {
        let access = context[Self.Keys.accessToken] as? String
        let refresh = context[Self.Keys.refreshToken] as? String
        let base = context[Self.Keys.serverBaseUrl] as? String
        guard let access, let refresh, let base, !access.isEmpty, !refresh.isEmpty, !base.isEmpty
        else { return nil }
        serverBaseUrl = base
        accessToken = access
        refreshToken = refresh
        username = context[Self.Keys.username] as? String
    }

    /// The sentinel the phone sends on sign-out: keys present, values empty —
    /// the watch wipes its stored session when it sees this.
    public static let cleared = SessionHandoff(
        serverBaseUrl: "",
        accessToken: "",
        refreshToken: "",
        username: nil
    )

    public var isCleared: Bool {
        accessToken.isEmpty || refreshToken.isEmpty || serverBaseUrl.isEmpty
    }

    /// The stored form: tokens at rest in the Keychain alongside the server
    /// they answer to.
    public var asTokens: SessionTokens {
        SessionTokens(
            serverBaseUrl: serverBaseUrl,
            accessToken: accessToken,
            refreshToken: refreshToken,
            username: username
        )
    }

    enum Keys {
        static let serverBaseUrl = "serverBaseUrl"
        static let accessToken = "accessToken"
        static let refreshToken = "refreshToken"
        static let username = "username"
    }
}

/// What the Keychain holds between handoffs: the token pair plus the server
/// they answer to (the pair dies at TTL or when the phone revokes it at
/// sign-out; the watch never sees the password to re-login itself).
public struct SessionTokens: Codable, Equatable, Sendable {
    public var serverBaseUrl: String
    public var accessToken: String
    public var refreshToken: String
    public var username: String?

    public init(
        serverBaseUrl: String,
        accessToken: String,
        refreshToken: String,
        username: String? = nil
    ) {
        self.serverBaseUrl = serverBaseUrl
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.username = username
    }

    public var handoff: SessionHandoff {
        SessionHandoff(
            serverBaseUrl: serverBaseUrl,
            accessToken: accessToken,
            refreshToken: refreshToken,
            username: username
        )
    }
}
