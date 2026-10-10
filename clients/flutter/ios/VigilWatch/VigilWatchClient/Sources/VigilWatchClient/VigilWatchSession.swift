import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Typed failures the watch UI can branch on. `alreadyDecided` is not an
/// error to surface — it is the server reporting it is the source of record
/// (409 conflict / 404 the action is gone), so the card updates to the
/// server's truth and any queued copy of the decision is retired.
public enum VigilWatchAPIError: Error, Equatable {
    /// No session has been handed over yet (or it was cleared).
    case notConfigured
    /// Transport-level failure — network unreachable, timeout, DNS.
    case network(String)
    /// Non-2xx that is neither an auth retry case nor a decided action.
    case http(status: Int, detail: String?)
    /// The action was already decided (or never existed) server-side.
    case alreadyDecided(status: Int, detail: String?)
    /// Refresh was consumed, blacklisted, or the pair was revoked — the
    /// watch needs a fresh handoff from the phone (open Vigil on iPhone).
    case authRevoked
    /// A 200 response body did not decode against the frozen contract.
    case decoding(String)
}

/// The watch's client for the five-endpoint surface:
///
/// 1. `GET  /api/v1/approvals/needs-you` — the "needs a human" feed
/// 2. `POST /api/v1/approvals/{id}/approve`
/// 3. `POST /api/v1/approvals/{id}/reject`
/// 4. `POST /api/auth/refresh` — the watch's own single-use rotation
/// 5. `GET  /api/health` — connectivity probe
///
/// Auth: bearer tokens from the Keychain, the byte-stable
/// `VigilWatch/1.0 (watchOS)` User-Agent on every request (the `sfp`
/// fingerprint binds this exact string), and a one-shot 401 → refresh →
/// replay — the watch-side twin of the console interceptor and the phone's
/// Dio `VigilAuthenticator`. A second 401 after a fresh rotation means the
/// session is revoked, never a loop.
///
/// Concurrency: an actor, so concurrent polls/taps serialize; a single
/// in-flight refresh task dedupes simultaneous 401s onto one rotation (the
/// refresh token is single-use — a second rotation with it would fail as a
/// consumed `jti` and wrongly sign the watch out).
public actor VigilWatchSession {
    private let transport: HTTPTransport
    private let store: TokenStoring
    private let userAgent: String
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    /// In-flight refresh dedupe: task plus the refresh token it rotates, so
    /// a refresh that already succeeded is not rotated again by a straggler.
    private var refreshingTask: Task<AuthTokenResponseBody, Error>?
    private var refreshingToken: String?

    public init(
        transport: HTTPTransport,
        store: TokenStoring,
        userAgent: String = vigilWatchUserAgent
    ) {
        self.transport = transport
        self.store = store
        self.userAgent = userAgent
    }

    // MARK: - Session lifecycle (WatchConnectivity handoff)

    /// Applies a fresh handoff from the phone (or the cleared sentinel).
    public func applyHandoff(_ handoff: SessionHandoff) {
        if handoff.isCleared {
            store.clear()
        } else {
            store.save(handoff.asTokens)
        }
        refreshingTask = nil
        refreshingToken = nil
    }

    public func hasSession() -> Bool {
        store.load() != nil
    }

    public func clearSession() {
        store.clear()
    }

    /// The server base URL the current session answers to, if any.
    public func serverBaseURL() -> String? {
        store.load()?.serverBaseUrl
    }

    // MARK: - Endpoints

    /// `GET /api/v1/approvals/needs-you` — the wrist's entire data plane.
    public func needsYou() async throws -> [NeedsYouItem] {
        let data = try await authorizedJSON(method: "GET", path: "/api/v1/approvals/needs-you")
        do {
            return try decoder.decode(NeedsYouResponse.self, from: data).items
        } catch {
            throw VigilWatchAPIError.decoding(Self.decodeDetail(error))
        }
    }

    /// `POST /api/v1/approvals/{id}/approve` — reversible or held-complete.
    public func approve(
        actionId: String,
        approvedBy: String? = nil
    ) async throws -> PendingActionResponse {
        let body = try encodedBody(ApproveRequest(approvedBy: approvedBy))
        let data = try await authorizedJSON(
            method: "POST",
            path: "/api/v1/approvals/\(Self.pathEscaped(actionId))/approve",
            body: body
        )
        return try Self.mapDecisionResponse(data)
    }

    /// `POST /api/v1/approvals/{id}/reject` — reason is mandatory upstream
    /// and enforced here: an empty reason never leaves the watch.
    public func reject(
        actionId: String,
        reason: String,
        rejectedBy: String? = nil
    ) async throws -> PendingActionResponse {
        let trimmed = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw VigilWatchAPIError.http(status: 0, detail: "reject requires a reason")
        }
        let body = try encodedBody(RejectRequest(reason: trimmed, rejectedBy: rejectedBy))
        let data = try await authorizedJSON(
            method: "POST",
            path: "/api/v1/approvals/\(Self.pathEscaped(actionId))/reject",
            body: body
        )
        return try Self.mapDecisionResponse(data)
    }

    /// `POST /api/auth/refresh` — rotates the pair in place. Exposed for the
    /// pro-active re-refresh the poll scheduler can run near the 30-minute
    /// access TTL; the 401 path uses the same deduped core.
    @discardableResult
    public func refreshNow() async throws -> SessionTokens {
        guard let tokens = store.load() else { throw VigilWatchAPIError.notConfigured }
        return try await refreshOnce(tokens: tokens)
    }

    /// `GET /api/health` — public liveness probe; never throws, because a
    /// dead server is a display state ("reconnecting"), not a crash.
    public func isServerAlive() async -> Bool {
        guard let tokens = store.load(),
              let url = Self.serverURL(tokens.serverBaseUrl, path: "/api/health")
        else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        do {
            let response = try await transport.send(request)
            return (200..<300).contains(response.statusCode)
        } catch {
            return false
        }
    }

    // MARK: - Authorized request core (one-shot refresh + replay)

    private func authorizedJSON(
        method: String,
        path: String,
        body: Data? = nil
    ) async throws -> Data {
        guard let tokens = store.load() else { throw VigilWatchAPIError.notConfigured }

        var (data, status) = try await sendAuthorized(
            method: method, path: path, body: body, accessToken: tokens.accessToken
        )

        // One-shot: a 401 triggers exactly one refresh + replay. The replay
        // carries the freshly rotated access token; a second 401 is the
        // revoke signal (consumed jti / blacklist), never a loop.
        if status == 401 {
            let rotated = try await refreshOnce(tokens: tokens)
            (data, status) = try await sendAuthorized(
                method: method, path: path, body: body, accessToken: rotated.accessToken
            )
            if status == 401 {
                store.clear()
                throw VigilWatchAPIError.authRevoked
            }
        }

        try Self.checkStatus(status: status, body: data)
        return data
    }

    private func sendAuthorized(
        method: String,
        path: String,
        body: Data?,
        accessToken: String
    ) async throws -> (Data, Int) {
        guard let tokens = store.load(),
              let url = Self.serverURL(tokens.serverBaseUrl, path: path)
        else { throw VigilWatchAPIError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue(userAgent, forHTTPHeaderField: "User-Agent")

        do {
            let response = try await transport.send(request)
            return (response.body, response.statusCode)
        } catch let error as HTTPTransportError {
            switch error {
            case .network(let detail): throw VigilWatchAPIError.network(detail)
            }
        } catch {
            throw VigilWatchAPIError.network(String(describing: error))
        }
    }

    /// The deduped single-use rotation. Concurrent 401s share one task; the
    /// rotated pair is persisted BEFORE any replay, mirroring the phone's
    /// interceptor contract ("persist the NEW pair before replaying").
    private func refreshOnce(tokens: SessionTokens) async throws -> SessionTokens {
        if let task = refreshingTask, refreshingToken == tokens.refreshToken {
            let rotated = try await task.value
            return SessionTokens(
                serverBaseUrl: tokens.serverBaseUrl,
                accessToken: rotated.accessToken,
                refreshToken: rotated.refreshToken,
                username: tokens.username
            )
        }
        let task = Task { [transport, store, userAgent] in
            try await VigilWatchSession.performRefresh(
                transport: transport,
                store: store,
                userAgent: userAgent,
                tokens: tokens
            )
        }
        refreshingTask = task
        refreshingToken = tokens.refreshToken

        do {
            let rotated = try await task.value
            refreshingTask = nil
            refreshingToken = nil
            return SessionTokens(
                serverBaseUrl: tokens.serverBaseUrl,
                accessToken: rotated.accessToken,
                refreshToken: rotated.refreshToken,
                username: tokens.username
            )
        } catch {
            refreshingTask = nil
            refreshingToken = nil
            throw error
        }
    }

    /// The refresh request itself, static so the in-flight task captures no
    /// reference to the owning actor.
    private static func performRefresh(
        transport: HTTPTransport,
        store: TokenStoring,
        userAgent: String,
        tokens: SessionTokens
    ) async throws -> AuthTokenResponseBody {
        guard let url = serverURL(tokens.serverBaseUrl, path: "/api/auth/refresh") else {
            throw VigilWatchAPIError.notConfigured
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        request.httpBody = try JSONEncoder().encode(
            RefreshRequestBody(refreshToken: tokens.refreshToken)
        )

        let response: TransportResponse
        do {
            response = try await transport.send(request)
        } catch let error as HTTPTransportError {
            switch error {
            case .network(let detail): throw VigilWatchAPIError.network(detail)
            }
        } catch {
            throw VigilWatchAPIError.network(String(describing: error))
        }

        if response.statusCode == 401 || response.statusCode == 423 {
            store.clear()
            throw VigilWatchAPIError.authRevoked
        }
        guard (200..<300).contains(response.statusCode) else {
            throw VigilWatchAPIError.http(
                status: response.statusCode,
                detail: detail(from: response.body)
            )
        }
        do {
            let rotated = try JSONDecoder().decode(AuthTokenResponseBody.self, from: response.body)
            store.save(
                SessionTokens(
                    serverBaseUrl: tokens.serverBaseUrl,
                    accessToken: rotated.accessToken,
                    refreshToken: rotated.refreshToken,
                    username: tokens.username
                )
            )
            return rotated
        } catch {
            throw VigilWatchAPIError.decoding(decodeDetail(error))
        }
    }

    // MARK: - Mapping helpers

    private func encodedBody<T: Encodable>(_ payload: T) throws -> Data {
        do {
            return try encoder.encode(payload)
        } catch {
            throw VigilWatchAPIError.decoding(Self.decodeDetail(error))
        }
    }

    /// Status → typed error. 409/404 on a decision POST is `alreadyDecided`
    /// (the server's truth won); anything else is a plain `http` failure.
    private static func checkStatus(status: Int, body: Data) throws {
        guard !(200..<300).contains(status) else { return }
        let detail = detail(from: body)
        switch status {
        case 409, 404:
            throw VigilWatchAPIError.alreadyDecided(status: status, detail: detail)
        default:
            throw VigilWatchAPIError.http(status: status, detail: detail)
        }
    }

    private static func mapDecisionResponse(_ data: Data) throws -> PendingActionResponse {
        do {
            return try JSONDecoder().decode(ApprovalActionResult.self, from: data).action
        } catch let error as VigilWatchAPIError {
            throw error
        } catch {
            throw VigilWatchAPIError.decoding(decodeDetail(error))
        }
    }

    private static func serverURL(_ base: String, path: String) -> URL? {
        var trimmed = base.trimmingCharacters(in: .whitespacesAndNewlines)
        while trimmed.hasSuffix("/") {
            trimmed.removeLast()
        }
        return URL(string: trimmed + path)
    }

    private static func pathEscaped(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }

    private static func detail(from body: Data) -> String? {
        struct Detail: Decodable { let detail: String? }
        return (try? JSONDecoder().decode(Detail.self, from: body))?.detail
    }

    static func decodeDetail(_ error: Error) -> String {
        if let decoding = error as? DecodingError {
            return String(describing: decoding)
        }
        return String(describing: error)
    }

    /// One-line, user-facing text for an API error — the watch banner and
    /// card footers use this instead of dumping the case path.
    public static func describe(_ error: VigilWatchAPIError) -> String {
        switch error {
        case .notConfigured:
            return "No session — open Vigil on iPhone to connect"
        case .network(let detail):
            return "Can't reach the server — \(detail)"
        case .http(let status, _):
            return "Server error (\(status))"
        case .alreadyDecided:
            return "Already decided on the server"
        case .authRevoked:
            return "Session ended — open Vigil on iPhone to reconnect"
        case .decoding(let detail):
            return "Unexpected server response — \(detail)"
        }
    }
}
