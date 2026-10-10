/// Time and duration in the console's vocabulary (DESIGN.md §2): UTC,
/// 24-hour, "14:22"; durations "4 min 12 s"; ages relative.
String fmtUtc(DateTime utc) =>
    '${utc.year.toString().padLeft(4, '0')}-${utc.month.toString().padLeft(2, '0')}-${utc.day.toString().padLeft(2, '0')} '
    '${utc.hour.toString().padLeft(2, '0')}:${utc.minute.toString().padLeft(2, '0')}';

/// Durations as the console writes them: "4 min 12 s", "2 h 05 min",
/// "3 d 4 h". Seconds drop when the value dominates.
String fmtDuration(Duration d) {
  var total = d.inSeconds;
  if (total < 0) total = 0;
  final days = total ~/ 86400;
  final hours = (total % 86400) ~/ 3600;
  final minutes = (total % 3600) ~/ 60;
  final seconds = total % 60;
  if (days > 0) return '$days d $hours h';
  if (hours > 0) return '$hours h ${minutes.toString().padLeft(2, '0')} min';
  if (minutes > 0) return '$minutes min $seconds s';
  return '$seconds s';
}

/// "4 min ago" / "2 h ago" / "3 d ago" — the age label on polled data.
String fmtAge(Duration age) {
  var total = age.inSeconds;
  if (total < 0) total = 0;
  if (total < 60) return 'just now';
  if (total < 3600) {
    final m = total ~/ 60;
    return '$m min ago';
  }
  if (total < 86400) return '${total ~/ 3600} h ago';
  return '${total ~/ 86400} d ago';
}

/// Best-effort parse of the server's ISO timestamps (naive UTC, per
/// `triage_read._iso` and the v1 models' string timestamps). Null on
/// anything unparseable — the UI shows no time rather than a wrong one.
DateTime? parseUtc(String? iso) {
  if (iso == null || iso.isEmpty) return null;
  return DateTime.tryParse(iso)?.toUtc();
}
