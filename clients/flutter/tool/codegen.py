#!/usr/bin/env python3
"""Generate the Vigil Flutter design system from the console token sources.

Inputs (canonical, owned by docs/design/console/):
  docs/design/console/tokens/tokens.json       colors, type scale, radius, control, space
  docs/design/console/assets/icons/icons.json  the 82-icon line set (name -> svg path data)

Outputs (generated, committed under lib/theme/):
  vigil_colors.dart      VigilColors ThemeExtension (dark + light instances)
  vigil_theme.dart       VigilTheme ThemeExtension (radius/control/space) + ThemeData builder
  vigil_typography.dart  the token type ramp as TextStyles
  vigil_icons.dart       typed VigilIcons class (one entry per manifest icon)

test/design_tokens_test.dart re-parses the sources and fails on drift, so
regenerating after a token edit is always safe.

Not ported: tokens.json "layout" — the web console's root min-width and dock
widths are web-shell constraints, not client tokens.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FLUTTER_CLIENT = Path(__file__).resolve().parents[1]
REPO_ROOT = FLUTTER_CLIENT.parents[1]
TOKENS_JSON = REPO_ROOT / "docs" / "design" / "console" / "tokens" / "tokens.json"
ICONS_JSON = REPO_ROOT / "docs" / "design" / "console" / "assets" / "icons" / "icons.json"
OUT = FLUTTER_CLIENT / "lib" / "theme"

UI_FAMILY = "Plus Jakarta Sans"
MONO_FAMILY = "Roboto Mono"
# tokens.json carries "650" (CSS variable-font weight). Static fonts ship in
# hundreds; CSS font matching for a 650 request with 600/700 available picks 700.
W650_REPLACEMENT = 700


def dart_ident(token: str) -> str:
    """bg0 -> bg0, ac-bg -> acBg, sev-crit -> sevCrit, dt-red -> dtRed."""
    return re.sub(r"-([a-z0-9])", lambda m: m.group(1).upper(), token)


def dart_ident_cap(token: str) -> str:
    """pill-sm -> PillSm — for concatenating behind a lowercase prefix."""
    i = dart_ident(token)
    return i[0].upper() + i[1:]


def dart_color(value: str, token: str) -> str:
    """Exact conversion: #RRGGBB -> Color(0xFF...), rgba -> Color.fromRGBO."""
    v = value.strip()
    if v.startswith("#"):
        hexv = v[1:]
        if len(hexv) == 6:
            return f"Color(0xFF{hexv.upper()})"
        if len(hexv) == 8:
            return f"Color(0x{hexv.upper()})"
        raise ValueError(f"{token}: unsupported hex length in {value!r}")
    m = re.fullmatch(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)", v)
    if m:
        r, g, b, a = int(m[1]), int(m[2]), int(m[3]), m[4]
        return f"Color.fromRGBO({r}, {g}, {b}, {a})"
    raise ValueError(f"{token}: unsupported color value {value!r}")


def dart_double(px: str) -> str:
    v = float(str(px).rstrip("px"))
    return f"{v:g}" if v == int(v) else f"{v}"


def header(source: str) -> str:
    return (
        "// GENERATED FILE — do not edit by hand.\n"
        "// Regenerate from clients/flutter: python3 tool/codegen.py\n"
        f"// Source: {source}\n"
        "// Values are the console's canonical tokens (exact hex/rgba as authored);\n"
        "// test/design_tokens_test.dart re-parses the sources and fails on drift.\n\n"
    )


