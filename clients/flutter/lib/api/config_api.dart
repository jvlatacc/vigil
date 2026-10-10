import 'package:dio/dio.dart';

/// The color scheme, as the `/api/config/theme` wire values (`'dark'` /
/// `'light'`).
enum VigilScheme { dark, light }

/// Hand-written client for the console-surface config endpoints the shell
/// needs. Like the auth endpoints these sit outside the frozen `/api/v1`
/// snapshot, so they are typed by hand against
/// `services/api/routers/config.py` and covered by unit tests instead of
/// codegen. The Dio passed in is the app's *authenticated* instance — bearer
/// injection, the byte-stable User-Agent, and one-shot refresh-then-replay
/// ride on the shared [VigilAuthenticator].
class ConfigApi {
  ConfigApi({required Dio dio}) : _dio = dio;

  final Dio _dio;

  /// GET `/api/config/theme` → `{"theme": "dark"|"light"}`. Unknown or
  /// missing values fall back to dark — the server's default and the
  /// console's default scheme.
  Future<VigilScheme> theme() async {
    final res = await _dio.get<Map<String, dynamic>>('/api/config/theme');
    final value = res.data?['theme'];
    return value == 'light' ? VigilScheme.light : VigilScheme.dark;
  }

  /// POST `/api/config/theme` with `{"theme": ...}`. The server persists it
  /// under `theme.current` and enforces `settings.write` — callers decide
  /// what a refusal means (the console's ColorSchemeContext swallows it and
  /// keeps the local flip).
  Future<void> setTheme(VigilScheme scheme) =>
      _dio.post<void>('/api/config/theme', data: {'theme': scheme.name});
}
