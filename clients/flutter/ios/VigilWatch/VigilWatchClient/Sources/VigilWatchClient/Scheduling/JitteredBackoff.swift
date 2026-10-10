import Foundation

/// Jittered exponential backoff for the decision queue's retry loop: queued
/// decisions re-send with growing spacing (5 s base, ×2 per attempt, capped
/// at 10 minutes) with ±50% jitter so a fleet of watches does not stampede a
/// recovering server. `random` is injected so tests are deterministic.
public struct JitteredBackoff: Sendable {
    public let base: TimeInterval
    public let multiplier: Double
    public let cap: TimeInterval
    private let random: @Sendable () -> Double

    public init(
        base: TimeInterval = 5,
        multiplier: Double = 2,
        cap: TimeInterval = 600,
        random: @escaping @Sendable () -> Double = { Double.random(in: 0...1) }
    ) {
        self.base = base
        self.multiplier = multiplier
        self.cap = cap
        self.random = random
    }

    /// Delay after `attempt` consecutive failures (1-based). Never below the
    /// base and never above the cap.
    public func delay(afterAttempt attempt: Int) -> TimeInterval {
        let exp = pow(multiplier, Double(max(0, attempt - 1)))
        let uncapped = base * exp
        let capped = min(cap, uncapped)
        let jitter = 0.5 + random()
        return min(cap, capped * jitter)
    }
}
