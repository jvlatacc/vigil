// GENERATED FILE — do not edit by hand.
// Regenerate from clients/flutter: python3 tool/codegen.py
// Source: docs/design/console/tokens/tokens.json — type.scale
// Values are the console's canonical tokens (exact hex/rgba as authored);
// test/design_tokens_test.dart re-parses the sources and fails on drift.

import 'package:flutter/material.dart';

/// The token type ramp as TextStyles. The ramp's exact sizes (13/12/11)
/// and weights are re-checked against tokens.json by the parity test.
/// Styles carry no color: scheme colors come from VigilColors at the
/// call site (the token's color pairing, where one exists, is in a
/// comment).
class VigilTypography {
  VigilTypography._();

  static const String uiFamily = 'Plus Jakarta Sans';
  static const String monoFamily = 'Roboto Mono';
  static const TextStyle pageTitle = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w600,
    fontFamily: uiFamily,
  );
  static const TextStyle caseTitle = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    fontFamily: uiFamily,
  );
  static const TextStyle blockTitle = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w700,
    fontFamily: uiFamily,
  );

  /// token weight 650 -> w700 (static-font CSS matching).
  static const TextStyle sectionTitle = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w700,
    fontFamily: uiFamily,
  );
  static const TextStyle body = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.5,
    fontFamily: uiFamily,
  );
  static const TextStyle bodyStrong = TextStyle(
    fontSize: 13.5,
    fontWeight: FontWeight.w500,
    fontFamily: uiFamily,
  );
  static const TextStyle label = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w600,
    fontFamily: uiFamily,
  );

  /// token pairs this style with tx2.
  static const TextStyle meta = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    fontFamily: uiFamily,
  );
  static const TextStyle micro = TextStyle(
    fontSize: 11.5,
    fontFamily: uiFamily,
  );
  static const TextStyle countChip = TextStyle(
    fontSize: 11,
    fontFamily: monoFamily,
  );

  /// Roboto Mono — secrets, codes, and other copy-as-data (DESIGN.md §6).
  static const TextStyle mono = TextStyle(
    fontSize: 12.5,
    fontWeight: FontWeight.w400,
    fontFamily: monoFamily,
  );

  /// Styles keyed by token name (parity-test surface).
  static const Map<String, TextStyle> byName = {
    'page-title': pageTitle,
    'case-title': caseTitle,
    'block-title': blockTitle,
    'section-title': sectionTitle,
    'body': body,
    'body-strong': bodyStrong,
    'label': label,
    'meta': meta,
    'micro': micro,
    'count-chip': countChip,
  };
}
