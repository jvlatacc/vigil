import 'dart:async';
import 'dart:math';

import 'package:flutter/widgets.dart';

/// Polls [tick] forever on [interval], backing off with jitter when it
/// fails, and holding when the app is backgrounded.
///
/// The console's cadences are bare `setInterval`s (findings 10 s, approvals
/// 20 s — `useFindings.ts:44`, `useDecisions.ts:178`); a mobile client
/// needs the same cadence with three additions the console gets for free:
///
/// * **Silent background ticks.** Only the first (or explicit) load may
///   show a loading phase — a background blip must not blank the screen
///   (`useFindings.ts`: "a background blip shouldn't blank the table").
/// * **Jittered exponential backoff.** A dead server must not produce a
///   metronome of doomed requests; backoff doubles per consecutive
///   failure, jitters ±10%, and caps at [backoffCap]. Success resets it.
/// * **Lifecycle awareness.** Ticks hold while backgrounded and fire once
///   on resume, so the poll never drains the battery behind the lock
///   screen. Desktop sessions rarely leave `resumed` and are unaffected.
///
/// Ticks run on real [Timer]s, so widget tests drive cadence with
/// `tester.pump(duration)` — no async gymnastics.
class PollingScheduler with WidgetsBindingObserver {
  PollingScheduler({
    required this.interval,
    required this.tick,
    this.backoffCap = const Duration(minutes: 5),
    this.lifecycleAware = true,
  });

  /// One poll. [silent] is false only for the first tick and for
  /// [refresh] — loads the user asked for and may surface a loading state
  /// for. Throwing marks the tick as failed and advances the backoff.
  final Future<void> Function(bool silent) tick;

  /// The cadence after a successful tick — the console's poll interval
  /// (findings 10 s, approvals 20 s).
  final Duration interval;

  /// The ceiling on backoff growth; a server down for longer than this is
  /// re-probed every [backoffCap] rather than never.
  final Duration backoffCap;

  /// Whether ticks hold while the app is backgrounded. Tests pass false
  /// when there is no meaningful lifecycle to observe.
  final bool lifecycleAware;

  final Random _random = Random();

  Timer? _timer;
  bool _started = false;
  bool _held = false;
  int _failures = 0;

  /// Consecutive failed ticks — resets on the first success. Exposed for
  /// tests (and for callers that want to say "retrying" after N failures).
  int get consecutiveFailures => _failures;

  /// The delay the next background tick would wait for if the current one
  /// fails — the current backoff with jitter applied.
  Duration get nextBackoff => _backoffFor(_failures);

  void start() {
    if (_started) return;
    _started = true;
    if (lifecycleAware) WidgetsBinding.instance.addObserver(this);
    _run(silent: false);
  }

  /// An explicit reload: reset the backoff and poll now, as a load the
  /// user asked for (a pull-to-refresh, a Retry button).
  void refresh() {
    if (!_started) return;
    _failures = 0;
    _run(silent: false);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        if (!_started || !_held) return;
        _held = false;
        // Fresh data on the way back into the foreground.
        _run(silent: true);
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        // Detached/locked: hold the cadence, resume on `resumed`.
        _timer?.cancel();
        _timer = null;
        _held = true;
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
        break;
    }
  }

  void dispose() {
    _timer?.cancel();
    if (lifecycleAware) WidgetsBinding.instance.removeObserver(this);
    _started = false;
  }

  void _run({required bool silent}) {
    _timer?.cancel();
    _timer = null;
    tick(silent)
        .then((_) {
          if (!_started) return;
          _failures = 0;
          _scheduleNext();
        })
        .catchError((Object error) {
          if (!_started) return;
          _failures += 1;
          _scheduleNext();
        });
  }

  void _scheduleNext() {
    if (_held) return;
    final delay = _failures == 0 ? interval : _backoffFor(_failures);
    _timer = Timer(delay, () => _run(silent: true));
  }

  /// `interval * 2^failures`, jittered ±10%, capped at [backoffCap].
  Duration _backoffFor(int failures) {
    // Milliseconds throughout: Duration arithmetic has no `>` against ints.
    final base = interval.inMilliseconds * pow(2, min(failures, 12)).toDouble();
    final jittered = base * (0.9 + 0.2 * _random.nextDouble());
    final capped = min(jittered, backoffCap.inMilliseconds.toDouble());
    return Duration(milliseconds: capped.round());
  }
}
