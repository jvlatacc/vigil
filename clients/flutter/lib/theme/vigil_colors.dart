// GENERATED FILE — do not edit by hand.
// Regenerate from clients/flutter: python3 tool/codegen.py
// Source: docs/design/console/tokens/tokens.json — color
// Values are the console's canonical tokens (exact hex/rgba as authored);
// test/design_tokens_test.dart re-parses the sources and fails on drift.

import 'package:flutter/material.dart';

/// Every color token from the console design tokens, for one scheme.
/// Field order mirrors tokens.json; Good/Fair/Poor levels, the severity
/// scale, and the DeepTempo brand tokens are all carried verbatim.
class VigilColors extends ThemeExtension<VigilColors> {
  const VigilColors({
    required this.bg0,
    required this.bg1,
    required this.bg2,
    required this.bg3,
    required this.bg4,
    required this.ln0,
    required this.ln1,
    required this.ln2,
    required this.tx0,
    required this.tx1,
    required this.tx2,
    required this.tx3,
    required this.ac,
    required this.acBg,
    required this.acLn,
    required this.acTx,
    required this.good,
    required this.goodBg,
    required this.goodLn,
    required this.fair,
    required this.fairBg,
    required this.fairLn,
    required this.poor,
    required this.poorBg,
    required this.poorLn,
    required this.sevCrit,
    required this.sevHigh,
    required this.sevMed,
    required this.sevLow,
    required this.sevNone,
    required this.vio,
    required this.vioBg,
    required this.scrim,
    required this.shadow,
    required this.spot,
    required this.dtRed,
    required this.dtBlack,
    required this.dtSilver,
  });

  final Color bg0;
  final Color bg1;
  final Color bg2;
  final Color bg3;
  final Color bg4;
  final Color ln0;
  final Color ln1;
  final Color ln2;
  final Color tx0;
  final Color tx1;
  final Color tx2;
  final Color tx3;
  final Color ac;
  final Color acBg;
  final Color acLn;
  final Color acTx;
  final Color good;
  final Color goodBg;
  final Color goodLn;
  final Color fair;
  final Color fairBg;
  final Color fairLn;
  final Color poor;
  final Color poorBg;
  final Color poorLn;
  final Color sevCrit;
  final Color sevHigh;
  final Color sevMed;
  final Color sevLow;
  final Color sevNone;
  final Color vio;
  final Color vioBg;
  final Color scrim;
  final Color shadow;
  final Color spot;
  final Color dtRed;
  final Color dtBlack;
  final Color dtSilver;

  /// The .vg-dark token class.
  static const VigilColors dark = VigilColors(
    bg0: Color(0xFF141414), // Page background
    bg1: Color(0xFF1B1B1B), // Panels, header, cards on page
    bg2: Color(0xFF212121), // Card interior, rows, inputs
    bg3: Color(0xFF292929), // Hover, selected row
    bg4: Color(0xFF323232), // Track backgrounds (bars), strong hover
    ln0: Color(0xFF262626), // Hairline dividers
    ln1: Color(0xFF303030), // Card and input borders
    ln2: Color(0xFF454545), // Button borders, scrollbar
    tx0: Color(0xFFF5F5F5), // Primary text
    tx1: Color(0xFFC7C7C7), // Secondary text
    tx2: Color(0xFF9E9E9E), // Muted text, labels
    tx3: Color(0xFF838383), // Placeholder, tertiary
    ac: Color(0xFF3AA8FF), // Accent (links, primary buttons, active tab)
    acBg: Color.fromRGBO(58, 168, 255, 0.12), // Accent tint background
    acLn: Color.fromRGBO(58, 168, 255, 0.42), // Accent tint border
    acTx: Color(0xFF111111), // Text on accent
    good: Color(0xFF00E676), // Good level
    goodBg: Color.fromRGBO(0, 230, 118, 0.10), // Good tint
    goodLn: Color.fromRGBO(0, 230, 118, 0.38), // Good border
    fair: Color(0xFFFFB300), // Fair level
    fairBg: Color.fromRGBO(255, 179, 0, 0.11), // Fair tint
    fairLn: Color.fromRGBO(255, 179, 0, 0.40), // Fair border
    poor: Color(0xFFFF3B5C), // Poor level, Needs you, destructive
    poorBg: Color.fromRGBO(255, 59, 92, 0.12), // Poor tint
    poorLn: Color.fromRGBO(255, 59, 92, 0.45), // Poor border
    sevCrit: Color(0xFFFF3B5C), // Severity critical
    sevHigh: Color(0xFFFF8A3D), // Severity high
    sevMed: Color(0xFFFFC53D), // Severity medium
    sevLow: Color(0xFF5AA9FF), // Severity low
    sevNone: Color(0xFF838383), // Severity noise
    vio: Color(0xFFA78BFA), // Human contribution, Tell mode, parsed actions
    vioBg: Color.fromRGBO(167, 139, 250, 0.13), // Human tint
    scrim: Color.fromRGBO(0, 0, 0, 0.62), // Drawer scrim
    shadow: Color.fromRGBO(0, 0, 0, 0.55), // Elevation shadow colour
    spot: Color.fromRGBO(0, 0, 0, 0.66), // Tour spotlight
    dtRed: Color(0xFFD92424), // DeepTempo brand red
    dtBlack: Color(0xFF0C0A0E), // DeepTempo brand black
    dtSilver: Color(0xFFA9B0B8), // DeepTempo brand silver
  );

