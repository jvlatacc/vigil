import 'package:dio/dio.dart';

import 'errors.dart';
import 'session.dart';

/// Hand-written client for the console-surface auth endpoints and health.
///
/// These sit outside the frozen `/api/v1` snapshot (the only public paths the
/// app needs), so they are typed by hand against `services/api/routers/auth.py`
/// and covered by unit tests instead of codegen. The Dio instance passed in is
/// the *bare* one — login/refresh run before any session exists and must never
/// pass through [VigilAuthenticator] (a refresh routed back through the
/// interceptor could recurse into itself). Calls that need authentication take
/// the access token explicitly and send `Authorization: Bearer` themselves.
///
/// Every request carries the byte-stable User-Agent: tokens bind an `sfp`
/// claim of `sha256(User-Agent)[:16]`, verified per request.
class AuthApi {
  AuthApi({required Dio dio, required String userAgent})
      : _dio = dio,
        _userAgent = userAgent;

  static const _userAgentHeader = 'user-agent';
  static const _mfaRequiredHeader = 'x-mfa-required';
  static const _retryAfterHeader = 'retry-after';

  final Dio _dio;
  final String _userAgent;

  Options _options({Map<String, String> extra = const {}}) => Options(
        headers: {_userAgentHeader: _userAgent, ...extra},
      );

