import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../auth/errors.dart';
import 'failures.dart';

/// One turn sent to the stream endpoint — role is `user` or `assistant`
/// (the console maps its `vigil` role to `assistant` on the wire).
class ChatTurn {
  const ChatTurn({required this.role, required this.content});

  final String role;
  final String content;

  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}

/// Events a chat turn streams. The backend relays the agent layer's frames
/// unchanged (`services/api/routers/claude.py::_relay`): text frames carry
/// the answer, `tool_processing` separates tool output from the prose
/// around it, `context_windowed` is an engine detail the console ignores.
sealed class ChatStreamEvent {
  const ChatStreamEvent();
}

/// A slice of the answer — append [content] to the accumulated text and
/// render incrementally.
class ChatTextChunk extends ChatStreamEvent {
  const ChatTextChunk(this.content);

  final String content;
}

/// Tool output begins — the console inserts a paragraph break so the tool
/// block is not glued to the prose preceding it.
class ChatToolProcessing extends ChatStreamEvent {
  const ChatToolProcessing();
}

/// A conversation as the history list shows it (`ConversationSummarySchema`).
class ConversationSummary {
  const ConversationSummary({
    required this.id,
    required this.title,
    required this.messageCount,
    required this.archived,
  });

  factory ConversationSummary.fromBody(Map<String, dynamic> body) =>
      ConversationSummary(
        id: body['id'] as String,
        title: body['title'] as String?,
        messageCount: (body['message_count'] as num?)?.toInt() ?? 0,
        archived: (body['archived'] as bool?) ?? false,
      );

  final String id;
  final String? title;
  final int messageCount;
  final bool archived;

  /// Picker label — untitled conversations exist until the first turn lands.
  String get label =>
      (title == null || title!.trim().isEmpty) ? 'Conversation' : title!.trim();
}

/// One message of an opened conversation (`ChatMessageSchema` subset).
class ConversationMessage {
  const ConversationMessage({required this.role, required this.content});

  final String? role;
  final String? content;

  factory ConversationMessage.fromBody(Map<String, dynamic> body) =>
      ConversationMessage(
        role: body['role'] as String?,
        content: body['content'] as String?,
      );
}

/// A conversation with its ordered messages (`ConversationSchema`).
class Conversation {
  const Conversation({required this.summary, required this.messages});

  final ConversationSummary summary;
  final List<ConversationMessage> messages;

  factory Conversation.fromBody(Map<String, dynamic> body) => Conversation(
        summary: ConversationSummary.fromBody(body),
        messages: [
          for (final m in (body['messages'] as List? ?? []))
            ConversationMessage.fromBody(m as Map<String, dynamic>),
        ],
      );
}

/// Parses the byte-chunk stream into SSE frames, byte-boundary agnostic: a
/// JSON frame may arrive split across chunks, so partial lines are carried
/// over until a newline completes them (the console's chat does the same
/// with its read buffer). Only `data:` lines carry frames.
class SseFrameParser {
  final StringBuffer _carry = StringBuffer();

  /// Feeds one decoded chunk; returns every complete JSON frame it ends.
  List<Map<String, dynamic>> addChunk(String text) {
    final frames = <Map<String, dynamic>>[];
    final combined = _carry.isEmpty ? text : _carry.toString() + text;
    final lines = combined.split('\n');
    final partial = lines.removeLast();
    _carry
      ..clear()
      ..write(partial);
    for (final raw in lines) {
      final line = raw.endsWith('\r') ? raw.substring(0, raw.length - 1) : raw;
      if (!line.startsWith(_dataPrefix)) continue;
      final data = line.substring(_dataPrefix.length).trim();
      if (data.isEmpty) continue;
      try {
        final frame = jsonDecode(data);
        if (frame is Map<String, dynamic>) frames.add(frame);
      } on FormatException {
        // A frame the backend never wrote — skip it, like the console.
      }
    }
    return frames;
  }

  /// What the backend wrote: `data: {json}\n\n` per frame (claude.py `_frame`).
  static const _dataPrefix = 'data: ';
}

/// Hand-written client for the chat surface — the endpoints outside the
/// frozen `/api/v1` snapshot: `POST /api/claude/chat/stream` (SSE) and the
/// `/api/conversations` history CRUD the dock needs. Like [ConfigApi] it is
/// typed by hand against the routers and covered by unit tests instead of
/// codegen. The Dio passed in is the app's *authenticated* instance, so the
/// bearer injection, byte-stable User-Agent, and one-shot 401 → refresh →
/// replay all ride the shared `VigilAuthenticator` — the SSE stream is a
/// first-class citizen of the session, not a side channel.
class VigilChatClient {
  VigilChatClient({required Dio dio}) : _dio = dio;

  final Dio _dio;

  /// Timeout parity with the console's `LLM_TIMEOUT` (180 s). On a streamed
  /// response dio applies `receiveTimeout` as the longest silence between
  /// chunks — a turn that stops talking for 180 s dies instead of hanging.
  static const sseTimeout = Duration(seconds: 180);

