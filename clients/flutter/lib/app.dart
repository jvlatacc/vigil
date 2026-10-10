import 'package:flutter/material.dart';

import 'api/config_api.dart';
import 'api/vigil_client.dart';
import 'approvals/approvals_controller.dart';
import 'auth/session.dart';
import 'auth/token_store.dart';
import 'auth/user_agent.dart';
import 'onboarding/onboarding_flow.dart';
import 'onboarding/server_profile.dart';
import 'onboarding/sign_in_pane.dart';
import 'settings/scheme_controller.dart';
import 'shell/screens.dart';
import 'shell/vigil_shell.dart';
import 'theme/extensions.dart';
import 'theme/vigil_colors.dart';
import 'theme/vigil_icon.dart';
import 'theme/vigil_icons.dart';
import 'theme/vigil_theme.dart';
import 'theme/vigil_typography.dart';

/// The app root: boots from stored state into onboarding, sign-in, or the
/// shell, and owns the server-persisted color scheme.
///
/// Gate order mirrors the console (`App.tsx`): a stored server profile is
/// the SetupGate's "configured" state; a stored session decides console vs
/// login; `/auth/me` supplies the permission map the shell gates on.
class VigilApp extends StatefulWidget {
  VigilApp({
    super.key,
    ServerProfileStore? profileStore,
    TokenStore? tokenStore,
    VigilClientFactory clientFactory = defaultClientFactory,
    this.initialRoute,
  })  : profileStore = profileStore ?? SecureServerProfileStore(),
        tokenStore = tokenStore ?? SecureTokenStore(),
        _clientFactoryOverride = clientFactory;

  final ServerProfileStore profileStore;
  final TokenStore tokenStore;
  final VigilClientFactory _clientFactoryOverride;
  final String? initialRoute;

  @override
  State<VigilApp> createState() => _VigilAppState();
}

enum _Phase { booting, onboarding, signIn, ready, bootError }

class _VigilAppState extends State<VigilApp> {
  late final ServerProfileStore _profileStore;
  late final TokenStore _tokenStore;
  late final VigilClientFactory _clientFactory;

  VigilClient? _client;
  UserProfile? _user;
  SchemeController? _scheme;
  ApprovalsController? _approvals;
  VigilScreen? _deepLink;
  _Phase _phase = _Phase.booting;

  @override
  void initState() {
    super.initState();
    _profileStore = widget.profileStore;
    _tokenStore = widget.tokenStore;
    _clientFactory = widget._clientFactoryOverride;
    _deepLink = screenFromRoute(widget.initialRoute);
    _restore();
  }

  @override
  void dispose() {
    _scheme?.dispose();
    _approvals?.dispose();
    super.dispose();
  }

  void _onSchemeChanged() {
    if (mounted) setState(() {});
  }

  /// A VigilClient for [profile] against the app's token store.
  VigilClient _clientFor(ServerProfile profile) => _clientFactory(
        baseUrl: profile.baseUrl,
        tokenStore: _tokenStore,
        userAgent: vigilUserAgent(),
      );

  Future<void> _restore() async {
    setState(() {
      _phase = _Phase.booting;
    });
    try {
      final profile = await _profileStore.read();
      if (!mounted) return;
      if (profile == null) {
        setState(() => _phase = _Phase.onboarding);
        return;
      }
      final client = _clientFor(profile);
      final user = await client.restoreSession();
      if (!mounted) return;
      _client = client;
      if (user == null) {
        setState(() => _phase = _Phase.signIn);
      } else {
        _enterShell(user);
      }
    } on Exception catch (e) {
      // Boot failure (dead server with a stored session, storage trouble):
      // an honest error state with a retry, not a silent fallback that
      // looks signed-out and quietly discards the session.
      if (!mounted) return;
      setState(() {
        _phase = _Phase.bootError;
        _error = e.toString();
      });
    }
  }

  String? _error;

