import 'package:dio/dio.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../auth/auth_api.dart';
import '../auth/errors.dart';
import '../auth/session.dart';
import '../auth/token_store.dart';
import '../auth/vigil_authenticator.dart';
import 'attack_api.dart';
import 'config_api.dart';
import 'triage_api.dart';

/// Builds a [VigilClient] for a server. Injectable so tests script the
/// transport — one adapter captures every request the app makes, across
/// every client a session (or onboarding flow) builds.
typedef VigilClientFactory = VigilClient Function({
  required String baseUrl,
  required TokenStore tokenStore,
  required String userAgent,
});

/// Production factory — real secure storage, default HTTP transport.
VigilClient defaultClientFactory({
  required String baseUrl,
  required TokenStore tokenStore,
  required String userAgent,
}) =>
    VigilClient(
      baseUrl: baseUrl,
      tokenStore: tokenStore,
      userAgent: userAgent,
    );

/// Composition root for the Vigil data plane.
///
/// Two Dio instances, mirroring the console's split between pre-auth and
/// session traffic:
///
/// * `_authDio` (bare) — `/api/auth/*` and `/api/health`. No interceptors: a
///   refresh must never be routed back through the authenticator.
/// * `_apiDio` — the frozen `/api/v1` surface, guarded by
///   [VigilAuthenticator] for bearer injection, the byte-stable User-Agent,
///   and one-shot refresh-then-replay.
///
/// Both carry the same User-Agent string: the backend binds tokens to
/// `sha256(User-Agent)[:16]` and verifies it on every request, so the string
/// must be byte-identical from login through refresh through every v1 call.
class VigilClient {
  VigilClient({
    required String baseUrl,
    required TokenStore tokenStore,
    required String userAgent,
    Duration connectTimeout = const Duration(seconds: 10),
    Duration receiveTimeout = const Duration(seconds: 30),

    /// Test seams: replace the transport of each Dio instance with a scripted
    /// adapter. Null in production — the default HTTP transport is used.
    HttpClientAdapter? authAdapter,
    HttpClientAdapter? apiAdapter,
  }) : _tokenStore = tokenStore {
    BaseOptions baseOptions() => BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: connectTimeout,
          receiveTimeout: receiveTimeout,
          // The UA rides on every request of both instances; the
          // authenticator re-asserts it per request on _apiDio.
          headers: {'user-agent': userAgent},
        );

    final authDio = Dio(baseOptions());
    if (authAdapter != null) authDio.httpClientAdapter = authAdapter;
    auth = AuthApi(dio: authDio, userAgent: userAgent);

    final authenticator = VigilAuthenticator(
      store: tokenStore,
      auth: auth,
      userAgent: userAgent,
    );
    _apiDio = Dio(baseOptions());
    if (apiAdapter != null) _apiDio.httpClientAdapter = apiAdapter;
    _apiDio.interceptors.add(authenticator);
    authenticator.attach(_apiDio);

    v1 = VigilApiV1(dio: _apiDio);
    config = ConfigApi(dio: _apiDio);
    attack = AttackApi(dio: _apiDio);
    triage = TriageApi(dio: _apiDio);
  }

  final TokenStore _tokenStore;
  late final Dio _apiDio;

  /// Hand-written auth endpoints (`/api/auth/*`, `/api/health`).
  late final AuthApi auth;

  /// Generated client for the frozen `/api/v1` contract.
  late final VigilApiV1 v1;

  /// Console-surface config endpoints the shell needs (theme persistence).
  /// Bare `/api` carries no stability promise — the accepted exception,
  /// like [auth] — so only the calls with console parity live here.
  late final ConfigApi config;

  /// ATT&CK technique rollup (console surface, hand-written).
  late final AttackApi attack;

  /// Triage intake queue (console surface, hand-written).
  late final TriageApi triage;

  /// Whether a session is stored on this device (drives the sign-in gate).
  Future<bool> get hasSession async => (await _tokenStore.readAccess()) != null;

  /// Exchanges credentials for a token pair and persists it. Throws the
  /// typed auth failures — [MfaRequired] (retry with the TOTP code),
  /// [AccountLocked], [InvalidCredentials].
  Future<Session> signIn({
    required String usernameOrEmail,
    required String password,
    String? mfaCode,
  }) async {
    final session = await auth.login(
      usernameOrEmail: usernameOrEmail,
      password: password,
      mfaCode: mfaCode,
    );
    await _tokenStore.save(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
    );
    return session;
  }

  /// Fetches the current user + permission map (shell navigation gating).
  Future<UserProfile> currentUser() async {
    final token = await _tokenStore.readAccess();
    if (token == null) {
      throw AuthRevoked(reason: 'not signed in');
    }
    return auth.me(accessToken: token);
  }

  /// Rebuilds the signed-in user from stored tokens after an app restart:
  /// `/auth/me` with the stored access token; on 401, one refresh-then-retry
  /// — the same one-shot rule the interceptor applies to `/api/v1` calls
  /// (`/auth/me` runs on the bare auth Dio, so it cannot rely on it).
  /// Returns null when there is no stored session or it is revoked
  /// (consumed jti / blacklist) — sign-in required.
  Future<UserProfile?> restoreSession() async {
    final access = await _tokenStore.readAccess();
    if (access == null) return null;
    try {
      return await auth.me(accessToken: access);
    } on DioException catch (e) {
      if (e.response?.statusCode != 401) rethrow;
      final refresh = await _tokenStore.readRefresh();
      if (refresh == null) return null;
      try {
        final session = await auth.refresh(refreshToken: refresh);
        await _tokenStore.save(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
        );
        return await auth.me(accessToken: session.accessToken);
      } on AuthRevoked {
        await _tokenStore.clear();
        return null;
      }
    }
  }

  /// Revokes both tokens server-side (refresh token in the body — bearer
  /// clients have no cookie fallback) and clears local state.
  Future<void> signOut() async {
    try {
      final access = await _tokenStore.readAccess();
      final refresh = await _tokenStore.readRefresh();
      if (access != null && refresh != null) {
        await auth.logout(accessToken: access, refreshToken: refresh);
      }
    } finally {
      // The local session ends even when the revocation call fails
      // (offline): an orphaned refresh token dies at its TTL, and a
      // successful sign-in here replaces it.
      await _tokenStore.clear();
    }
  }
}
