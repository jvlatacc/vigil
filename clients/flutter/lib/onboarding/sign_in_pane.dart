import 'dart:async';

import 'package:flutter/material.dart';

import '../api/vigil_client.dart';
import '../auth/errors.dart';
import '../auth/session.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// Credentials + TOTP sign-in against a connected server. Mirrors the
/// console login's MFA step: a 401 with `X-MFA-Required: true` reveals the
/// code field and the retry carries `mfa_code`; a 423 starts the lockout
/// countdown from the server's `Retry-After`. A wrong TOTP code returns a
/// plain 401 (services/api/routers/auth.py:324-328), so while the MFA field
/// is open the failure reads "Invalid MFA code".
class SignInPane extends StatefulWidget {
  const SignInPane({
    super.key,
    required this.client,
    required this.onSignedIn,
    this.serverUrl,
    this.initialError,
  });

  final VigilClient client;

  /// Shown for confirmation under the title — which server you're signing
  /// into (the console's login shows the host implicitly; a native client
  /// can point anywhere, so it is spelled out).
  final String? serverUrl;

  /// Seeded by the host when arriving with context — e.g. the bootstrap
  /// window closed while the pane was open ("An account already exists.").
  final String? initialError;

  final ValueChanged<Session> onSignedIn;

  @override
  State<SignInPane> createState() => _SignInPaneState();
}

class _SignInPaneState extends State<SignInPane> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _mfa = TextEditingController();

  bool _busy = false;
  bool _mfaRequired = false;
  String? _error;

  /// Lockout countdown, in seconds — ticks down once per second instead of
  /// reading the wall clock, so the shown number matches what the server
  /// asked for even if the device suspends mid-countdown.
  int? _lockRemaining;
  Timer? _lockTimer;

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
  }

  @override
  void dispose() {
    _lockTimer?.cancel();
    _username.dispose();
    _password.dispose();
    _mfa.dispose();
    super.dispose();
  }

  bool get _locked => _lockRemaining != null;

  Future<void> _submit() async {
    if (_busy || _locked) return;
    final username = _username.text.trim();
    final password = _password.text;
    if (username.isEmpty || password.isEmpty) {
      setState(() => _error = 'Enter your username and password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await widget.client.signIn(
        usernameOrEmail: username,
        password: password,
        mfaCode: _mfaRequired ? _mfa.text.trim() : null,
      );
      widget.onSignedIn(session);
      // No setState on success — the parent swaps the tree.
    } on MfaRequired {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _mfaRequired = true;
      });
    } on AccountLocked catch (e) {
      if (!mounted) return;
      _startLockout(e.retryAfter);
    } on InvalidCredentials catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = _mfaRequired ? 'Invalid MFA code.' : e.message;
      });
    } on VigilAuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  void _startLockout(Duration? retryAfter) {
    _lockTimer?.cancel();
    _lockTimer = null;
    if (retryAfter == null) {
      // No Retry-After supplied — surface the lock without a countdown and
      // let the server keep enforcing.
      setState(() {
        _busy = false;
        _lockRemaining = null;
        _error = 'Account locked due to repeated failed sign-in attempts.';
      });
      return;
    }
    setState(() {
      _busy = false;
      _lockRemaining = retryAfter.inSeconds;
      _error = _lockMessage(retryAfter.inSeconds);
    });
    _lockTimer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => _tickLock(),
    );
  }

  void _tickLock() {
    final remaining = (_lockRemaining ?? 0) - 1;
    if (remaining <= 0) {
      _lockTimer?.cancel();
      _lockTimer = null;
      if (!mounted) return;
      setState(() {
        _lockRemaining = null;
        _error = null;
      });
      return;
    }
    if (!mounted) return;
    setState(() {
      _lockRemaining = remaining;
      _error = _lockMessage(remaining);
    });
  }

  static String _lockMessage(int secondsRemaining) =>
      'Account locked — retry in ${_format(Duration(seconds: secondsRemaining))}.';

  /// Console duration format (DESIGN.md): "4 min 12 s" — a lockout is
  /// usually under a minute, so seconds alone until a minute.
  static String _format(Duration d) {
    final seconds = d.inSeconds;
    if (seconds < 60) return '${seconds}s';
    final minutes = seconds ~/ 60;
    final rest = seconds % 60;
    return rest == 0 ? '$minutes min' : '$minutes min ${rest}s';
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
              VigilIcon(VigilIcons.shield, size: 36, color: colors.dtRed),
              const SizedBox(height: 12),
              Text(
                'Sign in to Vigil',
                textAlign: TextAlign.center,
                style: VigilTypography.sectionTitle.copyWith(color: colors.tx0),
              ),
              if (widget.serverUrl != null) ...[
                const SizedBox(height: 6),
                Text(
                  widget.serverUrl!,
                  textAlign: TextAlign.center,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ],
              const SizedBox(height: 20),
              TextField(
                key: const Key('sign-in-username'),
                controller: _username,
                autofillHints: const [AutofillHints.username],
                textInputAction: TextInputAction.next,
                decoration:
                    const InputDecoration(labelText: 'Username or email'),
                onChanged: (_) => _clearError(),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('sign-in-password'),
                controller: _password,
                obscureText: true,
                autofillHints: const [AutofillHints.password],
                onSubmitted: (_) => _submit(),
                decoration: const InputDecoration(labelText: 'Password'),
              ),
              if (_mfaRequired) ...[
                const SizedBox(height: 12),
                TextField(
                  key: const Key('sign-in-mfa'),
                  controller: _mfa,
                  obscureText: true,
                  keyboardType: TextInputType.number,
                  onSubmitted: (_) => _submit(),
                  decoration: const InputDecoration(
                    labelText: 'MFA code',
                    helperText:
                        'Enter the 6-digit code from your authenticator app.',
                  ),
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  key: const Key('sign-in-error'),
                  style: VigilTypography.meta.copyWith(color: colors.poor),
                ),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: const Key('sign-in-submit'),
                onPressed: _busy || _locked ? null : _submit,
                child: Text(
                  _busy
                      ? 'Signing in…'
                      : _mfaRequired
                          ? 'Verify and sign in'
                          : 'Sign in',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _clearError() {
    if (_error != null && !_locked) setState(() => _error = null);
  }
}
