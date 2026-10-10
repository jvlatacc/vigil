import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/chat/chat_session.dart';

import '../helpers/chat_stub.dart';
import '../helpers/fake_adapter.dart';
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

  /// Ends the stream — the client's stream completes and the turn finishes.
  Future<void> close() => _controller.close();
}

void main() {
  group('ChatSession streaming', () {
    test('accumulates frames into streamText and commits the vigil row',
        () async {
      final stream = ScriptedStream();
      final session = stubChatSession(handler: (options, request) {
        if (request.path.contains('/api/conversations')) {
          return json(200, {'conversations': []});
        }
        return stream.body;
      });

      final sends = session.send('what is isolated?');
      // Frames arrive on separate controller events — intermediate state is
      // observable between them (the dio pipeline needs several turns before
      // the first frame lands).
      stream.add(sseFrame({'type': 'text', 'content': 'Isolating '}));
      await untilCondition(() => session.streamText == 'Isolating ',
          reason: 'frame 1 consumed');
      expect(session.streaming, isTrue);
      expect(session.streamText, 'Isolating ');

      stream.add(sseFrame({'type': 'text', 'content': 'web-prod-3.'}));
      await untilCondition(() => session.streamText == 'Isolating web-prod-3.',
          reason: 'frame 2 consumed');
      expect(session.streamText, 'Isolating web-prod-3.');

      await stream.close();
      await sends;

      expect(session.streaming, isFalse);
      expect(session.streamText, isEmpty);
      expect(session.entries, hasLength(2));
      expect(session.entries.first.role, ChatRole.user);
      expect(session.entries.first.text, 'what is isolated?');
      expect(session.entries.last.role, ChatRole.vigil);
      expect(session.entries.last.text, 'Isolating web-prod-3.');
    });

    test('tool_processing separates tool output from prose', () async {
      final stream = ScriptedStream();
      final session = stubChatSession(handler: (options, request) {
        if (request.path.contains('/api/conversations')) {
          return json(200, {'conversations': []});
        }
        return stream.body;
      });

      final sends = session.send('check the host');
      stream.add(sseFrame({'type': 'text', 'content': 'On it.'}));
      await untilCondition(() => session.streamText == 'On it.',
          reason: 'text frame consumed');
      stream.add(sseFrame({'type': 'tool_processing'}));
      await untilCondition(
          () => session.toolProcessing && session.streamText == 'On it.\n\n',
          reason: 'tool marker consumed');
      expect(session.toolProcessing, isTrue);
      expect(session.streamText, endsWith('\n\n'));

      await stream.close();
      await sends;
      expect(session.entries.last.text, 'On it.\n\n');
    });

    test('an empty answer commits the console no-response marker', () async {
      final stream = ScriptedStream();
      final session = stubChatSession(handler: (options, request) {
        if (request.path.contains('/api/conversations')) {
          return json(200, {'conversations': []});
        }
        return stream.body;
      });

      final sends = session.send('hello');
      await stream.close();
      await sends;

      expect(session.entries.last.role, ChatRole.vigil);
      expect(session.entries.last.text, '_(no response)_');
    });
  });

  group('ChatSession failures', () {
    test('an error frame becomes an error row and offers a retry', () async {
      final stream = ScriptedStream();
      final session = stubChatSession(handler: (options, request) {
        if (request.path.contains('/api/conversations')) {
          return json(200, {'conversations': []});
        }
        return stream.body;
      });

      final sends = session.send('isolate web-prod-3');
      stream.add(sseFrame({'error': 'provider overloaded'}));
      await Future<void>.delayed(Duration.zero);
      await sends;

      expect(session.streaming, isFalse);
      expect(session.entries, hasLength(2));
      final errorRow = session.entries.last;
      expect(errorRow.role, ChatRole.error);
      expect(errorRow.text, 'provider overloaded');
      expect(session.retryText, 'isolate web-prod-3');
    });

    test('an unreachable backend says so, and offers a retry', () async {
      final session = stubChatSession(
        handler: (options, request) => throw DioException.connectionError(
          reason: 'refused',
          error: Exception('refused'),
          requestOptions: RequestOptions(path: '/x'),
        ),
      );

      await session.send('anyone there?');

      expect(session.entries.last.role, ChatRole.error);
      expect(
        session.entries.last.text,
        contains('Could not reach Vigil'),
        reason: 'a dead backend must not read like a model refusal',
      );
      expect(session.retryText, 'anyone there?');
    });

    test('a retry resends the failed user turn; errors never ride along',
        () async {
      var streamCalls = 0;
      final requests = <RecordedRequest>[];
      final session = stubChatSession(handler: (options, request) {
        requests.add(request);
        if (request.path.contains('/api/claude/chat/stream')) {
          streamCalls++;
          if (streamCalls == 1) return json(502, {'detail': 'bad gateway'});
          return sseResponse(
            [
              sseFrame({'type': 'text', 'content': 'back online'})
            ],
          );
        }
        return json(200, {'conversations': []});
      });

      await session.send('retry me');
      expect(session.entries.last.role, ChatRole.error);

      final retryText = session.retryText;
      expect(retryText, 'retry me');
      await session.send(retryText!);

      // Transcript: user, error, user, vigil — the failure is a visible
      // row, never a context turn.
      expect(
        session.entries.map((e) => e.role),
        [ChatRole.user, ChatRole.error, ChatRole.user, ChatRole.vigil],
      );
      expect(session.entries.last.text, 'back online');

      final chatRequests = requests
          .where((r) => r.path.contains('/claude/chat/stream'))
          .toList();
      final secondBody = chatRequests.last.body as Map<String, dynamic>;
      final turns = secondBody['messages'] as List;
      expect(turns, hasLength(2), reason: 'only user/vigil turns ride along');
      expect(
          turns,
          everyElement(predicate(
              (t) => (t as Map<String, dynamic>)['role'] != 'error')));
    });
  });

  group('ChatSession stop and history', () {
    test('stop cancels the in-flight turn without rows and settles send',
        () async {
      final stream = ScriptedStream();
      final session = stubChatSession(handler: (options, request) {
        if (request.path.contains('/api/conversations')) {
          return json(200, {'conversations': []});
        }
        return stream.body;
      });

      final sends = session.send('long question');
      stream.add(sseFrame({'type': 'text', 'content': 'partial answer'}));
      await untilCondition(() => session.streamText == 'partial answer',
          reason: 'partial answer consumed before the stop');

      session.stop();
      await sends.timeout(
        const Duration(seconds: 1),
        onTimeout: () => fail('stop must settle the awaited send future'),
      );

      expect(session.streaming, isFalse);
      expect(session.streamText, isEmpty);
      expect(
        session.entries.map((e) => e.role),
        [ChatRole.user],
        reason: 'an aborted turn leaves no vigil or error row',
      );
    });

    test('loadConversations parses the list; failures surface honestly',
        () async {
      var fail = false;
      final session = stubChatSession(
        handler: (options, request) {
          if (request.path.contains('/api/conversations')) {
            if (fail) return json(503, {'detail': 'down'});
            return json(200, {
              'conversations': [
                {'id': 'c-1', 'title': 'Triage review', 'message_count': 2},
              ],
            });
          }
          return json(404, {'detail': 'unscripted'});
        },
      );

      await session.loadConversations();
      expect(session.historyError, isNull);
      expect(session.conversations.single.label, 'Triage review');

      fail = true;
      await session.loadConversations();
      expect(session.historyError, isNotNull,
          reason: 'a failed history load is an error state, not an empty list');
    });

    test('openConversation replaces the transcript with server messages',
        () async {
      final session = stubChatSession(
        handler: (options, request) {
          if (request.path.contains('/api/conversations/c-9')) {
            return json(200, {
              'id': 'c-9',
              'title': 'Opened one',
              'messages': [
                {'role': 'user', 'content': 'earlier question'},
                {'role': 'assistant', 'content': 'earlier answer'},
                {'role': 'user', 'content': ''},
              ],
            });
          }
          return json(200, {'conversations': []});
        },
      );

      await session.openConversation('c-9');

      expect(session.activeConversationId, 'c-9');
      expect(session.currentLabel, 'Opened one');
      expect(
        session.entries.map((e) => '${e.role.name}:${e.text}'),
        ['user:earlier question', 'vigil:earlier answer'],
        reason: 'blank server rows are dropped',
      );
    });

    test('startNewConversation clears the transcript and session id', () async {
      final session = stubChatSession();
      await session.loadConversations();
      session.startNewConversation();

      expect(session.activeConversationId, isNull);
      expect(session.entries, isEmpty);
      expect(session.currentLabel, 'New conversation');
    });
  });
}
