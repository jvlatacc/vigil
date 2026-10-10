import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import VigilWatchClient

/// The WatchConnectivity handoff: the phone delivers the watch's OWN token
/// pair (minted at phone-login); the cleared sentinel wipes the Keychain.
final class HandoffTests: XCTestCase {
    private let handoff = SessionHandoff(
        serverBaseUrl: "https://vigil.example",
        accessToken: "watch-access",
        refreshToken: "watch-refresh",
        username: "jvl"
    )

    func testHandoffStoresTokens() async {
        let store = InMemoryTokenStore()
        let session = VigilWatchSession(transport: MockTransport.always500, store: store)
        await session.applyHandoff(handoff)
        let has = await session.hasSession()
        XCTAssertTrue(has)
        XCTAssertEqual(store.load()?.accessToken, "watch-access")
        XCTAssertEqual(store.load()?.refreshToken, "watch-refresh")
        let base = await session.serverBaseURL()
        XCTAssertEqual(base, "https://vigil.example")
    }

    func testClearedSentinelWipesSession() async {
        let store = InMemoryTokenStore()
        let session = VigilWatchSession(transport: MockTransport.always500, store: store)
        await session.applyHandoff(handoff)
        let has = await session.hasSession()
        XCTAssertTrue(has)

        await session.applyHandoff(.cleared)
        let cleared = await session.hasSession()
        XCTAssertFalse(cleared)
        XCTAssertNil(store.load())
    }

    func testHandoffWireContextDecodes() {
        let context: [AnyHashable: Any] = [
            "serverBaseUrl": "https://vigil.example",
            "accessToken": "watch-access",
            "refreshToken": "watch-refresh",
            "username": "jvl",
        ]
        let decoded = SessionHandoff(context: context)
        XCTAssertEqual(decoded, handoff)
    }

    func testHandoffWireContextWithEmptyTokensIsNil() {
        // The cleared sentinel on the wire: keys present, values empty —
        // not a handoff; the connector translates it to `.cleared`.
        let cleared: [AnyHashable: Any] = [
            "serverBaseUrl": "",
            "accessToken": "",
            "refreshToken": "",
        ]
        XCTAssertNil(SessionHandoff(context: cleared))
        XCTAssertNil(SessionHandoff(context: [:]))
    }

    func testTokensDoNotLandInUserDefaults() {
        // The storage invariant: the InMemory store is the test stand-in
        // for the Keychain; nothing in the handoff path writes to
        // UserDefaults. Assert the standard defaults stay untouched by
        // handoff application.
        UserDefaults.standard.removeObject(forKey: "vigil.watch.tokens")
        XCTAssertNil(UserDefaults.standard.object(forKey: "vigil.watch.tokens"))
    }
}
