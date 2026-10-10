import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/token_store.dart';

import 'fake_adapter.dart';

const testBaseUrl = 'https://soc.example.com';
const testUserAgent = 'Vigil/1.0.0 (widget-test)';

/// JSON [ResponseBody] with the content-type dio needs to decode the body.
ResponseBody json(
  int status,
  Map<String, dynamic> body, {
  Map<String, String> headers = const {},
}) =>
    ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
        ...headers.map((k, v) => MapEntry(k, [v])),
      },
    );

/// Login/me payloads in the shape `Session.fromBody`/`UserProfile.fromBody`
/// parse (`_user_payload` on the backend).
Map<String, dynamic> userBody({Map<String, bool> permissions = const {}}) => {
      'user_id': 'u-1',
      'username': 'jane',
      'email': 'jane@corp.example',
      'full_name': 'Jane Doe',
      'permissions': permissions,
    };

Map<String, dynamic> loginBody({Map<String, bool> permissions = const {}}) => {
      'access_token': 'access-1',
      'refresh_token': 'refresh-1',
      'token_type': 'bearer',
      'user': userBody(permissions: permissions),
    };

/// Everything the shell needs from the server, scripted by path — the
/// answers a healthy Vigil gives the entry flows. Tests override specific
/// paths by matching them first.
ResponseBody defaultAuthHandler(RequestOptions options, RecordedRequest r) {
  final path = r.path;
  if (path.contains('/api/health')) {
    return json(200, {'status': 'ok', 'version': '1'});
  }
  if (path.contains('/api/auth/bootstrap') && r.method == 'GET') {
    return json(200, {'required': false});
  }
  if (path.contains('/api/auth/bootstrap')) {
    return json(201, userBody());
  }
  if (path.contains('/api/auth/login')) {
    return json(200, loginBody());
  }
  if (path.contains('/api/auth/me')) {
    return json(200, userBody());
  }
  if (path.contains('/api/auth/logout')) {
    return json(204, {});
  }
  return json(404, {'detail': 'unscripted auth path $path'});
}

ResponseBody defaultApiHandler(RequestOptions options, RecordedRequest r) {
  final path = r.path;
  if (path.contains('/api/config/theme')) {
    if (r.method == 'GET') return json(200, {'theme': 'dark'});
    return json(200, {'theme': 'light'});
  }
  if (path.contains('/api/v1/approvals/needs-you')) {
    return json(200, needsYouBody(const []));
  }
  if (path.contains('/api/v1/approvals')) {
    if (r.method == 'POST') {
      return json(200, approvalActionResultBody());
    }
    return json(200, approvalListBody(const []));
  }
  return json(404, {'detail': 'unscripted api path $path'});
}

// ---- approvals fixtures (snake_case wire names of the frozen contract) ----

Map<String, dynamic> needsYouBody(List<Map<String, dynamic>> items) =>
    {'count': items.length, 'items': items};

Map<String, dynamic> needsYouItemBody({
  String sourceId = 'a-1',
  String kind = 'response_action',
  String title = 'Isolate host web-prod-3',
  String reason = 'Confidence below the 0.90 auto-approve line',
  String reversibility = 'reversible',
  String? caseId = 'c-1',
  String createdAt = '2026-10-10T13:58:00Z',
}) =>
    {
      'kind': kind,
      'source_id': sourceId,
      'title': title,
      'reason': reason,
      'created_at': createdAt,
      'reversibility': reversibility,
      'case_id': caseId,
    };

Map<String, dynamic> approvalListBody(
        List<Map<String, dynamic>> actions) =>
    {'count': actions.length, 'actions': actions};

Map<String, dynamic> pendingActionBody({
  String actionId = 'a-1',
  String title = 'Isolate host web-prod-3',
  double confidence = 0.88,
  String reversibility = 'reversible',
  String status = 'pending',
  String reason = 'Confidence below the 0.90 auto-approve line',
  String createdAt = '2026-10-10T13:58:00Z',
  Object? evidence,
}) =>
    {
      'action_id': actionId,
      'action_type': 'isolate_host',
      'title': title,
      'confidence': confidence,
      'reversibility': reversibility,
      'status': status,
      'reason': reason,
      'created_at': createdAt,
      'requires_approval': true,
      if (evidence != null) 'evidence': evidence,
    };

Map<String, dynamic> approvalActionResultBody({
  String actionId = 'a-1',
  String status = 'approved',
}) =>
    {
      'action': pendingActionBody(actionId: actionId, status: status),
      'resume_result': null,
    };

/// Path-routed scripted transport for widget tests: a handler decides each
/// response, so tests override single endpoints (`/api/auth/login` → MFA
/// 401 first, 200 second) without depending on queue order.
class RoutedAdapter implements HttpClientAdapter {
  RoutedAdapter(
    ResponseBody Function(RequestOptions options, RecordedRequest request)
        handler,
  ) : _handler = handler;

  final ResponseBody Function(RequestOptions options, RecordedRequest request)
      _handler;

  final List<RecordedRequest> requests = [];

  RecordedRequest? call(String pathSubstring) {
    for (final r in requests.reversed) {
      if (r.path.contains(pathSubstring)) return r;
    }
    return null;
  }

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(RecordedRequest.of(options));
    return _handler(options, requests.last);
  }

  @override
  void close({bool force = false}) {}
}

/// A [VigilClient] wired to [auth] and [api] scripted transports over an
/// in-memory token store — every widget test's data plane.
VigilClient wiredClient({
  required RoutedAdapter auth,
  required RoutedAdapter api,
  TokenStore? tokenStore,
  String baseUrl = testBaseUrl,
}) =>
    VigilClient(
      baseUrl: baseUrl,
      tokenStore: tokenStore ?? InMemoryTokenStore(),
      userAgent: testUserAgent,
      authAdapter: auth,
      apiAdapter: api,
    );
