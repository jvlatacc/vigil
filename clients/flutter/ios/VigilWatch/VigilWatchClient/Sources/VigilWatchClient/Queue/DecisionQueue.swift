import Foundation

/// A decision the analyst made on the wrist that has not been confirmed by
/// the server yet. Queued decisions retry with backoff and are NEVER
/// silently expired client-side — the server is the source of record; only
/// its confirmation (or its explicit 409/404 "already decided") retires an
/// entry.
public struct QueuedDecision: Codable, Equatable, Identifiable, Sendable {
    public enum Kind: String, Codable, Sendable {
        case approve
        case reject
    }

    /// The approval action id (the needs-you item's `source_id`).
    public var actionId: String
    public var kind: Kind
    /// Mandatory for rejections; nil for approvals.
    public var reason: String?
    /// Epoch seconds when the analyst made the call — displayed as "queued
    /// 2 min ago" if the queue outlives connectivity.
    public var enqueuedAt: Double
    public var attempts: Int
    /// Epoch seconds after which the next send may fire.
    public var nextAttemptAt: Double

    public init(
        actionId: String,
        kind: QueuedDecision.Kind,
        reason: String? = nil,
        enqueuedAt: Double = Date().timeIntervalSince1970,
        attempts: Int = 0,
        nextAttemptAt: Double = Date().timeIntervalSince1970
    ) {
        self.actionId = actionId
        self.kind = kind
        self.reason = reason
        self.enqueuedAt = enqueuedAt
        self.attempts = attempts
        self.nextAttemptAt = nextAttemptAt
    }

    public var id: String { "\(kind.rawValue):\(actionId)" }
}

/// Persistence for the queue. The file store survives watch-app restarts
/// (a decision made in a dead zone must outlive the process); tests inject
/// an in-memory store.
public protocol DecisionStoring: AnyObject, Sendable {
    func load() -> [QueuedDecision]
    func save(_ decisions: [QueuedDecision])
}

/// JSON file under Application Support (or the chosen directory in tests).
public final class FileDecisionStore: DecisionStoring, @unchecked Sendable {
    private let url: URL
    private let lock = NSLock()

    public init(directory: URL? = nil, filename: String = "queued-decisions.json") {
        let dir: URL
        if let directory {
            dir = directory
        } else {
            dir = FileManager.default.urls(
                for: .applicationSupportDirectory, in: .userDomainMask
            ).first
                ?? URL(fileURLWithPath: NSTemporaryDirectory())
        }
        self.url = dir.appendingPathComponent(filename)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    public func load() -> [QueuedDecision] {
        lock.lock()
        defer { lock.unlock() }
        guard let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([QueuedDecision].self, from: data)) ?? []
    }

    public func save(_ decisions: [QueuedDecision]) {
        lock.lock()
        defer { lock.unlock() }
        guard let data = try? JSONEncoder().encode(decisions) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

/// The durable queue of decisions made offline. `drain` is the retry loop's
/// body: entries whose `nextAttemptAt` has passed are sent; successes and
/// server-truth retirements are removed; transport failures stay queued with
/// a backoff-scheduled retry. Nothing auto-expires.
public actor DecisionQueue {
    private let store: DecisionStoring
    private let backoff: JitteredBackoff
    private let clock: @Sendable () -> Double

    public init(
        store: DecisionStoring,
        backoff: JitteredBackoff = JitteredBackoff(),
        clock: @escaping @Sendable () -> Double = { Date().timeIntervalSince1970 }
    ) {
        self.store = store
        self.backoff = backoff
        self.clock = clock
    }

    public func pendingCount() -> Int {
        store.load().count
    }

    public func enqueue(_ decision: QueuedDecision) {
        var decisions = store.load()
        // One entry per (kind, action) — a re-tap replaces the queued call
        // rather than stacking duplicates of the same decision.
        decisions.removeAll { $0.id == decision.id }
        decisions.append(decision)
        store.save(decisions)
    }

    public func remove(actionId: String, kind: QueuedDecision.Kind) {
        var decisions = store.load()
        decisions.removeAll { $0.actionId == actionId && $0.kind == kind }
        store.save(decisions)
    }

    /// Sends every due decision through `session`. Returns what happened so
    /// the UI can update cards: delivered decisions, decisions the server
    /// reports as already made (the server's truth won), and how many
    /// remain queued.
    @discardableResult
    public func drain(using session: VigilWatchSession) async -> DrainReport {
        var report = DrainReport()
        let now = clock()
        for var entry in store.load() where entry.nextAttemptAt <= now {
            do {
                switch entry.kind {
                case .approve:
                    _ = try await session.approve(actionId: entry.actionId)
                case .reject:
                    _ = try await session.reject(
                        actionId: entry.actionId,
                        reason: entry.reason ?? ""
                    )
                }
                remove(actionId: entry.actionId, kind: entry.kind)
                report.delivered.append(entry.id)
            } catch let error as VigilWatchAPIError {
                switch error {
                case .alreadyDecided:
                    // The server already decided — its truth retires the entry.
                    remove(actionId: entry.actionId, kind: entry.kind)
                    report.decidedElsewhere.append(entry.id)
                case .notConfigured, .authRevoked:
                    // No session (or revoked): hold the entry without
                    // burning attempts — the decision waits for the next
                    // handoff rather than racing a dead session.
                    report.blocked.append(entry.id)
                default:
                    report.retried.append(
                        reschedule(entry, now: now)
                    )
                }
            } catch {
                report.retried.append(reschedule(entry, now: now))
            }
        }
        return report
    }

    /// Bumps attempts, schedules the backoff retry, and persists the entry.
    private func reschedule(_ entry: QueuedDecision, now: Double) -> String {
        var entry = entry
        entry.attempts += 1
        entry.nextAttemptAt = now + backoff.delay(afterAttempt: entry.attempts)
        remove(actionId: entry.actionId, kind: entry.kind)
        var decisions = store.load()
        decisions.append(entry)
        store.save(decisions)
        return entry.id
    }

    public struct DrainReport: Equatable, Sendable {
        public var delivered: [String] = []
        public var decidedElsewhere: [String] = []
        public var retried: [String] = []
        public var blocked: [String] = []

        public init() {}
    }
}
