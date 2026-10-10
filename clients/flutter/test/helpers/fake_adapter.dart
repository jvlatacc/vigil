import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

/// One request the [FakeAdapter] saw, with the header values the auth layer
/// must control (User-Agent byte-stability, bearer injection, bodies).
class RecordedRequest {
  RecordedRequest({
    required this.method,
    required this.path,
    required this.headers,
    required this.body,
  });

  factory RecordedRequest.of(RequestOptions options) {
    final data = options.data;
    Object? body;
    if (data is String && data.isNotEmpty) {
      // dio encodes the JSON body before the adapter sees it.
      body = jsonDecode(data);
    } else {
      body = data;
    }
    return RecordedRequest(
      method: options.method,
      path: options.uri.toString(),
      headers: Map<String, String>.from(
        options.headers.map((k, v) => MapEntry(k, v.toString())),
      ),
      body: body,
    );
  }

  final String method;
  final String path;
  final Map<String, String> headers;
  final Object? body;

  String? header(String name) => headers[name.toLowerCase()] ?? headers[name];
}

class _ScriptedResponse {
  _ScriptedResponse(this.status, this.body, this.headers);
  final int status;
  final String body;
  final Map<String, List<String>> headers;
}

/// Scripted in-memory [HttpClientAdapter]: records every request and answers
/// with the queued responses in order. The Dio-under-test equivalent of a
/// mocked transport — no sockets, no clocks.
class FakeAdapter implements HttpClientAdapter {
  final List<RecordedRequest> requests = [];
  final List<_ScriptedResponse> _responses = [];

  final Map<String, Exception Function(RequestOptions options)> _failures = {};

  /// Makes every request whose uri contains [pathSubstring] fail
  /// transport-style (e.g. connection error) instead of consuming a scripted
  /// response — used to test rotation failures independent of the API path.
  void failOnPath(
    String pathSubstring,
    Exception Function(RequestOptions options) make,
  ) =>
      _failures[pathSubstring] = make;

  /// Queues a JSON response for the next request.
  void enqueueJson(
    int status,
    Map<String, dynamic> body, {
    Map<String, String> headers = const {},
  }) {
    _responses.add(_ScriptedResponse(
      status,
      jsonEncode(body),
      {
        // KEY 'content-type' (Headers.jsonContentType is the MIME VALUE,
        // not the header name — using it as a key left responses without a
        // content-type and dio skipped JSON decoding).
        Headers.contentTypeHeader: ['application/json'],
        ...headers.map((k, v) => MapEntry(k, [v])),
      },
    ));
  }

  /// Queues an empty-body response (e.g. non-JSON 204s).
  void enqueueEmpty(int status, {Map<String, String> headers = const {}}) {
    _responses.add(_ScriptedResponse(
      status,
      '',
      headers.map((k, v) => MapEntry(k, [v])),
    ));
  }

  RecordedRequest get last => requests.last;

  /// All recorded requests whose uri contains [pathSuffix], in order.
  List<RecordedRequest> wherePath(String pathSuffix) =>
      requests.where((r) => r.path.contains(pathSuffix)).toList();

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(RecordedRequest.of(options));
    for (final entry in _failures.entries) {
      if (options.uri.toString().contains(entry.key)) {
        throw entry.value(options);
      }
    }
    if (_responses.isEmpty) {
      throw StateError(
          'FakeAdapter has no scripted response for ${options.uri}');
    }
    final scripted = _responses.removeAt(0);
    return ResponseBody.fromString(
      scripted.body,
      scripted.status,
      headers: scripted.headers,
    );
  }

  @override
  void close({bool force = false}) {}
}

/// Adapter that always fails transport-style — simulates a dead network
/// without scripting a response. The error factory decides the DioException.
class FailureAdapter implements HttpClientAdapter {
  FailureAdapter(this.onFetch);
  final Exception Function(RequestOptions options) onFetch;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) =>
      Future.error(onFetch(options));

  @override
  void close({bool force = false}) {}
}
