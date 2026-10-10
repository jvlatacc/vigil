// GENERATED FILE — do not edit by hand.
// Regenerate from clients/flutter: python3 tool/codegen.py
// Source: docs/design/console/tokens/tokens.json — radius, control, space
// Values are the console's canonical tokens (exact hex/rgba as authored);
// test/design_tokens_test.dart re-parses the sources and fails on drift.

import 'package:flutter/material.dart';

import 'vigil_colors.dart';
import 'vigil_typography.dart';

/// Non-color metrics from the console tokens: corner radii, control
/// heights, and the spacing ramp. Scheme-independent — tokens.json
/// carries one value for each.
class VigilTheme extends ThemeExtension<VigilTheme> {
  const VigilTheme({
    required this.radiusPillSm,
    required this.radiusButton,
    required this.radiusCardInner,
    required this.radiusCard,
    required this.radiusPanel,
    required this.radiusRound,
    required this.controlButtonSm,
    required this.controlButton,
    required this.controlTab,
    required this.controlStatePill,
    required this.controlHeaderRow,
    required this.controlNavRow,
    required this.controlSearch,
    required this.space,
  });

  final double radiusPillSm; // 8px
  final double radiusButton; // 10px
  final double radiusCardInner; // 10px
  final double radiusCard; // 14px
  final double radiusPanel; // 12px
  final double radiusRound; // 999px

  final double controlButtonSm; // 28px
  final double controlButton; // 36px
  final double controlTab; // 38px
  final double controlStatePill; // 22px
  final double controlHeaderRow; // 52px
  final double controlNavRow; // 46px
  final double controlSearch; // 38px

  /// Spacing ramp in px: 4px, 6px, 8px, 10px, 12px, 14px, 16px, 18px, 20px, 24px, 28px.
  final List<double> space;

  /// The single metric set (radius/control/space do not vary by scheme).
  static const VigilTheme metrics = VigilTheme(
      radiusPillSm: 8,
      radiusButton: 10,
      radiusCardInner: 10,
      radiusCard: 14,
      radiusPanel: 12,
      radiusRound: 999,
      controlButtonSm: 28,
      controlButton: 36,
      controlTab: 38,
      controlStatePill: 22,
      controlHeaderRow: 52,
      controlNavRow: 46,
      controlSearch: 38,
    space: [4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28],
  );

  /// Radius values keyed by token name (parity-test surface).
  static const Map<String, double> radiusTokens = {
    'pill-sm': 8,
    'button': 10,
    'card-inner': 10,
    'card': 14,
    'panel': 12,
    'round': 999,
  };

  /// Control heights keyed by token name (parity-test surface).
  static const Map<String, double> controlTokens = {
    'button-sm': 28,
    'button': 36,
    'tab': 38,
    'state-pill': 22,
    'header-row': 52,
    'nav-row': 46,
    'search': 38,
  };

  static double _lerpDouble(double a, double b, double t) => a + (b - a) * t;

  static bool _listEquals(List<double> a, List<double> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }

  @override
  VigilTheme copyWith({
    double? radiusPillSm,
    double? radiusButton,
    double? radiusCardInner,
    double? radiusCard,
    double? radiusPanel,
    double? radiusRound,
    double? controlButtonSm,
    double? controlButton,
    double? controlTab,
    double? controlStatePill,
    double? controlHeaderRow,
    double? controlNavRow,
    double? controlSearch,
    List<double>? space,
  }) => VigilTheme(
      radiusPillSm: radiusPillSm ?? this.radiusPillSm,
      radiusButton: radiusButton ?? this.radiusButton,
      radiusCardInner: radiusCardInner ?? this.radiusCardInner,
      radiusCard: radiusCard ?? this.radiusCard,
      radiusPanel: radiusPanel ?? this.radiusPanel,
      radiusRound: radiusRound ?? this.radiusRound,
      controlButtonSm: controlButtonSm ?? this.controlButtonSm,
      controlButton: controlButton ?? this.controlButton,
      controlTab: controlTab ?? this.controlTab,
      controlStatePill: controlStatePill ?? this.controlStatePill,
      controlHeaderRow: controlHeaderRow ?? this.controlHeaderRow,
      controlNavRow: controlNavRow ?? this.controlNavRow,
      controlSearch: controlSearch ?? this.controlSearch,
      space: space ?? this.space,
  );

