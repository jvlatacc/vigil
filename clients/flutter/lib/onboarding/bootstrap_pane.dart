import 'package:flutter/material.dart';

import '../api/vigil_client.dart';
import '../auth/errors.dart';
import '../auth/session.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// First-admin creation on an empty instance (`POST /api/auth/bootstrap`):
/// there is no self-service signup, so the first account — which becomes the
/// administrator — is the only one this endpoint ever creates. On success
/// the pane signs in with the same credentials and hands the session up.
class BootstrapPane extends StatefulWidget {
  const BootstrapPane({
    super.key,
    required this.client,
    required this.onSignedIn,

    /// 403 — an account already exists on this server; the flow falls back
    /// to sign-in with the server's explanation.
    required this.onBootstrapClosed,
  });

  final VigilClient client;
  final ValueChanged<Session> onSignedIn;
  final ValueChanged<String> onBootstrapClosed;

  @override
  State<BootstrapPane> createState() => _BootstrapPaneState();
}

class _BootstrapPaneState extends State<BootstrapPane> {
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _fullName = TextEditingController();

  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _email.dispose();
    _password.dispose();
    _fullName.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    final username = _username.text.trim();
    final email = _email.text.trim();
    final password = _password.text;
    if (username.isEmpty || email.isEmpty || password.isEmpty) {
      setState(() =>
          _error = 'Fill in username, email, and a password to continue.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.client.auth.bootstrap(
        username: username,
        email: email,
        password: password,
        fullName: _fullName.text.trim(),
      );
      // The endpoint returns the account, not tokens — sign in right away.
      final session = await widget.client.signIn(
        usernameOrEmail: username,
        password: password,
      );
      widget.onSignedIn(session);
    } on BootstrapClosed catch (e) {
      if (!mounted) return;
      widget.onBootstrapClosed(e.message);
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              VigilIcon(VigilIcons.userPlus, size: 36, color: colors.ac),
              const SizedBox(height: 12),
              Text(
                'Create the first account',
                textAlign: TextAlign.center,
                style: VigilTypography.sectionTitle.copyWith(color: colors.tx0),
              ),
              const SizedBox(height: 6),
              Text(
                'This instance has no accounts yet. The first one becomes '
                'the administrator.',
                textAlign: TextAlign.center,
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
              const SizedBox(height: 20),
              TextField(
                key: const Key('bootstrap-username'),
                controller: _username,
                autofillHints: const [AutofillHints.username],
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: 'Username'),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('bootstrap-email'),
                controller: _email,
                autofillHints: const [AutofillHints.email],
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: 'Email'),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('bootstrap-password'),
                controller: _password,
                obscureText: true,
                autofillHints: const [AutofillHints.newPassword],
                onSubmitted: (_) => _submit(),
                decoration: const InputDecoration(labelText: 'Password'),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('bootstrap-full-name'),
                controller: _fullName,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
                decoration: const InputDecoration(
                  labelText: 'Full name (optional)',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  key: const Key('bootstrap-error'),
                  style: VigilTypography.meta.copyWith(color: colors.poor),
                ),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: const Key('bootstrap-submit'),
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Creating…' : 'Create account'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
