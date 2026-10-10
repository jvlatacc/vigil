import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The severity scale the console's tokens define (critical → low). A local
/// notification preference is "tell me about findings at this level or
/// above" — `none` exists on the server's scale but is never a useful
/// notification floor, so it is not offered here.
enum NotifySeverity { critical, high, medium, low }

/// The wire name of a severity floor (the console's severity tokens).
String notifySeverityName(NotifySeverity severity) => severity.name;

NotifySeverity? notifySeverityFromName(String? name) {
  for (final value in NotifySeverity.values) {
    if (value.name == name) return value;
  }
  return null;
}

/// What the user asked this app to notify them about, locally. Vigil has no
/// server push today (no WebSockets/APNs/FCM), so nothing here promises
/// server behavior — these settings govern what this client surfaces when it
/// can (e.g. new findings while the app is open) and ship ahead of the
/// surfaces that consume them.
class NotificationPreferences {
  const NotificationPreferences({
    this.enabled = false,
    this.minimumSeverity = NotifySeverity.critical,
  });

  /// Master local switch. Off — the quiet default — until the user asks.
  final bool enabled;

  /// Notify at this severity or above.
  final NotifySeverity minimumSeverity;

  NotificationPreferences copyWith({
    bool? enabled,
    NotifySeverity? minimumSeverity,
  }) =>
      NotificationPreferences(
        enabled: enabled ?? this.enabled,
        minimumSeverity: minimumSeverity ?? this.minimumSeverity,
      );

  Map<String, dynamic> toBody() => {
        'enabled': enabled,
        'minimum_severity': notifySeverityName(minimumSeverity),
      };

  static NotificationPreferences fromBody(Map<String, dynamic> body) =>
      NotificationPreferences(
        enabled: body['enabled'] == true,
        minimumSeverity:
            notifySeverityFromName(body['minimum_severity'] as String?) ??
                NotifySeverity.critical,
      );

  @override
  bool operator ==(Object other) =>
      other is NotificationPreferences &&
      other.enabled == enabled &&
      other.minimumSeverity == minimumSeverity;

  @override
  int get hashCode => Object.hash(enabled, minimumSeverity);
}

/// Where local notification preferences live between runs.
abstract class NotificationPreferencesStore {
  Future<NotificationPreferences> read();
  Future<void> save(NotificationPreferences prefs);
}

/// [NotificationPreferencesStore] over platform secure storage — the same
/// vault the tokens use. Unreadable or absent data falls back to the quiet
/// default rather than failing the settings screen.
class SecureNotificationPreferencesStore
    implements NotificationPreferencesStore {
  SecureNotificationPreferencesStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'vigil.notification_preferences';

  final FlutterSecureStorage _storage;

  @override
  Future<NotificationPreferences> read() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null || raw.isEmpty) return const NotificationPreferences();
      final body = jsonDecode(raw);
      if (body is! Map<String, dynamic>) return const NotificationPreferences();
      return NotificationPreferences.fromBody(body);
    } on Exception {
      return const NotificationPreferences();
    }
  }

  @override
  Future<void> save(NotificationPreferences prefs) =>
      _storage.write(key: _key, value: jsonEncode(prefs.toBody()));
}

/// Ephemeral [NotificationPreferencesStore] — tests and callers that manage
/// persistence elsewhere. Nothing here ever touches disk.
class InMemoryNotificationPreferencesStore
    implements NotificationPreferencesStore {
  InMemoryNotificationPreferencesStore({NotificationPreferences? initial})
      : _prefs = initial ?? const NotificationPreferences();

  NotificationPreferences _prefs;

  @override
  Future<NotificationPreferences> read() async => _prefs;

  @override
  Future<void> save(NotificationPreferences prefs) async => _prefs = prefs;
}
