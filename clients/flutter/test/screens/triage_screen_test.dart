import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/screens/triage/triage_screen.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/vigil_fonts.dart';
import '../helpers/wired_vigil.dart';

/// The triage payload in the shape `TriagePayload.fromBody` decodes —
/// intake rows, the strip figures, and the chip-filter counts.
Map<String, dynamic> triageRowJson({
  int id = 1,
  String kind = 'detection',
  String kindLabel = 'Alert',
  String state = 'queued',
  String stateLabel = 'Waiting for a slot',
  String source = 'vpn',
  String severityBand = 'critical',
  String? caseDoor,
}) =>
    {
      'id': id,
      'kind': kind,
      'kind_label': kindLabel,
      'state': state,
      'state_label': stateLabel,
      'source': source,
      'severity_band': severityBand,
      'age_seconds': 90,
      'ttl_seconds': 600,
      'last_quarter': false,
      'workflow_id': 'wf-1',
      if (caseDoor != null) 'case_door': caseDoor,
      'description': 'Suspicious logins from two distant ASNs',
    };

Map<String, dynamic> triageBodyJson({
  required List<Map<String, dynamic>> rows,
  required int matched,
}) =>
    {
      'rows': rows,
      'matched': matched,
      'strip': {
        'picked_up': {
          'launched_or_merged': 1,
          'created_today': 2,
          'share': 0.5,
        },
        'waiting': rows.length,
        'cases_created_today': 1,
        'trust_floor': 'Not measured yet',
      },
      'counts': {
        'total': 2,
        'kind': {'detection': 1, 'schedule': 1},
        'source': {'vpn': 1, 'okta': 1},
        'state': {'queued': 1, 'launched': 1},
      },
      'sources': [],
    };

({VigilClient client, RoutedAdapter api}) _wired(
  List<Map<String, dynamic>> queue,
) {
  final api = RoutedAdapter((options, r) {
    final path = r.path;
    if (path.contains('/api/triage')) {
      // Kind/state filters narrow server-side, like the real endpoint.
      final query = Uri.parse(path).queryParameters;
      final rows = queue.where((row) {
        if (query['kind'] != null && query['kind']!.isNotEmpty) {
          return row['kind'] == query['kind'];
        }
        return true;
      }).toList();
      return json(200, triageBodyJson(rows: rows, matched: rows.length));
    }
    return json(404, {'detail': 'unscripted triage path $path'});
  });
  return (
    client: wiredClient(auth: RoutedAdapter(defaultAuthHandler), api: api),
    api: api,
  );
}

Future<void> _pumpTriage(WidgetTester tester, VigilClient client) async {
  tester.view.physicalSize = const Size(900, 800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: buildVigilThemeData(Brightness.dark),
    home: Scaffold(body: TriageScreen(client: client)),
  ));
  // The scheduler's first tick fires in initState; let the read resolve.
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

  testWidgets('queue renders the strip, rows, and honest unmeasured scores',
      (tester) async {
    final w = _wired([
      triageRowJson(id: 1),
      triageRowJson(
        id: 2,
        kind: 'schedule',
        kindLabel: 'Schedule',
        state: 'launched',
        stateLabel: 'Started a case',
        source: 'okta',
        severityBand: 'medium',
        caseDoor: 'case-2',
      ),
    ]);
    await _pumpTriage(tester, w.client);

    expect(find.byKey(const Key('triage-row-1')), findsOneWidget);
    expect(find.byKey(const Key('triage-row-2')), findsOneWidget);
    // The strip reports the trust floor as the server sends it — never
    // rendered as a number.
    expect(find.byKey(const Key('triage-strip')), findsOneWidget);
    expect(find.text('Not measured yet'), findsOneWidget);
    // Scores are unmeasured server-side; every row's meta line says so
    // honestly (joined with state, source, and age).
    expect(find.textContaining('Not measured yet'), findsWidgets);
    // The launched row carries its door into the case page.
    expect(find.byKey(const Key('triage-door-2')), findsOneWidget);
    expect(find.byKey(const Key('triage-door-1')), findsNothing);

    await _teardown(tester);
  });

  testWidgets('kind filter chips narrow the queue', (tester) async {
    final w = _wired([
      triageRowJson(id: 1),
      triageRowJson(
        id: 2,
        kind: 'schedule',
        kindLabel: 'Schedule',
        state: 'launched',
        stateLabel: 'Started a case',
        source: 'okta',
        severityBand: 'medium',
      ),
    ]);
    await _pumpTriage(tester, w.client);

    await tester.tap(find.byKey(const Key('triage-kind-detection')));
    await tester.pump(const Duration(milliseconds: 100));

    // The scripted server answered kind=detection with only row 1.
    expect(find.byKey(const Key('triage-row-1')), findsOneWidget);
    expect(find.byKey(const Key('triage-row-2')), findsNothing);

    await _teardown(tester);
  });
}
