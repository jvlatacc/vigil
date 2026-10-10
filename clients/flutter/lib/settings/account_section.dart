import 'package:flutter/material.dart';

import '../api/vigil_client.dart';
import '../auth/errors.dart';
import '../auth/session.dart';
import 'server_section.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// The Account section: who is signed in, the password change, and sign-out.
///
/// A successful password change ends the session server-side (the backend
/// revokes every outstanding token for the user), so the form gives way to
/// an explicit "sign in again" panel — user-paced, never a silent swap, and
/// the dead local tokens are harmless because the sign-out clears them.
class AccountSection extends StatefulWidget {
  const AccountSection({
    super.key,
    required this.client,
    required this.user,
    required this.onSignOut,
  });

  final VigilClient client;
  final UserProfile user;
  final VoidCallback onSignOut;

  @override
  State<AccountSection> createState() => _AccountSectionState();
}

class _AccountSectionState extends State<AccountSection> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();

  bool _changing = false;
  bool _busy = false;
  bool _changed = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    final current = _current.text;
    final next = _next.text;
    if (current.isEmpty || next.isEmpty) {
      setState(() => _error = 'Enter your current password and a new one.');
      return;
    }
    if (next != _confirm.text) {
      setState(() => _error = "The new passwords don't match.");
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final access = await _readAccessToken();
      await widget.client.auth.changePassword(
        accessToken: access,
        currentPassword: current,
        newPassword: next,
      );
      if (!mounted) return;
      setState(() {
        _busy = false;
        _changed = true;
      });
    } on CurrentPasswordRejected {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Current password is incorrect.';
      });
    } on PasswordPolicyRejected catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  /// The stored access token, or '' when absent — the server refuses an
  /// empty bearer and the section shows the typed failure, the same path a
  /// genuinely expired session takes.
  Future<String> _readAccessToken() async {
    final store = widget.client.tokenStore;
    return await store.readAccess() ?? '';
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final user = widget.user;
    final who = user.username ?? user.email ?? 'Signed in';
    return SectionCard(
      icon: VigilIcons.user,
      title: 'Account',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(who, style: VigilTypography.bodyStrong.copyWith(color: colors.tx0)),
          if (user.email != null && user.email != who)
            Text(
              user.email!,
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          const SizedBox(height: 4),
          Row(
            children: [
              VigilIcon(
                user.mfaEnabled ? VigilIcons.shield : VigilIcons.lock,
                size: 14,
                color: user.mfaEnabled ? colors.good : colors.tx3,
              ),
              const SizedBox(width: 6),
              Text(
                user.mfaEnabled ? 'MFA enabled' : 'MFA not enrolled',
                key: const Key('account-mfa-state'),
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
            ],
          ),
          if (!_changed) ...[
            const SizedBox(height: 12),
            if (!_changing)
              TextButton.icon(
                key: const Key('change-password-open'),
                onPressed: _busy ? null : () => setState(() => _changing = true),
                icon: const VigilIcon(VigilIcons.key, size: 16),
                label: const Text('Change password'),
              )
            else ...[
              TextField(
                key: const Key('current-password-field'),
                controller: _current,
                enabled: !_busy,
                obscureText: true,
                decoration:
                    const InputDecoration(labelText: 'Current password'),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('new-password-field'),
                controller: _next,
                enabled: !_busy,
                obscureText: true,
                decoration:
                    const InputDecoration(labelText: 'New password'),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('confirm-password-field'),
                controller: _confirm,
                enabled: !_busy,
                obscureText: true,
                decoration:
                    const InputDecoration(labelText: 'Confirm new password'),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  FilledButton(
                    key: const Key('change-password-submit'),
                    onPressed: _busy ? null : _submit,
                    child: Text(_busy ? 'Changing…' : 'Change password'),
                  ),
                  const SizedBox(width: 8),
                  TextButton(
                    key: const Key('change-password-cancel'),
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _changing = false;
                              _error = null;
                            }),
                    child: const Text('Cancel'),
                  ),
                ],
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                key: const Key('account-error'),
                style: VigilTypography.meta.copyWith(color: colors.poor),
              ),
            ],
          ] else ...[
            const SizedBox(height: 12),
            Text(
              'Password changed. Every session was signed out — '
              'sign in with the new password.',
              key: const Key('password-changed-note'),
              style: VigilTypography.meta.copyWith(color: colors.good),
            ),
            const SizedBox(height: 8),
            FilledButton(
              key: const Key('password-changed-sign-in'),
              onPressed: widget.onSignOut,
              child: const Text('Sign in again'),
            ),
          ],
          if (!_changed && !_changing) ...[
            const SizedBox(height: 4),
            TextButton.icon(
              key: const Key('account-sign-out'),
              onPressed: widget.onSignOut,
              icon: const VigilIcon(VigilIcons.stop, size: 16),
              label: const Text('Sign out'),
            ),
          ],
        ],
      ),
    );
  }
}