  @override
  VigilTheme lerp(VigilTheme? other, double t) {
    if (other == null) return this;
    return VigilTheme(
      radiusPillSm: _lerpDouble(radiusPillSm, other.radiusPillSm, t),
      radiusButton: _lerpDouble(radiusButton, other.radiusButton, t),
      radiusCardInner: _lerpDouble(radiusCardInner, other.radiusCardInner, t),
      radiusCard: _lerpDouble(radiusCard, other.radiusCard, t),
      radiusPanel: _lerpDouble(radiusPanel, other.radiusPanel, t),
      radiusRound: _lerpDouble(radiusRound, other.radiusRound, t),
      controlButtonSm: _lerpDouble(controlButtonSm, other.controlButtonSm, t),
      controlButton: _lerpDouble(controlButton, other.controlButton, t),
      controlTab: _lerpDouble(controlTab, other.controlTab, t),
      controlStatePill: _lerpDouble(controlStatePill, other.controlStatePill, t),
      controlHeaderRow: _lerpDouble(controlHeaderRow, other.controlHeaderRow, t),
      controlNavRow: _lerpDouble(controlNavRow, other.controlNavRow, t),
      controlSearch: _lerpDouble(controlSearch, other.controlSearch, t),
      space: List.generate(
        space.length,
        (i) => _lerpDouble(space[i], other.space[i], t),
      ),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(other, this) ||
      other is VigilTheme &&
            other.radiusPillSm == radiusPillSm
            && other.radiusButton == radiusButton
            && other.radiusCardInner == radiusCardInner
            && other.radiusCard == radiusCard
            && other.radiusPanel == radiusPanel
            && other.radiusRound == radiusRound &&
            other.controlButtonSm == controlButtonSm
            && other.controlButton == controlButton
            && other.controlTab == controlTab
            && other.controlStatePill == controlStatePill
            && other.controlHeaderRow == controlHeaderRow
            && other.controlNavRow == controlNavRow
            && other.controlSearch == controlSearch &&
            _listEquals(other.space, space);

  @override
  int get hashCode => Object.hashAll([radiusPillSm, radiusButton, radiusCardInner, radiusCard, radiusPanel, radiusRound, controlButtonSm, controlButton, controlTab, controlStatePill, controlHeaderRow, controlNavRow, controlSearch, space]);
}

/// Builds the app ThemeData from the tokens for [brightness]. The
/// scheme mapping mirrors the console: accent -> primary, violet ->
/// secondary, Poor -> error, bg1 -> surface, bg0 -> scaffold.
ThemeData buildVigilThemeData(Brightness brightness) {
  final colors =
      brightness == Brightness.dark ? VigilColors.dark : VigilColors.light;
  final scheme = ColorScheme(
    brightness: brightness,
    primary: colors.ac,
    onPrimary: colors.acTx,
    secondary: colors.vio,
    onSecondary: colors.acTx,
    error: colors.poor,
    onError: colors.acTx,
    surface: colors.bg1,
    onSurface: colors.tx0,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: colors.bg0,
    dividerColor: colors.ln0,
    fontFamily: 'Plus Jakarta Sans',
    extensions: [colors, VigilTheme.metrics],
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: colors.bg1,
      indicatorColor: colors.acBg,
      // Selected state reads as accent, like the console's active nav row.
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? colors.ac : colors.tx1,
          )),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => VigilTypography.label.copyWith(
              color: states.contains(WidgetState.selected) ? colors.tx0 : colors.tx2,
            ),
      ),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: colors.bg1,
      indicatorColor: colors.acBg,
      selectedIconTheme: IconThemeData(color: colors.ac),
      unselectedIconTheme: IconThemeData(color: colors.tx1),
      selectedLabelTextStyle: VigilTypography.label.copyWith(color: colors.tx0),
      unselectedLabelTextStyle: VigilTypography.label.copyWith(color: colors.tx2),
    ),
  );
}
