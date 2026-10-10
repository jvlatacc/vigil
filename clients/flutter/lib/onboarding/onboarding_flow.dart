import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../api/vigil_client.dart';
import '../auth/session.dart';
import '../auth/token_store.dart';
import '../auth/user_agent.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';
import 'bootstrap_pane.dart';
import 'server_probe.dart';
import 'server_profile.dart';
import 'sign_in_pane.dart';

/// Fresh-install onboarding, mirroring the console's SetupGate
/// (setup once, then console): pick the server, then either create the
/// first admin (empty instance, `GET /api/auth/bootstrap`) or sign in.
/// The server URL is validated against `/api/health` — public, cheap, and
/// version-stamped — before anything is stored.
class OnboardingFlow extends StatefulWidget {
  OnboardingFlow({
    super.key,
    required this.profileStore,
    required this.tokenStore,
    required this.clientFactory,
    required this.onFinished,
    String? userAgent,
  }) : userAgent = userAgent ?? vigilUserAgent();

  final ServerProfileStore profileStore;
  final TokenStore tokenStore;

  /// Builds the client for a validated server URL. Injectable so tests
  /// script the transport (one adapter across every client built here).
  final VigilClientFactory clientFactory;
  final String userAgent;

  /// Sign-in (or bootstrap-then-sign-in) succeeded.
  final void Function(VigilClient client, Session session) onFinished;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

enum _Step { serverUrl, bootstrap, signIn }

class _OnboardingFlowState extends State<OnboardingFlow> {
  final _url = TextEditingController();

  _Step _step = _Step.serverUrl;
  VigilClient? _client;
  ServerProfile? _profile;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (_busy) return;
    final profile = ServerProfile.tryParse(_url.text);
    if (profile == null) {
      setState(() {
        _error = 'Enter the full server URL, e.g. '
            'https://soc.example.com:6987';
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final client = widget.clientFactory(
        baseUrl: profile.baseUrl,
        tokenStore: widget.tokenStore,
        userAgent: widget.userAgent,
      );
      await probeVigilHealth(
        profile: profile,
        probe: client.auth.health,
      );
      final needsBootstrap = await client.auth.bootstrapRequired();
      await widget.profileStore.save(profile);
      if (!mounted) return;
      setState(() {
        _client = client;
        _profile = profile;
        _step = needsBootstrap ? _Step.bootstrap : _Step.signIn;
        _busy = false;
      });
    } on DioException {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = "Couldn't reach a Vigil server at ${profile.baseUrl}.";
      });
    } on NotVigilServer {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error =
            'That URL answered, but not like a Vigil server. Check the '
            'address and port.';
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = 'Server check failed: $e';
      });
    }
  }

  /// The server changed underneath us (bootstrap closed → sign-in). The
  /// stored profile stays; only the step moves.
  void _fallbackToSignIn(String message) {
    setState(() {
      _step = _Step.signIn;
      _busy = false;
      _error = message;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final client = _client;
    // The flow owns the screen chrome; panes are surfaces inside it.
    if (_step == _Step.serverUrl || client == null) {
      return Scaffold(body: _serverUrlPane(colors));
    }
    return Scaffold(
      body: switch (_step) {
        _Step.bootstrap => BootstrapPane(
            client: client,
            onSignedIn: (session) => widget.onFinished(client, session),
            onBootstrapClosed: _fallbackToSignIn,
          ),
        _Step.signIn => SignInPane(
            client: client,
            serverUrl: _profile?.baseUrl,
            initialError: _error,
            onSignedIn: (session) => widget.onFinished(client, session),
          ),
        _Step.serverUrl => _serverUrlPane(colors),
      },
    );
  }

  Widget _serverUrlPane(colors) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              VigilIcon(VigilIcons.globe, size: 36, color: colors.ac),
              const SizedBox(height: 12),
              Text(
                'Connect to Vigil',
                textAlign: TextAlign.center,
                style: VigilTypography.sectionTitle.copyWith(color: colors.tx0),
              ),
              const SizedBox(height: 6),
              Text(
                'The URL of a running Vigil server — the same one the web '
                'console uses, including the port if it is not 443.',
                textAlign: TextAlign.center,
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
              const SizedBox(height: 20),
              TextField(
                key: const Key('server-url-field'),
                controller: _url,
                keyboardType: TextInputType.url,
                autocorrect: false,
                onSubmitted: (_) => _connect(),
                decoration: const InputDecoration(
                  labelText: 'Server URL',
                  hintText: 'https://soc.example.com:6987',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  key: const Key('server-url-error'),
                  style: VigilTypography.meta.copyWith(color: colors.poor),
                ),
              ],
              const SizedBox(height: 20),
              FilledButton(
                key: const Key('server-url-submit'),
                onPressed: _busy ? null : _connect,
                child: Text(_busy ? 'Checking…' : 'Connect'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
