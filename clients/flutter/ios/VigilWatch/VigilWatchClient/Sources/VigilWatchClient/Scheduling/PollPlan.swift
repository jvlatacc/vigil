import Foundation

/// Poll cadence for the watch, matched to how the app is actually used.
///
/// Foreground: the console polls approvals every 20 s (`APPROVALS_POLL_MS`,
/// `clients/web/src/screens/decisions/useDecisions.ts`) — the watch matches
/// while the app is on-screen. Background: watchOS wakes apps sparingly, so
/// the plan requests a long first refresh after a clean poll, and backs off
/// exponentially when the server is unreachable — never silently silent:
/// the UI labels data with its age.
public struct PollPlan: Sendable {
    /// Foreground cadence — parity with the console's approvals poller.
    public static let foregroundInterval: TimeInterval = 20

    /// After a clean background poll, ask for the next wake in 15 minutes.
    public static let backgroundSuccessInterval: TimeInterval = 15 * 60

    /// First background retry after a failure; doubles per failure, capped.
    public static let backgroundBaseOnFailure: TimeInterval = 5 * 60
    public static let backgroundCap: TimeInterval = 60 * 60

    /// How long to wait before the next background refresh. `random` ∈ [0,1]
    /// jitters the schedule ±25% so paired watches don't poll in lockstep.
    public static func backgroundDelay(
        consecutiveFailures: Int,
        random: Double
    ) -> TimeInterval {
        let base: TimeInterval
        if consecutiveFailures <= 0 {
            base = backgroundSuccessInterval
        } else {
            let exp = pow(2.0, Double(min(consecutiveFailures - 1, 4)))
            base = min(backgroundCap, backgroundBaseOnFailure * exp)
        }
        let jitter = 0.75 + (random * 0.5)
        return min(backgroundCap, base * jitter)
    }
}
