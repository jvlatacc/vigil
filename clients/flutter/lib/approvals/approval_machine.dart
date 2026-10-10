/// The approval state machine's pure rules — one module, no I/O, no
/// widgets: the undo fuse (8 s deferred commit), hold-to-confirm length,
/// poll cadence and jittered backoff, stale rule, and the time formats the
/// console's Home screen renders. Timers and API calls live in
/// `approvals_poller.dart` / `approvals_controller.dart`; everything here is
/// trivially unit-testable without fake async.
library;

/// Undo fuse — the console's `vg-fuse 8s linear` / toast `FUSE_MS = 8000`
/// (docs/design/console/components/undo-fuse.md). A reversible decision is
/// final when the bar is gone; until then undo cancels it outright.
const Duration undoFuseLength = Duration(seconds: 8);

/// Hold to confirm — the console's 1.6 s press (the poor fill grows over
/// 1.6 s; release early cancels; completion cannot be undone).
const Duration holdConfirmLength = Duration(milliseconds: 1600);

/// Approvals poll cadence — the console's `APPROVALS_POLL_MS = 20_000`
/// (clients/web/src/screens/home/HomeScreen.tsx).
const Duration approvalsPollInterval = Duration(seconds: 20);

/// Ceiling of the jittered exponential backoff after poll failures. The
/// console has no backoff at all (a fixed interval); a phone must not
/// hammer a struggling server, and 5 min keeps reconnecting honest.
const Duration maxPollBackoff = Duration(minutes: 5);

/// Consecutive poll failures before the feed is labeled stale ("Checked
/// Xm ago — reconnecting"). One failure is a blip; two is a pattern.
const int staleAfterFailures = 2;

/// Delay until the next approvals poll after [consecutiveFailures]. A
/// healthy poll keeps the console's exact 20 s cadence; a failure keeps
/// the base cadence with ±20% jitter, and growth doubles per extra
/// failure, capped at [maxBackoff]. [jitter01] is a fraction in [0, 1) —
/// inject a fixed value in tests.
Duration nextPollDelay({
  required int consecutiveFailures,
  Duration base = approvalsPollInterval,
  Duration maxBackoff = maxPollBackoff,
  required double jitter01,
}) {
  if (consecutiveFailures <= 0) return base;
  final clampedJitter = jitter01.clamp(0.0, 0.999999).toDouble();
  final factor = _pow2(consecutiveFailures - 1) * (0.8 + 0.4 * clampedJitter);
  final millis = base.inMilliseconds * factor;
  final capped = millis >= maxBackoff.inMilliseconds ? maxBackoff.inMilliseconds.toDouble() : millis;
  return Duration(milliseconds: capped.round());
}

double _pow2(int exponent) => exponent == 0 ? 1.0 : _pow2(exponent - 1) * 2;

/// Whether [consecutiveFailures] consecutive poll failures put the feed in
/// the stale state (banner with the data age, reconnecting).
bool isStale(int consecutiveFailures) =>
    consecutiveFailures >= staleAfterFailures;

/// The pending decision's moment in the undo fuse. The fuse runs while the
/// fused toast shows "Approving/Rejecting: …" with an Undo button; expiry
/// commits the queued API call.
enum FuseStage { running, expired }

enum FuseVerb {
  approve('Approving', 'Approved'),
  reject('Rejecting', 'Rejected');

  const FuseVerb(this.presentTense, this.pastTense);

  final String presentTense;
  final String pastTense;
}

class ApprovalFuse {
  ApprovalFuse({
    required this.actionId,
    required this.title,
    required this.verb,
    required this.startedAt,
    this.reason,
  }) : expiresAt = startedAt.add(undoFuseLength);

  /// The approval action this fuse will commit (needs-you `source_id` /
  /// `PendingActionResponse.action_id`).
  final String actionId;
  final String title;
  final FuseVerb verb;

  /// The mandatory rejection reason when [verb] is [FuseVerb.reject].
  final String? reason;
  final DateTime startedAt;
  final DateTime expiresAt;

  FuseStage stageAt(DateTime now) =>
      now.isBefore(expiresAt) ? FuseStage.running : FuseStage.expired;

  /// Fuse time left — drives the undo bar's width (scaleX of remaining).
  Duration remainingAt(DateTime now) {
    final left = expiresAt.difference(now);
    return left.isNegative ? Duration.zero : left;
  }

  /// Fraction of the fuse left in [0, 1] — 1 just after start, 0 at commit.
  double progressAt(DateTime now) =>
      remainingAt(now).inMicroseconds / undoFuseLength.inMicroseconds;
}

/// Parses a naive API timestamp as UTC — the console's `parseCreatedAt`
/// ("Naive timestamps from the API are UTC. `Date.parse` would read them as
/// local."). Returns null when unparseable.
DateTime? parseCreatedAt(String? createdAt) {
  if (createdAt == null || createdAt.isEmpty) return null;
  final hasZone =
      RegExp(r'(?:Z|[+-]\d{2}:\d{2})$').hasMatch(createdAt);
  final parsed = DateTime.tryParse(hasZone ? createdAt : '${createdAt}Z');
  return parsed?.toUtc();
}

/// How long a pending item has waited — the console's `waited()`:
/// "Waited under a minute", "Waited 12m", "Waited 3h 4m"; '' unparseable.
String waitedLabel(String? createdAt, DateTime now) {
  final then = parseCreatedAt(createdAt);
  if (then == null) return '';
  final minutes = now.difference(then).inMinutes;
  if (minutes < 1) return 'Waited under a minute';
  if (minutes < 60) return 'Waited ${minutes}m';
  final hours = minutes ~/ 60;
  final rem = minutes % 60;
  return rem > 0 ? 'Waited ${hours}h ${rem}m' : 'Waited ${hours}h';
}

/// The stale banner's data age — "Checked just now" under a minute, then
/// "Checked 4 min ago" / "Checked 2 h 5 min ago".
String dataAgeLabel(DateTime? lastGoodAt, DateTime now) {
  if (lastGoodAt == null) return 'Checked never';
  final age = now.difference(lastGoodAt);
  if (age.inMinutes < 1) return 'Checked just now';
  if (age.inMinutes < 60) return 'Checked ${age.inMinutes} min ago';
  final hours = age.inMinutes ~/ 60;
  final rem = age.inMinutes % 60;
  return rem > 0 ? 'Checked $hours h $rem min ago' : 'Checked $hours h ago';
}
