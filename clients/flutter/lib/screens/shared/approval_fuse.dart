import 'dart:async';

import 'package:flutter/material.dart';

import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';

/// A reversible action waiting out its undo fuse. The commit runs when
/// the fuse ends — until then nothing has been sent, so Undo is a pure
/// cancellation (the console's `notifyUndoable`, `shell/toast.tsx`).
class FusedAction {
  FusedAction({
    required this.key,
    required this.message,
    required this.commit,
    this.doneText,
  });

  /// Identifies the subject (an action id); one fuse per key — starting a
  /// second fuse for a key already pending is a no-op.
  final String key;

  /// Banner copy while the fuse runs: "Approving · Isolate host web-prod-3".
  final String message;

  /// The call the fuse owns — approve/reject — run only on expiry.
  final Future<void> Function() commit;

  /// Toast copy once the commit lands ok ("Approved · resuming run").
  final String? doneText;
}

/// An outcome of a fused commit, after the bar ran out.
class FuseEvent {
  const FuseEvent.ok(this.doneText) : error = null;
  const FuseEvent.failure(this.error) : doneText = null;

  final String? doneText;
  final Object? error;
}

class _RunningFuse {
  _RunningFuse(this.action, this.timer);

  final FusedAction action;
  final Timer timer;

  /// Milliseconds burned since the fuse started, advanced by the
  /// controller's tick — drives the banner's shrinking bar without
  /// touching the wall clock (stays deterministic under pump()).
  int elapsedMs = 0;
}

/// The shell-level undo fuse. Owned by the shell (not a screen) so a fuse
/// survives navigating away — a reversible approval keeps ticking while
/// the user reads another case, exactly like the console's toast fuses.
///
/// Screens read [pendingKeys] to keep subjects whose fuse is running out
/// of lists and counts (so a poll can't flash them back), and reload when
/// [settled] changes after a fused commit lands.
class FuseController extends ChangeNotifier {
  FuseController({
    this.fuseDuration = const Duration(seconds: 8),
    this.onEvent,
  });

  /// The console's 8 s reversible window (undo-fuse spec).
  final Duration fuseDuration;

  /// Resolves when a fused commit settles, ok or not.
  final void Function(FuseEvent event)? onEvent;

  static const _tick = Duration(milliseconds: 100);

  final List<_RunningFuse> _running = [];
  Timer? _ticking;
  int _settled = 0;

  /// Bumps each time a fused commit settles, ok or not. Screens listen
  /// and reload on change.
  int get settled => _settled;

  /// Keys whose fuse is running — hide these subjects.
  List<String> get pendingKeys =>
      [for (final fuse in _running) fuse.action.key];

  bool isPending(String key) => _running.any((f) => f.action.key == key);

  FusedAction? actionFor(String key) {
    for (final fuse in _running) {
      if (fuse.action.key == key) return fuse.action;
    }
    return null;
  }

  /// 1.0 → bar full, 0.0 → the fuse ran out.
  double remainingFraction(String key) {
    for (final fuse in _running) {
      if (fuse.action.key != key) continue;
      return (1.0 - fuse.elapsedMs / fuseDuration.inMilliseconds)
          .clamp(0.0, 1.0);
    }
    return 0.0;
  }

  /// Start the fuse. A second fuse for a key already pending is ignored.
  void start(FusedAction action) {
    if (isPending(action.key)) return;
    final timer = Timer(fuseDuration, () => _commit(action));
    _running.add(_RunningFuse(action, timer));
    _ticking ??= Timer.periodic(_tick, _advance);
    notifyListeners();
  }

  /// Cancel the fuse — nothing has been sent, nothing to revert.
  void undo(String key) {
    final index = _running.indexWhere((f) => f.action.key == key);
    if (index < 0) return;
    _running[index].timer.cancel();
    _running.removeAt(index);
    _stopTickingWhenIdle();
    notifyListeners();
  }

  void _advance(Timer _) {
    for (final fuse in _running) {
      fuse.elapsedMs += _tick.inMilliseconds;
    }
    notifyListeners();
  }

  Future<void> _commit(FusedAction action) async {
    _running.removeWhere((f) => f.action.key == action.key);
    _stopTickingWhenIdle();
    // The key stays out of lists while the commit is in flight.
    notifyListeners();
    try {
      await action.commit();
      onEvent?.call(
        action.doneText == null
            ? const FuseEvent.ok(null)
            : FuseEvent.ok(action.doneText!),
      );
    } catch (error) {
      onEvent?.call(FuseEvent.failure(error));
    } finally {
      _settled += 1;
      notifyListeners();
    }
  }

  void _stopTickingWhenIdle() {
    if (_running.isNotEmpty) return;
    _ticking?.cancel();
    _ticking = null;
  }

  @override
  void dispose() {
    // Like the console on unmount: clearing timers drops any fused
    // commit — an action is only final once its bar has run out.
    _ticking?.cancel();
    for (final fuse in _running) {
      fuse.timer.cancel();
    }
    _running.clear();
    super.dispose();
  }
}

/// Carries a [FuseController] to every screen, the way the console's
/// ToastProvider does.
class FuseScope extends InheritedNotifier<FuseController> {
  const FuseScope({
    super.key,
    required FuseController controller,
    required super.child,
  }) : super(notifier: controller);

  static FuseController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<FuseScope>();
    assert(scope != null, 'No FuseScope above this screen');
    return scope!.notifier!;
  }
}

/// The running fuse, rendered as the console's fused toast: message,
/// outlined Undo pill, and a 2px accent bar that runs out in 8 s
/// (undo-fuse spec). Docked by the shell above its bottom chrome.
class FusedActionBanner extends StatelessWidget {
  const FusedActionBanner({super.key, required this.controller});

  final FuseController controller;

  @override
  Widget build(BuildContext context) {
    if (controller.pendingKeys.isEmpty) return const SizedBox.shrink();
    final colors = context.vigilColors;
    final key = controller.pendingKeys.first;
    final action = controller.actionFor(key);
    if (action == null) return const SizedBox.shrink();
    return Container(
      key: const Key('fused-action-banner'),
      margin: const EdgeInsets.all(12),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.ln1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(Icons.info_outline, size: 15, color: colors.tx2),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  action.message,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.body,
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                key: const Key('fuse-undo'),
                onPressed: () => controller.undo(key),
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 11),
                  minimumSize: const Size(0, 26),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(999),
                    side: BorderSide(color: colors.ln2),
                  ),
                ),
                child: Text(
                  'Undo',
                  style: VigilTypography.label.copyWith(color: colors.tx0),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: SizedBox(
              height: 2,
              child: Stack(
                children: [
                  Positioned.fill(child: ColoredBox(color: colors.ln0)),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: FractionallySizedBox(
                      widthFactor: controller.remainingFraction(key),
                      child: Container(color: colors.ac),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
