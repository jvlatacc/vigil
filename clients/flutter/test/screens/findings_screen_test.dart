import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/screens/findings/findings_screen.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/vigil_fonts.dart';
import '../helpers/wired_vigil.dart';

/// Findings payloads in the shapes the generated v1 client decodes
/// (`FindingListResponse`, `FindingsSummaryResponse`) plus the ATT&CK
/// rollup envelope the hand-written client reads.
Map<String, dynamic> findingJson({
  String id = 'f-1',
  String title = 'Credential stuffing on vpn-edge',
  String severity = 'critical',
}) =>
    {
      'finding_id': id,
      'title': title,
      'severity': severity,
      'status': 'open',
      'timestamp': '2026-10-10T12:00:00Z',
      'data_source': 'vpn',
    };

Map<String, dynamic> findingsListJson({
  List<Map<String, dynamic>> findings = const [],
}) =>
    {
      'findings': findings,
      'has_more': false,
      'limit': 200,
      'offset': 0,
      'total': findings.length,
    };

Map<String, dynamic> summaryJson(int total) => {
      'total': total,
      'by_severity': {'critical': total, 'high': 0, 'medium': 0, 'low': 0},
      'by_data_source': {'vpn': total},
    };

Map<String, dynamic> rollupJson() => {
      'total_techniques': 1,
      'techniques': [
        {
          'technique_id': 'T1110',
          'technique_name': 'Credential Stuffing',
          'count': 2,
          'severities': {'critical': 2},
        },
      ],
    };

({VigilClient client, RoutedAdapter api}) _wired(
  List<Map<String, dynamic>> queue,
  bool Function(String path) failFindings,
) {
  final api = RoutedAdapter((options, r) {
    final path = r.path;
    final failing = failFindings(path);
    if (path.contains('/api/v1/findings/stats/summary')) {
      if (failing) return json(500, {'detail': 'boom'});
      return json(200, summaryJson(queue.length));
    }
    if (path.contains('/api/v1/findings')) {
      if (failing) return json(500, {'detail': 'boom'});
      // The severity filter narrows server-side, like the real endpoint.
      final severity = Uri.parse(path).queryParameters['severity'];
      final rows = severity == null
          ? queue
          : queue.where((f) => f['severity'] == severity).toList();
      return json(200, findingsListJson(findings: rows));
    }
    if (path.contains('/api/attack/techniques/rollup')) {
      return json(200, rollupJson());
    }
    return json(404, {'detail': 'unscripted findings path $path'});
  });
  return (
    client: wiredClient(auth: RoutedAdapter(defaultAuthHandler), api: api),
    api: api,
  );
}

Future<void> _pumpFindings(WidgetTester tester, VigilClient client) async {
  tester.view.physicalSize = const Size(900, 800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: buildVigilThemeData(Brightness.dark),
    home: Scaffold(body: FindingsScreen(client: client)),
  ));
  // The scheduler's first tick fires in initState; let the reads resolve.
  await tester.pump(const Duration(milliseconds: 100));
}

/// Disposes the tree so the screen's poll timer cannot linger into the
/// binding's post-test pending-timer check.
Future<void> _teardown(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 10));
}

void main() {
  setUpAll(loadVigilFonts);

  testWidgets('queue renders severity chips, stats, and the attack rollup',
      (tester) async {
    final w = _wired([
      findingJson(id: 'f-1', severity: 'critical'),
      findingJson(id: 'f-2', title: 'Impossible travel — okta', severity: 'high'),
    ], (_) => false);
    await _pumpFindings(tester, w.client);

    expect(find.byKey(const Key('finding-f-1')), findsOneWidget);
    expect(find.byKey(const Key('finding-f-2')), findsOneWidget);
    // Severity chip mapping: the row carries the display label.
    expect(
      find.descendant(
        of: find.byKey(const Key('finding-f-1')),
        matching: find.text('Critical'),
      ),
      findsOneWidget,
    );
    // Stats summary from the frozen endpoint.
    expect(find.byKey(const Key('findings-stats')), findsOneWidget);
    expect(find.text('2'), findsWidgets);
    // The rollup loaded on the first (slow) tick.
    expect(find.byKey(const Key('findings-attack')), findsOneWidget);
    expect(find.text('T1110 — Credential Stuffing'), findsOneWidget);

    await _teardown(tester);
  });

  testWidgets('severity filter chip narrows the queue', (tester) async {
    final w = _wired([
      findingJson(id: 'f-1', severity: 'critical'),
      findingJson(id: 'f-2', title: 'Impossible travel — okta', severity: 'high'),
    ], (_) => false);
    await _pumpFindings(tester, w.client);

    await tester.tap(find.byKey(const Key('findings-sev-high')));
    await tester.pump(const Duration(milliseconds: 100));

    // The scripted server answered severity=high with only f-2.
    expect(find.byKey(const Key('finding-f-2')), findsOneWidget);
    expect(find.byKey(const Key('finding-f-1')), findsNothing);

    await _teardown(tester);
  });

  testWidgets('a failed poll keeps the last data and labels its age',
      (tester) async {
    var failing = false;
    final w = _wired(
      [findingJson(id: 'f-1')],
      (path) => failing && path.contains('/api/v1/findings'),
    );
    await _pumpFindings(tester, w.client);
    expect(find.byKey(const Key('finding-f-1')), findsOneWidget);
    expect(find.byKey(const Key('findings-stale')), findsNothing);

    // The 10 s findings cadence elapses; this poll fails.
    failing = true;
    await tester.pump(const Duration(seconds: 10));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byKey(const Key('findings-stale')), findsOneWidget);
    // Last good data stays visible under the stale banner.
    expect(find.byKey(const Key('finding-f-1')), findsOneWidget);

    await _teardown(tester);
  });
}
