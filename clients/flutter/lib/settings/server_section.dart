import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../onboarding/server_probe.dart';
import '../onboarding/server_profile.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// Probes a candidate server URL (throws on unreachable / not Vigil) — the
/// app root supplies it, mirroring onboarding's validation.
typedef ServerUrlProbe = Future<Map<String, dynamic>> Function(String url);

/// The Server section: which Vigil this device talks to. Shows the stored
/// base URL, probes it on demand, and edits it — a save re-probes (the same
/// `/api/health` gate onboarding applies) and hands the new profile up; the
/// app root persists it and re-authenticates, because a stored session's
/// tokens belong to the previous server.
class ServerSection extends StatefulWidget {
  const ServerSection({
    super.key,
    required this.profile,
    required this.probeServer,
    required this.onServerChanged,
  });

  final ServerProfile profile;
  final ServerUrlProbe probeServer;
  final ValueChanged<ServerProfile> onServerChanged;

  @override
  State<ServerSection> createState() => _ServerSectionState();
}

class _ServerSectionState extends State<ServerSection> {
  final _url = TextEditingController();

  bool _editing = false;
  bool _busy = false;
  String? _error;

  /// The last probe outcome: a result line while healthy, null while
  /// erroring (the error text takes over).
  String? _probeResult;

  @override
  void initState() {
    super.initState();
    _url.text = widget.profile.baseUrl;
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(ServerSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.profile.baseUrl != widget.profile.baseUrl) {
      _url.text = widget.profile.baseUrl;
      _probeResult = null;
      _error = null;
    }
  }

  /// Runs [action] against a parsed candidate URL and reports the outcome.
  /// Malformed input never reaches the probe — it reads as a field error.
  Future<void> _withParsed({
    required Future<String> Function(ServerProfile profile) action,
  }) async {
    final profile = ServerProfile.tryParse(_url.text);
    if (profile == null) {
      setState(() {
        _error = 'Enter the full server URL, e.g. '
            'https://soc.example.com:6987';
        _probeResult = null;
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await action(profile);
      if (!mounted) return;
      setState(() {
        _busy = false;
        _probeResult = result;
      });
    } on DioException {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _probeResult = null;
        _error = "Couldn't reach a Vigil server at ${profile.baseUrl}.";
      });
    } on NotVigilServer {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _probeResult = null;
        _error = 'That URL answered, but not like a Vigil server. Check the '
            'address and port.';
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _probeResult = null;
        _error = 'Server check failed: $e';
      });
    }
  }

  void _test() => _withParsed(
        action: (profile) async {
          final health = await widget.probeServer(profile.baseUrl);
          final version = health['version'];
          return 'Connected — Vigil version '
              '${version is String ? version : '$version'}';
        },
      );

  /// Save = probe (the onboarding gate), then hand the profile up. The parent
  /// persists it and re-authenticates; this section only reports failure.
  void _save() => _withParsed(
        action: (profile) async {
          await widget.probeServer(profile.baseUrl);
          widget.onServerChanged(profile);
          return 'Connected — server updated. Sign in to continue.';
        },
      );

  void _startEdit() {
    setState(() {
      _editing = true;
      _error = null;
      _probeResult = null;
    });
  }

  void _cancelEdit() {
    setState(() {
      _editing = false;
      _url.text = widget.profile.baseUrl;
      _error = null;
      _probeResult = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return SectionCard(
      icon: VigilIcons.globe,
      title: 'Server',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!_editing)
            Row(
              children: [
                Expanded(
                  child: Text(
                    widget.profile.baseUrl,
                    key: const Key('server-url-value'),
                    style: VigilTypography.mono.copyWith(color: colors.tx0),
                  ),
                ),
                IconButton(
                  key: const Key('server-edit'),
                  tooltip: 'Edit server URL',
                  icon: const VigilIcon(VigilIcons.edit),
                  onPressed: _busy ? null : _startEdit,
                ),
              ],
            )
          else ...[
            TextField(
              key: const Key('server-url-field'),
              controller: _url,
              keyboardType: TextInputType.url,
              autocorrect: false,
              enabled: !_busy,
              decoration: const InputDecoration(
                labelText: 'Server URL',
                hintText: 'https://soc.example.com:6987',
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                FilledButton(
                  key: const Key('server-save'),
                  onPressed: _busy ? null : _save,
                  child: Text(_busy ? 'Checking…' : 'Save'),
                ),
                const SizedBox(width: 8),
                TextButton(
                  key: const Key('server-cancel'),
                  onPressed: _busy ? null : _cancelEdit,
                  child: const Text('Cancel'),
                ),
              ],
            ),
          ],
          if (!_editing) ...[
            const SizedBox(height: 8),
            TextButton.icon(
              key: const Key('server-test'),
              onPressed: _busy ? null : _test,
              icon: const VigilIcon(VigilIcons.refresh, size: 16),
              label: const Text('Test connection'),
            ),
          ],
          if (_probeResult != null)
            Text(
              _probeResult!,
              key: const Key('server-test-result'),
              style: VigilTypography.meta.copyWith(color: colors.good),
            ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              key: const Key('server-error'),
              style: VigilTypography.meta.copyWith(color: colors.poor),
            ),
          ],
          if (!_editing) ...[
            const SizedBox(height: 8),
            Text(
              'Changing the server signs this device out — tokens belong to '
              'the server that issued them.',
              style: VigilTypography.meta.copyWith(color: colors.tx3),
            ),
          ],
        ],
      ),
    );
  }
}

/// The section card chrome every settings section shares: token-styled
/// container with an icon, a 13px/650 title, and the section body.
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.child,
  });

  final VigilIconData icon;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Card(
      color: colors.bg1,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusCard),
        side: BorderSide(color: colors.ln0),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                VigilIcon(icon, size: 18, color: colors.tx1),
                const SizedBox(width: 8),
                Text(
                  title,
                  style:
                      VigilTypography.sectionTitle.copyWith(color: colors.tx0),
                ),
              ],
            ),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}
