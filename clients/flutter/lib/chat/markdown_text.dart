import 'package:flutter/material.dart';
import 'package:markdown/markdown.dart' as md;

import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_typography.dart';

/// Streaming markdown rendering for Ask Vigil answers: the accumulated text
/// is parsed on every build and rendered with the Vigil theme. Chat-length
/// texts re-parse cheaply, and per-frame rebuilds are what make the answer
/// stream in — the console renders with react-markdown the same way.
///
/// Covered: headings, paragraphs, bold/italic/inline code, links (styled,
/// not tappable — no URL-launcher dependency in the client yet), fenced
/// code blocks, lists, blockquotes, horizontal rules. Anything else falls
/// back to its inline content.
class MarkdownText extends StatelessWidget {
  const MarkdownText(this.data, {super.key, this.baseStyle});

  final String data;

  /// Style the inline text inherits — the transcript's body style.
  final TextStyle? baseStyle;

  static final md.Document _document = md.Document(encodeHtml: false);

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final style = baseStyle ??
        VigilTypography.body.copyWith(color: colors.tx0, height: 1.45);
    final nodes = _document.parse(data);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final node in nodes) _block(context, node, style),
      ],
    );
  }

  Widget _block(BuildContext context, md.Node node, TextStyle style) {
    if (node is md.Text) {
      return Text(node.text, style: style);
    }
    if (node is! md.Element) {
      return const SizedBox.shrink();
    }
    final colors = context.vigilColors;
    switch (node.tag) {
      case 'h1':
      case 'h2':
        return _pad(
          _rich(TextSpanHelper.heading(node, style, colors, level: 1)),
          top: 8,
          bottom: 4,
        );
      case 'h3':
      case 'h4':
      case 'h5':
      case 'h6':
        return _pad(
          _rich(TextSpanHelper.heading(node, style, colors, level: 3)),
          top: 6,
          bottom: 4,
        );
      case 'p':
        return _pad(
          _rich(TextSpanHelper.rich(node.children, style, colors)),
          bottom: 8,
        );
      case 'blockquote':
        return _pad(
          Container(
            decoration: BoxDecoration(
              border: Border(left: BorderSide(color: colors.ln2, width: 2)),
            ),
            padding: const EdgeInsets.only(left: 12),
            child: _rich(
              TextSpanHelper.rich(
                node.children,
                style.copyWith(color: colors.tx1),
                colors,
              ),
            ),
          ),
          bottom: 8,
        );
      case 'pre':
        return _pad(
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: colors.bg2,
              border: Border.all(color: colors.ln1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              TextSpanHelper.textContent(node),
              style: TextStyle(
                fontFamily: VigilTypography.monoFamily,
                fontSize: 12,
                color: colors.tx0,
              ),
            ),
          ),
          bottom: 8,
        );
      case 'ul':
      case 'ol':
        final children = node.children ?? const <md.Node>[];
        return _pad(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var i = 0; i < children.length; i++)
                _listItem(
                  children[i],
                  style,
                  colors: colors,
                  marker: node.tag == 'ol' ? '${i + 1}.' : '•',
                ),
            ],
          ),
          bottom: 8,
        );
      case 'hr':
        return _pad(Container(height: 1, color: colors.ln0), bottom: 8);
      default:
        // Unknown block: render its inline content so nothing is dropped.
        return _pad(_rich(TextSpanHelper.rich(node.children, style, colors)));
    }
  }

  Widget _listItem(
    md.Node node,
    TextStyle style, {
    required VigilColors colors,
    required String marker,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 18,
            child: Text(
              marker,
              style: style.copyWith(color: colors.tx2),
              textAlign: TextAlign.end,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _rich(
              TextSpanHelper.rich(
                node is md.Element ? node.children : null,
                style,
                colors,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Spans render through a bare RichText — selectable is unnecessary for
  /// a streaming surface and costs a rebuild per frame.
  static Widget _rich(InlineSpan span) =>
      RichText(text: span, textScaler: TextScaler.noScaling);

  static Widget _pad(Widget child, {double top = 0, double bottom = 0}) =>
      Padding(
        padding: EdgeInsets.only(top: top, bottom: bottom),
        child: child,
      );
}

/// Inline-span construction over the markdown AST — shared by paragraph,
/// heading, list, and quote rendering. Block helpers return widgets; these
/// return spans so a paragraph can mix styles in one RichText.
abstract final class TextSpanHelper {
  /// Inline spans for [nodes]; unknown nodes degrade to their text content.
  static InlineSpan rich(
    List<md.Node>? nodes,
    TextStyle style,
    VigilColors colors,
  ) =>
      TextSpan(children: [
        if (nodes == null || nodes.isEmpty)
          const TextSpan(text: '')
        else
          for (final node in nodes) _inline(node, style, colors),
      ]);

  /// Headings: the title ramp's size and weight over the body's inheritance.
  static InlineSpan heading(
    md.Element node,
    TextStyle style,
    VigilColors colors, {
    required int level,
  }) =>
      rich(
        node.children,
        level == 1
            ? style.copyWith(
                fontSize: VigilTypography.sectionTitle.fontSize,
                fontWeight: VigilTypography.sectionTitle.fontWeight,
                letterSpacing: VigilTypography.sectionTitle.letterSpacing,
              )
            : style.copyWith(
                fontSize: VigilTypography.bodyStrong.fontSize,
                fontWeight: VigilTypography.bodyStrong.fontWeight,
              ),
        colors,
      );

  /// Concatenated text of a subtree — code blocks, link labels.
  static String textContent(md.Node? node) {
    if (node is md.Text) return node.text;
    if (node is md.Element) {
      return [
        for (final c in node.children ?? const <md.Node>[]) textContent(c)
      ].join();
    }
    return '';
  }

  static InlineSpan _inline(md.Node node, TextStyle style, VigilColors colors) {
    if (node is md.Text) return TextSpan(text: node.text, style: style);
    if (node is! md.Element) {
      return TextSpan(text: textContent(node), style: style);
    }
    switch (node.tag) {
      case 'strong':
        return TextSpan(
          children: [
            for (final c in node.children ?? const <md.Node>[])
              _inline(c, style, colors)
          ],
          style: style.copyWith(fontWeight: FontWeight.w700),
        );
      case 'em':
        return TextSpan(
          children: [
            for (final c in node.children ?? const <md.Node>[])
              _inline(c, style, colors)
          ],
          style: style.copyWith(fontStyle: FontStyle.italic),
        );
      case 'code':
        return TextSpan(
          text: textContent(node),
          style: style.copyWith(
            fontFamily: VigilTypography.monoFamily,
            fontSize: (style.fontSize ?? 13) - 1,
            backgroundColor: colors.bg3,
          ),
        );
      case 'a':
        return TextSpan(
          text: textContent(node),
          style: style.copyWith(
            color: colors.ac,
            decoration: TextDecoration.underline,
          ),
        );
      case 'br':
        return const TextSpan(text: '\n');
      default:
        return TextSpan(
          children: [
            for (final c in node.children ?? const <md.Node>[])
              _inline(c, style, colors)
          ],
        );
    }
  }
}
