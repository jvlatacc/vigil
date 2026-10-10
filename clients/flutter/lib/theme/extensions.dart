import 'package:flutter/material.dart';

import 'vigil_colors.dart';
import 'vigil_theme.dart';

/// Typed access to the generated ThemeExtensions the app installs on
/// ThemeData. Falls back to the dark scheme (the console's default).
extension VigilThemeAccess on BuildContext {
  VigilColors get vigilColors =>
      Theme.of(this).extension<VigilColors>() ?? VigilColors.dark;

  VigilTheme get vigilMetrics =>
      Theme.of(this).extension<VigilTheme>() ?? VigilTheme.metrics;
}