def generate_colors(tokens: dict) -> str:
    colors = tokens["color"]
    idents = [(k, dart_ident(k), colors[k]) for k in colors]
    fields = "\n".join(f"  final Color {i};" for _, i, _ in idents)
    ctor = "\n".join(f"    required this.{i}," for _, i, _ in idents)

    def instance(which: str) -> str:
        lines = []
        for key, i, spec in idents:
            lines.append(f"    {i}: {dart_color(spec[which], key)}, // {spec.get('use', '')}")
        joined = "\n".join(lines)
        return f"  static const VigilColors {which} = VigilColors(\n{joined}\n  );"

    names = ", ".join(f"'{k}'" for k, _, _ in idents)
    switch = "\n".join(f"      '{k}' => {i}," for k, i, _ in idents)
    copy = "\n".join(f"      {i}: {i} ?? this.{i}," for _, i, _ in idents)
    lerp = "\n".join(f"      {i}: Color.lerp({i}, other.{i}, t)!," for _, i, _ in idents)
    eq = "\n            && ".join(f"other.{i} == {i}" for _, i, _ in idents)
    hvals = ", ".join(i for _, i, _ in idents)
    copy_params = ", Color? ".join(i for _, i, _ in idents)

    return (
        header("docs/design/console/tokens/tokens.json — color")
        + "import 'package:flutter/material.dart';\n\n"
        "/// Every color token from the console design tokens, for one scheme.\n"
        "/// Field order mirrors tokens.json; Good/Fair/Poor levels, the severity\n"
        "/// scale, and the DeepTempo brand tokens are all carried verbatim.\n"
        "class VigilColors extends ThemeExtension<VigilColors> {\n"
        f"  const VigilColors({{\n{ctor}\n  }});\n\n"
        f"{fields}\n\n"
        "  /// The .vg-dark token class.\n"
        f"{instance('dark')}\n\n"
        "  /// The .vg-light token class.\n"
        f"{instance('light')}\n\n"
        "  /// Token names in tokens.json order.\n"
        f"  static const List<String> tokenNames = [{names}];\n\n"
        "  /// Color for [name]; throws on unknown tokens.\n"
        "  Color byName(String name) => switch (name) {\n"
        f"{switch}\n"
        "      _ => throw ArgumentError('Unknown Vigil color token: $name'),\n"
        "  };\n\n"
        "  @override\n"
        f"  VigilColors copyWith({{Color? {copy_params}}}) => VigilColors(\n"
        f"{copy}\n"
        "  );\n\n"
        "  @override\n"
        "  VigilColors lerp(VigilColors? other, double t) {\n"
        "    if (other == null) return this;\n"
        "    return VigilColors(\n"
        f"{lerp}\n"
        "    );\n"
        "  }\n\n"
        "  @override\n"
        "  bool operator ==(Object other) =>\n"
        "      identical(other, this) ||\n"
        "      other is VigilColors &&\n"
        f"            {eq};\n\n"
        "  @override\n"
        f"  int get hashCode => Object.hashAll([{hvals}]);\n"
        "}\n"
    )


