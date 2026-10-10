import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/approvals/approvals_controller.dart';
import 'package:vigil_flutter/shell/screens.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/fake_adapter.dart';
import '../helpers/wired_vigil.dart';

/// A shell user that passes every gate Home and Decisions sit behind.
const _approver = UserProfile(
  username: 'jane',
  email: 'jane@corp.example',
  permissions: {
    'ai_decisions.approve': true,
    'cases.read': true,
    'settings.read': true,
  },
);

/// Jitter pinned at 0.5 makes the backoff factor exactly 1.0 — every delay
/// is a clean 2^n × 20 s, so pump windows are deterministic.
class _FixedRandom implements math.Random {
  _FixedRandom(this.value);
  final double value;

  @override
  double nextDouble() => value;

  @override
  bool nextBool() => true;

  @override
  int nextInt(int max) => 0;
}

RoutedAdapter _reversibleApi() => RoutedAdapter((options, r) {
      final path = r.path;
      if (path.contains('/api/v1/approvals/needs-you')) {
        return json(200, needsYouBody([needsYouItemBody()]));
      }
      if (path.contains('/api/v1/approvals')) {
        if (r.method == 'POST') return json(200, approvalActionResultBody());
        return json(200, approvalListBody([pendingActionBody()]));
      }
      return defaultApiHandler(options, r);
    });

RoutedAdapter _irreversibleApi() => RoutedAdapter((options, r) {
      final path = r.path;
      if (path.contains('/api/v1/approvals/needs-you')) {
        return json(200, [
          needsYouBody([
            needsYouItemBody(
              sourceId: 'a-2',
              title: 'Quarantine mailbox j.doe',
              reversibility: 'irreversible',
            ),
          ]),
        ].first);
      }
      if (path.contains('/api/v1/approvals')) {
        if (r.method == 'POST') return json(200, approvalActionResultBody());
        return json(
            200,
            approvalListBody([
              pendingActionBody(
                actionId: 'a-2',
                title: 'Quarantine mailbox j.doe',
                reversibility: 'irreversible',
              ),
            ]),
          );
      }
      return defaultApiHandler(options, r);
    });

/// Needs-you polls: the first [succeedFirst] succeed with the reversible
/// fixture, the next [failCount] return 500, everything after succeeds.
RoutedAdapter _flakyApi({required int failCount}) {
  var needsYouCalls = 0;
  return RoutedAdapter((options, r) {
    if (r.path.contains('/api/v1/approvals/needs-you')) {
      needsYouCalls += 1;
      if (needsYouCalls > 1 && needsYouCalls <= 1 + failCount) {
        return json(500, {'detail': 'down'});
      }
      return json(200, needsYouBody([needsYouItemBody()]));
    }
    if (r.path.contains('/api/v1/approvals')) {
      if (r.method == 'POST') return json(200, approvalActionResultBody());
      return json(200, approvalListBody([pendingActionBody()]));
    }
    return defaultApiHandler(options, r);
  });
}

List<RecordedRequest> _posts(RoutedAdapter api, String pathSubstring) =>
    api.requests
        .where((r) => r.method == 'POST' && r.path.contains(pathSubstring))
        .toList();

int _needsYouGets(RoutedAdapter api) =>
    api.requests.where((r) => r.path.contains('needs-you')).length;

/// Test harness that OWNS the approvals controller: its dispose runs during
/// widget-tree unmount — before flutter_test's pending-timer invariant —
/// so the poller's cadence timer is canceled in time. Tear-down callbacks
/// run AFTER that invariant check and cannot clean timers in time.
class _ShellHarness extends StatefulWidget {
  const _ShellHarness({
    required this.screen,
    required this.api,
    required this.onController,
  });

  final VigilScreen screen;
  final RoutedAdapter api;
  final void Function(ApprovalsController) onController;

  @override
  State<_ShellHarness> createState() => _ShellHarnessState();
}

class _ShellHarnessState extends State<_ShellHarness> {
  late final ApprovalsController controller;

  @override
  void initState() {
    super.initState();
    final client = wiredClient(
      auth: RoutedAdapter(defaultAuthHandler),
      api: widget.api,
    );
    controller = ApprovalsController(
      client: client,
      approver: 'jane',
      jitterRandom: _FixedRandom(0.5),
    );
    widget.onController(controller);
    controller.startPolling();
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: buildVigilThemeData(Brightness.dark),
      home: Scaffold(
        body: VigilShell(
          user: _approver,
          initialScreen: widget.screen,
          onSignOut: () {},
          approvals: controller,
        ),
      ),
    );
  }
}