  void _enterShell(UserProfile user) {
    _scheme?.dispose();
    _scheme = SchemeController(configApi: _client?.config)
      ..addListener(_onSchemeChanged)
      // Console parity: pull the persisted scheme once a session exists;
      // failures keep the dark default.
      ..load();
    // One approvals controller per session — Home and Decisions share it;
    // polling starts immediately and pauses with app lifecycle.
    _approvals?.dispose();
    final client = _client;
    if (client == null) {
      _approvals = null;
    } else {
      _approvals = ApprovalsController(client: client, approver: user.username)
        ..startPolling();
    }
    setState(() {
      _user = user;
      _phase = _Phase.ready;
    });
  }

  Future<void> _signOut() async {
    final client = _client;
    if (client != null) {
      try {
        await client.signOut();
      } on Exception {
        // signOut clears the local session in a finally block — a failed
        // server-side revocation is TTL-bounded (access 30 min, refresh
        // 7 d) and must not trap the user in the shell.
      }
    }
    _approvals?.dispose();
    _approvals = null;
    if (!mounted) return;
    setState(() {
      _user = null;
      _deepLink = null;
      _phase = _Phase.signIn;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = _scheme;
    return MaterialApp(
      title: 'Vigil',
      debugShowCheckedModeBanner: false,
      theme: buildVigilThemeData(Brightness.light),
      darkTheme: buildVigilThemeData(Brightness.dark),
      // Dark-first, like the console; the server-persisted scheme wins
      // once loaded.
      themeMode: scheme?.scheme == VigilScheme.light
          ? ThemeMode.light
          : ThemeMode.dark,
      home: switch (_phase) {
        _Phase.booting => _Splash(colors: context.vigilColors),
        _Phase.bootError =>
          _BootError(colors: context.vigilColors, error: _error, onRetry: _restore),
        _Phase.onboarding => OnboardingFlow(
            profileStore: _profileStore,
            tokenStore: _tokenStore,
            clientFactory: _clientFactory,
            onFinished: (client, session) {
              _client = client;
              _enterShell(session.user);
            },
          ),
        _Phase.signIn => _client == null
            ? _Splash(colors: context.vigilColors)
            // The host owns the screen chrome (OnboardingFlow wraps its
            // panes the same way); the shell builds its own Scaffold.
            : Scaffold(
                body: SignInPane(
                  client: _client!,
                  onSignedIn: (session) => _enterShell(session.user),
                ),
              ),
        _Phase.ready => _readyBody(),
      },
    );
  }

  Widget _readyBody() {
    final user = _user!;
    final target = _deepLink;
    if (target != null && !canSeeScreen(target, user.permissions)) {
      return PermissionDeniedScreen(
        screen: target,
        user: user,
        onSignOut: _signOut,
      );
    }
    return VigilShell(
      user: user,
      initialScreen: target ?? _landing(user),
      scheme: _scheme,
      approvals: _approvals,
      onSignOut: _signOut,
    );
  }

  /// First destination the role can see (Ask Vigil is ungated, so this
  /// always resolves) — full landing parity arrives with the Home port.
  static VigilScreen _landing(UserProfile user) =>
      visibleDestinations(user.permissions).first;
}

class _Splash extends StatelessWidget {
  const _Splash({required this.colors});

  final VigilColors colors;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: colors.bg0,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: colors.dtRed,
                borderRadius:
                    BorderRadius.circular(context.vigilMetrics.radiusCard),
              ),
              alignment: Alignment.center,
              child: Text(
                'V',
                style: VigilTypography.sectionTitle.copyWith(
                  color: colors.dtSilver,
                  fontSize: 24,
                ),
              ),
            ),
            const SizedBox(height: 20),
            const CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}

class _BootError extends StatelessWidget {
  const _BootError({
    required this.colors,
    required this.error,
    required this.onRetry,
  });

  final VigilColors colors;
  final String? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: colors.bg0,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            VigilIcon(VigilIcons.warn, size: 32, color: colors.poor),
            const SizedBox(height: 12),
            Text(
              'Vigil could not reach its server',
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
            ),
            if (error != null) ...[
              const SizedBox(height: 6),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Text(
                  error!,
                  textAlign: TextAlign.center,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.tonal(
              key: const Key('boot-retry'),
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
