import 'dart:io' show Platform;

/// The app version reported in the User-Agent. Kept in step with the app's
/// pubspec version; the backend only uses the string opaquely.
const String vigilAppVersion = '1.0.0';

/// Builds the byte-stable User-Agent the backend's `sfp` session-fingerprint
/// claim binds (tokens carry `sfp = sha256(User-Agent)[:16]`, verified on
/// every request — core/auth/auth_service.py). A client that varies its
/// User-Agent between login and later calls gets 401 "Session fingerprint
/// mismatch", so this exact string must be attached to every request of a
/// session: login, refresh, and all `/api/v1` calls alike.
///
/// Pure function — the app computes it once per session and never rebuilds it.
String vigilUserAgent({String? version, String? platform}) {
  final os = platform ??
      Platform.operatingSystem; // ios | android | macos | linux | windows
  return 'Vigil/${version ?? vigilAppVersion} ($os)';
}
