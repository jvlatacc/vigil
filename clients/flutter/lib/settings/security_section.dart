import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/vigil_client.dart';
import '../auth/errors.dart';
import '../auth/session.dart';
import 'server_section.dart';
import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// The Security section: TOTP MFA enrollment, the first self-service surface
/// for it (the console only displays the enabled flag — the UsersSection
/// column and the UserMenu chip). Enabling is the backend's three-step
/// dance, each step typed: `/mfa/setup` returns the secret, `/mfa/verify`
/// confirms the first code and returns the one-time recovery codes,
/// `DELETE /mfa` turns it off. The parent re-reads `/auth/me` after every
/// server-side state change ([onMfaToggled]) — the server is the source of
/// record.
class SecuritySection extends StatefulWidget {
  const SecuritySection({
    super.key,
    required this.client,
    required this.user,
    required this.onMfaToggled,
  });

  final VigilClient client;
  final UserProfile user;

  /// Called after a successful verify or disable so the parent refreshes the
  /// user (and the MFA state re-renders from the server's answer).
  final VoidCallback onMfaToggled;

  @override
  State<SecuritySection> createState() => _SecuritySectionState();
}

class _SecuritySectionState extends State<SecuritySection> {
  final _code = TextEditingController();

  /// idle → enrolling (secret shown, confirm code) → codes (shown once).
  /// Regenerating codes reuses the codes step from the enabled state.
  _MfaStep _step = _MfaStep.idle;
  MfaSetup? _setup;
  RecoveryCodes? _codes;

  bool _busy = false;
  bool _copied = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<String> _accessToken() async =>
      await widget.client.tokenStore.readAccess() ?? '';

  void _reset() {
    setState(() {
      _step = _MfaStep.idle;
      _setup = null;
      _codes = null;
      _busy = false;
      _copied = false;
      _error = null;
    });
  }