Future<ApprovalsController> _pumpShellAt(
  WidgetTester tester, {
  required VigilScreen screen,
  required RoutedAdapter api,
}) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(400, 900);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.binding.setSurfaceSize(const Size(400, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  ApprovalsController? controller;
  await tester.pumpWidget(_ShellHarness(
    screen: screen,
    api: api,
    onController: (c) => controller = c,
  ));
  // Flush the first poll (needs-you + pending in parallel).
  await tester.pump(const Duration(milliseconds: 50));
  await tester.pump(const Duration(milliseconds: 50));
  return controller!;
}

void main() {
  group('reversible approve — the 8 s undo fuse (Home)', () {
    testWidgets('undo inside the fuse reverts and never posts', (tester) async {
      final api = _reversibleApi();
      final controller =
          await _pumpShellAt(tester, screen: VigilScreen.home, api: api);

      // The feed arrived: one card, one pending-approval count.
      expect(find.text('Isolate host web-prod-3'), findsOneWidget);
      expect(find.text('1 need you'), findsOneWidget);
      expect(controller.needsYouCount, 1);

      await tester.tap(find.byKey(const Key('approve-a-1')));
      await tester.pump();

      // The fuse is running — toast with undo, item out of the feed,
      // nothing on the wire yet.
      expect(find.text('Undo'), findsOneWidget);
      expect(controller.isFusing('a-1'), isTrue);
      expect(_posts(api, '/approve'), isEmpty);
      expect(find.text('Isolate host web-prod-3'), findsNothing);

      // Halfway through the fuse, undo cancels the queued decision.
      await tester.pump(const Duration(seconds: 4));
      await tester.tap(find.text('Undo'));
      await tester.pump();

      expect(controller.isFusing('a-1'), isFalse);
      expect(find.text('Isolate host web-prod-3'), findsOneWidget);
      expect(find.text('Undo'), findsNothing);

      // Past the point where the fuse would have committed — nothing sent.
      await tester.pump(const Duration(seconds: 10));
      expect(_posts(api, '/approve'), isEmpty);
    });

    testWidgets('fuse expiry commits the approval and ends the toast',
        (tester) async {
      final api = _reversibleApi();
      await _pumpShellAt(tester, screen: VigilScreen.home, api: api);

      await tester.tap(find.byKey(const Key('approve-a-1')));
      await tester.pump();
      expect(find.text('Undo'), findsOneWidget);

      // Past the 8 s fuse the queued decision commits itself.
      await tester.pump(const Duration(seconds: 8, milliseconds: 200));
      await tester.pump(const Duration(milliseconds: 50));

      final posts = _posts(api, '/approve');
      expect(posts, hasLength(1));
      expect(posts.single.body, {'approved_by': 'jane'});
      expect(find.text('Undo'), findsNothing);
    });
  });

  group('irreversible approve — hold to confirm (Decisions)', () {
    testWidgets('hold released at 1.5 s does nothing', (tester) async {
      final api = _irreversibleApi();
      await _pumpShellAt(tester, screen: VigilScreen.decisions, api: api);

      expect(find.text('Quarantine mailbox j.doe'), findsOneWidget);
      final hold = find.byKey(const ValueKey('hold-approve'));
      expect(hold, findsOneWidget);

      final gesture = await tester.startGesture(tester.getCenter(hold));
      await tester.pump();
      expect(find.text('Keep holding…'), findsOneWidget);

      // 93.75% through the fill — releasing cancels, nothing is sent.
      await tester.pump(const Duration(milliseconds: 1500));
      await gesture.up();
      await tester.pump();

      expect(find.text('Keep holding…'), findsNothing);
      expect(find.text('Approve'), findsOneWidget);
      expect(_posts(api, '/approve'), isEmpty);

      // Still nothing after any further wait.
      await tester.pump(const Duration(seconds: 10));
      expect(_posts(api, '/approve'), isEmpty);
    });

    testWidgets('completing the hold approves immediately, never a fuse',
        (tester) async {
      final api = _irreversibleApi();
      final controller =
          await _pumpShellAt(tester, screen: VigilScreen.decisions, api: api);

      final hold = find.byKey(const ValueKey('hold-approve'));
      final gesture = await tester.startGesture(tester.getCenter(hold));
      await tester.pump();
      await tester
          .pump(const Duration(milliseconds: 1700)); // past the 1.6 s fill
      await tester.pump(const Duration(milliseconds: 50));

      final posts = _posts(api, '/approve');
      expect(posts, hasLength(1));
      expect(posts.single.body, {'approved_by': 'jane'});
      // No undo fuse exists for irreversible actions.
      expect(controller.isFusing('a-2'), isFalse);
      expect(find.text('Undo'), findsNothing);
      await gesture.up();
      expect(_posts(api, '/approve'), hasLength(1));
    });
  });

  group('reject — a reason is mandatory (Decisions)', () {
    testWidgets('submit stays disabled without a reason, then posts it',
        (tester) async {
      final api = _reversibleApi();
      await _pumpShellAt(tester, screen: VigilScreen.decisions, api: api);

      // Open the reject form.
      await tester.tap(find.widgetWithText(OutlinedButton, 'Reject'));
      await tester.pump();
      expect(find.text('A reason is required.'), findsOneWidget);

      final submit = find.byType(FilledButton);
      expect(tester.widget<FilledButton>(submit).onPressed, isNull,
          reason: 'no reason yet — the submit must be disabled');

      // Whitespace is not a reason.
      await tester.enterText(find.byType(TextField), '   ');
      await tester.pump();
      expect(tester.widget<FilledButton>(submit).onPressed, isNull);

      // A quick-pick fills the field and enables the submit.
      await tester.tap(find.text('Duplicate'));
      await tester.pump();
      expect(tester.widget<FilledButton>(submit).onPressed, isNotNull);

      await tester.tap(submit);
      await tester.pump();
      expect(find.text('Undo'), findsOneWidget,
          reason: 'the reject commits through the same 8 s fuse');

      await tester.pump(const Duration(seconds: 8, milliseconds: 200));
      await tester.pump(const Duration(milliseconds: 50));

      final posts = _posts(api, '/reject');
      expect(posts, hasLength(1));
      expect(posts.single.body, {'reason': 'Duplicate', 'rejected_by': 'jane'});
    });
  });

  group('polling cadence, backoff, and the stale banner', () {
    testWidgets('polls every 20 s; pause stops; resume refreshes now',
        (tester) async {
      final api = _reversibleApi();
      final controller =
          await _pumpShellAt(tester, screen: VigilScreen.home, api: api);

      expect(_needsYouGets(api), 1); // the immediate first poll
      await tester.pump(const Duration(seconds: 20));
      expect(_needsYouGets(api), 2);
      await tester.pump(const Duration(seconds: 20));
      expect(_needsYouGets(api), 3);

      // Backgrounded: the cadence stops entirely.
      controller.pause();
      await tester.pump(const Duration(seconds: 60));
      expect(_needsYouGets(api), 3);

      // Foregrounded: refresh immediately, cadence continues.
      controller.resume();
      await tester.pump(const Duration(milliseconds: 50));
      expect(_needsYouGets(api), 4);
    });

    testWidgets(
        'failures back the cadence off; two raise the banner; recovery clears it',
        (tester) async {
      final api = _flakyApi(failCount: 2);
      final controller =
          await _pumpShellAt(tester, screen: VigilScreen.home, api: api);

      expect(_needsYouGets(api), 1);
      expect(controller.stale, isFalse);

      await tester.pump(const Duration(seconds: 20)); // failure 1 — a blip
      expect(_needsYouGets(api), 2);
      expect(controller.consecutiveFailures, 1);
      expect(controller.stale, isFalse);

      await tester.pump(const Duration(seconds: 20)); // failure 2 — a pattern
      expect(_needsYouGets(api), 3);
      expect(controller.consecutiveFailures, 2);
      expect(controller.stale, isTrue);
      // The banner labels the data's age and keeps the card visible.
      expect(find.textContaining('— reconnecting'), findsOneWidget);
      expect(find.text('Isolate host web-prod-3'), findsOneWidget);

      // The backoff doubled to 40 s — no poll at the plain 20 s cadence.
      await tester.pump(const Duration(seconds: 20));
      expect(_needsYouGets(api), 3);
      expect(controller.stale, isTrue);

      // Past the backoff (fires at t=80) but a beat short of the resumed
      // 20 s cadence (t=100) so the recovery poll is the only one in the
      // window.
      await tester.pump(const Duration(seconds: 39));
      await tester.pump(const Duration(milliseconds: 50));
      expect(_needsYouGets(api), 4);
      expect(controller.stale, isFalse);
      expect(find.textContaining('— reconnecting'), findsNothing);
    });
  });
}
