import XCTest
@testable import VigilWatchClient

/// Decode tests against fixture payloads derived from the frozen contract —
/// the watch's enforcement of `contract.snapshot.json` without a generator.
final class ContractDecodeTests: XCTestCase {
    func testNeedsYouResponseDecodesAllItems() throws {
        let response = try JSONDecoder().decode(
            NeedsYouResponse.self,
            from: Fixtures.data("needs-you")
        )
        XCTAssertEqual(response.count, 3)
        XCTAssertEqual(response.items.count, 3)
        XCTAssertEqual(response.items[0].sourceId, "act_iso_host")
        XCTAssertEqual(response.items[0].caseId, "case_1042")
        XCTAssertEqual(response.items[0].reversibility, "reversible")
    }

    func testNeedsYouItemEmptyReasonIsTolerated() throws {
        let response = try JSONDecoder().decode(
            NeedsYouResponse.self,
            from: Fixtures.data("needs-you")
        )
        // The contract types `reason` as a required string; an empty value
        // must decode — the card renders nothing for it.
        XCTAssertEqual(response.items[1].reason, "")
        XCTAssertEqual(response.items[1].reversibility, "irreversible")
        XCTAssertNil(response.items[1].caseId)
    }

    func testNeedsYouUnknownReversibilityKeptRaw() throws {
        let response = try JSONDecoder().decode(
            NeedsYouResponse.self,
            from: Fixtures.data("needs-you")
        )
        // An unrecognized reversibility must survive decode as the raw
        // string — the UI falls back to the review chip, never drops the
        // card silently.
        XCTAssertEqual(response.items[2].reversibility, "soft-delete")
    }

    func testNeedsYouItemsAbsentDefaultsToEmpty() throws {
        // `items` is optional in the contract (only `count` is required).
        let bare = try JSONDecoder().decode(
            NeedsYouResponse.self,
            from: Data(#"{"count": 0}"#.utf8)
        )
        XCTAssertEqual(bare.items, [])
    }

    func testPendingActionResponseDecodesFullOptionalSet() throws {
        let action = try JSONDecoder().decode(
            PendingActionResponse.self,
            from: Fixtures.data("pending-action")
        )
        XCTAssertEqual(action.actionId, "act_iso_host")
        XCTAssertEqual(action.confidence, 0.88)
        XCTAssertEqual(action.isReversible, true)
        XCTAssertEqual(action.workflowRunId, "run_5521")
        // Open-JSON fields decode to the value wrapper.
        if case .object(let evidence) = action.evidence {
            XCTAssertTrue(evidence.keys.contains("finding_ids"))
        } else {
            XCTFail("evidence should decode as an open object")
        }
        if case .object(let parameters) = action.parameters {
            XCTAssertEqual(parameters["host"], .string("web-prod-3"))
        } else {
            XCTFail("parameters should decode as an open object")
        }
        // Explicit nulls decode to a nil Optional (decodeIfPresent) —
        // presence of the key with null means no value, same as absence.
        XCTAssertNil(action.executionResult)
    }

    func testApprovalActionResultDecodes() throws {
        let result = try JSONDecoder().decode(
            ApprovalActionResult.self,
            from: Fixtures.data("approval-action-result")
        )
        XCTAssertEqual(result.action.actionId, "act_iso_host")
        XCTAssertEqual(result.action.status, "approved")
        XCTAssertEqual(result.action.approvedBy, "jvl")
        if case .object(let resume) = result.resumeResult {
            XCTAssertEqual(resume["resumed"], .bool(true))
        } else {
            XCTFail("resume_result should decode as an open object")
        }
    }

    func testAuthTokenBodyToleratesExtraKeys() throws {
        let tokens = try JSONDecoder().decode(
            AuthTokenResponseBody.self,
            from: Fixtures.data("auth-tokens")
        )
        XCTAssertEqual(tokens.accessToken, "watch-access-token")
        XCTAssertEqual(tokens.refreshToken, "watch-refresh-token")
    }

    func testAuthTokenBodyWithoutAccessTokenThrows() {
        // A body without tokens must throw — never construct a session
        // around an empty credential.
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                AuthTokenResponseBody.self,
                from: Data(#"{"token_type": "bearer"}"#.utf8)
            )
        )
    }

    func testVigilDateParsesContractTimestamps() {
        // Offset + Z, with and without fractional seconds, and naive UTC.
        XCTAssertNotNil(VigilDate.parse("2026-10-10T13:58:02Z"))
        XCTAssertNotNil(VigilDate.parse("2026-10-10T13:58:02.123456Z"))
        XCTAssertNotNil(VigilDate.parse("2026-10-10T13:58:02"))
        XCTAssertNotNil(VigilDate.parse("2026-10-10T13:58:02+00:00"))
        XCTAssertNil(VigilDate.parse(""))
        XCTAssertNil(VigilDate.parse("not a date"))
    }

    func testNeedsYouItemCreatedAtParsesToDate() throws {
        let response = try JSONDecoder().decode(
            NeedsYouResponse.self,
            from: Fixtures.data("needs-you")
        )
        XCTAssertNotNil(response.items[0].createdAtDate)
    }
}
