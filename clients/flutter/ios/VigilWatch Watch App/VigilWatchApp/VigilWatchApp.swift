import SwiftUI
import VigilWatchClient
import WatchConnectivity

@main
struct VigilWatchApp: App {
    @State private var state = WatchAppState()

    var body: some Scene {
        WindowGroup {
            RootView(state: state)
                // The console is dark-first; the watch renders dark always.
                .preferredColorScheme(.dark)
                .task {
                    state.startPolling()
                    HandoffConnector.shared.activate(state: state)
                }
        }
    }
}

/// Receives WatchConnectivity messages from the paired iPhone and feeds
/// them into the app state. Lives here rather than in the package because
/// WatchConnectivity is an OS framework, not package-testable logic —
/// the package owns everything except this thin receive shim.
@MainActor
final class HandoffConnector: NSObject, WCSessionDelegate {
    /// Message key — must match the phone's `VigilWatchHandoff` channel.
    static let messageKey = "session_handoff"

    static let shared = HandoffConnector()
    private weak var state: WatchAppState?

    func activate(state: WatchAppState) {
        self.state = state
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        session.activate()
        // applicationContext carries the latest handoff even before a live
        // message arrives (install-time, watch restarts).
        let context = session.receivedApplicationContext
        if let payload = context[Self.messageKey] {
            state.applyHandoff(SessionHandoff(payload: payload))
        }
    }

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if let payload = session.receivedApplicationContext[Self.messageKey] {
            state?.applyHandoff(SessionHandoff(payload: payload))
        }
    }

    /// Live handoff while both ends are reachable.
    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if let payload = message[Self.messageKey] as? [String: Any] {
            state?.applyHandoff(SessionHandoff(payload: payload))
        }
    }

    /// Background-reliable handoff (phone may deliver while the watch app
    /// is not running).
    func session(
        _ session: WCSession,
        didReceiveApplicationContext applicationContext: [String: Any]
    ) {
        if let payload = applicationContext[Self.messageKey] {
            state?.applyHandoff(SessionHandoff(payload: payload))
        }
    }
}
