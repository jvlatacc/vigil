import 'package:flutter/material.dart';

import '../api/config_api.dart';
import '../settings/scheme_controller.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';

/// The color-scheme toggle the shell and the entry screens carry — the
/// console's `.auth-theme` login button and UserMenu toggle, one control.
/// Dark-first; the flip is local and persistence is the controller's job.
class SchemeToggleAction extends StatelessWidget {
  const SchemeToggleAction({super.key, required this.scheme});

  final SchemeController scheme;

  @override
  Widget build(BuildContext context) {
    final light = scheme.scheme == VigilScheme.light;
    return IconButton(
      key: const Key('scheme-toggle'),
      tooltip: light ? 'Switch to dark theme' : 'Switch to light theme',
      icon: VigilIcon(light ? VigilIcons.moon : VigilIcons.sun),
      onPressed: () =>
          scheme.set(light ? VigilScheme.dark : VigilScheme.light),
    );
  }
}
