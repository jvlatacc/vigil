import 'package:flutter/material.dart';
import 'package:path_parsing/path_parsing.dart';

/// A line icon from the console's icon set: a single SVG path on a 24x24
/// box, stroked (never filled) at 1.8 with round caps and joins — the
/// stroke color is the "currentColor" of the source SVGs.
class VigilIconData {
  const VigilIconData(this.name, this.path);

  final String name;
  final String path;
}

final Map<String, Path> _pathCache = <String, Path>{};

/// Parses [pathData] (SVG path syntax) into a [Path] on the 24x24 icon box,
/// once per string; icons render many times, paths never change.
Path vigilIconPath(String pathData) {
  return _pathCache.putIfAbsent(pathData, () {
    final path = Path();
    writeSvgPathDataToPath(pathData, _PathSink(path));
    return path;
  });
}

/// Bridges path_parsing's callbacks onto dart:ui's [Path].
class _PathSink implements PathProxy {
  _PathSink(this.path);

  final Path path;

  @override
  void close() => path.close();

  @override
  void lineTo(double x, double y) => path.lineTo(x, y);

  @override
  void moveTo(double x, double y) => path.moveTo(x, y);

  @override
  void cubicTo(double x1, double y1, double x2, double y2, double x3, double y3) =>
      path.cubicTo(x1, y1, x2, y2, x3, y3);
}

/// Renders a [VigilIconData] with the set's stroke styling. Color resolves
/// from the explicit [color], then the ambient [IconTheme] (the currentColor
/// equivalent), then the ambient text style.
class VigilIcon extends StatelessWidget {
  const VigilIcon(
    this.data, {
    super.key,
    this.size = 24,
    this.color,
    this.strokeWidth = 1.8,
  });

  final VigilIconData data;
  final double size;
  final Color? color;

  /// Stroke width inside the 24x24 source box; scales with the icon.
  final double strokeWidth;

  @override
  Widget build(BuildContext context) {
    final resolved = color ??
        IconTheme.of(context).color ??
        DefaultTextStyle.of(context).style.color ??
        const Color(0xFF000000);
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        painter: _VigilIconPainter(
          path: vigilIconPath(data.path),
          color: resolved,
          scale: size / 24,
          strokeWidth: strokeWidth,
        ),
      ),
    );
  }
}

class _VigilIconPainter extends CustomPainter {
  _VigilIconPainter({
    required this.path,
    required this.color,
    required this.scale,
    required this.strokeWidth,
  });

  final Path path;
  final Color color;
  final double scale;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(scale);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = color;
    canvas.drawPath(path, paint);
    canvas.restore();
  }

  @override
  bool shouldRepaint(_VigilIconPainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.scale != scale ||
      oldDelegate.strokeWidth != strokeWidth;
}
