import 'package:dio/dio.dart';

import '../api/vigil_client.dart';
import '../auth/token_store.dart';
import 'server_profile.dart';

/// The response answered, but not with a Vigil `/api/health` payload — a URL
/// valid as HTTP but not pointing at Vigil.
class NotVigilServer implements Exception {
  const NotVigilServer();

  @override
  String toString() => 'NotVigilServer';
}

/// What a Vigil `/api/health` answered — the payload, version included.
typedef HealthProbe = Future<Map<String, dynamic>> Function();

/// Builds a throwaway client for probing a candidate server. Injectable so
/// tests script the transport; the real factory comes from the app root.
typedef ProbeClientFactory = HealthProbe Function(String baseUrl);

/// The production probe client: a bare [HealthProbe] over `/api/health` with
/// a throwaway token store — probing a candidate server must never touch the
/// session tokens, which belong to the currently connected server.
ProbeClientFactory defaultProbeClientFactory({
  required VigilClientFactory clientFactory,
  required String userAgent,
}) =>
    (String baseUrl) {
      final client = clientFactory(
        baseUrl: baseUrl,
        tokenStore: InMemoryTokenStore(),
        userAgent: userAgent,
      );
      return client.auth.health;
    };

/// Validates a candidate server URL the way onboarding does: reachable, and
/// answering like a Vigil (`/api/health` with a `version` field). Throws
/// [NotVigilServer] when the URL answered but is not Vigil, and propagates
/// transport failures ([DioException]) — callers translate both for users.
Future<Map<String, dynamic>> probeVigilHealth({
  required ServerProfile profile,
  required HealthProbe probe,
}) async {
  final health = await probe();
  if (!health.containsKey('version')) throw const NotVigilServer();
  return health;
}
