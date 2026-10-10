import Foundation

/// Pure timing for the hold-to-confirm gesture on irreversible approvals —
/// 1.6 seconds, identical to the console's `hold-to-confirm` spec and the
/// phone's hold button. Releasing early cancels: a completed hold is the
/// only way an irreversible action commits, and it can never be undone.
///
/// Rendering (the progress ring) belongs to SwiftUI; this type owns the
/// math so the acceptance timing is unit-testable on Linux.
public struct HoldProgress: Equatable, Sendable {
    /// The frozen hold duration: 1.6 seconds.
    public static let duration: TimeInterval = 1.6

    public init() {}

    /// Fraction of the hold completed (0.0–1.0) after holding `elapsed`
    /// seconds. Clamped; values past the duration read as complete.
    public func fraction(elapsed: TimeInterval) -> Double {
        guard Self.duration > 0 else { return 1 }
        return min(1, max(0, elapsed / Self.duration))
    }

    /// Whether the hold has fully completed after `elapsed` seconds.
    public func isComplete(elapsed: TimeInterval) -> Bool {
        fraction(elapsed: elapsed) >= 1
    }

    /// User-facing instruction at a moment in the hold. "Keep holding —
    /// cannot be undone" (DESIGN.md vocabulary) while mid-hold.
    public func instruction(elapsed: TimeInterval) -> String {
        isComplete(elapsed: elapsed)
            ? "Release to confirm"
            : "Keep holding — cannot be undone"
    }
}
