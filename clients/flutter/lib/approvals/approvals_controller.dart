import 'dart:async';
import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../api/vigil_client.dart';
import 'approval_machine.dart';
import 'approvals_poller.dart';

/// How a feed is doing — the console's `Phase` ('loading' | 'ready' | 'error').
enum FeedPhase { loading, ready, error }

/// A settled decision outcome the shell may surface as a toast/snackbar.
class ApprovalsOutcome {
  const ApprovalsOutcome({required this.text, required this.ok});

  final String text;
  final bool ok;
}

/// Owner of the approval flows' state — the phone counterpart of the
/// console's approvals poller + undo-fuse toast, shared by Home and
/// Decisions so both stay consistent with one poll and one fuse map.
///
/// Console parity (clients/web/src/screens/home/HomeScreen.tsx `fuse()` +
/// shell/toast.tsx): a reversible approve or any reject starts an 8 s fuse
/// during which the item hides from its feed and the count ("so a poll
/// can't bring them back"); the API call commits when the fuse expires —
/// undo inside the fuse cancels outright, nothing was ever sent (the
/// frozen contract has no un-approve). An irreversible hold-to-confirm
/// commits immediately with no fuse, ever.
class ApprovalsController extends ChangeNotifier {
  ApprovalsController({
    required VigilClient client,

    /// Display identity sent as `approved_by`/`rejected_by` (the server
    /// defaults to 'analyst' when null).
    String? approver,

    /// Injectable clock for fuse stamps and data-age labels. Timer drives
    /// expiry — this only timestamps, so tests need no fake wall clock.
    DateTime Function()? now,
    math.Random? jitterRandom,
    void Function(ApprovalsOutcome outcome)? onOutcome,
  })  : _client = client,
        _approver = approver,
        _now = now ?? DateTime.now,
        _jitter = jitterRandom ?? math.Random(),
        _onOutcome = onOutcome {
    _poller = PollTimer(
      onTick: () => refresh(),
      nextDelay: () => nextPollDelay(
        consecutiveFailures: _consecutiveFailures,
        jitter01: _jitter.nextDouble(),
      ),
    );
  }

  final VigilClient _client;
  final String? _approver;
  final DateTime Function() _now;
  final math.Random _jitter;
  final void Function(ApprovalsOutcome outcome)? _onOutcome;

  /// The generated approvals API of the frozen contract — one instance
  /// over the client's own authenticated dio.
  late final _approvalsApi = _client.v1.getApprovalsApi();

  late final PollTimer _poller;

  // Needs-you feed (GET /api/v1/approvals/needs-you), oldest first.
  List<NeedsYouItem> _needsYou = const [];
  int _needsYouCount = 0;
  FeedPhase _needsYouPhase = FeedPhase.loading;
  String? _needsYouError;

  // Pending approvals queue (GET /api/v1/approvals?status=pending).
  List<PendingActionResponse> _pending = const [];
  FeedPhase _pendingPhase = FeedPhase.loading;
  String? _pendingError;

  // Fusing decisions by action id; their Timers commit at expiry.
  final Map<String, ApprovalFuse> _fuses = {};
  final Map<String, Timer> _fuseTimers = {};

  // The one action committing right now (the console's single busyRef).
  String? _busyId;

  int _consecutiveFailures = 0;
  DateTime? _lastGoodAt;
  bool _refreshing = false;
  ApprovalsOutcome? _lastOutcome;

  // ---------------------------------------------------------------- reads

  /// Needs-you items whose fuse is not running — console rule: cards whose
  /// fuse is running stay out of the list and the count, so a poll can't
  /// bring them back.
  List<NeedsYouItem> get needsYou =>
      _needsYou.where((i) => !_fuses.containsKey(i.sourceId)).toList();

  List<NeedsYouItem> get allNeedsYou => List.unmodifiable(_needsYou);
  int get needsYouCount => _needsYouCount;
  FeedPhase get needsYouPhase => _needsYouPhase;
  String? get needsYouError => _needsYouError;

