import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/approvals/approvals_controller.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/shell/screens.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/wired_vigil.dart';

/// Golden captures of the human-on-the-loop surfaces — the Home needs-you
/// feed and the Decisions decision blocks in their three decision states
/// (reversible tap, irreversible hold mid-fill, committed with the undo
/// fuse running). Regenerate with:
///   flutter test --update-goldens test/approvals/approval_goldens_test.dart

/// A user the shell renders with — every gated screen visible.
const _approver = UserProfile(
  username: 'jane',
  email: 'jane@corp.example',
  permissions: {
    'ai_decisions.approve': true,
    'cases.read': true,
    'settings.read': true,
  },
);

/// Deterministic mid-range jitter so goldens are reproducible.
class _GoldenRandom implements math.Random {
  @override
  double nextDouble() => 0.5;
  @override
  int nextInt(int max) => (max * 0.5).floor();
  @override
  bool nextBool() => true;
}

/// The approvals-controller-owning harness from approval_flow_widget_test,
/// sized for desktop goldens. Its dispose runs during widget-tree unmount,
/// before flutter_test's pending-timer invariant.
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
      jitterRandom: _GoldenRandom(),
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

RoutedAdapter _decisionsApi({
  required String reversibility,
  String actionId = 'a-1',
}) =>
    RoutedAdapter((options, r) {
      if (r.path.contains('/api/v1/approvals/needs-you')) {
        return json(
          200,
          needsYouBody([
            needsYouItemBody(reversibility: reversibility),
          ]),
        );
      }
      if (r.path.contains('/api/v1/approvals')) {
        if (r.method == 'POST') return json(200, approvalActionResultBody());
        return json(
          200,
          approvalListBody([
            pendingActionBody(
              actionId: actionId,
              confidence: 0.88,
              reversibility: reversibility,
            ),
          ]),
        );
      }
      return defaultApiHandler(options, r);
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // Same loaders as design_goldens_test.dart — without the bundled TTFs
    // the goldens silently render in the Ahem fallback font.
    Future<void> load(String family, List<String> files) async {
      final loader = FontLoader(family);
      for (final file in files) {
        loader.addFont(rootBundle.load('assets/fonts/$file'));
      }
      await loader.load();
    }

    await load('Plus Jakarta Sans', [
      'plus-jakarta-sans-400.ttf',
      'plus-jakarta-sans-500.ttf',
      'plus-jakarta-sans-600.ttf',
      'plus-jakarta-sans-700.ttf',
    ]);
    await load('Roboto Mono', [
      'roboto-mono-400.ttf',
      'roboto-mono-500.ttf',
    ]);
  });

  Future<ApprovalsController> pumpShell(
    WidgetTester tester, {
    required VigilScreen screen,
    required RoutedAdapter api,
  }) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(1200, 800);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.binding.setSurfaceSize(const Size(1200, 800));
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

  Future<void> snap(WidgetTester tester, String name) {
    return expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../goldens/$name'),
    );
  }

  testWidgets('home — the needs-you feed and pending count', (tester) async {
    await pumpShell(
      tester,
      screen: VigilScreen.home,
      api: _decisionsApi(reversibility: 'reversible'),
    );
    await snap(tester, 'home-needs-you.png');
  });

  testWidgets('decisions — a reversible block (tap approve, undo fuse)',
      (tester) async {
    await pumpShell(
      tester,
      screen: VigilScreen.decisions,
      api: _decisionsApi(reversibility: 'reversible'),
    );
    await snap(tester, 'decisions-reversible.png');
  });

  testWidgets('decisions — an irreversible block mid-hold', (tester) async {
    await pumpShell(
      tester,
      screen: VigilScreen.decisions,
      api: _decisionsApi(
        reversibility: 'irreversible',
        actionId: 'a-2',
      ),
    );
    final hold = find.byKey(const ValueKey('hold-approve'));
    final gesture = await tester.startGesture(tester.getCenter(hold));
    await tester.pump(const Duration(milliseconds: 800)); // half the 1.6 s
    await snap(tester, 'decisions-irreversible-hold.png');
    await gesture.up();
  });

  testWidgets('decisions — committed with the 8 s undo fuse running',
      (tester) async {
    final controller = await pumpShell(
      tester,
      screen: VigilScreen.decisions,
      api: _decisionsApi(reversibility: 'reversible'),
    );
    await tester.tap(find.byKey(const ValueKey('approve-tap')));
    await tester.pump(const Duration(seconds: 2)); // 6 s of fuse remaining
    expect(controller.isFusing('a-1'), isTrue);
    await snap(tester, 'decisions-undo-fuse.png');
  });
}
