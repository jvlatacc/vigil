import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/chat/chat_api.dart';
import 'package:vigil_flutter/chat/chat_session.dart';

import 'fake_adapter.dart';
import 'wired_vigil.dart';

/// Default chat transport: an empty conversation list and 404s elsewhere —
/// enough for surfaces that never open the pane, and an honest error state
/// (historyError) for those that do.
ResponseBody defaultChatHandler(RequestOptions options, RecordedRequest r) {
  if (r.path.contains('/api/conversations')) {
    return json(200, {'conversations': []});
  }
  return json(404, {'detail': 'unscripted chat path ${r.path}'});
}

/// A [ChatSession] over a scripted transport. [handler] overrides responses
/// per path; [random] pins session-id generation in tests.
ChatSession stubChatSession({
  ResponseBody Function(RequestOptions options, RecordedRequest request)?
      handler,
  Random? random,
}) {
  final dio = Dio(BaseOptions(baseUrl: testBaseUrl))
    ..httpClientAdapter = RoutedAdapter(handler ?? defaultChatHandler);
  return ChatSession(chat: VigilChatClient(dio: dio), random: random);
}

/// One SSE frame as the backend writes it (`data: {json}\n\n`).
String sseFrame(Map<String, dynamic> body) => 'data: ${jsonEncode(body)}\n\n';

/// Advances the event loop until [condition] holds — the dio pipeline needs
/// several turns between `send()` and the first frame, so a fixed microtask
/// count races. Fails the test when the budget is spent.
Future<void> untilCondition(
  bool Function() condition, {
  int budget = 2000,
  String reason = 'condition not reached',
}) async {
  for (var i = 0; i < budget && !condition(); i++) {
    await Future<void>.delayed(Duration.zero);
  }
  if (!condition()) fail('$reason within $budget event-loop turns');
}

/// A streamed `text/event-stream` response body whose chunks arrive on
/// [Stream] boundaries exactly as scripted — the mid-frame splits stay
/// where the test puts them.
ResponseBody sseResponse(Iterable<String> chunks) => ResponseBody(
      Stream<Uint8List>.fromIterable([
        for (final chunk in chunks) Uint8List.fromList(utf8.encode(chunk)),
      ]),
      200,
      headers: {
        Headers.contentTypeHeader: const ['text/event-stream'],
      },
    );
