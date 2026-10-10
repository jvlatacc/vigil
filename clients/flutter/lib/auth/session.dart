/// Parsed auth payloads from `/api/auth/*`.
///
/// `LoginResponse` and the `/me` payload carry tokens plus the user dict the
/// console gates on — `UserSchema.dump(user)` plus the resolved
/// `permissions` map (services/api/routers/auth.py `_user_payload`).
library;

/// The user dict attached to login/refresh responses and returned by `/me`.
class UserProfile {
  const UserProfile({
    required this.permissions,
    this.userId,
    this.username,
    this.email,
    this.fullName,
  });

  factory UserProfile.fromBody(Map<String, dynamic> body) {
    final rawPermissions = body['permissions'];
    return UserProfile(
      userId: body['user_id'] as String?,
      username: body['username'] as String?,
      email: body['email'] as String?,
      fullName: body['full_name'] as String?,
      permissions: {
        if (rawPermissions is Map)
          for (final entry in rawPermissions.entries)
            if (entry.key is String) entry.key as String: entry.value == true,
      },
    );
  }

  final String? userId;
  final String? username;
  final String? email;
  final String? fullName;

  /// Permission-key map the console's SCREEN_PERMS gating reads, e.g.
  /// `ai_decisions.approve`, `cases.read`, `settings.read`.
  final Map<String, bool> permissions;

  bool hasPermission(String key) => permissions[key] == true;
}

/// An issued token pair plus the user it belongs to.
class Session {
  const Session({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  factory Session.fromBody(Map<String, dynamic> body) {
    final access = body['access_token'];
    final refresh = body['refresh_token'];
    if (access is! String || access.isEmpty) {
      throw ArgumentError('login/refresh response missing access_token');
    }
    if (refresh is! String || refresh.isEmpty) {
      throw ArgumentError('login/refresh response missing refresh_token');
    }
    final user = body['user'];
    return Session(
      accessToken: access,
      refreshToken: refresh,
      user: UserProfile.fromBody(
        user is Map<String, dynamic> ? user : const {},
      ),
    );
  }

  final String accessToken;
  final String refreshToken;
  final UserProfile user;
}