def generate_theme(tokens: dict) -> str:
    radius = tokens["radius"]
    control = tokens["control"]
    space = [dart_double(v) for v in tokens["space"]]

    def fields(section: dict, prefix: str) -> str:
        return "\n".join(
            f"  final double {prefix}{dart_ident_cap(k)}; // {v}" for k, v in section.items()
        )

    def ctor(section: dict, prefix: str) -> str:
        return "\n".join(f"    required this.{prefix}{dart_ident_cap(k)}," for k in section)

    def args(section: dict, prefix: str) -> str:
        return "\n".join(f"      {prefix}{dart_ident_cap(k)}: {dart_double(v)}," for k, v in section.items())

    def copy(section: dict, prefix: str) -> str:
        return "\n".join(
            f"      {prefix}{dart_ident_cap(k)}: {prefix}{dart_ident_cap(k)} ?? this.{prefix}{dart_ident_cap(k)},"
            for k in section
        )

    def lerp(section: dict, prefix: str) -> str:
        return "\n".join(
            f"      {prefix}{dart_ident_cap(k)}: _lerpDouble({prefix}{dart_ident_cap(k)}, other.{prefix}{dart_ident_cap(k)}, t),"
            for k in section
        )

    def eq(section: dict, prefix: str) -> str:
        return "\n            && ".join(
            f"other.{prefix}{dart_ident_cap(k)} == {prefix}{dart_ident_cap(k)}" for k in section
        )

    def hvals(section: dict, prefix: str) -> str:
        return ", ".join(f"{prefix}{dart_ident_cap(k)}" for k in section)

    def value_map(section: dict) -> str:
        return "\n".join(f"    '{k}': {dart_double(v)}," for k, v in section.items())

    copy_params = "\n".join(
        [f"    double? radius{dart_ident_cap(k)}," for k in radius]
        + [f"    double? control{dart_ident_cap(k)}," for k in control]
        + ["    List<double>? space,"]
    )
    hash_list = (
        ", ".join(
            [f"radius{dart_ident_cap(k)}" for k in radius]
            + [f"control{dart_ident_cap(k)}" for k in control]
        )
        + ", space"
    )
    space_list = ", ".join(space)

    return (
        header("docs/design/console/tokens/tokens.json — radius, control, space")
        + "import 'package:flutter/material.dart';\n\n"
        "import 'vigil_colors.dart';\n"
        "import 'vigil_typography.dart';\n\n"
        "/// Non-color metrics from the console tokens: corner radii, control\n"
        "/// heights, and the spacing ramp. Scheme-independent — tokens.json\n"
        "/// carries one value for each.\n"
        "class VigilTheme extends ThemeExtension<VigilTheme> {\n"
        "  const VigilTheme({\n"
        f"{ctor(radius, 'radius')}\n"
        f"{ctor(control, 'control')}\n"
        "    required this.space,\n"
        "  });\n\n"
        f"{fields(radius, 'radius')}\n\n"
        f"{fields(control, 'control')}\n\n"
        "  /// Spacing ramp in px: " + ", ".join(tokens["space"]) + ".\n"
        "  final List<double> space;\n\n"
        "  /// The single metric set (radius/control/space do not vary by scheme).\n"
        "  static const VigilTheme metrics = VigilTheme(\n"
        f"{args(radius, 'radius')}\n"
        f"{args(control, 'control')}\n"
        f"    space: [{space_list}],\n"
        "  );\n\n"
        "  /// Radius values keyed by token name (parity-test surface).\n"
        "  static const Map<String, double> radiusTokens = {\n"
        f"{value_map(radius)}\n"
        "  };\n\n"
        "  /// Control heights keyed by token name (parity-test surface).\n"
        "  static const Map<String, double> controlTokens = {\n"
        f"{value_map(control)}\n"
        "  };\n\n"
        "  static double _lerpDouble(double a, double b, double t) => a + (b - a) * t;\n\n"
        "  static bool _listEquals(List<double> a, List<double> b) {\n"
        "    if (a.length != b.length) return false;\n"
        "    for (var i = 0; i < a.length; i++) {\n"
        "      if (a[i] != b[i]) return false;\n"
        "    }\n"
        "    return true;\n"
        "  }\n\n"
        "  @override\n"
        "  VigilTheme copyWith({\n"
        f"{copy_params}\n"
        "  }) => VigilTheme(\n"
        f"{copy(radius, 'radius')}\n"
        f"{copy(control, 'control')}\n"
        "      space: space ?? this.space,\n"
        "  );\n\n"
        "  @override\n"
        "  VigilTheme lerp(VigilTheme? other, double t) {\n"
        "    if (other == null) return this;\n"
        "    return VigilTheme(\n"
        f"{lerp(radius, 'radius')}\n"
        f"{lerp(control, 'control')}\n"
        "      space: List.generate(\n"
        "        space.length,\n"
        "        (i) => _lerpDouble(space[i], other.space[i], t),\n"
        "      ),\n"
        "    );\n"
        "  }\n\n"
        "  @override\n"
        "  bool operator ==(Object other) =>\n"
        "      identical(other, this) ||\n"
        "      other is VigilTheme &&\n"
        f"            {eq(radius, 'radius')} &&\n"
        f"            {eq(control, 'control')} &&\n"
        "            _listEquals(other.space, space);\n\n"
        "  @override\n"
        f"  int get hashCode => Object.hashAll([{hash_list}]);\n"
        "}\n\n"
        "/// Builds the app ThemeData from the tokens for [brightness]. The\n"
        "/// scheme mapping mirrors the console: accent -> primary, violet ->\n"
        "/// secondary, Poor -> error, bg1 -> surface, bg0 -> scaffold.\n"
        "ThemeData buildVigilThemeData(Brightness brightness) {\n"
        "  final colors =\n"
        "      brightness == Brightness.dark ? VigilColors.dark : VigilColors.light;\n"
        "  final scheme = ColorScheme(\n"
        "    brightness: brightness,\n"
        "    primary: colors.ac,\n"
        "    onPrimary: colors.acTx,\n"
        "    secondary: colors.vio,\n"
        "    onSecondary: colors.acTx,\n"
        "    error: colors.poor,\n"
        "    onError: colors.acTx,\n"
        "    surface: colors.bg1,\n"
        "    onSurface: colors.tx0,\n"
        "  );\n"
        "  return ThemeData(\n"
        "    useMaterial3: true,\n"
        "    colorScheme: scheme,\n"
        "    scaffoldBackgroundColor: colors.bg0,\n"
        "    dividerColor: colors.ln0,\n"
        f"    fontFamily: '{UI_FAMILY}',\n"
        "    extensions: [colors, VigilTheme.metrics],\n"
        "    navigationBarTheme: NavigationBarThemeData(\n"
        "      backgroundColor: colors.bg1,\n"
        "      indicatorColor: colors.acBg,\n"
        "      iconTheme: WidgetStatePropertyAll(\n"
        "        IconThemeData(color: colors.tx1),\n"
        "      ),\n"
        "      labelTextStyle: WidgetStatePropertyAll(\n"
        "        VigilTypography.label.copyWith(color: colors.tx2),\n"
        "      ),\n"
        "    ),\n"
        "  );\n"
        "}\n"
    )


