import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/auth_api.dart';
import 'package:vigil_flutter/auth/errors.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/auth/vigil_authenticator.dart';

import '../helpers/fake_adapter.dart';

const userAgent = 'Vigil/1.0.0 (linux)';
const baseUrl = 'https://vigil.example.com';

Map<String, dynamic> _tokens(String access, String refresh) => {
      'access_token': access,
      'refresh_token': refresh,
      'user': {'username': 'analyst'},
    };

/// A wired authenticator over a scripted adapter: the auth API shares the
/// [FakeAdapter] so login/refresh requests are recorded on the same tape.
class _Harness {
  _Harness({String? access, String? refresh})
      : store = InMemoryTokenStore(accessToken: access, refreshToken: refresh) {
    final authDio = Dio(BaseOptions(baseUrl: baseUrl));
    adapter = FakeAdapter();
    authDio.httpClientAdapter = adapter;
    auth = AuthApi(dio: authDio, userAgent: userAgent);
    final apiDio = Dio(BaseOptions(baseUrl: baseUrl));
    apiDio.httpClientAdapter = adapter;
    authenticator = VigilAuthenticator(
      store: store,
      auth: auth,
      userAgent: userAgent,
    );
    apiDio.interceptors.add(authenticator);
    authenticator.attach(apiDio);
    dio = apiDio;
  }

  final InMemoryTokenStore store;

  late final FakeAdapter adapter;
  late final AuthApi auth;
  late final VigilAuthenticator authenticator;
  late final Dio dio;
}

void main() {
  group('VigilAuthenticator: refresh then replay', () {
    test('401 → one refresh → replay succeeds with the NEW pair', () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..enqueueJson(401, {'detail': 'Token expired'}) // original findings
        ..enqueueJson(200, _tokens('a2', 'r2')) // refresh rotation
        ..enqueueJson(200, {'items': []}); // replayed findings

      final res = await h.dio.get<Map<String, dynamic>>('/api/v1/findings');

      expect(res.statusCode, 200);

      final findings = h.adapter.wherePath('/api/v1/findings');
      expect(findings, hasLength(2));
      // Original call used the old token.
      expect(findings[0].header('authorization'), 'Bearer a1');
      // Replay used the rotated token — proof the NEW pair was persisted
      // BEFORE the replay fired.
      expect(findings[1].header('authorization'), 'Bearer a2');

      final refresh = h.adapter.wherePath('/api/auth/refresh');
      expect(refresh, hasLength(1));
      expect(refresh.first.body, {'refresh_token': 'r1'});

      // The store now holds the rotated pair.
      expect(await h.store.readAccess(), 'a2');
      expect(await h.store.readRefresh(), 'r2');
    });

    test('a second 401 after replay surfaces — no refresh loop', () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..enqueueJson(401, {'detail': 'Token expired'}) // original
        ..enqueueJson(200, _tokens('a2', 'r2')) // rotation #1
        ..enqueueJson(401, {'detail': 'Still denied'}); // replay 401s too

      await expectLater(
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        throwsA(isA<DioException>()
            .having((e) => e.response?.statusCode, 'status', 401)),
      );

      // Exactly one refresh was attempted for the whole chain.
      expect(h.adapter.wherePath('/api/auth/refresh'), hasLength(1));
      expect(h.adapter.wherePath('/api/v1/findings'), hasLength(2));
    });

    test('revoked refresh clears the store — sign-in required', () async {
      final h = _Harness(access: 'a1', refresh: 'consumed');
      h.adapter
        ..enqueueJson(401, {'detail': 'Token expired'})
        ..enqueueJson(401, {'detail': 'Refresh token already used'});

      await expectLater(
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        throwsA(isA<DioException>().having(
            (e) => e.error is AuthRevoked, 'error is AuthRevoked', isTrue)),
      );

      // Tokens are gone — the app shows Sign-in, not a silent loop.
      expect(await h.store.readAccess(), isNull);
      expect(await h.store.readRefresh(), isNull);
      expect(h.adapter.wherePath('/api/v1/findings'), hasLength(1));
    });

    test('missing refresh token → revoked without a refresh call', () async {
      final h = _Harness(); // no tokens stored
      h.adapter.enqueueJson(401, {'detail': 'Token expired'});

      await expectLater(
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        throwsA(isA<DioException>().having(
            (e) => e.error is AuthRevoked, 'error is AuthRevoked', isTrue)),
      );
      expect(h.adapter.wherePath('/api/auth/refresh'), isEmpty);
    });

    test('non-401 errors pass through untouched', () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..enqueueJson(500, {'detail': 'boom'})
        // Nothing else should be consumed.
        ..enqueueJson(200, {'should': 'never be reached'});

      await expectLater(
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        throwsA(isA<DioException>()
            .having((e) => e.response?.statusCode, 'status', 500)),
      );
      expect(h.adapter.wherePath('/api/auth/refresh'), isEmpty);
      expect(await h.store.readAccess(), 'a1');
    });

    test('User-Agent is byte-identical on every request of the chain',
        () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..enqueueJson(401, {'detail': 'Token expired'})
        ..enqueueJson(200, _tokens('a2', 'r2'))
        ..enqueueJson(200, {'items': []});

      await h.dio.get<Map<String, dynamic>>('/api/v1/findings');

      // Original, refresh, replay — every request carries the identical UA.
      expect(h.adapter.requests, hasLength(3));
      for (final req in h.adapter.requests) {
        expect(req.header('user-agent'), userAgent,
            reason: 'UA drifted on ${req.path}');
      }
    });

    test('concurrent 401s rotate once — the stale sibling replays directly',
        () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..enqueueJson(401, {'detail': 'Token expired'}) // request A
        ..enqueueJson(401, {'detail': 'Token expired'}) // request B
        ..enqueueJson(200, _tokens('a2', 'r2')) // the single rotation
        ..enqueueJson(200, {
          'items': ['a']
        }) // replay A
        ..enqueueJson(200, {
          'items': ['b']
        }); // replay B

      final results = await Future.wait([
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        h.dio.get<Map<String, dynamic>>('/api/v1/cases'),
      ]);

      expect(results, hasLength(2));
      // Single-use rotation means a second refresh could revoke the session —
      // exactly one is acceptable, the stale 401 replays with the new token.
      expect(h.adapter.wherePath('/api/auth/refresh'), hasLength(1));
      expect(h.adapter.wherePath('/api/v1/findings'), hasLength(2));
      expect(h.adapter.wherePath('/api/v1/cases'), hasLength(2));
      for (final req in h.adapter.requests) {
        expect(req.header('user-agent'), userAgent);
      }
    });

    test(
        'network failure during refresh keeps tokens — the original 401 '
        'propagates for the stale/offline state', () async {
      final h = _Harness(access: 'a1', refresh: 'r1');
      h.adapter
        ..failOnPath(
          '/api/auth/refresh',
          (options) => DioException(
            requestOptions: options,
            type: DioExceptionType.connectionError,
          ),
        )
        ..enqueueJson(401, {'detail': 'Token expired'});

      await expectLater(
        h.dio.get<Map<String, dynamic>>('/api/v1/findings'),
        throwsA(isA<DioException>()
            // The ORIGINAL 401 surfaces — not the connection error, not a
            // revocation.
            .having((e) => e.response?.statusCode, 'status', 401)),
      );

      // Tokens retained — a dead network is not a revoked session.
      expect(await h.store.readAccess(), 'a1');
      expect(await h.store.readRefresh(), 'r1');
      expect(h.adapter.wherePath('/api/v1/findings'), hasLength(1));
    });
  });
}
