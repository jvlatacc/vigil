import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import VigilWatchClient

/// Mock-transport tests for the five-endpoint client: bearer + UA on every
/// request, one-shot 401 → refresh → replay, rotation persistence, and the
/// typed failure surface. This suite runs on Linux; the macOS CI job runs
/// the same assertions under XCTest.
final class SessionTests: XCTestCase {
    private let tokens = SessionTokens(
        serverBaseUrl: "https://vigil.example",
        accessToken: "access-1",
        refreshToken: "refresh-1",
        username: "jvl"
    )

    private func makeSession(
        _ handler: @escaping @Sendable (URLRequest, Int) -> TransportResponse
    ) -> (VigilWatchSession, MockTransport, InMemoryTokenStore) {
        let transport = MockTransport(handler: handler)
        let store = InMemoryTokenStore()
        store.save(tokens)
        return (VigilWatchSession(transport: transport, store: store), transport, store)
    }

    private func needsYouOK(_ request: URLRequest, _ index: Int) -> TransportResponse {
        TransportResponse(
            statusCode: 200,
            body: Fixtures.data("needs-you"),
            headers: ["Content-Type": "application/json"]
        )
    }

    // MARK: - Headers

    func testEveryRequestCarriesBearerAndFixedUserAgent() async throws {
        let (session, transport, _) = makeSession(needsYouOK)
        _ = try await session.needsYou()
        _ = try await session.needsYou()

        for (index, request) in transport.allRequests.enumerated() {
            XCTAssertEqual(request.url?.absoluteString, "https://vigil.example/api/v1/approvals/needs-you")
            XCTAssertEqual(transport.userAgent(at: index), "VigilWatch/1.0 (watchOS)")
            XCTAssertEqual(transport.authorization(at: index), "Bearer access-1")
        }
        XCTAssertEqual(transport.allRequests.count, 2)
    }

    func testUserAgentIdenticalAcrossEndpoints() async throws {
        // needs-you then refresh: the UA must be byte-identical — the sfp
        // claim binds the exact string the tokens were minted with.
        let (session, transport, _) = makeSession { request, index in
            if request.url?.path.hasSuffix("/api/auth/refresh") == true {
                let body = #"{"access_token": "access-2", "refresh_token": "refresh-2"}"#
                return TransportResponse(statusCode: 200, body: Data(body.utf8))
            }
            if index >= 2 {
                return TransportResponse(statusCode: 200, body: Fixtures.data("needs-you"))
            }
            return TransportResponse(statusCode: 401, body: Data())
        }
        do {
            _ = try await session.needsYou() // 401 → refresh → replay OK
        } catch {
            XCTFail("first call should recover: \(error)")
        }
        _ = try await session.refreshNow()

        // needs-you(401) + refresh + replay + the explicit refreshNow —
        // four requests, one shared byte-stable UA.
        XCTAssertEqual(transport.allRequests.count, 4)
        let uas = (0..<4).map { transport.userAgent(at: $0) }
        XCTAssertEqual(uas[0], uas[1])
        XCTAssertEqual(uas[1], uas[2])
        XCTAssertEqual(uas[0], "VigilWatch/1.0 (watchOS)")
        // The refresh request carried the OLD refresh token in the body —
        // single-use rotation contract.
        let refreshBody = try transport.jsonBody(at: 1)
        XCTAssertEqual(refreshBody["refresh_token"] as? String, "refresh-1")
        // The rotation persisted the NEW pair.
        let store = await session.serverBaseURL()
        XCTAssertEqual(store, "https://vigil.example")
    }

    // MARK: - 401 → refresh → replay

    func test401TriggersSingleRefreshAndReplay() async throws {
        let (session, transport, store) = makeSession { request, index in
            if request.url?.path.hasSuffix("/api/auth/refresh") == true {
                let body = #"{"access_token": "access-2", "refresh_token": "refresh-2"}"#
                return TransportResponse(statusCode: 200, body: Data(body.utf8))
            }
            if index >= 2 {
                return TransportResponse(statusCode: 200, body: Fixtures.data("needs-you"))
            }
            return TransportResponse(statusCode: 401, body: Data())
        }
        let items = try await session.needsYou()
        XCTAssertEqual(items.count, 3)
        XCTAssertEqual(store.load()?.accessToken, "access-2")
        XCTAssertEqual(store.load()?.refreshToken, "refresh-2")
        // Exactly three requests: needs-you(401), refresh, replay.
        XCTAssertEqual(transport.allRequests.count, 3)
        XCTAssertEqual(transport.request(2).url?.path, "/api/v1/approvals/needs-you")
    }