def generate_typography(tokens: dict) -> str:
    scale = tokens["type"]["scale"]
    families = tokens["type"]["families"]
    ui_family = families["ui"].split(",")[0].strip("' ")
    mono_family = families["mono"].split(",")[0].strip("' ")
    assert ui_family == UI_FAMILY and mono_family == MONO_FAMILY, (
        f"font families drifted from the bundled TTFs: {ui_family!r}, {mono_family!r}"
    )

    parsed = {}
    for name, spec in scale.items():
        toks = spec.replace("/", " ").split()
        size = float(toks[0].rstrip("px"))
        weight = None
        spacing = None
        height = None
        mono = False
        color_hint = None
        for tok in toks[1:]:
            if re.fullmatch(r"\d+", tok):
                weight = int(tok)
            elif re.fullmatch(r"-?[0-9.]+px", tok):
                spacing = float(tok.rstrip("px"))
            elif re.fullmatch(r"[0-9.]+", tok):
                height = float(tok)
            elif tok == "mono":
                mono = True
            elif re.fullmatch(r"tx\d", tok):
                color_hint = tok
            else:
                raise ValueError(f"type scale {name!r}: unrecognized token {tok!r}")
        parsed[name] = (size, weight, spacing, height, mono, color_hint)

    dart_names = {name: dart_ident(name) for name in scale}
    assert len(set(dart_names.values())) == len(dart_names), "type scale name collision"

    lines = [
        header("docs/design/console/tokens/tokens.json — type.scale")
        + "import 'package:flutter/material.dart';\n\n"
        "/// The token type ramp as TextStyles. The ramp's exact sizes (13/12/11)\n"
        "/// and weights are re-checked against tokens.json by the parity test.\n"
        "/// Styles carry no color: scheme colors come from VigilColors at the\n"
        "/// call site (the token's color pairing, where one exists, is in a\n"
        "/// comment).\n"
        "class VigilTypography {\n"
        "  VigilTypography._();\n\n"
        f"  static const String uiFamily = '{UI_FAMILY}';\n"
        f"  static const String monoFamily = '{MONO_FAMILY}';\n"
    ]
    for name, (size, weight, spacing, height, mono, color_hint) in parsed.items():
        notes = []
        emit_weight = weight
        if emit_weight is not None and emit_weight % 100 != 0:
            # tokens.json carries variable-font weights (650); static TTFs
            # ship hundreds and CSS matching rounds 650 up to 700.
            notes.append(
                f"token weight {emit_weight} -> w{W650_REPLACEMENT} "
                "(static-font CSS matching)"
            )
            emit_weight = W650_REPLACEMENT
        if color_hint:
            notes.append(f"token pairs this style with {color_hint}")
        doc = f"  /// {'; '.join(notes)}.\n" if notes else ""
        props = [f"fontSize: {size:g}"]
        if emit_weight is not None:
            props.append(f"fontWeight: FontWeight.w{emit_weight}")
        if spacing is not None:
            props.append(f"letterSpacing: {spacing:g}")
        if height is not None:
            props.append(f"height: {height:g}")
        props.append(f"fontFamily: {mono and 'monoFamily' or 'uiFamily'}")
        joined = ",\n    ".join(props)
        lines.append(f"{doc}  static const TextStyle {dart_names[name]} = TextStyle(\n    {joined},\n  );\n")
    by_name = ",\n    ".join(f"'{name}': {dart_names[name]}" for name in scale)
    lines.append(
        "\n  /// Styles keyed by token name (parity-test surface).\n"
        "  static const Map<String, TextStyle> byName = {\n    " + by_name + ",\n  };\n"
        "}\n"
    )
    return "".join(lines)


