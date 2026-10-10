import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import VigilWatchClient

/// The decision queue: dedupe, drain outcomes (delivered / decided
/// elsewhere / retried / blocked), backoff growth, and durability — queued
/// decisions are never silently expired; only the server retires them.
final class DecisionQueueTests: XCTestCase {
    private var tempDirectory: URL!

    override func setUpWithError() throws {
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDirectory)
    }

    private func makeStore() -> FileDecisionStore {
        FileDecisionStore(directory: tempDirectory)
    }

    private func makeSession(
        _ handler: @escaping @Sendable (URLRequest, Int) throws -> TransportResponse
    ) -> VigilWatchSession {
        let store = InMemoryTokenStore()
        store.save(SessionTokens(
            serverBaseUrl: "https://vigil.example",
            accessToken: "access-1",
            refreshToken: "refresh-1",
            username: "jvl"
        ))
        return VigilWatchSession(transport: MockTransport(handler: handler), store: store)
    }

    private func approveEntry(
        actionId: String = "act_1",
        attempts: Int = 0,
        nextAttemptAt: Double = 0
    ) -> QueuedDecision {
        QueuedDecision(
            actionId: actionId,
            kind: .approve,
            attempts: attempts,
            nextAttemptAt: nextAttemptAt
        )
    }

    func testEnqueueDeduplicatesPerActionAndKind() async {
        let queue = DecisionQueue(store: makeStore())
        await queue.enqueue(approveEntry())
        await queue.enqueue(approveEntry())
        // A re-tap replaces the queued call — never stacks duplicates.
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 1)

        await queue.enqueue(QueuedDecision(
            actionId: "act_1",
            kind: .reject,
            reason: "Too risky"
        ))
        let countTwoKinds = await queue.pendingCount()
        XCTAssertEqual(countTwoKinds, 2)
    }

    func testDrainDeliversDueDecisionsAndClearsThem() async {
        let queue = DecisionQueue(store: makeStore())
        await queue.enqueue(approveEntry())
        let session = makeSession { _, _ in
            TransportResponse(statusCode: 200, body: Fixtures.data("approval-action-result"))
        }
        let report = await queue.drain(using: session)
        XCTAssertEqual(report.delivered, ["approve:act_1"])
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 0)
    }

    func testDrainRetiresAlreadyDecidedAsServerTruth() async {
        let queue = DecisionQueue(store: makeStore())
        await queue.enqueue(approveEntry())
        let session = makeSession { _, _ in
            TransportResponse(statusCode: 409, body: Data(#"{"detail": "already approved"}"#.utf8))
        }
        let report = await queue.drain(using: session)
        XCTAssertEqual(report.decidedElsewhere, ["approve:act_1"])
        // The server's truth retires the entry — it is not retried forever.
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 0)
    }

    func testDrainRetriesFailedDecisionsWithBackoff() async {
        var now: Double = 1_000
        let queue = DecisionQueue(
            store: makeStore(),
            backoff: JitteredBackoff(base: 5, multiplier: 2, cap: 600, random: { 0.5 }),
            clock: { now }
        )
        await queue.enqueue(approveEntry())
        let session = makeSession { _, _ in
            throw URLError(.notConnectedToInternet)
        }
        let report = await queue.drain(using: session)
        XCTAssertEqual(report.retried, ["approve:act_1"])
        // The decision STAYS queued — never silently expired.
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 1)
        // attempts 0 → 1, nextAttemptAt = now + 5 (deterministic jitter 0.5).
        let decisions = FileDecisionStore(directory: tempDirectory).load()
        XCTAssertEqual(decisions.first?.attempts, 1)
        XCTAssertEqual(decisions.first?.nextAttemptAt, 1_005)
        now = 1_100
        // A later drain (entry now due) retries it again.
        let second = await queue.drain(using: session)
        XCTAssertEqual(second.retried, ["approve:act_1"])
        let afterSecond = FileDecisionStore(directory: tempDirectory).load()
        XCTAssertEqual(afterSecond.first?.attempts, 2)
        XCTAssertEqual(afterSecond.first?.nextAttemptAt, 1_110)
    }

    func testDrainBlocksOnRevokedAuthButKeepsTheDecision() async {
        let queue = DecisionQueue(store: makeStore())
        await queue.enqueue(approveEntry())
        // Approve 401s, refresh also 401s → authRevoked → the entry stays.
        let session = makeSession { _, _ in
            TransportResponse(statusCode: 401, body: Data())
        }
        let report = await queue.drain(using: session)
        XCTAssertEqual(report.blocked, ["approve:act_1"])
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 1)
    }

    func testDrainSkipsEntriesNotYetDue() async {
        var now: Double = 1_000
        let queue = DecisionQueue(store: makeStore(), clock: { now })
        await queue.enqueue(approveEntry(nextAttemptAt: 1_500))
        let session = makeSession { _, _ in
            TransportResponse(statusCode: 200, body: Fixtures.data("approval-action-result"))
        }
        let report = await queue.drain(using: session)
        XCTAssertTrue(report.delivered.isEmpty)
        let count = await queue.pendingCount()
        XCTAssertEqual(count, 1)
        now = 2_000
        let second = await queue.drain(using: session)
        XCTAssertEqual(second.delivered, ["approve:act_1"])
    }

    func testQueueSurvivesStoreRecreation() async {
        // Durability: a decision made in a dead zone outlives the process.
        let first = DecisionQueue(store: makeStore())
        await first.enqueue(QueuedDecision(
            actionId: "act_2",
            kind: .reject,
            reason: "Not relevant",
            enqueuedAt: 42
        ))
        let reloaded = FileDecisionStore(directory: tempDirectory).load()
        XCTAssertEqual(reloaded.count, 1)
        XCTAssertEqual(reloaded.first?.actionId, "act_2")
        XCTAssertEqual(reloaded.first?.reason, "Not relevant")
        XCTAssertEqual(reloaded.first?.enqueuedAt, 42)
    }
}
