import SwiftUI
import VigilWatchClient
import WatchKit

/// One needs-you item as a decision card — the spec's watch mock: title,
/// reason, reversibility chip, then the guarded actions. A reversible
/// approve is a tap that flips into the 8 s undo fuse; an irreversible one
/// is the 1.6 s hold ring; reject opens the reason sheet.
struct ApprovalCardView: View {
    let item: NeedsYouItem
    /// Called with the resolved decision from any gesture on this card.
    let onDecision: (WatchAppState.CardDecision) -> Void

    @State private var fuse: UndoFuse?
    @State private var fuseNow = Date()
    @State private var showReject = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            chipRow
            Text(item.title)
                .font(.headline)
                .foregroundStyle(VigilWatchTheme.text)
                .lineLimit(3)
            if !item.reason.isEmpty {
                Text(item.reason)
                    .font(.caption2)
                    .foregroundStyle(VigilWatchTheme.textMeta)
                    .lineLimit(3)
            }
            actions
        }
        .padding(10)
        .background(VigilWatchTheme.card)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(VigilWatchTheme.hairline, lineWidth: 1)
        )
        .sheet(isPresented: $showReject) {
            RejectReasonSheet(itemTitle: item.title) { reason in
                showReject = false
                fuse = nil
                onDecision(.reject(reason: reason))
            }
        }
    }

    @ViewBuilder
    private var chipRow: some View {
        HStack(spacing: 6) {
            Text(chipTitle)
                .font(.caption2)
                .foregroundStyle(VigilWatchTheme.chipColor(for: item.reversibility))
            Spacer()
            if let createdAt = item.createdAtDate {
                Text(age(createdAt))
                    .font(.caption2)
                    .foregroundStyle(VigilWatchTheme.textMeta)
            }
        }
    }

    private var chipTitle: String {
        switch item.reversibility {
        case "reversible": return "reversible"
        case "irreversible": return "irreversible"
        default: return "review"
        }
    }

    @ViewBuilder
    private var actions: some View {
        if let fuse {
            committedRow(fuse)
        } else {
            actionRow
        }
    }

    /// The undo-fuse row after a reversible approve: countdown plus the
    /// Undo button; after expiry the undo button disappears — nothing
    /// after fuse expiry.
    private func committedRow(_ fuse: UndoFuse) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(VigilWatchTheme.good)
            TimelineView(.periodic(from: fuse.startedAt, by: 1)) { context in
                let remaining = fuse.remainingSeconds(now: context.date)
                Text(remaining > 0 ? "Approved · fuse \(Int(remaining))s" : "Approved")
                    .font(.caption2)
                    .foregroundStyle(VigilWatchTheme.good)
            }
            Spacer()
            if fuse.canUndo(now: fuseNow) {
                Button {
                    onDecision(.undo(fuse: fuse))
                    self.fuse = nil
                } label: {
                    Text("Undo")
                        .font(.caption2)
                }
                .buttonStyle(.bordered)
                .tint(VigilWatchTheme.accent)
            }
        }
        .task {
            // Re-render once the fuse has expired so the Undo button
            // disappears — nothing after fuse expiry.
            fuseNow = Date()
            try? await Task.sleep(for: .seconds(UndoFuse.duration + 0.2))
            fuseNow = Date()
        }
    }

    @ViewBuilder
    private var actionRow: some View {
        if item.reversibility == "irreversible" {
            // 1.6 s hold-to-confirm; releasing early cancels. No tap path
            // exists for irreversible actions.
            HoldToConfirmButton {
                onDecision(.approveHold)
            }
            Button {
                showReject = true
            } label: {
                Text("Reject")
                    .font(.caption)
            }
            .buttonStyle(.bordered)
            .tint(VigilWatchTheme.poor)
        } else {
            // Reversible approve is a plain tap — the undo fuse follows.
            Button {
                fuse = UndoFuse()
                onDecision(.approve)
            } label: {
                Text("Approve")
                    .font(.caption)
            }
            .buttonStyle(.borderedProminent)
            .tint(VigilWatchTheme.accent)
            Button {
                showReject = true
            } label: {
                Text("Reject")
                    .font(.caption)
            }
            .buttonStyle(.bordered)
            .tint(VigilWatchTheme.poor)
        }
    }

    /// "2 min ago" for the item's created_at (optional — absent renders
    /// nothing). The console's vocabulary is UTC 24-hour absolute time; on
    /// the wrist relative age wins for glanceability.
    private func age(_ createdAt: Date) -> String {
        let seconds = Int(Date().timeIntervalSince(createdAt))
        if seconds < 90 { return "now" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) min ago" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) h ago" }
        return "\(hours / 24) d ago"
    }
}

