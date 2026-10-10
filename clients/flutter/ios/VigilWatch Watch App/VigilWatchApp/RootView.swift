import SwiftUI
import VigilWatchClient

/// Root: handoff gate → needs-you feed. Mirrors the spec's state table —
/// no session shows "Open Vigil on iPhone"; a ready session shows the feed
/// with age labels and the queued-decisions badge.
struct RootView: View {
    @State var state: WatchAppState

    var body: some View {
        switch state.phase {
        case .needsHandoff:
            HandoffPromptView(error: state.lastError)
        case .ready:
            NeedsYouListView(state: state)
        }
    }
}

/// The no-session screen. The watch never logs in — the phone owns
/// credentials; pairing hands over a dedicated token pair.
struct HandoffPromptView: View {
    let error: String?

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "applewatch.radiowaves.left.and.right")
                .font(.system(size: 30))
                .foregroundStyle(VigilWatchTheme.accent)
            Text("Open Vigil on iPhone")
                .font(.headline)
            Text("Vigil sends this watch its own secure sign-in — nothing to type here.")
                .font(.caption2)
                .foregroundStyle(VigilWatchTheme.textMeta)
                .multilineTextAlignment(.center)
            if let error {
                Text(error)
                    .font(.caption2)
                    .foregroundStyle(VigilWatchTheme.fair)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
    }
}

/// "Needs you" — one card per NeedsYouItem, plus the staleness banner and
/// the queued-decisions badge.
struct NeedsYouListView: View {
    @State var state: WatchAppState

    var body: some View {
        NavigationStack {
            List {
                if let banner = bannerText {
                    Text(banner)
                        .font(.caption2)
                        .foregroundStyle(VigilWatchTheme.fair)
                        .listRowBackground(VigilWatchTheme.card)
                }
                if state.queuedCount > 0 {
                    Text("\(state.queuedCount) queued · retries automatically")
                        .font(.caption2)
                        .foregroundStyle(VigilWatchTheme.accent)
                        .listRowBackground(VigilWatchTheme.card)
                }
                ForEach(state.items) { item in
                    ApprovalCardView(item: item) { decision in
                        Task { await state.commit(decision, for: item) }
                    }
                    .listRowBackground(VigilWatchTheme.card)
                    .listRowInsets(EdgeInsets(top: 6, leading: 6, bottom: 6, trailing: 6))
                }
                if state.items.isEmpty, bannerText == nil {
                    Text("Nothing needs a person")
                        .font(.headline)
                        .foregroundStyle(VigilWatchTheme.textMeta)
                }
            }
            .listStyle(.carousel)
            .navigationTitle(needYouTitle)
            .navigationBarTitleDisplayMode(.nested)
            .refreshAction {
                await state.refreshNow()
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Text(ageText)
                        .font(.caption2)
                        .foregroundStyle(VigilWatchTheme.textMeta)
                }
            }
        }
    }

    private var needYouTitle: String {
        if state.items.isEmpty { return "Needs you" }
        return "Needs you · \(state.items.count)"
    }

    private var bannerText: String? {
        state.lastError
    }

    /// "Checked 14:22" or "Last checked 4 min ago — reconnecting" per the
    /// spec's stale-state copy. UTC 24-hour formatting per DESIGN.md §2.
    private var ageText: String {
        switch state.feed {
        case .loaded(let at):
            return "Checked \(Self.utcTime(at))"
        case .stale(let at):
            let minutes = Int((Date().timeIntervalSince(at) / 60).rounded())
            return "Last checked \(max(1, minutes)) min ago — reconnecting"
        case .idle:
            return ""
        }
    }

    static func utcTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }
}
