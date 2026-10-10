import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The Vigil server this device talks to — captured once during onboarding
/// and reused from then on (the console's equivalent is a same-origin
/// deployment; a native client reaches a running Vigil from anywhere).
class ServerProfile {
  const ServerProfile({required this.baseUrl});

  /// Base URL without a trailing slash, e.g. `https://vigil.example.com:6987`.
  final String baseUrl;

  /// Parses a user-entered URL for storage and use as the Dio base URL.
  /// Returns null when the input is not a usable http(s) URL — the
  /// onboarding server step shows a validation error instead of guessing.
  static ServerProfile? tryParse(String input) {
    final text = input.trim();
    final uri = Uri.tryParse(text);
    if (uri == null ||
        (uri.scheme != 'http' && uri.scheme != 'https') ||
        uri.host.isEmpty) {
      return null;
    }
    return ServerProfile(baseUrl: uri.toString());
  }

  @override
  bool operator ==(Object other) =>
      other is ServerProfile && other.baseUrl == baseUrl;

  @override
  int get hashCode => baseUrl.hashCode;

  @override
  String toString() => 'ServerProfile($baseUrl)';
}

/// Where the server URL lives between runs.
abstract class ServerProfileStore {
  Future<ServerProfile?> read();
  Future<void> save(ServerProfile profile);
  Future<void> clear();
}

/// [ServerProfileStore] over platform secure storage (iOS Keychain, Android
/// Keystore, desktop keyrings) — the same vault the tokens use.
class SecureServerProfileStore implements ServerProfileStore {
  SecureServerProfileStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _urlKey = 'vigil.server_url';

  final FlutterSecureStorage _storage;

  @override
  Future<ServerProfile?> read() async {
    final value = await _storage.read(key: _urlKey);
    if (value == null || value.isEmpty) return null;
    return ServerProfile(baseUrl: value);
  }

  @override
  Future<void> save(ServerProfile profile) =>
      _storage.write(key: _urlKey, value: profile.baseUrl);

  @override
  Future<void> clear() => _storage.delete(key: _urlKey);
}

/// Ephemeral [ServerProfileStore] — tests and callers that manage
/// persistence elsewhere. Nothing here ever touches disk.
class InMemoryServerProfileStore implements ServerProfileStore {
  InMemoryServerProfileStore({ServerProfile? profile}) : _profile = profile;

  ServerProfile? _profile;

  @override
  Future<ServerProfile?> read() async => _profile;

  @override
  Future<void> save(ServerProfile profile) async => _profile = profile;

  @override
  Future<void> clear() async => _profile = null;
}