/// The 1.6 s hold-to-confirm ring for irreversible actions — same duration
/// as the console's `hold-to-confirm` spec. Releasing early cancels; a
/// completed hold fires exactly once.
struct HoldToConfirmButton: View {
    let onComplete: () -> Void

    @State private var holdStart: Date?
    @State private var progress: Double = 0
    @State private var fired = false
    @State private var ticker: Timer?

    var body: some View {
        ZStack {
            Circle()
                .stroke(VigilWatchTheme.poor.opacity(0.35), lineWidth: 4)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(
                    VigilWatchTheme.poor,
                    style: StrokeStyle(lineWidth: 4, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
            Text(progress > 0 ? "Keep holding" : "Hold")
                .font(.caption)
                .foregroundStyle(VigilWatchTheme.poor)
        }
        .frame(maxWidth: .infinity, minHeight: 44)
        .gesture(holdGesture)
        .onDisappear {
            ticker?.invalidate()
            ticker = nil
        }
    }

    private var holdGesture: some Gesture {
        LongPressGesture(minimumDuration: 0)
            .sequenced(before: DragGesture(minimumDistance: 0, coordinateSpace: .local))
            .onChanged { value in
                switch value {
                case .first:
                    beginHold()
                case .second:
                    if holdStart == nil { beginHold() }
                @unknown default:
                    break
                }
            }
            .onEnded { _ in
                ticker?.invalidate()
                ticker = nil
                if !fired {
                    // Released early — cancel. A completed hold is the only
                    // way an irreversible action commits.
                    holdStart = nil
                    progress = 0
                }
            }
    }

    private func beginHold() {
        guard ticker == nil else { return }
        fired = false
        holdStart = Date()
        ticker = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { timer in
            guard let start = holdStart else { timer.invalidate(); return }
            let elapsed = Date().timeIntervalSince(start)
            let hold = HoldProgress()
            progress = hold.fraction(elapsed: elapsed)
            if hold.isComplete(elapsed: elapsed), !fired {
                fired = true
                timer.invalidate()
                ticker = nil
                progress = 0
                holdStart = nil
                // Haptics confirm the irreversible commit.
                WKExtension.shared().playHaptic(.success)
                onComplete()
            }
        }
    }
}

/// Reject requires a reason — quick-picks plus free text (dictation is the
/// watch keyboard's default input). Submit stays disabled until a reason
/// exists; the trimmed value is what the server records.
struct RejectReasonSheet: View {
    let itemTitle: String
    let onSubmit: (String) -> Void

    @State private var text = ""

    /// Quick-picks from the console's vocabulary, shortened for a glance
    /// read.
    static let quickPicks = [
        "Not relevant",
        "False positive",
        "Too risky",
        "Handled without a person",
    ]

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(itemTitle)
                        .font(.headline)
                        .foregroundStyle(VigilWatchTheme.textMeta)
                }
                Section("Reason") {
                    ForEach(Self.quickPicks, id: \.self) { pick in
                        Button {
                            text = pick
                        } label: {
                            HStack {
                                Text(pick).font(.caption)
                                Spacer()
                                if text == pick {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(VigilWatchTheme.accent)
                                }
                            }
                        }
                    }
                    TextField("Or dictate a reason", text: $text)
                        .font(.caption)
                }
                Button {
                    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    onSubmit(trimmed)
                } label: {
                    Text("Reject")
                        .font(.caption)
                }
                .disabled(text.trimmingCharacters(
                    in: .whitespacesAndNewlines
                ).isEmpty)
            }
            .navigationTitle("Reject")
        }
    }
}
