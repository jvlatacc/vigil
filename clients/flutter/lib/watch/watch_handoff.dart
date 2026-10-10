import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Outcome of a watch handoff attempt — typed, never thrown. The mint and
/// delivery are best-effort by design: a failed handoff leaves the watch on
/// its "open Vigil on your iPhone" state, which is the pairing truth the
/// watch itself renders; sign-in is never blocked by it.
enum WatchHandoffOutcome {
  /// The second login (watch User-Agent) succeeded and the payload reached
  /// WatchConnectivity — live-delivered or durably queued for the watch to
  /// pick up.
  sent,

  /// The mint succeeded but the paired watch was not reachable; the phone
  /// holds the pair and delivers it when the WCSession activates.
  deferred,

  /// The second login or delivery failed (rate limit, transport). The watch
  /// stays unpaired until the next sign-in.
  mintFailed,

  /// No bridge on this platform (not iOS, tests, or a host app without the
  /// channel registered).
  unavailable,
}

/// The phone-side half of the watch token handoff.
///
/// At phone sign-in the app mints the watch its OWN token pair by performing
/// a second `/api/auth/login` with the watch's fixed User-Agent
/// (`VigilWatch/1.0 (watchOS)`) — the tokens' `sfp` claim then matches every
/// request the watch makes. The pair travels over WatchConnectivity; the
/// watch never sees the password and never touches the phone's live tokens,
/// so the single-use refresh rotation never contends between devices
/// (spec: "The watch holds its own token pair").
///
/// The native bridge lives at
/// `clients/flutter/ios/Runner/WatchHandoffBridge.swift`; the watch-side
/// receiver is `HandoffConnector` in the watch app. One wire shape, two
/// hand-written ends, each covered by tests on its own side.
class WatchHandoff {
  WatchHandoff({
    MethodChannel? channel,
    void Function(WatchHandoffOutcome)? onOutcome,
    bool? platformSupportedOverride,
  })  : _channel = channel ?? const MethodChannel(_channelName),
        onOutcome = onOutcome ?? ((_) {}),
        _platformSupportedOverride = platformSupportedOverride;

  static const _channelName = 'vigil/watch_handoff';

  /// Exposed for the native side and tests — the name is the contract.
  static String get channelName => _channelName;

  final MethodChannel _channel;

  /// Test seam: when set, replaces the real platform check (true on iOS
  /// only) so channel behavior is testable on every desktop.
  final bool? _platformSupportedOverride;

  /// Observability hook: sign-in fires the handoff without awaiting the UI,
  /// so the outcome surfaces here instead of blocking the flow.
  final void Function(WatchHandoffOutcome outcome) onOutcome;

  /// The channel is registered by the iOS Runner only. macOS and the
  /// desktop targets have no watch to pair.
  bool get isSupportedPlatform =>
      _platformSupportedOverride ?? (!kIsWeb && Platform.isIOS);

  /// Mints the watch's token pair and hands it over. Call right after a
  /// successful phone sign-in, while the credentials are still in hand.
  Future<WatchHandoffOutcome> mintAfterLogin({
    required String serverBaseUrl,
    required String usernameOrEmail,
    required String password,
    String? mfaCode,
  }) =>
      _invoke('mintAndSend', {
        'serverBaseUrl': serverBaseUrl,
        'usernameOrEmail': usernameOrEmail,
        'password': password,
        if (mfaCode != null) 'mfaCode': mfaCode,
      });

  /// Sign-out symmetric: the cleared sentinel wipes the watch's stored
  /// session (and the phone's staged copy) — the watch's tokens die at TTL
  /// otherwise, but a revoked watch must not keep approving.
  Future<WatchHandoffOutcome> revoke() => _invoke('revoke', {});

  Future<WatchHandoffOutcome> _invoke(
    String method,
    Map<String, Object?> arguments,
  ) async {
    final outcome = await _invokeInner(method, arguments);
    onOutcome(outcome);
    return outcome;
  }

  Future<WatchHandoffOutcome> _invokeInner(
    String method,
    Map<String, Object?> arguments,
  ) async {
    if (!isSupportedPlatform) return WatchHandoffOutcome.unavailable;
    try {
      final result = await _channel.invokeMethod<String>(method, arguments);
      return switch (result) {
        'sent' => WatchHandoffOutcome.sent,
        'deferred' => WatchHandoffOutcome.deferred,
        _ => WatchHandoffOutcome.unavailable,
      };
    } on PlatformException {
      // The bridge reports mint failures as errors — the watch stays
      // unpaired; sign-in itself already succeeded and must proceed.
      return WatchHandoffOutcome.mintFailed;
    } on MissingPluginException {
      return WatchHandoffOutcome.unavailable;
    } on TypeError {
      // A native reply of the wrong shape (contract break) — treat like an
      // absent bridge rather than crashing sign-in.
      return WatchHandoffOutcome.unavailable;
    }
  }
}