  /// The server's needs-you count minus items hidden behind a running fuse
  /// (floored at 0) — what the Home headline shows.
  int get shownNeedsYouCount =>
      math.max(0, _needsYouCount - (_needsYou.length - needsYou.length));

  /// Pending approvals the Decisions screen renders, fuse-hidden like the
  /// needs-you feed.
  List<PendingActionResponse> get pending =>
      _pending.where((a) => !_fuses.containsKey(a.actionId)).toList();

  List<PendingActionResponse> get allPending => List.unmodifiable(_pending);
  FeedPhase get pendingPhase => _pendingPhase;
  String? get pendingError => _pendingError;

  Map<String, ApprovalFuse> get fuses => Map.unmodifiable(_fuses);
  String? get busyId => _busyId;
  bool isBusy(String actionId) => _busyId == actionId;
  bool isFusing(String actionId) => _fuses.containsKey(actionId);

  /// Two consecutive poll failures → the stale state: last data stays
  /// visible with its age and a reconnecting banner.
  bool get stale => isStale(_consecutiveFailures);
  DateTime? get lastGoodAt => _lastGoodAt;
  int get consecutiveFailures => _consecutiveFailures;
  ApprovalsOutcome? get lastOutcome => _lastOutcome;

  DateTime now() => _now();

  // ------------------------------------------------------------------ poll

  /// Starts the 20 s cadence with an immediate poll (shell attach). No-op
  /// when already running.
  void startPolling() => _poller.startNow();

  /// App backgrounded — stop polling; running fuses keep their timers.
  void pause() => _poller.pause();

  /// App foregrounded — refresh immediately, then resume the cadence.
  void resume() => _poller.resumeNow();

  /// One poll: needs-you + pending queue in parallel. Failures update the
  /// feeds' error state and the stale counter; they never throw out of
  /// this method (the poller owns no error handling).
  Future<void> refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    var failed = false;
    try {
      await Future.wait([_loadNeedsYou(), _loadPending()]);
    } on Exception {
      // Future.wait rethrows the first child error; each load already
      // recorded its own feed state — this guard keeps refresh
      // never-throwing for the poller.
      failed = true;
    } finally {
      _refreshing = false;
    }

