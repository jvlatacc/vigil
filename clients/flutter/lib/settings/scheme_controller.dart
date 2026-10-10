import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/config_api.dart';

/// Owns the color scheme — dark-first, persisted server-side exactly like
/// the console's `ColorSchemeContext` (`configApi.getTheme()` on load,
/// `configApi.setTheme()` on change): the flip is local-first and the server
/// call may fail silently, because `/api/config/theme` POST enforces
/// `settings.write` and viewers still get the visual flip in the console.
class SchemeController extends ChangeNotifier {
  SchemeController({ConfigApi? configApi}) : _configApi = configApi;

  final ConfigApi? _configApi;

  VigilScheme _scheme = VigilScheme.dark;

  /// The current scheme; dark until a session's GET says otherwise.
  VigilScheme get scheme => _scheme;

  /// Pulls the persisted scheme. A failed GET keeps the default (dark) —
  /// the console treats it the same way (`.catch(() => {})`).
  Future<void> load() async {
    final api = _configApi;
    if (api == null) return;
    try {
      final server = await api.theme();
      if (server != _scheme) {
        _scheme = server;
        notifyListeners();
      }
    } on Exception {
      // Console parity — see the class doc. No session or a refused call
      // must not break the app over a color scheme.
    }
  }

  void set(VigilScheme next) {
    if (next == _scheme) return;
    _scheme = next;
    notifyListeners();
    unawaited(_persist(next));
  }

  Future<void> _persist(VigilScheme next) async {
    try {
      await _configApi?.setTheme(next);
    } on Exception {
      // Console parity — see the class doc.
    }
  }
}