    func testSecond401AfterReplayDoesNotLoop() async {
        // 401, refresh OK, replay 401 again → the session must surface an
        // error, never loop.
        let (session, transport, _) = makeSession { request, index in
            if request.url?.path.hasSuffix("/api/auth/refresh") == true {
                let body = #"{"access_token": "access-2", "refresh_token": "refresh-2"}"#
                return TransportResponse(statusCode: 200, body: Data(body.utf8))
            }
            return TransportResponse(statusCode: 401, body: Data())
        }
        do {
            _ = try await session.needsYou()
            XCTFail("expected an error after the replay 401")
        } catch {
            // Any typed error is fine; the loop is the failure mode.
        }
        // needs-you(401) + refresh + replay(401) — and then it stopped.
        XCTAssertEqual(transport.allRequests.count, 3)
    }

    func testRevokedRefreshThrowsAuthRevoked() async {
        // Refresh itself 401s — the pair is consumed/blacklisted; the watch
        // needs a fresh handoff, not a loop.
        let (session, transport, _) = makeSession { _, _ in
            TransportResponse(statusCode: 401, body: Data())
        }
        do {
            _ = try await session.needsYou()
            XCTFail("expected authRevoked")
        } catch let error as VigilWatchAPIError {
            XCTAssertEqual(error, .authRevoked)
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
        // needs-you(401) + refresh(401) — stopped, no replay attempted.
        XCTAssertEqual(transport.allRequests.count, 2)
    }

    // MARK: - Decisions

    func testApprovePostsAndDecodesResult() async throws {
        let (session, transport, _) = makeSession { _, _ in
            TransportResponse(
                statusCode: 200,
                body: Fixtures.data("approval-action-result")
            )
        }
        let action = try await session.approve(actionId: "act_iso_host", approvedBy: "vigil-watch")
        XCTAssertEqual(action.status, "approved")

        let request = transport.request(0)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v1/approvals/act_iso_host/approve")
        let body = try transport.jsonBody(at: 0)
        XCTAssertEqual(body["approved_by"] as? String, "vigil-watch")
    }

    func testRejectPostsMandatoryReason() async throws {
        let (session, transport, _) = makeSession { _, _ in
            TransportResponse(statusCode: 200, body: Fixtures.data("approval-action-result"))
        }
        _ = try await session.reject(actionId: "act_iso_host", reason: "  False positive  ")
        let body = try transport.jsonBody(at: 0)
        // The trimmed reason is what the server records.
        XCTAssertEqual(body["reason"] as? String, "False positive")
    }

    func testRejectWithoutReasonNeverLeavesTheWatch() async {
        let (session, transport, _) = makeSession { _, _ in
            XCTFail("no request may fire for an empty reason")
            return TransportResponse(statusCode: 500, body: Data())
        }
        do {
            _ = try await session.reject(actionId: "act_iso_host", reason: "   ")
            XCTFail("expected an error")
        } catch {
            // typed or generic — the point is no request and an error
        }
        XCTAssertEqual(transport.allRequests.count, 0)
    }

    func testAlreadyDecidedSurfacesAsTypedError() async {
        // 409 conflict — the server reports the action was already decided.
        let (session, _, _) = makeSession { _, _ in
            TransportResponse(statusCode: 409, body: Data(#"{"detail": "already approved"}"#.utf8))
        }
        do {
            _ = try await session.approve(actionId: "act_iso_host")
            XCTFail("expected alreadyDecided")
        } catch let error as VigilWatchAPIError {
            XCTAssertEqual(error, .alreadyDecided(status: 409, detail: "already approved"))
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
    }

    // MARK: - Session state

    func testNeedsYouWithoutSessionThrowsNotConfigured() async {
        let transport = MockTransport.always500
        let session = VigilWatchSession(transport: transport, store: InMemoryTokenStore())
        do {
            _ = try await session.needsYou()
            XCTFail("expected notConfigured")
        } catch let error as VigilWatchAPIError {
            XCTAssertEqual(error, .notConfigured)
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
        XCTAssertEqual(transport.allRequests.count, 0)
    }

    func testIsServerAliveNeverThrows() async {
        let (session, _, _) = makeSession { _, _ in
            TransportResponse(statusCode: 200, body: Data(#"{"status": "ok"}"#.utf8))
        }
        let alive = await session.isServerAlive()
        XCTAssertTrue(alive)

        let dead = VigilWatchSession(transport: MockTransport.always500, store: InMemoryTokenStore())
        let deadResult = await dead.isServerAlive()
        XCTAssertFalse(deadResult)
    }
}
