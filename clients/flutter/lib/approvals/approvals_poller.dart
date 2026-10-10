import 'dart:async';

/// Timer loop for the approvals cadence. Runs [onTick] immediately on
/// start/resume and then on whatever delay [nextDelay] returns after each
/// completed tick — the controller feeds it `nextPollDelay` with its live
/// failure count, so backoff is the machine's math, this is only wiring.
///
/// - A tick that is still running never overlaps the next one.
/// - [pause] stops the loop (app backgrounded); [resumeNow] ticks
///   immediately and restarts the cadence (lifecycle-aware resume).
/// - [onTick] must not throw (the controller owns error state); this class
///   only owns time.
class PollTimer {
  PollTimer({required Future<void> Function() onTick, required Duration Function() nextDelay})
      : _onTick = onTick,
        _nextDelay = nextDelay;

  final Future<void> Function() _onTick;
  final Duration Function() _nextDelay;

  Timer? _timer;
  bool _ticking = false;
  bool _paused = false;
  bool _started = false;
  bool _disposed = false;

  /// Starts the cadence with an immediate first tick. Re-starting a running
  /// timer is a no-op — callers own restart semantics via pause/resume.
  void startNow() {
    if (_disposed || _started) return;
    _started = true;
    _paused = false;
    unawaited(_tickAndSchedule());
  }

  /// App backgrounded — stop the cadence (no timer while paused).
  void pause() {
    if (_disposed) return;
    _paused = true;
    _timer?.cancel();
    _timer = null;
  }

  /// App foregrounded — tick immediately, then continue the cadence.
  void resumeNow() {
    if (_disposed || !_started || !_paused) return;
    _paused = false;
    unawaited(_tickAndSchedule());
  }

  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _tickAndSchedule() async {
    if (_ticking || _paused || _disposed) return;
    _ticking = true;
    try {
      await _onTick();
    } finally {
      _ticking = false;
      if (!_paused && !_disposed) {
        _timer?.cancel();
        _timer = Timer(_nextDelay(), _tickAndSchedule);
      }
    }
  }
}
