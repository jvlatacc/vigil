import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/screens/cases/cases_screen.dart';
import 'package:vigil_flutter/screens/shared/approval_fuse.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/fake_adapter.dart';
import '../helpers/vigil_fonts.dart';

const baseUrl = 'https://vigil.example.com';
const userAgent = 'VigilTest/1.0';

/// Scripted `/api/v1` payloads — the exact wire shapes the console's case
/// queue and case page consume (`screens/cases/*`, SCREENS.md phase-1).
Map<String, dynamic> casesListJson() => {
      'cases': [
        {
          'case_id': 'case-1',
          'title': 'Credential stuffing on vpn-edge',
          'combined_state': 'open',
          'priority': 'high',
          'needs_you': true,
          'findings_count': 4,
          'assignee': 'jane',
          'age_seconds': 3600,
          'sla_seconds_left': 86400,
        },
        {
          'case_id': 'case-2',
          'title': 'Impossible travel — okta',
          'combined_state': 'closed',
          'needs_you': false,
          'age_seconds': 7200,
        },
      ],
      'strip': {
        'by_state': {'open': 1, 'closed': 1},
        'needs_you': 1,
        'sla_at_risk': 0,
        'closed_today': 1,
        'agent_closure_share': 0.5,
      },
      'has_more': false,
      'limit': 200,
      'offset': 0,
      'total': 2,
    };

Map<String, dynamic> caseDetailJson() => {
      'case_id': 'case-2',
      'title': 'Impossible travel — okta',
      'combined_state': 'closed',
      'priority': 'medium',
      'description': 'Okta session for j.doe used two distant ASNs in 9 min.',
      'assignee': 'jane',
      'mitre_techniques': ['T1078'],
      'linked_findings': [
        {
          'finding_id': 'f-1',
          'title': 'Impossible travel j.doe',
          'description': 'Two ASNs in 9 minutes',
          'source_link': 'okta://events/123',
        },
      ],
      'created_at': '2026-10-10T12:00:00Z',
      'updated_at': '2026-10-10T14:00:00Z',
    };

Map<String, dynamic> evidenceJson() => {
      'evidence': [
        {
          'evidence_id': 1,
          'evidence_type': 'log',
          'description': 'vpn-edge auth log excerpt',
          'collected_by': 'vigil-daemon',
          'collected_at': '2026-10-10T13:05:00Z',
        },
        {
          'evidence_id': 2,
          'evidence_type': 'screenshot',
          'description': 'Console session photograph',
        },
      ],
    };

Map<String, dynamic> needsYouJson() => {
      'count': 1,
      'items': [
        {
          'kind': 'workflow_approval',
          'source_id': 'action-9',
          'title': 'Quarantine mailbox j.doe',
          'reason': 'Confidence 0.92 · irreversible',
          'created_at': '2026-10-10T14:20:11Z',
          'reversibility': 'irreversible',
          'case_id': 'case-2',
        },
      ],
    };

/// Client + fuse wired to a scripted adapter. The store is pre-seeded, so
/// no auth traffic runs and the case requests consume responses in order.
class _Wired {
  _Wired() {
    api.enqueueJson(200, casesListJson()); // the screen's first poll
    client = VigilClient(
      baseUrl: baseUrl,
      tokenStore: InMemoryTokenStore(accessToken: 'a1', refreshToken: 'r1'),
      userAgent: userAgent,
      apiAdapter: api,
    );
  }

  final FakeAdapter api = FakeAdapter();
  late final VigilClient client;
  final FuseController fuse = FuseController();

  /// Enqueues the three responses the case detail pane loads in parallel
  /// (detail, evidence, needs-you — the pane's `.wait` issue order).
  void enqueueCaseDetail() {
    api
      ..enqueueJson(200, caseDetailJson())
      ..enqueueJson(200, evidenceJson())
      ..enqueueJson(200, needsYouJson());
  }
}

Future<void> _pumpCases(
  WidgetTester tester,
  _Wired w,
  CasesScreen screen, {
  required Size size,
  double dpr = 1.0,
}) async {
  // `size` is the LOGICAL viewport; the view wants physical pixels. At 3x
  // this is a real phone's render resolution (390×844 → 1170×2532).
  tester.view.physicalSize = size * dpr;
  tester.view.devicePixelRatio = dpr;
  addTearDown(tester.view.reset);
  // The app's own theme: screens style themselves explicitly, but Material
  // chrome (buttons, sheets) reads it — and goldens must render the brand
  // typography, not the test-default theme.
  await tester.pumpWidget(MaterialApp(
    theme: buildVigilThemeData(Brightness.dark),
    home: Scaffold(body: screen),
  ));
  // The scheduler's first tick fires in initState; let it resolve.
  await tester.pump(const Duration(milliseconds: 100));
}

/// Disposes the tree so the screen's poll timer cannot linger into the
/// binding's post-test pending-timer check.
Future<void> teardownTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 10));
}

