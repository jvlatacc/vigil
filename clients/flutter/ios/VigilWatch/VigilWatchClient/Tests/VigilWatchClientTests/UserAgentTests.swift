import XCTest
@testable import VigilWatchClient

/// The `sfp` claim binds `sha256(User-Agent)[:16]` per request — a varying
/// UA earns 401 "Session fingerprint mismatch". The watch UA is a constant
/// and these tests keep it that way.
final class UserAgentTests: XCTestCase {
    func testUserAgentConstant() {
        XCTAssertEqual(vigilWatchUserAgent, "VigilWatch/1.0 (watchOS)")
    }

    func testUserAgentIsByteStableAcrossReads() {
        // Trivially true for a `let` constant, but pinned so a future
        // refactor to computed/platform-varying values fails here first.
        XCTAssertEqual(vigilWatchUserAgent, vigilWatchUserAgent)
        XCTAssertFalse(vigilWatchUserAgent.isEmpty)
    }
}