  /// The .vg-light token class.
  static const VigilColors light = VigilColors(
    bg0: Color(0xFFF2F4F8), // Page background
    bg1: Color(0xFFFFFFFF), // Panels, header, cards on page
    bg2: Color(0xFFF7F8FB), // Card interior, rows, inputs
    bg3: Color(0xFFEDF0F5), // Hover, selected row
    bg4: Color(0xFFE3E8F0), // Track backgrounds (bars), strong hover
    ln0: Color(0xFFE3E7EE), // Hairline dividers
    ln1: Color(0xFFD5DBE5), // Card and input borders
    ln2: Color(0xFFB8C2D1), // Button borders, scrollbar
    tx0: Color(0xFF0B0F19), // Primary text
    tx1: Color(0xFF33415A), // Secondary text
    tx2: Color(0xFF56637A), // Muted text, labels
    tx3: Color(0xFF6E7A8F), // Placeholder, tertiary
    ac: Color(0xFF0A6FD6), // Accent (links, primary buttons, active tab)
    acBg: Color.fromRGBO(10, 111, 214, 0.09), // Accent tint background
    acLn: Color.fromRGBO(10, 111, 214, 0.38), // Accent tint border
    acTx: Color(0xFFFFFFFF), // Text on accent
    good: Color(0xFF00794A), // Good level
    goodBg: Color.fromRGBO(0, 121, 74, 0.09), // Good tint
    goodLn: Color.fromRGBO(0, 121, 74, 0.35), // Good border
    fair: Color(0xFF8F5E00), // Fair level
    fairBg: Color.fromRGBO(209, 148, 0, 0.12), // Fair tint
    fairLn: Color.fromRGBO(143, 94, 0, 0.35), // Fair border
    poor: Color(0xFFC8102E), // Poor level, Needs you, destructive
    poorBg: Color.fromRGBO(200, 16, 46, 0.08), // Poor tint
    poorLn: Color.fromRGBO(200, 16, 46, 0.35), // Poor border
    sevCrit: Color(0xFFC8102E), // Severity critical
    sevHigh: Color(0xFFC24E00), // Severity high
    sevMed: Color(0xFF8F5E00), // Severity medium
    sevLow: Color(0xFF1F64C8), // Severity low
    sevNone: Color(0xFF6E7A8F), // Severity noise
    vio: Color(0xFF6D3FD9), // Human contribution, Tell mode, parsed actions
    vioBg: Color.fromRGBO(109, 63, 217, 0.09), // Human tint
    scrim: Color.fromRGBO(11, 15, 25, 0.38), // Drawer scrim
    shadow: Color.fromRGBO(11, 15, 25, 0.18), // Elevation shadow colour
    spot: Color.fromRGBO(11, 15, 25, 0.55), // Tour spotlight
    dtRed: Color(0xFFD92424), // DeepTempo brand red
    dtBlack: Color(0xFF0C0A0E), // DeepTempo brand black
    dtSilver: Color(0xFF8A939E), // DeepTempo brand silver
  );

  /// Token names in tokens.json order.
  static const List<String> tokenNames = [
    'bg0',
    'bg1',
    'bg2',
    'bg3',
    'bg4',
    'ln0',
    'ln1',
    'ln2',
    'tx0',
    'tx1',
    'tx2',
    'tx3',
    'ac',
    'ac-bg',
    'ac-ln',
    'ac-tx',
    'good',
    'good-bg',
    'good-ln',
    'fair',
    'fair-bg',
    'fair-ln',
    'poor',
    'poor-bg',
    'poor-ln',
    'sev-crit',
    'sev-high',
    'sev-med',
    'sev-low',
    'sev-none',
    'vio',
    'vio-bg',
    'scrim',
    'shadow',
    'spot',
    'dt-red',
    'dt-black',
    'dt-silver'
  ];

