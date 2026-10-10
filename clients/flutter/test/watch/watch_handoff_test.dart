import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/watch/watch_handoff.dart';

import '../helpers/fake_adapter.dart';

const userAgent = 'Vigil/1.0.0 (linux)';
const baseUrl = 'https://vigil.example.com';

Map<String, dynamic> tokens(String access, String refresh) => {
      'access_token': access,
      'refresh_token': refresh,
      'user': {'username': 'analyst'},
    };

class Recorded {
  final List<MethodCall> calls = [];
  Future<Object?>? Function(MethodCall call)? handler;

  Future<Object?>? onCall(MethodCall call) {
    calls.add(call);
    return handler?.call(call);
  }
}

/// A mocked method channel wired through the test binary messenger —
/// the same transport a real FlutterMethodChannel uses, scripted per test.
Future<(MethodChannel, Recorded)> mockChannel(String name) async {
  final channel = MethodChannel(name);
  final recorded = Recorded();
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, recorded.onCall);
  addTearDown(() => TestDefaultBinaryMessengerBinding.instance
      .defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
  return (channel, recorded);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('WatchHandoff channel mapping', () {
    test('is a no-op off iOS — the channel is never invoked', () async {
      final (channel, recorded) = await mockChannel('watch-gate');
      final outcomes = <WatchHandoffOutcome>[];
      final handoff = WatchHandoff(
        channel: channel,
        onOutcome: outcomes.add,
      );

      // Linux test host: the real platform check is false.
      expect(handoff.isSupportedPlatform, isFalse);
      expect(
        await handoff.mintAfterLogin(
          serverBaseUrl: baseUrl,
          usernameOrEmail: 'analyst',
          password: 'hunter2',
        ),
        WatchHandoffOutcome.unavailable,
      );
      expect(await handoff.revoke(), WatchHandoffOutcome.unavailable);
      expect(recorded.calls, isEmpty);
      expect(outcomes, everyElement(WatchHandoffOutcome.unavailable));
    });

    test('mintAfterLogin sends the credentials and maps "sent"', () async {
      final (channel, recorded) = await mockChannel('watch-mint');
      recorded.handler = (_) async => 'sent';
      final outcomes = <WatchHandoffOutcome>[];
      final handoff = WatchHandoff(
        channel: channel,
        onOutcome: outcomes.add,
        platformSupportedOverride: true,
      );

      final outcome = await handoff.mintAfterLogin(
        serverBaseUrl: baseUrl,
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
        mfaCode: '123456',
      );

      expect(outcome, WatchHandoffOutcome.sent);
      expect(recorded.calls, hasLength(1));
      expect(recorded.calls.single.method, 'mintAndSend');
      expect(recorded.calls.single.arguments, {
        'serverBaseUrl': baseUrl,
        'usernameOrEmail': 'analyst@corp.example',
        'password': 'hunter2',
        'mfaCode': '123456',
      });
      expect(outcomes, [WatchHandoffOutcome.sent]);
    });

    test('an unreachable watch maps to deferred', () async {
      final (channel, recorded) = await mockChannel('watch-deferred');
      recorded.handler = (_) async => 'deferred';
      final handoff = WatchHandoff(
        channel: channel,
        platformSupportedOverride: true,
      );

      expect(
        await handoff.mintAfterLogin(
          serverBaseUrl: baseUrl,
          usernameOrEmail: 'analyst',
          password: 'hunter2',
        ),
        WatchHandoffOutcome.deferred,
      );
    });

    test('a bridge error maps to mintFailed — never throws', () async {
      final (channel, recorded) = await mockChannel('watch-error');
      recorded.handler = (_) async =>
          throw PlatformException(code: 'mint_failed', message: 'HTTP 429');
      final handoff = WatchHandoff(
        channel: channel,
        platformSupportedOverride: true,
      );

      expect(
        await handoff.mintAfterLogin(
          serverBaseUrl: baseUrl,
          usernameOrEmail: 'analyst',
          password: 'hunter2',
        ),
        WatchHandoffOutcome.mintFailed,
      );
    });

    test('a missing host handler maps to unavailable', () async {
      final (channel, _) = await mockChannel('watch-missing');
      // No handler set — the messenger throws MissingPluginException.
      final handoff = WatchHandoff(
        channel: channel,
        platformSupportedOverride: true,
      );

      expect(
        await handoff.revoke(),
        WatchHandoffOutcome.unavailable,
      );
    });

    test('an unrecognized reply maps to unavailable', () async {
      final (channel, recorded) = await mockChannel('watch-junk');
      recorded.handler = (_) async => 42;
      final handoff = WatchHandoff(
        channel: channel,
        platformSupportedOverride: true,
      );

      expect(await handoff.revoke(), WatchHandoffOutcome.unavailable);
    });
  });

  group('VigilClient watch hooks', () {
    test('signIn mints the watch its own pair with the sign-in context',
        () async {
      final (channel, recorded) = await mockChannel('client-mint');
      recorded.handler = (_) async => 'sent';
      final client = VigilClient(
        baseUrl: baseUrl,
        tokenStore: InMemoryTokenStore(),
        userAgent: userAgent,
        authAdapter: FakeAdapter()..enqueueJson(200, tokens('a1', 'r1')),
        watchHandoff: WatchHandoff(
          channel: channel,
          platformSupportedOverride: true,
        ),
      );

      await client.signIn(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
        mfaCode: '654321',
      );

      expect(recorded.calls, hasLength(1));
      final call = recorded.calls.single;
      expect(call.method, 'mintAndSend');
      // serverBaseUrl comes from the client's base URL — the watch must
      // answer the same server as the phone.
      expect(call.arguments['serverBaseUrl'], baseUrl);
      expect(call.arguments['usernameOrEmail'], 'analyst@corp.example');
      expect(call.arguments['password'], 'hunter2');
      expect(call.arguments['mfaCode'], '654321');
    });

    test('a failed handoff never fails sign-in', () async {
      final (channel, recorded) = await mockChannel('client-fail');
      recorded.handler = (_) async =>
          throw PlatformException(code: 'mint_failed', message: 'boom');
      final client = VigilClient(
        baseUrl: baseUrl,
        tokenStore: InMemoryTokenStore(),
        userAgent: userAgent,
        authAdapter: FakeAdapter()..enqueueJson(200, tokens('a1', 'r1')),
        watchHandoff: WatchHandoff(
          channel: channel,
          platformSupportedOverride: true,
        ),
      );

      final session = await client.signIn(
        usernameOrEmail: 'analyst',
        password: 'hunter2',
      );

      // Sign-in succeeded and the phone session persisted even though the
      // watch mint blew up.
      expect(session.accessToken, 'a1');
      expect(await client.hasSession, isTrue);
      expect(recorded.calls.single.method, 'mintAndSend');
    });

    test('signOut revokes the watch session and clears local state', () async {
      final (channel, recorded) = await mockChannel('client-revoke');
      recorded.handler = (_) async => 'sent';
      final authAdapter = FakeAdapter()
        ..enqueueJson(200, tokens('a1', 'r1'))
        ..enqueueJson(200, <String, dynamic>{}); // logout
      final client = VigilClient(
        baseUrl: baseUrl,
        tokenStore: InMemoryTokenStore(),
        userAgent: userAgent,
        authAdapter: authAdapter,
        watchHandoff: WatchHandoff(
          channel: channel,
          platformSupportedOverride: true,
        ),
      );
      await client.signIn(usernameOrEmail: 'analyst', password: 'hunter2');
      recorded.calls.clear();

      await client.signOut();

      expect(recorded.calls.single.method, 'revoke');
      expect(await client.hasSession, isFalse);
    });

    test('no watchHandoff — sign-in and sign-out stay channel-free', () async {
      final client = VigilClient(
        baseUrl: baseUrl,
        tokenStore: InMemoryTokenStore(),
        userAgent: userAgent,
        authAdapter: FakeAdapter()
          ..enqueueJson(200, tokens('a1', 'r1'))
          ..enqueueJson(200, <String, dynamic>{}),
      );

      await client.signIn(usernameOrEmail: 'analyst', password: 'hunter2');
      await client.signOut();

      expect(client.watchHandoff, isNull);
    });
  });
}
