import XCTest
@testable import VigilWatchClient

/// Pure timing helpers — the approval semantics the watch must share with
/// the console and the phone: the 8 s undo fuse, the 1.6 s hold-to-confirm,
/// the jittered retry backoff, and the poll cadences.
final class TimingTests: XCTestCase {
    // MARK: - Undo fuse (8 s)

    func testUndoFuseDurationMatchesConsole() {
        XCTAssertEqual(UndoFuse.duration, 8.0)
        XCTAssertEqual(UndoFuse.undoReason, "Undo")
    }

    func testUndoFuseWindowMath() {
        let startedAt = Date(timeIntervalSince1970: 1_000)
        let fuse = UndoFuse(startedAt: startedAt)
        XCTAssertEqual(fuse.remainingSeconds(now: startedAt.addingTimeInterval(2)), 6)
        XCTAssertTrue(fuse.canUndo(now: startedAt.addingTimeInterval(7.9)))
        XCTAssertTrue(fuse.hasExpired(now: startedAt.addingTimeInterval(8.1)))
        XCTAssertFalse(fuse.canUndo(now: startedAt.addingTimeInterval(8.5)))
        // Nothing after fuse expiry.
        XCTAssertFalse(fuse.canUndo(now: startedAt.addingTimeInterval(80)))
    }

    // MARK: - Hold to confirm (1.6 s)

    func testHoldProgressMatchesConsole() {
        XCTAssertEqual(HoldProgress.duration, 1.6)
        let hold = HoldProgress()
        XCTAssertEqual(hold.fraction(elapsed: 0), 0, accuracy: 0.0001)
        XCTAssertEqual(hold.fraction(elapsed: 0.8), 0.5, accuracy: 0.0001)
        XCTAssertEqual(hold.fraction(elapsed: 10), 1, accuracy: 0.0001)
        XCTAssertFalse(hold.isComplete(elapsed: 1.59))
        XCTAssertTrue(hold.isComplete(elapsed: 1.6))
    }

    func testHoldInstructionChangesAtCompletion() {
        let hold = HoldProgress()
        XCTAssertEqual(
            hold.instruction(elapsed: 0),
            "Keep holding — cannot be undone"
        )
        XCTAssertEqual(hold.instruction(elapsed: 1.6), "Release to confirm")
    }

    // MARK: - Jittered backoff (queue retries)

    func testBackoffGrowsExponentiallyAndCaps() {
        // Deterministic: random() = 0.5 → jitter factor 1.0.
        let backoff = JitteredBackoff(base: 5, multiplier: 2, cap: 600, random: { 0.5 })
        XCTAssertEqual(backoff.delay(afterAttempt: 1), 5, accuracy: 0.0001)
        XCTAssertEqual(backoff.delay(afterAttempt: 2), 10, accuracy: 0.0001)
        XCTAssertEqual(backoff.delay(afterAttempt: 3), 20, accuracy: 0.0001)
        XCTAssertEqual(backoff.delay(afterAttempt: 20), 600, accuracy: 0.0001)
    }

    func testBackoffJitterStaysWithinFiftyPercent() {
        let backoff = JitteredBackoff(base: 5, multiplier: 2, cap: 600, random: { 0.5 })
        // Jitter factor 0.5..1.5 around the capped base.
        XCTAssertEqual(backoff.delay(afterAttempt: 1), 5, accuracy: 0.0001)
        let zeroJitter = JitteredBackoff(base: 5, multiplier: 2, cap: 600, random: { 0 })
        XCTAssertEqual(zeroJitter.delay(afterAttempt: 3), 10, accuracy: 0.0001)
        let fullJitter = JitteredBackoff(base: 5, multiplier: 2, cap: 600, random: { 1 })
        XCTAssertEqual(fullJitter.delay(afterAttempt: 3), 30, accuracy: 0.0001)
    }

    // MARK: - Poll plan (cadences)

    func testForegroundCadenceMatchesConsole() {
        // The console polls approvals every 20 s (`useDecisions.ts`).
        XCTAssertEqual(PollPlan.foregroundInterval, 20)
        XCTAssertEqual(PollPlan.backgroundSuccessInterval, 15 * 60)
        XCTAssertEqual(PollPlan.backgroundBaseOnFailure, 5 * 60)
        XCTAssertEqual(PollPlan.backgroundCap, 60 * 60)
    }

    func testBackgroundDelaySucceedsThenBacksOffAndCaps() {
        // No failures: 15 min ±25%.
        XCTAssertEqual(
            PollPlan.backgroundDelay(consecutiveFailures: 0, random: 0.5),
            900, accuracy: 0.0001
        )
        // One failure: 5 min base; two: 10; the cap holds at 60 min.
        let one = PollPlan.backgroundDelay(consecutiveFailures: 1, random: 0.5)
        XCTAssertEqual(one, 300, accuracy: 0.0001)
        let two = PollPlan.backgroundDelay(consecutiveFailures: 2, random: 0.5)
        XCTAssertEqual(two, 600, accuracy: 0.0001)
        let capped = PollPlan.backgroundDelay(consecutiveFailures: 50, random: 0.5)
        XCTAssertEqual(capped, 3_600, accuracy: 0.0001)
        // Jitter bounds: ±25%.
        let low = PollPlan.backgroundDelay(consecutiveFailures: 1, random: 0)
        let high = PollPlan.backgroundDelay(consecutiveFailures: 1, random: 1)
        XCTAssertEqual(low, 225, accuracy: 0.0001)
        XCTAssertEqual(high, 375, accuracy: 0.0001)
    }
}
