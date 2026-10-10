import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Where the bearer tokens live across the session.
///
/// The refresh token is single-use (the server rotates it on every refresh
/// and blacklists the consumed jti), so [save] must persist the NEW pair
/// before a failed request is replayed — persisting after the replay would
/// hand the old (now-blacklisted) refresh token to the next rotation and
/// break the session.
abstract class TokenStore {
  /// Current access token, or null when signed out.
  Future<String?> readAccess();

  /// Current refresh token, or null when signed out.
  Future<String?> readRefresh();

  /// Persists the pair as the session's current tokens.
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  });

  /// Removes both tokens (sign-out or server-side revocation).
  Future<void> clear();
}

/// [TokenStore] over platform secure storage: iOS Keychain, Android Keystore,
/// and the desktop keyrings via flutter_secure_storage.
class SecureTokenStore implements TokenStore {
  SecureTokenStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'vigil.access_token';
  static const _refreshKey = 'vigil.refresh_token';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readAccess() => _storage.read(key: _accessKey);

  @override
  Future<String?> readRefresh() => _storage.read(key: _refreshKey);

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}

/// Ephemeral [TokenStore] — tests and callers that manage persistence
/// elsewhere. Nothing here ever touches disk.
class InMemoryTokenStore implements TokenStore {
  InMemoryTokenStore({String? accessToken, String? refreshToken})
      : _access = accessToken,
        _refresh = refreshToken;

  String? _access;
  String? _refresh;

  @override
  Future<String?> readAccess() async => _access;

  @override
  Future<String?> readRefresh() async => _refresh;

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    _access = accessToken;
    _refresh = refreshToken;
  }

  @override
  Future<void> clear() async {
    _access = null;
    _refresh = null;
  }
}