def generate_icons(manifest: dict) -> str:
    names = list(manifest.keys())
    idents = {k: dart_ident(k) for k in names}
    assert len(set(idents.values())) == len(idents), "icon name collision after camelCasing"

    entries = []
    for k in names:
        path = manifest[k].strip()
        assert re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-]+", path), f"icon {k}: unexpected path chars"
        entries.append(f"  static const VigilIconData {idents[k]} = VigilIconData('{k}', r'{path}');")

    all_list = ", ".join(idents[k] for k in names)
    by_name = ", ".join(f"'{k}': {idents[k]}" for k in names)

    return (
        header("docs/design/console/assets/icons/icons.json — 82-icon line set")
        + "import 'vigil_icon.dart';\n\n"
        "/// The console's 82-icon line set as typed icon data: one SVG path on\n"
        "/// a 24x24 box, stroked at 1.8 with round caps/joins. Render with\n"
        "/// VigilIcon; paths are parsed once and cached.\n"
        "class VigilIcons {\n"
        "  VigilIcons._();\n\n"
        + "\n".join(entries)
        + "\n\n  /// Every icon, manifest order.\n"
        f"  static const List<VigilIconData> all = [{all_list}];\n\n"
        "  /// Icons keyed by manifest name.\n"
        f"  static const Map<String, VigilIconData> byName = {{{by_name}}};\n"
        "}\n"
    )


def main() -> int:
    tokens = json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    icons = json.loads(ICONS_JSON.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {
        "vigil_colors.dart": generate_colors(tokens),
        "vigil_theme.dart": generate_theme(tokens),
        "vigil_typography.dart": generate_typography(tokens),
        "vigil_icons.dart": generate_icons(icons),
    }
    for name, content in outputs.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)} ({len(content)} bytes)")
    print(
        f"{len(tokens['color'])} color tokens, {len(tokens['radius'])} radii, "
        f"{len(tokens['control'])} controls, {len(tokens['space'])} spaces, "
        f"{len(tokens['type']['scale'])} type styles, {len(icons)} icons"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