  /// Color for [name]; throws on unknown tokens.
  Color byName(String name) => switch (name) {
        'bg0' => bg0,
        'bg1' => bg1,
        'bg2' => bg2,
        'bg3' => bg3,
        'bg4' => bg4,
        'ln0' => ln0,
        'ln1' => ln1,
        'ln2' => ln2,
        'tx0' => tx0,
        'tx1' => tx1,
        'tx2' => tx2,
        'tx3' => tx3,
        'ac' => ac,
        'ac-bg' => acBg,
        'ac-ln' => acLn,
        'ac-tx' => acTx,
        'good' => good,
        'good-bg' => goodBg,
        'good-ln' => goodLn,
        'fair' => fair,
        'fair-bg' => fairBg,
        'fair-ln' => fairLn,
        'poor' => poor,
        'poor-bg' => poorBg,
        'poor-ln' => poorLn,
        'sev-crit' => sevCrit,
        'sev-high' => sevHigh,
        'sev-med' => sevMed,
        'sev-low' => sevLow,
        'sev-none' => sevNone,
        'vio' => vio,
        'vio-bg' => vioBg,
        'scrim' => scrim,
        'shadow' => shadow,
        'spot' => spot,
        'dt-red' => dtRed,
        'dt-black' => dtBlack,
        'dt-silver' => dtSilver,
        _ => throw ArgumentError('Unknown Vigil color token: $name'),
      };

  @override
  VigilColors copyWith(
          {Color? bg0,
          Color? bg1,
          Color? bg2,
          Color? bg3,
          Color? bg4,
          Color? ln0,
          Color? ln1,
          Color? ln2,
          Color? tx0,
          Color? tx1,
          Color? tx2,
          Color? tx3,
          Color? ac,
          Color? acBg,
          Color? acLn,
          Color? acTx,
          Color? good,
          Color? goodBg,
          Color? goodLn,
          Color? fair,
          Color? fairBg,
          Color? fairLn,
          Color? poor,
          Color? poorBg,
          Color? poorLn,
          Color? sevCrit,
          Color? sevHigh,
          Color? sevMed,
          Color? sevLow,
          Color? sevNone,
          Color? vio,
          Color? vioBg,
          Color? scrim,
          Color? shadow,
          Color? spot,
          Color? dtRed,
          Color? dtBlack,
          Color? dtSilver}) =>
      VigilColors(
        bg0: bg0 ?? this.bg0,
        bg1: bg1 ?? this.bg1,
        bg2: bg2 ?? this.bg2,
        bg3: bg3 ?? this.bg3,
        bg4: bg4 ?? this.bg4,
        ln0: ln0 ?? this.ln0,
        ln1: ln1 ?? this.ln1,
        ln2: ln2 ?? this.ln2,
        tx0: tx0 ?? this.tx0,
        tx1: tx1 ?? this.tx1,
        tx2: tx2 ?? this.tx2,
        tx3: tx3 ?? this.tx3,
        ac: ac ?? this.ac,
        acBg: acBg ?? this.acBg,
        acLn: acLn ?? this.acLn,
        acTx: acTx ?? this.acTx,
        good: good ?? this.good,
        goodBg: goodBg ?? this.goodBg,
        goodLn: goodLn ?? this.goodLn,
        fair: fair ?? this.fair,
        fairBg: fairBg ?? this.fairBg,
        fairLn: fairLn ?? this.fairLn,
        poor: poor ?? this.poor,
        poorBg: poorBg ?? this.poorBg,
        poorLn: poorLn ?? this.poorLn,
        sevCrit: sevCrit ?? this.sevCrit,
        sevHigh: sevHigh ?? this.sevHigh,
        sevMed: sevMed ?? this.sevMed,
        sevLow: sevLow ?? this.sevLow,
        sevNone: sevNone ?? this.sevNone,
        vio: vio ?? this.vio,
        vioBg: vioBg ?? this.vioBg,
        scrim: scrim ?? this.scrim,
        shadow: shadow ?? this.shadow,
        spot: spot ?? this.spot,
        dtRed: dtRed ?? this.dtRed,
        dtBlack: dtBlack ?? this.dtBlack,
        dtSilver: dtSilver ?? this.dtSilver,
      );