  /// Streams one chat turn from `POST /api/claude/chat/stream`.
  ///
  /// Yields [ChatTextChunk]/[ChatToolProcessing] as frames arrive; the
  /// returned stream *fails* with a [ChatFailure] when the turn cannot
  /// proceed — a server error frame, a refusal status, a dead network, or a
  /// revoked session (the authenticator's one-shot refresh-and-replay
  /// already ran for auth 401s; a second 401 surfaces here).
  Stream<ChatStreamEvent> streamTurn({
    required List<ChatTurn> turns,
    required String sessionId,
    String? caseId,
    CancelToken? cancelToken,
  }) async* {
    final Response<ResponseBody> res;
    try {
      res = await _dio.post<ResponseBody>(
        '/api/claude/chat/stream',
        data: {
          'messages': [for (final t in turns) t.toJson()],
          'session_id': sessionId,
          if (caseId != null) 'case_id': caseId,
        },
        cancelToken: cancelToken,
        options: Options(
          responseType: ResponseType.stream,
          receiveTimeout: sseTimeout,
          headers: {'accept': 'text/event-stream'},
        ),
      );
    } on DioException catch (e) {
      // A stop() while the request is still pending cancels the token —
      // the error would surface after the listener is gone (an unhandled
      // zone error), so a cancelled turn ends the stream silently.
      if (cancelToken?.isCancelled ??
          false || e.type == DioExceptionType.cancel) {
        return;
      }
      throw await _failureFor(e);
    }

    final body = res.data;
    if (body == null) {
      throw ChatRefusal('Empty response from Vigil.');
    }
    final parser = SseFrameParser();
    try {
      await for (final chunk in body.stream) {
        for (final frame in parser.addChunk(_decode(chunk))) {
          final error = frame['error'];
          if (error is String && error.isNotEmpty) {
            throw ChatRefusal(error);
          }
          switch (frame['type']) {
            case 'text':
              yield ChatTextChunk((frame['content'] as String?) ?? '');
            case 'tool_processing':
              yield const ChatToolProcessing();
            default:
            // `context_windowed` and unknown frame types: engine details,
            // not part of the answer — the console skips them too.
          }
        }
      }
    } on ChatFailure {
      rethrow;
    } on DioException catch (e) {
      // A cancelled stream ends silently — the listener asked to stop.
      if (e.type == DioExceptionType.cancel) return;
      throw await _failureFor(e);
    }
  }

  Future<List<ConversationSummary>> conversations() async {
    final res = await _dio.get<Map<String, dynamic>>('/api/conversations');
    final items = res.data?['conversations'] as List? ?? [];
    return [
      for (final item in items)
        ConversationSummary.fromBody(item as Map<String, dynamic>),
    ];
  }

  Future<Conversation> conversation(String id) async {
    try {
      final res =
          await _dio.get<Map<String, dynamic>>('/api/conversations/$id');
      return Conversation.fromBody(res.data ?? const {});
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        throw ChatRefusal('Conversation not found.');
      }
      rethrow;
    }
  }

  /// Maps a DioException to the failure the console would show: 502/503 and
  /// connection errors mean "could not reach"; other statuses carry the
  /// server's detail; a wrapped `AuthRevoked` ends the session.
  Future<ChatFailure> _failureFor(DioException e) async {
    final error = e.error;
    if (error is AuthRevoked) return ChatAuthRevoked();
    if (e.type == DioExceptionType.cancel) return ChatUnreachable('stopped');
    final status = e.response?.statusCode;
    if (status == 502 || status == 503) {
      return ChatUnreachable('HTTP $status');
    }
    if (e.response == null) {
      return ChatUnreachable(e.message ?? 'connection failed');
    }
    return ChatRefusal(await _detailOf(e.response!));
  }

  /// The refusal detail from an error body — `{"detail": …}` when the API
  /// wrote JSON, the raw text otherwise (the console's `refusalOf`).
  ///
  /// Stream-type responses keep the body unread: dio hands back a
  /// [ResponseBody] whose stream must be drained before the detail exists.
  static Future<String> _detailOf(Response response) async {
    final data = response.data;
    if (data is ResponseBody) {
      final buffer = StringBuffer();
      try {
        await for (final chunk in data.stream) {
          buffer.write(_decode(chunk));
        }
      } on Exception {
        return 'HTTP ${response.statusCode}';
      }
      return _detailFromBody(buffer.toString(), response.statusCode);
    }
    if (data is Map<String, dynamic> && data['detail'] is String) {
      return data['detail'] as String;
    }
    if (data is String) return _detailFromBody(data, response.statusCode);
    return 'HTTP ${response.statusCode}';
  }

  static String _detailFromBody(String body, int? statusCode) {
    if (body.trim().isEmpty) return 'HTTP $statusCode';
    try {
      final parsed = jsonDecode(body);
      if (parsed is Map<String, dynamic> && parsed['detail'] is String) {
        return parsed['detail'] as String;
      }
    } on FormatException {
      // Not JSON — show the raw body.
    }
    return body.trim();
  }

  static String _decode(Uint8List chunk) =>
      utf8.decode(chunk, allowMalformed: true);
}
