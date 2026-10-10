import SwiftUI
import VigilWatchClient

/// The watch app's state machine, owned by one `@Observable` object the
/// views read. It composes the VigilWatchClient package: session, decision
/// queue, and the poll/staleness bookkeeping.
///
/// States:
/// - `needsHandoff` — no tokens yet (or revoked): prompt to open Vigil on
///   the paired iPhone. The watch never runs a login flow.
/// - `ready` — session present; the feed shows the last poll with its age;
///   a reconnecting banner covers transport failures (2 consecutive →
///   stale per the spec's state table).
@Observable
@MainActor
final class WatchAppState {
    enum Phase: Equatable {
        case needsHandoff
        case ready
    }

    enum FeedState: Equatable {
        case idle
        case loaded(Date)
        case stale(Date)
    }

    private(set) var phase: Phase = .needsHandoff
    private(set) var items: [NeedsYouItem] = []
    private(set) var feed: FeedState = .idle
    private(set) var lastError: String?
    /// Count of decisions made here that the server has not confirmed —
    /// shown as a queue badge ("1 queued · retries automatically").
    private(set) var queuedCount = 0

    private let session: VigilWatchSession
    private let queue: DecisionQueue
    private var pollTask: Task<Void, Never>?
    private var consecutiveFailures = 0

    init() {
        let store = KeychainTokenStore()
        session = VigilWatchSession(transport: URLSessionTransport(), store: store)
        queue = DecisionQueue(store: FileDecisionStore())
        if store.load() != nil {
            phase = .ready
        }
        queuedCount = queue.pendingCount()
    }

    // MARK: - Handoff (WatchConnectivity → session)

    /// Applies a token pair handed over by the phone (or clears on revoke).
    func applyHandoff(_ handoff: SessionHandoff) {
        session.applyHandoff(handoff)
        if handoff.isCleared {
            phase = .needsHandoff
            items = []
            feed = .idle
        } else {
            phase = .ready
            Task { await refreshNow() }
        }
    }

    // MARK: - Polling

    /// One immediate refresh — used on launch, on wrist-raise (foreground
    /// activation), and on pull-to-refresh.
    func refreshNow() async {
        guard phase == .ready else { return }
        do {
            let fetched = try await session.needsYou()
            items = fetched
            consecutiveFailures = 0
            lastError = nil
            feed = .loaded(Date())
            queuedCount = queue.pendingCount()
            // A live server also drains whatever decisions were queued.
            let report = await queue.drain(using: session)
            queuedCount = queue.pendingCount()
            if !report.decidedElsewhere.isEmpty {
                // The server already acted — refetch so the feed shows the
                // server's truth instead of a card the analyst already
                // answered.
                items = (try? await session.needsYou()) ?? items
            }
        } catch let error as VigilWatchAPIError {
            handle(error)
        } catch {
            lastError = String(describing: error)
        }
    }

    private func handle(_ error: VigilWatchAPIError) {
        switch error {
        case .notConfigured:
            phase = .needsHandoff
        case .authRevoked:
            // Session revoked — keep the queue (decisions survive) but ask
            // for a fresh handoff.
            phase = .needsHandoff
            lastError = "Session ended — open Vigil on iPhone to reconnect"
        case .network, .http, .decoding:
            consecutiveFailures += 1
            lastError = VigilWatchSession.describe(error)
            switch feed {
            case .loaded(let at), .stale(let at):
                // Two consecutive failures → stale: keep the last data on
                // screen but label it with its age (the spec's state table).
                if consecutiveFailures >= 2 { feed = .stale(at) }
            case .idle:
                feed = .stale(Date())
            }
        case .alreadyDecided:
            break // handled by callers
        }
        queuedCount = queue.pendingCount()
    }

    /// Starts the foreground poll loop — 20 s cadence with jittered
    /// backoff on failure, matching the console's approvals poller.
    func startPolling() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            await self?.pollLoop()
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    private func pollLoop() async {
        while !Task.isCancelled {
            await refreshNow()
            let failures = consecutiveFailures
            let delay = PollPlan.backgroundDelay(
                consecutiveFailures: failures,
                random: Double.random(in: 0...1)
            )
            let interval = failures > 0 ? delay : PollPlan.foregroundInterval
            try? await Task.sleep(for: .seconds(interval))
        }
    }

    // MARK: - Decisions

    /// What one card interaction resolved to — the card owns the gestures
    /// (tap, hold, reject sheet, undo); the state routes the commit.
    enum CardDecision {
        /// Reversible approve — a tap that commits and starts the fuse.
        case approve
        /// Irreversible approve — the 1.6 s hold completed.
        case approveHold
        /// Reject with the mandatory reason.
        case reject(reason: String)
        /// Undo inside the fuse window.
        case undo(fuse: UndoFuse)
    }

    func commit(_ decision: CardDecision, for item: NeedsYouItem) async {
        switch decision {
        case .approve:
            await approve(item)
        case .approveHold:
            await approveIrreversible(item)
        case .reject(let reason):
            await reject(item, reason: reason)
        case .undo(let fuse):
            await undoApproval(item, fuse: fuse)
        }
    }

    /// Reversible approve: tap commits immediately, the 8 s undo fuse runs.
    func approve(_ item: NeedsYouItem) async {
        await commitDecision(item, kind: .approve, reason: nil)
    }

    /// Called when the hold-to-confirm gesture completes on an irreversible
    /// action — a completed hold commits with no undo fuse, ever.
    func approveIrreversible(_ item: NeedsYouItem) async {
        await commitDecision(item, kind: .approve, reason: nil)
    }

    func reject(_ item: NeedsYouItem, reason: String) async {
        await commitDecision(item, kind: .reject, reason: reason)
    }

    /// Undo inside the fuse: a reject of the already-approved action with
    /// the reserved reason (see `UndoFuse`). Outside the fuse this is
    /// refused — nothing after fuse expiry.
    func undoApproval(_ item: NeedsYouItem, fuse: UndoFuse) async {
        guard fuse.canUndo() else { return }
        await commitDecision(item, kind: .reject, reason: UndoFuse.undoReason)
    }

    private func commitDecision(
        _ item: NeedsYouItem,
        kind: QueuedDecision.Kind,
        reason: String?
    ) async {
        let entry = QueuedDecision(
            actionId: item.sourceId,
            kind: kind,
            reason: reason
        )
        queue.enqueue(entry)
        queuedCount = queue.pendingCount()
        let report = await queue.drain(using: session)
        queuedCount = queue.pendingCount()
        if !report.delivered.isEmpty {
            items.removeAll { $0.sourceId == item.sourceId }
            feed = .loaded(Date())
        } else if !report.retried.isEmpty {
            // Offline — the decision stays queued; the card shows queued
            // state via the badge. Leave the feed untouched.
            lastError = "Queued — will send when the server is reachable"
        } else if !report.decidedElsewhere.isEmpty {
            items.removeAll { $0.sourceId == item.sourceId }
        }
    }
}
