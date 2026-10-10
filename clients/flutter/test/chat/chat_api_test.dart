import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/errors.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/chat/chat_api.dart';
import 'package:vigil_flutter/chat/failures.dart';

import '../helpers/chat_stub.dart';
import '../helpers/fake_adapter.dart';
import '../helpers/wired_vigil.dart';

/// A chat transport scripted per path with call counters — the seam for the
/// 401 → refresh → reconnect test, which needs different responses for the
/// first and second stream calls.
class CountingRoutedAdapter implements HttpClientAdapter {
  CountingRoutedAdapter(this._onRequest);

  final ResponseBody Function(
          int callNumber, RequestOptions options, RecordedRequest request)
      _onRequest;

  final List<RecordedRequest> requests = [];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(RecordedRequest.of(options));
    final number = requests.where((r) => r.path == requests.last.path).length;
    return _onRequest(number, options, requests.last);
  }

  @override
  void close({bool force = false}) {}
}

/// The auth layer must treat the SSE stream like any other request: the
/// bearer header and byte-stable User-Agent ride it, and a 401 is answered
/// by exactly one refresh and a replayed stream — the console's one-shot
/// rule (`api.ts:61-73`), verified here end to end over the real
/// VigilAuthenticator instead of a mock.
void main() {
  group('VigilChatClient.streamTurn', () {
    test('yields text chunks as frames arrive, split across byte chunks',
        () async {
      // The frame JSON is split mid-payload across two network chunks —
      // the parser must reassemble it before decoding.
      final adapter = CountingRoutedAdapter(
        (number, options, request) => ResponseBody(
          Stream<Uint8List>.fromIterable([
            Uint8List.fromList(
                utf8.encode('data: {"type":"text","content":"Hel')),
            Uint8List.fromList(utf8.encode(
                'lo"}\n\ndata: {"type":"text","content":" world"}\n\n')),
          ]),
          200,
          headers: {
            Headers.contentTypeHeader: const ['text/event-stream'],
          },
        ),
      );
      final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
        ..httpClientAdapter = adapter;
      final client = VigilChatClient(dio: dio);

      final events = await client.streamTurn(
        turns: const [ChatTurn(role: 'user', content: 'hi')],
        sessionId: 's-1',
      ).toList();

      expect(events, hasLength(2), reason: 'one event per text frame');
      final text = events.whereType<ChatTextChunk>().map((e) => e.content);
      expect(
        text,
        const ['Hello', ' world'],
        reason: 'the split frame reassembles before decoding — one event '
            'per server frame, never per network chunk',
      );
    });

    test('surfaces tool_processing and skips context_windowed frames',
        () async {
      final adapter = CountingRoutedAdapter(
        (number, options, request) => sseResponse([
          sseFrame({'type': 'text', 'content': 'Checking.'}),
          sseFrame({'type': 'tool_processing'}),
          sseFrame({'type': 'context_windowed', 'at': 4}),
          sseFrame({'type': 'text', 'content': 'Found it.'}),
        ]),
      );
      final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
        ..httpClientAdapter = adapter;
      final client = VigilChatClient(dio: dio);

      final events =
          await client.streamTurn(turns: [], sessionId: 's-1').toList();

      expect(events.whereType<ChatToolProcessing>(), hasLength(1));
      expect(
        events.whereType<ChatTextChunk>().map((e) => e.content),
        ['Checking.', 'Found it.'],
        reason: 'context_windowed is an engine detail, not answer text',
      );
    });

    test('an error frame fails the stream with the server message', () async {
      final adapter = CountingRoutedAdapter(
        (number, options, request) => sseResponse([
          sseFrame({'type': 'text', 'content': 'partial'}),
          sseFrame({'error': 'provider overloaded'}),
        ]),
      );
      final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
        ..httpClientAdapter = adapter;
      final client = VigilChatClient(dio: dio);

      await expectLater(
        client.streamTurn(turns: [], sessionId: 's-1').drain<void>(),
        throwsA(isA<ChatRefusal>()
            .having((e) => e.message, 'message', 'provider overloaded')),
      );
    });

    test('a refused status carries the server detail', () async {
      final adapter = CountingRoutedAdapter(
        (number, options, request) =>
            ResponseBody.fromString('{"detail": "no provider"}', 422),
      );
      final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
        ..httpClientAdapter = adapter;
      final client = VigilChatClient(dio: dio);

      await expectLater(
        client.streamTurn(turns: [], sessionId: 's-1').drain<void>(),
        throwsA(isA<ChatRefusal>()
            .having((e) => e.message, 'message', 'no provider')),
      );
    });

    test('an unreachable backend and 502/503 map to ChatUnreachable', () async {
      Future<ChatFailure> failureFor(ResponseBody Function() respond) async {
        final adapter = CountingRoutedAdapter(
          (_, __, ___) => respond(),
        );
        final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
          ..httpClientAdapter = adapter;
        final client = VigilChatClient(dio: dio);
        try {
          await client.streamTurn(turns: [], sessionId: 's-1').drain<void>();
        } on ChatFailure catch (e) {
          return e;
        }
        fail('expected a ChatFailure');
      }

      final dead = await failureFor(
        () => throw DioException.connectionError(
          reason: 'refused',
          error: Exception('refused'),
          requestOptions: RequestOptions(path: '/api/claude/chat/stream'),
        ),
      );
      expect(dead, isA<ChatUnreachable>());

      final badGateway = await failureFor(
        () => ResponseBody.fromString('bad gateway', 502),
      );
      expect(badGateway, isA<ChatUnreachable>());
    });
  });

  group('SSE under the session auth layer', () {
    test('401 on the stream is refreshed once and the stream reconnects',
        () async {
      var refreshes = 0;
      final auth = RoutedAdapter((options, r) {
        if (r.path.contains('/api/auth/refresh')) {
          refreshes++;
          return json(200, loginBody());
        }
        return defaultAuthHandler(options, r);
      });
      var streamCalls = 0;
      final api = RoutedAdapter((options, r) {
        if (r.path.contains('/api/claude/chat/stream')) {
          streamCalls++;
          if (streamCalls == 1) {
            return ResponseBody.fromString(
              '{"detail": "Token revoked"}',
              401,
            );
          }
          return sseResponse([
            sseFrame({'type': 'text', 'content': 'reconnected answer'}),
          ]);
        }
        return defaultApiHandler(options, r);
      });
      final store = InMemoryTokenStore();
      await store.save(accessToken: 'stale-access', refreshToken: 'refresh-1');
      final client = VigilClient(
        baseUrl: testBaseUrl,
        tokenStore: store,
        userAgent: testUserAgent,
        authAdapter: auth,
        apiAdapter: api,
      );

      final events = await client.chat.streamTurn(
        turns: const [ChatTurn(role: 'user', content: 'hi')],
        sessionId: 's-1',
      ).toList();

      expect(streamCalls, 2, reason: 'the original call plus the replay');
      expect(refreshes, 1, reason: 'exactly one refresh — the one-shot rule');
      expect(
        events.whereType<ChatTextChunk>().map((e) => e.content),
        const ['reconnected answer'],
      );
      // The rotation persisted before replay, per the single-use rule.
      expect(await store.readAccess(), 'access-1');
      // The replayed request must carry the fresh token and the same UA.
      final replayed = api.requests.last;
      expect(replayed.header('authorization'), 'Bearer access-1');
      expect(replayed.header('user-agent'), testUserAgent);
    });

    test('a second 401 after refresh does not loop — the stream fails',
        () async {
      final auth = RoutedAdapter((options, r) {
        if (r.path.contains('/api/auth/refresh')) {
          return json(200, loginBody());
        }
        return defaultAuthHandler(options, r);
      });
      final api = RoutedAdapter((options, r) {
        if (r.path.contains('/api/claude/chat/stream')) {
          return ResponseBody.fromString('{"detail": "still revoked"}', 401);
        }
        return defaultApiHandler(options, r);
      });
      final store = InMemoryTokenStore();
      await store.save(accessToken: 'stale-access', refreshToken: 'refresh-1');
      final client = VigilClient(
        baseUrl: testBaseUrl,
        tokenStore: store,
        userAgent: testUserAgent,
        authAdapter: auth,
        apiAdapter: api,
      );

      await expectLater(
        client.chat.streamTurn(turns: [], sessionId: 's-1').drain<void>(),
        throwsA(anyOf(isA<ChatFailure>(), isA<AuthRevoked>())),
      );
      expect(
        api.requests.where((r) => r.path.contains('/claude/chat/stream')),
        hasLength(2),
        reason: 'original + one replay — no infinite loop',
      );
    });
  });

  group('conversation history', () {
    VigilChatClient clientFor(
        ResponseBody Function(RequestOptions, RecordedRequest) handler) {
      final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
        ..httpClientAdapter = RoutedAdapter(handler);
      return VigilChatClient(dio: dio);
    }

    test('parses the conversation list', () async {
      final client = clientFor((options, r) => json(200, {
            'conversations': [
              {
                'id': 'c-1',
                'title': 'Isolate web-prod-3',
                'message_count': 4,
                'archived': false,
              },
              {'id': 'c-2', 'message_count': 0},
            ],
          }));

      final list = await client.conversations();

      expect(list, hasLength(2));
      expect(list[0].label, 'Isolate web-prod-3');
      expect(list[0].messageCount, 4);
      expect(list[1].label, 'Conversation',
          reason: 'untitled conversations get a stable label');
    });

    test('opening a missing conversation is a typed refusal', () async {
      final client = clientFor(
          (options, r) => json(404, {'detail': 'conversation not found'}));

      await expectLater(
        client.conversation('nope'),
        throwsA(isA<ChatRefusal>()),
      );
    });
  });
}
