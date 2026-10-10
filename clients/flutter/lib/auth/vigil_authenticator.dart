import 'package:dio/dio.dart';

import 'auth_api.dart';
import 'errors.dart';
import 'token_store.dart';

/// Bearer-token interceptor for the authenticated Dio instance.
///
/// The native counterpart of the console's cookie flow
/// (`clients/web/src/services/api.ts`): attach the bearer + byte-stable
/// User-Agent to every request, and on a 401 run the one-shot refresh-then-
/// replay — the server rotates refresh tokens single-use, so the NEW pair is
/// persisted BEFORE the failed request is replayed.
///
/// Concurrency: a plain [Interceptor] plus an explicit refresh lock, NOT a
/// [QueuedInterceptor]. QueuedInterceptor serializes every callback through
/// one queue, and the replay is a nested `dio.fetch` — when the replayed
/// request itself 401s, its error callback waits on the queue the outer
/// handler still holds: a deadlock. The explicit lock gives the same
/// guarantee (concurrent 401s wait behind the in-flight rotation instead of
/// each minting a refresh call, which the server would treat as jti reuse
/// and answer with revocation) without blocking the replay path.
///
/// A second 401 on the replayed request is surfaced as-is — never a refresh
/// loop. When the refresh itself is refused (consumed jti, blacklist, invalid
/// token) the tokens are cleared and the error is escalated as
/// [AuthRevoked]: the session is over, sign-in required. A refresh that fails
/// for transport reasons (network down) is NOT treated as revocation — the
/// original 401 propagates so the stale/offline state can retry later.
class VigilAuthenticator extends Interceptor {
  VigilAuthenticator({
    required TokenStore store,
    required AuthApi auth,
    required String userAgent,
  })  : _store = store,
        _auth = auth,
        _userAgent = userAgent;

  /// Marks a replayed request so its own 401 ends the chain — one refresh per
  /// request, no loops.
  static const _retriedFlag = 'vigil.retried';

  final TokenStore _store;
  final AuthApi _auth;
  final String _userAgent;

  /// Promise chain serializing rotations: a 401 arriving while a refresh is
  /// in flight waits here, then sees the rotated token and replays directly.
  Future<void>? _refreshQueue;

  Dio? _dio;

  /// The owning Dio registers itself after construction — the replay is
  /// re-sent through the same instance (interceptors can't fetch otherwise).
  /// Composition roots and tests call this once right after creating the Dio.
  void attach(Dio dio) => _dio = dio;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    // The one place identity headers are decided for API calls. The UA string
    // is fixed for the session — the server's sfp claim binds it byte-for-byte.
    options.headers['user-agent'] = _userAgent;
    final token = await _store.readAccess();
    if (token != null) {
      options.headers['authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    if (err.response?.statusCode != 401 ||
        options.extra[_retriedFlag] == true) {
      return handler.next(err);
    }

    try {
      await _refreshAndPersist(options);
    } on AuthRevoked catch (revoked) {
      // Consumed jti or blacklist hit — the server has ended this session.
      await _store.clear();
      return handler.reject(_revoked(err, revoked.message));
    } on DioException {
      // Transport failure during rotation — the session is NOT revoked.
      // Surface the original 401 so the stale/offline state retries later;
      // tokens stay put.
      return handler.next(err);
    }

    // Replay exactly once — a second 401 surfaces to the caller.
    final dio = _dio;
    if (dio == null) {
      throw StateError('VigilAuthenticator used before attach(dio)');
    }
    try {
      final replayed = await dio.fetch(options..extra[_retriedFlag] = true);
      return handler.resolve(replayed);
    } on DioException catch (replayError) {
      return handler.reject(replayError);
    }
  }

  /// Rotates the session if this request's token is still the live one.
  /// Serialized through [_refreshQueue] so concurrent 401s share one
  /// rotation; a queued sibling that arrives after the rotation is a no-op.
  Future<void> _refreshAndPersist(RequestOptions options) async {
    final prev = _refreshQueue;
    final current = (prev ?? Future<void>.value()).then(
      (_) => _rotateIfNeeded(options),
    );
    _refreshQueue = current;
    // Never let one waiter's failure poison the chain for the next.
    return current.whenComplete(() {});
  }

  Future<void> _rotateIfNeeded(RequestOptions options) async {
    // A queued sibling 401 may have already rotated the session while this
    // request was in flight with the old token. Replay with the current
    // token instead of burning another single-use refresh.
    final storedAccess = await _store.readAccess();
    final requestAuth = options.headers['authorization'] as String?;
    final alreadyRotated = storedAccess != null &&
        requestAuth != null &&
        requestAuth != 'Bearer $storedAccess';
    if (alreadyRotated) return;

    final refreshToken = await _store.readRefresh();
    if (refreshToken == null) {
      // Nothing to rotate with — the session is already gone.
      await _store.clear();
      throw AuthRevoked(reason: 'no refresh token');
    }
    final session = await _auth.refresh(refreshToken: refreshToken);
    // Single-use rotation: persist the NEW pair before replaying.
    await _store.save(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
    );
  }

  /// Wraps the original 401 so the UI can distinguish "session revoked —
  /// sign in again" from an ordinary stale-data failure.
  static DioException _revoked(DioException original, String reason) =>
      DioException(
        requestOptions: original.requestOptions,
        response: original.response,
        type: DioExceptionType.unknown,
        error: AuthRevoked(reason: reason),
      );
}