void main() {
  // Real typography for the golden captures.
  setUpAll(loadVigilFonts);

  testWidgets('wide: master-detail — list and detail pane side by side',
      (tester) async {
    final w = _Wired();
    await _pumpCases(
      tester,
      w,
      CasesScreen(client: w.client, fuse: w.fuse),
      size: const Size(1000, 800),
    );

    expect(find.byKey(const Key('cases-list')), findsOneWidget);
    expect(find.byKey(const Key('cases-detail-pane')), findsOneWidget);
    // Nothing selected yet — an explicit empty state, not a blank pane.
    expect(find.text('Select a case'), findsOneWidget);
    expect(find.byKey(const Key('case-detail')), findsNothing);

    await teardownTree(tester);
  });

  testWidgets('wide: tapping a row selects the case in the detail pane',
      (tester) async {
    final w = _Wired();
    w.enqueueCaseDetail();
    await _pumpCases(
      tester,
      w,
      CasesScreen(client: w.client, fuse: w.fuse),
      size: const Size(1000, 800),
    );

    await tester.tap(find.byKey(const Key('case-row-case-2')));
    await tester.pump(const Duration(milliseconds: 100)); // pane mounts
    await tester.pump(const Duration(milliseconds: 300)); // load resolves

    // In place — no pushed sheet on wide screens.
    final detail = find.byKey(const Key('case-detail'));
    expect(detail, findsOneWidget);
    expect(find.text('Impossible travel — okta'), findsWidgets);
    expect(find.text('T1078'), findsOneWidget); // MITRE chip
    // The needs-you item scoped to this case renders with its action.
    expect(find.byKey(const Key('case-approval-action-9')), findsOneWidget);

    // Visual evidence for QA: both panes in one capture.
    await expectLater(
      find.byType(CasesScreen),
      matchesGoldenFile('../goldens/cases-wide-master-detail.png'),
    );

    await teardownTree(tester);
  });

  testWidgets('phone: list only — the detail is a pushed sheet',
      (tester) async {
    final w = _Wired();
    await _pumpCases(
      tester,
      w,
      CasesScreen(client: w.client, fuse: w.fuse),
      size: const Size(390, 844),
    );

    expect(find.byKey(const Key('cases-list')), findsOneWidget);
    expect(find.byKey(const Key('cases-detail-pane')), findsNothing,
        reason: 'no side pane below the breakpoint');

    await teardownTree(tester);
  });

  testWidgets('phone: tapping a row opens the detail sheet with evidence',
      (tester) async {
    final w = _Wired();
    w.enqueueCaseDetail();
    await _pumpCases(
      tester,
      w,
      CasesScreen(client: w.client, fuse: w.fuse),
      size: const Size(390, 844),
    );

    await tester.tap(find.byKey(const Key('case-row-case-2')));
    await tester.pump(const Duration(milliseconds: 100)); // push transition
    await tester.pump(const Duration(milliseconds: 300)); // detail resolves

    final detail = find.byKey(const Key('case-detail'));
    expect(detail, findsOneWidget);

    // Evidence trail read — each scripted entry renders its row.
    expect(find.byKey(const Key('evidence-1')), findsOneWidget);
    expect(find.byKey(const Key('evidence-2')), findsOneWidget);
    expect(find.text('vpn-edge auth log excerpt'), findsOneWidget);
    expect(find.textContaining('vigil-daemon'), findsOneWidget);

    // Visual evidence for QA: the pushed detail sheet over the list.
    // Re-pumped at the phone's real pixel ratio (3x, like an iPhone) so the
    // capture matches device output instead of a low-DPR test surface. The
    // fresh tree re-runs its first poll and the detail load, so the scripted
    // responses are queued again — the list before the pump (the poll fires
    // in initState), the detail trio before the tap.
    w.api.enqueueJson(200, casesListJson());
    await _pumpCases(
      tester,
      w,
      CasesScreen(client: w.client, fuse: w.fuse),
      size: const Size(390, 844),
      dpr: 3.0,
    );
    w.enqueueCaseDetail();
    await tester.tap(find.byKey(const Key('case-row-case-2')));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../goldens/cases-phone-detail-sheet.png'),
    );

    await teardownTree(tester);
  });

  testWidgets('deep link: ?case=<id> opens the detail on arrival (phone)',
      (tester) async {
    final w = _Wired();
    w.enqueueCaseDetail();
    await _pumpCases(
      tester,
      w,
      CasesScreen(
        client: w.client,
        fuse: w.fuse,
        initialCaseId: 'case-2',
      ),
      size: const Size(390, 844),
    );

    // The post-frame callback pushes the sheet without a tap.
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const Key('case-detail')), findsOneWidget);
    expect(find.text('Impossible travel — okta'), findsWidgets);

    await teardownTree(tester);
  });
}
