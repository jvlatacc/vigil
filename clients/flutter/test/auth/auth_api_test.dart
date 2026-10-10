import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/auth_api.dart';
import 'package:vigil_flutter/auth/errors.dart';

import '../helpers/fake_adapter.dart';

const userAgent = 'Vigil/1.0.0 (linux)';

Map<String, dynamic> loginSession() => {
      'access_token': 'access-1',
      'refresh_token': 'refresh-1',
      'token_type': 'bearer',
      'user': {
        'user_id': 'u-1',
        'username': 'analyst',
        'email': 'analyst@corp.example',
        'permissions': {'ai_decisions.approve': true, 'cases.read': false},
      },
    };

AuthApi _api(FakeAdapter adapter) {
  final dio = Dio(BaseOptions(baseUrl: 'https://vigil.example.com'));
  dio.httpClientAdapter = adapter;
  return AuthApi(dio: dio, userAgent: userAgent);
}

void main() {
  group('AuthApi.login', () {
    test('posts username_or_email + password and parses the session', () async {
      final adapter = FakeAdapter()..enqueueJson(200, loginSession());
      final api = _api(adapter);

      final session = await api.login(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
      );

      expect(session.accessToken, 'access-1');
      expect(session.refreshToken, 'refresh-1');
      expect(session.user.username, 'analyst');
      expect(session.user.hasPermission('ai_decisions.approve'), isTrue);
      expect(session.user.hasPermission('cases.read'), isFalse);

      final req = adapter.last;
      expect(req.method, 'POST');
      expect(req.path, 'https://vigil.example.com/api/auth/login');
      expect(req.body, {
        'username_or_email': 'analyst@corp.example',
        'password': 'hunter2',
      });
      // The sfp claim binds this exact string — present from the first call.
      expect(req.header('user-agent'), userAgent);
    });

    test('forwards the MFA code when provided', () async {
      final adapter = FakeAdapter()..enqueueJson(200, loginSession());
      final api = _api(adapter);

      await api.login(
        usernameOrEmail: 'analyst',
        password: 'hunter2',
        mfaCode: '123456',
      );

      expect(adapter.last.body, {
        'username_or_email': 'analyst',
        'password': 'hunter2',
        'mfa_code': '123456',
      });
    });

    test('401 with X-MFA-Required surfaces MfaRequired', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(
          401,
          {'detail': 'MFA code required'},
          headers: {'x-mfa-required': 'true'},
        );
      final api = _api(adapter);

      await expectLater(
        api.login(usernameOrEmail: 'analyst', password: 'hunter2'),
        throwsA(isA<MfaRequired>()),
      );
    });

    test('plain 401 surfaces InvalidCredentials', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(401, {'detail': 'Invalid credentials'});
      final api = _api(adapter);

      await expectLater(
        api.login(usernameOrEmail: 'analyst', password: 'wrong'),
        throwsA(isA<InvalidCredentials>()),
      );
    });

    test('423 surfaces AccountLocked with the parsed Retry-After', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(
          423,
          {'detail': 'Account locked'},
          headers: {'retry-after': '90'},
        );
      final api = _api(adapter);

      await expectLater(
        api.login(usernameOrEmail: 'analyst', password: 'hunter2'),
        throwsA(isA<AccountLocked>().having(
          (e) => e.retryAfter,
          'retryAfter',
          const Duration(seconds: 90),
        )),
      );
    });

    test('5xx surfaces the base exception with the status code', () async {
      final adapter = FakeAdapter()..enqueueJson(500, {'detail': 'boom'});
      final api = _api(adapter);

      await expectLater(
        api.login(usernameOrEmail: 'analyst', password: 'hunter2'),
        throwsA(isA<VigilAuthException>()
            .having((e) => e.statusCode, 'statusCode', 500)),
      );
    });
  });

  group('AuthApi.refresh', () {
    test('sends the refresh token in the body and returns the NEW pair',
        () async {
      final adapter = FakeAdapter()
        ..enqueueJson(200, {
          'access_token': 'access-2',
          'refresh_token': 'refresh-2',
          'user': {'username': 'analyst'},
        });
      final api = _api(adapter);

      final session = await api.refresh(refreshToken: 'refresh-1');

      expect(session.accessToken, 'access-2');
      expect(session.refreshToken, 'refresh-2');
      expect(adapter.last.path, 'https://vigil.example.com/api/auth/refresh');
      expect(adapter.last.body, {'refresh_token': 'refresh-1'});
      // UA byte-stable across login and refresh alike.
      expect(adapter.last.header('user-agent'), userAgent);
    });

    test('401 from refresh throws AuthRevoked — sign-in required', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(401, {'detail': 'Token revoked'});
      final api = _api(adapter);

      await expectLater(
        api.refresh(refreshToken: 'consumed-jti'),
        throwsA(isA<AuthRevoked>()),
      );
    });

    test('network failures propagate unchanged — not a revocation', () async {
      final dio = Dio(BaseOptions(baseUrl: 'https://vigil.example.com'))
        ..httpClientAdapter = FailureAdapter(
          (options) => DioException(
            requestOptions: options,
            type: DioExceptionType.connectionError,
          ),
        );
      final api = AuthApi(dio: dio, userAgent: userAgent);

      await expectLater(
        api.refresh(refreshToken: 'r1'),
        throwsA(isA<DioException>()
            .having((e) => e.type, 'type', DioExceptionType.connectionError)),
      );
    });
  });

  group('AuthApi.logout', () {
    test('sends the Bearer header AND the refresh token in the body', () async {
      final adapter = FakeAdapter()..enqueueEmpty(200);
      final api = _api(adapter);

      await api.logout(accessToken: 'access-1', refreshToken: 'refresh-1');

      final req = adapter.last;
      expect(req.method, 'POST');
      expect(req.path, 'https://vigil.example.com/api/auth/logout');
      // Bearer-flow clients revoke the refresh token via the body — the
      // server blacklists both tokens on logout.
      expect(req.body, {'refresh_token': 'refresh-1'});
      expect(req.header('authorization'), 'Bearer access-1');
      expect(req.header('user-agent'), userAgent);
    });

    test('401 on logout still succeeds — tokens are dead either way', () async {
      final adapter = FakeAdapter()..enqueueJson(401, {'detail': 'expired'});
      final api = _api(adapter);

      await api.logout(accessToken: 'stale', refreshToken: 'stale-r');
      expect(adapter.last.path, contains('/api/auth/logout'));
    });
  });

  group('AuthApi.me', () {
    test('returns the parsed profile with the permission map', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(200, {
          'user_id': 'u-1',
          'username': 'analyst',
          'permissions': {'cases.read': true},
        });
      final api = _api(adapter);

      final profile = await api.me(accessToken: 'access-1');

      expect(profile.userId, 'u-1');
      expect(profile.hasPermission('cases.read'), isTrue);
      expect(adapter.last.path, 'https://vigil.example.com/api/auth/me');
      expect(adapter.last.header('authorization'), 'Bearer access-1');
    });
  });

  group('AuthApi.health', () {
    test('returns the health payload', () async {
      final adapter = FakeAdapter()
        ..enqueueJson(200, {'status': 'ok', 'version': '0.7.0'});
      final api = _api(adapter);

      final payload = await api.health();

      expect(payload['status'], 'ok');
      expect(adapter.last.path, 'https://vigil.example.com/api/health');
      expect(adapter.last.header('user-agent'), userAgent);
    });
  });
}