  @override
  VigilColors lerp(VigilColors? other, double t) {
    if (other == null) return this;
    return VigilColors(
      bg0: Color.lerp(bg0, other.bg0, t)!,
      bg1: Color.lerp(bg1, other.bg1, t)!,
      bg2: Color.lerp(bg2, other.bg2, t)!,
      bg3: Color.lerp(bg3, other.bg3, t)!,
      bg4: Color.lerp(bg4, other.bg4, t)!,
      ln0: Color.lerp(ln0, other.ln0, t)!,
      ln1: Color.lerp(ln1, other.ln1, t)!,
      ln2: Color.lerp(ln2, other.ln2, t)!,
      tx0: Color.lerp(tx0, other.tx0, t)!,
      tx1: Color.lerp(tx1, other.tx1, t)!,
      tx2: Color.lerp(tx2, other.tx2, t)!,
      tx3: Color.lerp(tx3, other.tx3, t)!,
      ac: Color.lerp(ac, other.ac, t)!,
      acBg: Color.lerp(acBg, other.acBg, t)!,
      acLn: Color.lerp(acLn, other.acLn, t)!,
      acTx: Color.lerp(acTx, other.acTx, t)!,
      good: Color.lerp(good, other.good, t)!,
      goodBg: Color.lerp(goodBg, other.goodBg, t)!,
      goodLn: Color.lerp(goodLn, other.goodLn, t)!,
      fair: Color.lerp(fair, other.fair, t)!,
      fairBg: Color.lerp(fairBg, other.fairBg, t)!,
      fairLn: Color.lerp(fairLn, other.fairLn, t)!,
      poor: Color.lerp(poor, other.poor, t)!,
      poorBg: Color.lerp(poorBg, other.poorBg, t)!,
      poorLn: Color.lerp(poorLn, other.poorLn, t)!,
      sevCrit: Color.lerp(sevCrit, other.sevCrit, t)!,
      sevHigh: Color.lerp(sevHigh, other.sevHigh, t)!,
      sevMed: Color.lerp(sevMed, other.sevMed, t)!,
      sevLow: Color.lerp(sevLow, other.sevLow, t)!,
      sevNone: Color.lerp(sevNone, other.sevNone, t)!,
      vio: Color.lerp(vio, other.vio, t)!,
      vioBg: Color.lerp(vioBg, other.vioBg, t)!,
      scrim: Color.lerp(scrim, other.scrim, t)!,
      shadow: Color.lerp(shadow, other.shadow, t)!,
      spot: Color.lerp(spot, other.spot, t)!,
      dtRed: Color.lerp(dtRed, other.dtRed, t)!,
      dtBlack: Color.lerp(dtBlack, other.dtBlack, t)!,
      dtSilver: Color.lerp(dtSilver, other.dtSilver, t)!,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(other, this) ||
      other is VigilColors &&
          other.bg0 == bg0 &&
          other.bg1 == bg1 &&
          other.bg2 == bg2 &&
          other.bg3 == bg3 &&
          other.bg4 == bg4 &&
          other.ln0 == ln0 &&
          other.ln1 == ln1 &&
          other.ln2 == ln2 &&
          other.tx0 == tx0 &&
          other.tx1 == tx1 &&
          other.tx2 == tx2 &&
          other.tx3 == tx3 &&
          other.ac == ac &&
          other.acBg == acBg &&
          other.acLn == acLn &&
          other.acTx == acTx &&
          other.good == good &&
          other.goodBg == goodBg &&
          other.goodLn == goodLn &&
          other.fair == fair &&
          other.fairBg == fairBg &&
          other.fairLn == fairLn &&
          other.poor == poor &&
          other.poorBg == poorBg &&
          other.poorLn == poorLn &&
          other.sevCrit == sevCrit &&
          other.sevHigh == sevHigh &&
          other.sevMed == sevMed &&
          other.sevLow == sevLow &&
          other.sevNone == sevNone &&
          other.vio == vio &&
          other.vioBg == vioBg &&
          other.scrim == scrim &&
          other.shadow == shadow &&
          other.spot == spot &&
          other.dtRed == dtRed &&
          other.dtBlack == dtBlack &&
          other.dtSilver == dtSilver;

  @override
  int get hashCode => Object.hashAll([
        bg0,
        bg1,
        bg2,
        bg3,
        bg4,
        ln0,
        ln1,
        ln2,
        tx0,
        tx1,
        tx2,
        tx3,
        ac,
        acBg,
        acLn,
        acTx,
        good,
        goodBg,
        goodLn,
        fair,
        fairBg,
        fairLn,
        poor,
        poorBg,
        poorLn,
        sevCrit,
        sevHigh,
        sevMed,
        sevLow,
        sevNone,
        vio,
        vioBg,
        scrim,
        shadow,
        spot,
        dtRed,
        dtBlack,
        dtSilver
      ]);
}