    if (failed) {
      _consecutiveFailures += 1;
    } else {
      _consecutiveFailures = 0;
      _lastGoodAt = _now();
    }
    notifyListeners();
  }

  Future<void> _loadNeedsYou() async {
    try {
      final res = await _approvalsApi.getApiV1ApprovalsNeedsYou();
      final data = res.data;
      final items = (data?.items?.toList() ?? const <NeedsYouItem>[])
        ..sort(_oldestFirst);
      final count = data?.count ?? items.length;
      _needsYou = items;
      _needsYouCount = count;
      _needsYouPhase = FeedPhase.ready;
      _needsYouError = null;
      notifyListeners();
    } on Exception catch (e) {
      _needsYouPhase = FeedPhase.error;
      _needsYouError = _errorText(e, 'Could not load what needs you');
      notifyListeners();
      rethrow;
    }
  }

  Future<void> _loadPending() async {
    try {
      final res =
          await _approvalsApi.getApiV1Approvals(status: 'pending');
      final actions =
          res.data?.actions?.toList() ?? const <PendingActionResponse>[];
      _pending = actions;
      _pendingPhase = FeedPhase.ready;
      _pendingError = null;
      notifyListeners();
    } on Exception catch (e) {
      _pendingPhase = FeedPhase.error;
      _pendingError = _errorText(e, 'Could not load approvals');
      notifyListeners();
      rethrow;
    }
  }

  // ------------------------------------------------------------- decisions

  /// Reversible approve (or any reject): start the 8 s undo fuse with the
  /// decision queued behind it. [reason] carries the mandatory rejection
  /// reason for [FuseVerb.reject].
  void beginFused({
    required String actionId,
    required String title,
    required FuseVerb verb,
    String? reason,
  }) {
    if (_fuses.containsKey(actionId) || _busyId != null) return;
    _fuses[actionId] = ApprovalFuse(
      actionId: actionId,
      title: title,
      verb: verb,
      reason: reason,
      startedAt: _now(),
    );
    _fuseTimers[actionId] = Timer(undoFuseLength, () => _commitFuse(actionId));
    notifyListeners();
  }

  /// Undo inside the fuse — cancels the queued decision; nothing was sent.
  void undo(String actionId) {
    _fuseTimers.remove(actionId)?.cancel();
    if (_fuses.remove(actionId) != null) {
      notifyListeners();
    }
  }

  /// Irreversible hold-to-confirm path: commit now, no fuse, no undo, ever.
  Future<void> approveNow({
    required String actionId,
    required String title,
  }) async {
    if (_busyId != null || _fuses.containsKey(actionId)) return;
    _busyId = actionId;
    notifyListeners();
    try {
      await _postApprove(actionId);
      _emit('Approved: $title', ok: true);
    } on Exception catch (e) {
      _emit(_errorText(e, 'Could not update that decision'), ok: false);
    } finally {
      _busyId = null;
      notifyListeners();
      // Re-render around the server's truth either way (409/404 mean the
      // action was already decided — the server is the record).
      await refresh();
    }
  }

  Future<void> _commitFuse(String actionId) async {
    final fuse = _fuses.remove(actionId);
    _fuseTimers.remove(actionId);
    if (fuse == null) return;
    notifyListeners();
    try {
      switch (fuse.verb) {
        case FuseVerb.approve:
          await _postApprove(actionId);
        case FuseVerb.reject:
          await _postReject(actionId, reason: fuse.reason ?? 'Rejected');
      }
      _emit('${fuse.verb.pastTense}: ${fuse.title}', ok: true);
    } on Exception catch (e) {
      _emit(_errorText(e, 'Could not update that decision'), ok: false);
    } finally {
      await refresh();
    }
  }

  Future<void> _postApprove(String actionId) async {
    await _approvalsApi.postApiV1ApprovalsActionIdApprove(
      actionId: actionId,
      approveRequest: (ApproveRequestBuilder()..approvedBy = _approver).build(),
    );
  }

  Future<void> _postReject(String actionId, {required String reason}) async {
    await _approvalsApi.postApiV1ApprovalsActionIdReject(
      actionId: actionId,
      rejectRequest:
          (RejectRequestBuilder()
                ..reason = reason
                ..rejectedBy = _approver)
              .build(),
    );
  }

  // ----------------------------------------------------------------- misc

  void _emit(String text, {required bool ok}) {
    _lastOutcome = ApprovalsOutcome(text: text, ok: ok);
    _onOutcome?.call(_lastOutcome!);
  }

  @override
  void dispose() {
    _poller.dispose();
    for (final timer in _fuseTimers.values) {
      timer.cancel();
    }
    _fuseTimers.clear();
    super.dispose();
  }

  // ---------------------------------------------------------- pure helpers

  static int _oldestFirst(NeedsYouItem a, NeedsYouItem b) =>
      (parseCreatedAt(a.createdAt) ?? DateTime.utc(1970))
          .compareTo(parseCreatedAt(b.createdAt) ?? DateTime.utc(1970));

  /// Error copy for a failure — the server's `detail` when it answered,
  /// then dio's message, else the fallback (the console's `errorText`).
  static String _errorText(Object error, String fallback) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data['detail'] is String) {
        final detail = data['detail'] as String;
        if (detail.trim().isNotEmpty) return detail;
      }
      final message = error.message;
      if (message != null && message.trim().isNotEmpty) return message;
    }
    return fallback;
  }
}
