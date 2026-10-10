import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/chat/ask_vigil_pane.dart';
import 'package:vigil_flutter/chat/chat_session.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/chat_stub.dart';
import '../helpers/wired_vigil.dart';

/// A streamed response driven by a controller, so a test decides exactly
/// when each frame arrives — the seam the incremental-rendering assertions
/// need (a fixed stream would deliver everything at once).
class ScriptedStream {
  ScriptedStream() {
    body = ResponseBody(_controller.stream, 200, headers: {
      Headers.contentTypeHeader: const ['text/event-stream'],
    });
  }

  final StreamController<Uint8List> _controller = StreamController<Uint8List>();

  /// The transport body the adapter hands to dio.
  late final ResponseBody body;

  /// Delivers one raw string chunk now.
  void add(String text) =>
      _controller.add(Uint8List.fromList(utf8.encode(text)));

  /// Ends the stream — the turn finishes and the vigil row commits.
  Future<void> close() => _controller.close();
}

/// Every string the tree renders as rich text — the chat transcript's
/// rendered surface.
String renderedText(WidgetTester tester) => tester
    .widgetList<RichText>(find.byType(RichText))
    .map((w) => w.text.toPlainText())
    .join('\n');

Future<void> pumpPane(
  WidgetTester tester,
  ChatSession session, {
  VoidCallback? onClose,
}) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(480, 800);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.binding.setSurfaceSize(const Size(480, 800));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    theme: buildVigilThemeData(Brightness.dark),
    home: Scaffold(body: AskVigilPane(session: session, onClose: onClose)),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders answer text as frames arrive, not buffered-at-end',
      (tester) async {
    final stream = ScriptedStream();
    final session = stubChatSession(handler: (options, request) {
      if (request.path.contains('/api/conversations')) {
        return json(200, {'conversations': []});
      }
      return stream.body;
    });
    await pumpPane(tester, session);

    await tester.enterText(find.byType(TextField), 'what needs me?');
    // Rebuild so the send button's onPressed reflects the non-empty draft.
    await tester.pump();
    await tester.tap(find.byKey(const Key('ask-send')));
    // Elapse fake time: dio's request dispatch needs a timer turn, which a
    // bare pump() (no duration) never grants in testWidgets.
    await tester.pump(const Duration(milliseconds: 16));

    // First frame only.
    stream.add(sseFrame({'type': 'text', 'content': 'Isolating'}));
    await tester.pump(const Duration(milliseconds: 16));

    expect(renderedText(tester), contains('Isolating'),
        reason: 'frame 1 renders the moment it arrives');
    expect(renderedText(tester), isNot(contains('web-prod-3')),
        reason: 'frame 2 has not arrived yet — no buffered-at-end rendering');
    expect(find.byKey(const Key('ask-streaming-text')), findsOneWidget);

    // Second frame extends the answer in place.
    stream.add(sseFrame({'type': 'text', 'content': ' web-prod-3 now'}));
    await tester.pump(const Duration(milliseconds: 16));
    expect(renderedText(tester), contains('Isolating web-prod-3 now'));

    await stream.close();
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('ask-streaming-text')), findsNothing,
        reason: 'the completed turn commits as a vigil row');
    expect(renderedText(tester), contains('Isolating web-prod-3 now'));
    expect(find.byKey(const Key('ask-send')), findsOneWidget,
        reason: 'the stop affordance swaps back to send');
  });

  testWidgets('an error frame surfaces an error row with retry',
      (tester) async {
    final stream = ScriptedStream();
    final session = stubChatSession(handler: (options, request) {
      if (request.path.contains('/api/conversations')) {
        return json(200, {'conversations': []});
      }
      return stream.body;
    });
    await pumpPane(tester, session);

    await tester.enterText(find.byType(TextField), 'isolate web-prod-3');
    // Rebuild so the send button's onPressed reflects the non-empty draft.
    await tester.pump();
    await tester.tap(find.byKey(const Key('ask-send')));
    // Elapse fake time so dio's dispatch reaches the scripted body.
    await tester.pump(const Duration(milliseconds: 16));
    stream.add(sseFrame({'error': 'provider overloaded'}));
    // The error's propagation (throw → source cancel → onError) needs real
    // event-loop turns that FakeAsync never schedules — pump the chain in
    // real time, then render the settled state.
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pump();

    expect(find.byKey(const Key('ask-error')), findsOneWidget);
    expect(renderedText(tester), contains('provider overloaded'));
    expect(find.byKey(const Key('ask-retry')), findsOneWidget);
    expect(renderedText(tester), contains('isolate web-prod-3'),
        reason: 'the user turn stays visible under the failure');
    // The consumer died on the error frame, so done is never delivered —
    // close only at teardown, unawaited, after the assertions.
    unawaited(stream.close());
  });

  testWidgets('streaming swaps send for stop; the composer stays usable',
      (tester) async {
    final stream = ScriptedStream();
    final session = stubChatSession(handler: (options, request) {
      if (request.path.contains('/api/conversations')) {
        return json(200, {'conversations': []});
      }
      return stream.body;
    });
    await pumpPane(tester, session);

    await tester.enterText(find.byType(TextField), 'long question');
    // Rebuild so the send button's onPressed reflects the non-empty draft.
    await tester.pump();
    await tester.tap(find.byKey(const Key('ask-send')));
    await tester.pump();

    expect(find.byKey(const Key('ask-stop')), findsOneWidget);
    expect(find.byKey(const Key('ask-send')), findsNothing);
    expect(find.byKey(const Key('ask-waiting')), findsOneWidget);

    session.stop();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ask-send')), findsOneWidget);
    expect(session.entries.length, 1, reason: 'the abort adds no answer row');
    expect(session.entries.single.role, ChatRole.user,
        reason: 'the asked question stays; stop discards only the answer');
  });

  testWidgets('the empty state names the surface and its job', (tester) async {
    await pumpPane(tester, stubChatSession());

    expect(find.text('Ask Vigil'), findsOneWidget);
    expect(
        find.text(
            'Investigate alongside Vigil — ask about findings, cases, or what the agents are doing.'),
        findsOneWidget);
    // Console vocabulary only — the surface is never "Chat".
    expect(find.text('Chat'), findsNothing);
  });

  testWidgets('history picker opens a past conversation', (tester) async {
    final session = stubChatSession(handler: (options, request) {
      if (request.path.contains('/api/conversations/c-1')) {
        return json(200, {
          'id': 'c-1',
          'title': 'Triage review',
          'messages': [
            {'role': 'user', 'content': 'earlier question'},
            {'role': 'assistant', 'content': 'earlier answer'},
          ],
        });
      }
      if (request.path.contains('/api/conversations')) {
        return json(200, {
          'conversations': [
            {'id': 'c-1', 'title': 'Triage review', 'message_count': 2},
          ],
        });
      }
      return json(404, {'detail': 'unscripted'});
    });
    await pumpPane(tester, session);

    // The history list lives inside the picker's sheet, not inline.
    expect(find.text('Triage review'), findsNothing);
    await tester.tap(find.byKey(const Key('ask-picker')));
    await tester.pumpAndSettle();
    expect(find.text('Triage review'), findsOneWidget,
        reason: 'the picker shows the loaded conversation list');
    await tester.tap(find.byKey(const Key('conversation-c-1')));
    await tester.pumpAndSettle();

    expect(renderedText(tester), contains('earlier question'));
    expect(renderedText(tester), contains('earlier answer'));
  });
}