  /// POST `/api/auth/login` — exchanges credentials (plus optional TOTP code)
  /// for a token pair. Throws [MfaRequired] when the server demands a TOTP
  /// code (retry once with `mfaCode`), [AccountLocked] on 423, and
  /// [InvalidCredentials] on a plain 401.
  Future<Session> login({
    required String usernameOrEmail,
    required String password,
    String? mfaCode,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/login',
        data: {
          'username_or_email': usernameOrEmail,
          'password': password,
          if (mfaCode != null) 'mfa_code': mfaCode,
        },
        options: _options(),
      );
      return Session.fromBody(res.data!);
    } on DioException catch (e) {
      throw _loginFailure(e);
    }
  }

  /// POST `/api/auth/refresh` — single-use rotation: the passed refresh token
  /// is consumed and a NEW pair is returned. Throws [AuthRevoked] when the
  /// server refuses (blacklisted/consumed/invalid token) — sign-in required.
  Future<Session> refresh({required String refreshToken}) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/refresh',
        data: {'refresh_token': refreshToken},
        options: _options(),
      );
      return Session.fromBody(res.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        throw AuthRevoked(
          reason: _detail(e) ?? 'refresh token rejected',
          statusCode: 401,
        );
      }
      rethrow;
    }
  }

  /// POST `/api/auth/logout` — blacklists the access token (from the Bearer
  /// header) and the refresh token passed in the body, so neither can outlive
  /// the sign-out. Bearer-flow clients must send the refresh token in the
  /// body; the cookie fallback does not exist here.
  Future<void> logout({
    required String accessToken,
    required String refreshToken,
  }) async {
    try {
      await _dio.post<void>(
        '/api/auth/logout',
        data: {'refresh_token': refreshToken},
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        // Already signed out server-side — treat as success, the tokens are
        // dead either way and the caller clears them.
        return;
      }
      rethrow;
    }
  }

  /// GET `/api/auth/bootstrap` — whether the instance still needs its first
  /// account. There is no self-service signup, so an empty instance cannot
  /// be signed into at all; onboarding offers first-admin creation instead.
  Future<bool> bootstrapRequired() async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/auth/bootstrap',
      options: _options(),
    );
    return res.data?['required'] == true;
  }

  /// POST `/api/auth/bootstrap` — creates the first admin account (201) and
  /// returns its profile (no tokens: the caller signs in right after).
  /// Throws [BootstrapClosed] once any account exists (403 — the endpoint
  /// closes permanently) and [BootstrapRejected] when the password policy
  /// refuses (400 — the message carries the policy reason).
  Future<UserProfile> bootstrap({
    required String username,
    required String email,
    required String password,
    String? fullName,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/bootstrap',
        data: {
          'username': username,
          'email': email,
          'password': password,
          if (fullName != null && fullName.isNotEmpty) 'full_name': fullName,
        },
        options: _options(),
      );
      return UserProfile.fromBody(res.data!);
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final detail = _detail(e);
      switch (status) {
        case 403:
          throw BootstrapClosed(
            detail: detail ?? 'An account already exists.',
          );
        case 400:
          throw BootstrapRejected(
            detail: detail ?? 'The password was rejected.',
          );
        default:
          throw UnexpectedAuthResponse(
            detail ?? 'Could not create the account',
            statusCode: status,
          );
      }
    }
  }

  /// GET `/api/auth/me` — the current user with the resolved permissions map
  /// the shell gates navigation on.
  Future<UserProfile> me({required String accessToken}) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/auth/me',
      options: _options(extra: {'authorization': 'Bearer $accessToken'}),
    );
    return UserProfile.fromBody(res.data!);
  }

  /// POST `/api/auth/change-password` — verifies the current password, applies
  /// the strength policy, and revokes every outstanding token for the user:
  /// a successful change ends this session server-side and the caller must
  /// return the user to sign-in. Throws [CurrentPasswordRejected] (401) and
  /// [PasswordPolicyRejected] (400, with the server's reason).
  Future<void> changePassword({
    required String accessToken,
    required String currentPassword,
    required String newPassword,
  }) async {
    try {
      await _dio.post<void>(
        '/api/auth/change-password',
        data: {
          'current_password': currentPassword,
          'new_password': newPassword,
        },
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
    } on DioException catch (e) {
      final detail = _detail(e);
      switch (e.response?.statusCode) {
        case 401:
          throw CurrentPasswordRejected(statusCode: 401);
        case 400:
          throw PasswordPolicyRejected(
            detail: detail ?? 'The new password was rejected.',
          );
        default:
          throw UnexpectedAuthResponse(
            detail ?? 'Could not change the password',
            statusCode: e.response?.statusCode,
          );
      }
    }
  }

  /// POST `/api/auth/mfa/setup` — begins TOTP enrollment: a secret to enter
  /// into an authenticator app and the matching `otpauth://` URI. Codes are
  /// not issued here; [mfaVerify] returns them once the first TOTP confirms.
  Future<MfaSetup> mfaSetup({required String accessToken}) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/mfa/setup',
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
      return MfaSetup.fromBody(res.data!);
    } on DioException catch (e) {
      throw UnexpectedAuthResponse(
        _detail(e) ?? 'Could not start MFA setup',
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// POST `/api/auth/mfa/verify` — confirms the first TOTP code and enables
  /// MFA, returning the one-time recovery codes. Throws [InvalidMfaCode] on
  /// 400; the enrollment stays open.
  Future<RecoveryCodes> mfaVerify({
    required String accessToken,
    required String code,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/mfa/verify',
        data: {'code': code},
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
      return RecoveryCodes.fromBody(res.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 400) throw InvalidMfaCode(statusCode: 400);
      throw UnexpectedAuthResponse(
        _detail(e) ?? 'Could not verify the code',
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// POST `/api/auth/mfa/recovery-codes` — a fresh set of one-time codes,
  /// invalidating any previous set. Requires MFA to already be enabled;
  /// throws [MfaNotSetUp] on 400.
  Future<RecoveryCodes> mfaRecoveryCodes({required String accessToken}) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/mfa/recovery-codes',
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
      return RecoveryCodes.fromBody(res.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 400) throw MfaNotSetUp(statusCode: 400);
      throw UnexpectedAuthResponse(
        _detail(e) ?? 'Could not generate recovery codes',
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// DELETE `/api/auth/mfa` — turns MFA off for the account.
  Future<void> mfaDisable({required String accessToken}) async {
    try {
      await _dio.delete<void>(
        '/api/auth/mfa',
        options: _options(extra: {'authorization': 'Bearer $accessToken'}),
      );
    } on DioException catch (e) {
      throw UnexpectedAuthResponse(
        _detail(e) ?? 'Could not disable MFA',
        statusCode: e.response?.statusCode,
      );
    }
  }

  /// GET `/api/health` — public liveness probe, also used to validate a
  /// server URL during onboarding. Returns the payload (includes version).
  Future<Map<String, dynamic>> health() async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/health',
      options: _options(),
    );
    return res.data ?? const {};
  }

  VigilAuthException _loginFailure(DioException e) {
    final res = e.response;
    switch (res?.statusCode) {
      case 401:
        final mfa = res?.headers.value(_mfaRequiredHeader);
        if (mfa != null && mfa.toLowerCase() == 'true') return MfaRequired();
        return InvalidCredentials(statusCode: 401);
      case 423:
        return AccountLocked(retryAfter: _parseRetryAfter(res));
      default:
        return UnexpectedAuthResponse(
          _detail(e) ?? 'Login failed',
          statusCode: res?.statusCode,
        );
    }
  }

  static String? _detail(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic> && data['detail'] is String) {
      return data['detail'] as String;
    }
    return null;
  }

  static Duration? _parseRetryAfter(Response<dynamic>? res) {
    final value = res?.headers.value(_retryAfterHeader);
    if (value == null) return null;
    final seconds = int.tryParse(value.trim());
    return seconds == null ? null : Duration(seconds: seconds);
  }
}