  Future<void> _startSetup() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final setup =
          await widget.client.auth.mfaSetup(accessToken: await _accessToken());
      if (!mounted) return;
      setState(() {
        _busy = false;
        _step = _MfaStep.enrolling;
        _setup = setup;
      });
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  Future<void> _verify() async {
    if (_busy) return;
    final code = _code.text.trim();
    if (code.isEmpty) {
      setState(() => _error = 'Enter the 6-digit code from your app.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final codes = await widget.client.auth.mfaVerify(
        accessToken: await _accessToken(),
        code: code,
      );
      if (!mounted) return;
      setState(() {
        _busy = false;
        _step = _MfaStep.codes;
        _codes = codes;
        _copied = false;
      });
      widget.onMfaToggled();
    } on InvalidMfaCode {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Invalid MFA code.';
      });
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  Future<void> _regenerate() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final codes = await widget.client.auth
          .mfaRecoveryCodes(accessToken: await _accessToken());
      if (!mounted) return;
      setState(() {
        _busy = false;
        _step = _MfaStep.codes;
        _codes = codes;
        _copied = false;
      });
    } on MfaNotSetUp {
      // Disabled elsewhere while this screen was open — resync from the
      // server's view instead of arguing with it.
      if (!mounted) return;
      setState(() {
        _reset();
      });
      widget.onMfaToggled();
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  Future<void> _disable() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Disable MFA?'),
        content: const Text(
          'Signing in will again require only your password. You can '
          're-enable MFA at any time.',
        ),
        actions: [
          TextButton(
            key: const Key('mfa-disable-cancel'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('mfa-disable-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Disable'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.client.auth.mfaDisable(accessToken: await _accessToken());
      if (!mounted) return;
      setState(() {
        _reset();
      });
      widget.onMfaToggled();
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  Future<void> _copyCodes() async {
    final codes = _codes;
    if (codes == null) return;
    await Clipboard.setData(ClipboardData(text: codes.codes.join('\n')));
    if (!mounted) return;
    setState(() => _copied = true);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final enabled = widget.user.mfaEnabled;
    return SectionCard(
      icon: VigilIcons.shield,
      title: 'Security',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VigilIcon(
                enabled ? VigilIcons.shield : VigilIcons.lock,
                size: 14,
                color: enabled ? colors.good : colors.tx3,
              ),
              const SizedBox(width: 6),
              Text(
                enabled
                    ? 'MFA enabled — a TOTP code is required at sign-in.'
                    : 'MFA is not enrolled for this account.',
                key: const Key('security-mfa-state'),
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...switch (_step) {
            _MfaStep.idle => [
                if (!enabled)
                  FilledButton(
                    key: const Key('mfa-setup'),
                    onPressed: _busy ? null : _startSetup,
                    child: Text(_busy ? 'Starting…' : 'Set up MFA'),
                  )
                else ...[
                  TextButton.icon(
                    key: const Key('mfa-regenerate'),
                    onPressed: _busy ? null : _regenerate,
                    icon: const VigilIcon(VigilIcons.refresh, size: 16),
                    label: const Text('New recovery codes'),
                  ),
                  TextButton.icon(
                    key: const Key('mfa-disable'),
                    onPressed: _busy ? null : _disable,
                    icon: const VigilIcon(VigilIcons.trash, size: 16),
                    label: const Text('Disable MFA'),
                  ),
                ],
              ],
            _MfaStep.enrolling => [_enrollingBody(colors)],
            _MfaStep.codes => [_codesBody(colors)],
          },
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              key: const Key('security-error'),
              style: VigilTypography.meta.copyWith(color: colors.poor),
            ),
          ],
        ],
      ),
    );
  }

  Widget _enrollingBody(VigilColors colors) {
    final setup = _setup;
    if (setup == null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '1. Add the secret to your authenticator app (manual entry):',
          style: VigilTypography.meta.copyWith(color: colors.tx2),
        ),
        const SizedBox(height: 6),
        SelectableText(
          setup.secret,
          key: const Key('mfa-secret'),
          style: VigilTypography.mono.copyWith(
            color: colors.tx0,
            fontSize: 15,
            letterSpacing: 1.5,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Or paste this URI where your app accepts it: ${setup.qrUri}',
          key: const Key('mfa-qr-uri'),
          style: VigilTypography.meta.copyWith(color: colors.tx3),
        ),
        const SizedBox(height: 12),
        Text(
          '2. Enter the 6-digit code it shows to confirm:',
          style: VigilTypography.meta.copyWith(color: colors.tx2),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            SizedBox(
              width: 140,
              child: TextField(
                key: const Key('mfa-code-field'),
                controller: _code,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'TOTP code',
                  hintText: '123456',
                ),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              key: const Key('mfa-verify'),
              onPressed: _busy ? null : _verify,
              child: Text(_busy ? 'Verifying…' : 'Verify'),
            ),
            const SizedBox(width: 8),
            TextButton(
              key: const Key('mfa-setup-cancel'),
              onPressed: _busy ? null : _reset,
              child: const Text('Cancel'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _codesBody(VigilColors colors) {
    final codes = _codes;
    if (codes == null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          codes.message ??
              'Recovery codes — shown only once. Store them somewhere '
                  'safe; each works once if you lose your device.',
          key: const Key('recovery-codes-note'),
          style: VigilTypography.meta.copyWith(color: colors.tx2),
        ),
        const SizedBox(height: 8),
        Container(
          key: const Key('recovery-codes'),
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: colors.bg2,
            borderRadius:
                BorderRadius.circular(context.vigilMetrics.radiusCardInner),
            border: Border.all(color: colors.ln0),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final code in codes.codes)
                Text(
                  code,
                  style: VigilTypography.mono.copyWith(color: colors.tx0),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            TextButton.icon(
              key: const Key('copy-recovery-codes'),
              onPressed: _copyCodes,
              icon: const VigilIcon(VigilIcons.clip, size: 16),
              label: Text(_copied ? 'Copied' : 'Copy'),
            ),
            const SizedBox(width: 8),
            FilledButton(
              key: const Key('mfa-codes-done'),
              onPressed: _reset,
              child: const Text('Done'),
            ),
          ],
        ),
      ],
    );
  }
}

enum _MfaStep { idle, enrolling, codes }
