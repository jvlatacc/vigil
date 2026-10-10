import Foundation

/// The 8-second undo fuse on a reversible approval — identical timing to the
/// console (`undo-fuse` component spec, `.toast-fuse` 8 s) and to the phone.
///
/// A reversible approve commits server-side immediately; the fuse is the
/// window in which the analyst can take it back. The frozen `/api/v1`
/// surface has only approve and reject — there is no un-approve — so undo
/// is a reject of the same action with the reserved reason "Undo": the
/// server records the reversal and the resumed workflow run is cancelled.
/// After the fuse burns out, undo is refused — nothing after fuse expiry.
public struct UndoFuse: Equatable, Sendable {
    /// The frozen fuse duration: 8 seconds.
    public static let duration: TimeInterval = 8.0

    /// The reason recorded when undo fires (satisfies the mandatory-reason
    /// rule on reject without pretending it was a substantive rejection).
    public static let undoReason = "Undo"

    public let startedAt: Date

    public init(startedAt: Date = Date()) {
        self.startedAt = startedAt
    }

    /// Seconds left on the fuse at `now` — 0 once expired.
    public func remainingSeconds(now: Date = Date()) -> TimeInterval {
        max(0, Self.duration - now.timeIntervalSince(startedAt))
    }

    /// Whether the fuse has burned out at `now`.
    public func hasExpired(now: Date = Date()) -> Bool {
        remainingSeconds(now: now) <= 0
    }

    /// Undo is permitted strictly inside the window.
    public func canUndo(now: Date = Date()) -> Bool {
        !hasExpired(now: now)
    }
}
