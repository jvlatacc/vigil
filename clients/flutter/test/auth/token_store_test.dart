import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/token_store.dart';

/// In-memory stand-in for the platform channel — enough to prove
/// [SecureTokenStore] delegates to flutter_secure_storage correctly.
class _FakePlatform extends FlutterSecureStoragePlatform {
  final Map<String, String?> store = {};

  @override
  Future<void> write({
    required String key,
    required String value,
    required Map<String, String> options,
  }) async =>
      store[key] = value;

  @override
  Future<String?> read({
    required String key,
    required Map<String, String> options,
  }) async =>
      store[key];

  @override
  Future<bool> containsKey({
    required String key,
    required Map<String, String> options,
  }) async =>
      store.containsKey(key);

  @override
  Future<void> delete({
    required String key,
    required Map<String, String> options,
  }) async =>
      store[key] = null;

  @override
  Future<Map<String, String>> readAll({
    required Map<String, String> options,
  }) async =>
      {
        for (final entry in store.entries)
          if (entry.value != null) entry.key: entry.value!,
      };

  @override
  Future<void> deleteAll({required Map<String, String> options}) async =>
      store.clear();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('InMemoryTokenStore', () {
    test('starts empty, saves, and clears', () async {
      final store = InMemoryTokenStore();

      expect(await store.readAccess(), isNull);
      expect(await store.readRefresh(), isNull);

      await store.save(accessToken: 'a1', refreshToken: 'r1');
      expect(await store.readAccess(), 'a1');
      expect(await store.readRefresh(), 'r1');

      await store.clear();
      expect(await store.readAccess(), isNull);
      expect(await store.readRefresh(), isNull);
    });
  });

  group('SecureTokenStore', () {
    late _FakePlatform platform;

    setUp(() {
      platform = _FakePlatform();
      FlutterSecureStoragePlatform.instance = platform;
    });

    test('reads and writes through the platform secure storage', () async {
      final store = SecureTokenStore();

      expect(await store.readAccess(), isNull);
      await store.save(accessToken: 'access-1', refreshToken: 'refresh-1');

      // Persisted in secure storage under the app's keys.
      expect(platform.store['vigil.access_token'], 'access-1');
      expect(platform.store['vigil.refresh_token'], 'refresh-1');
      expect(await store.readAccess(), 'access-1');
      expect(await store.readRefresh(), 'refresh-1');
    });

    test('rotation overwrite: save replaces the current pair', () async {
      final store = SecureTokenStore();
      await store.save(accessToken: 'a1', refreshToken: 'r1');
      // Single-use rotation — the NEW pair must replace the old one.
      await store.save(accessToken: 'a2', refreshToken: 'r2');

      expect(await store.readAccess(), 'a2');
      expect(await store.readRefresh(), 'r2');
    });

    test('clear removes both tokens', () async {
      final store = SecureTokenStore();
      await store.save(accessToken: 'a1', refreshToken: 'r1');

      await store.clear();

      expect(platform.store['vigil.access_token'], isNull);
      expect(platform.store['vigil.refresh_token'], isNull);
      expect(await store.readAccess(), isNull);
      expect(await store.readRefresh(), isNull);
    });
  });
}
