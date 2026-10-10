import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/token_store.dart';

import '../helpers/fake_adapter.dart';

const userAgent = 'Vigil/1.0.0 (linux)';
const baseUrl = 'https://vigil.example.com';

Map<String, dynamic> _tokens(String access, String refresh) => {
      'access_token': access,
      'refresh_token': refresh,
      'user': {'username': 'analyst'},
    };

class _Wired {
  _Wired()
      : authAdapter = FakeAdapter(),
        apiAdapter = FakeAdapter(),
        store = InMemoryTokenStore() {
    client = VigilClient(
      baseUrl: baseUrl,
      tokenStore: store,
      userAgent: userAgent,
      authAdapter: authAdapter,
      apiAdapter: apiAdapter,
    );
  }

  final FakeAdapter authAdapter;
  final FakeAdapter apiAdapter;
  final InMemoryTokenStore store;
  late final VigilClient client;
}

void main() {
  group('VigilClient composition', () {
    test('signIn persists the session; every request carries the stable UA',
        () async {
      final w = _Wired();
      w.authAdapter.enqueueJson(200, _tokens('a1', 'r1'));

      expect(await w.client.hasSession, isFalse);

      final session = await w.client.signIn(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
      );

      expect(session.accessToken, 'a1');
      expect(await w.client.hasSession, isTrue);

      final login = w.authAdapter.wherePath('/api/auth/login').first;
      expect(login.body, {
        'username_or_email': 'analyst@corp.example',
        'password': 'hunter2',
      });
      // Pre-auth traffic carries the UA too — sfp is minted from it at login.
      expect(login.header('user-agent'), userAgent);
    });

    test(
        'v1 calls flow through the authenticator end-to-end: '
        'stale token → rotation → replay with the new pair', () async {
      final w = _Wired();
      w.authAdapter
        ..enqueueJson(200, _tokens('a1', 'r1')) // login
        ..enqueueJson(200, _tokens('a2', 'r2')); // rotation
      w.apiAdapter
        ..enqueueJson(401, {'detail': 'Token expired'}) // first needs-you
        ..enqueueJson(200, {
          'count': 1,
          'items': [
            {
              'kind': 'workflow_approval',
              'source_id': 'action-1',
              'title': 'Isolate host web-prod-3',
              'reason': 'Confidence below the 0.90 auto-approve line',
              'created_at': '2026-10-10T14:20:11Z',
              'reversibility': 'reversible',
            }
          ],
        }); // replay

      await w.client.signIn(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
      );

      final res =
          await w.client.v1.getApprovalsApi().getApiV1ApprovalsNeedsYou();

      expect(res.data!.count, 1);
      expect(res.data!.items!.first.title, 'Isolate host web-prod-3');
      expect(res.data!.items!.first.reversibility, 'reversible');

      // Rotation consumed once, replay carried the new token.
      expect(
          w.apiAdapter.wherePath('/api/v1/approvals/needs-you'), hasLength(2));
      final [first, replayed, ...] =
          w.apiAdapter.wherePath('/api/v1/approvals/needs-you').toList();
      expect(first.header('authorization'), 'Bearer a1');
      expect(replayed.header('authorization'), 'Bearer a2');
      expect(w.authAdapter.wherePath('/api/auth/refresh'), hasLength(1));

      // The store holds the rotated pair.
      expect(await w.store.readAccess(), 'a2');
      expect(await w.store.readRefresh(), 'r2');

      // Every request on both transports carries the identical UA.
      for (final req in [...w.authAdapter.requests, ...w.apiAdapter.requests]) {
        expect(req.header('user-agent'), userAgent,
            reason: 'UA drifted on ${req.path}');
      }
    });

    test('signOut posts the refresh token in the body and clears the store',
        () async {
      final w = _Wired();
      w.authAdapter
        ..enqueueJson(200, _tokens('a1', 'r1')) // login
        ..enqueueEmpty(204); // logout

      await w.client.signIn(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
      );

      await w.client.signOut();

      expect(await w.client.hasSession, isFalse);
      final logout = w.authAdapter.wherePath('/api/auth/logout').first;
      expect(logout.body, {'refresh_token': 'r1'});
      expect(logout.header('authorization'), 'Bearer a1');
      expect(logout.header('user-agent'), userAgent);
    });

    test('currentUser surfaces the profile for the navigation gate', () async {
      final w = _Wired();
      final userPayload = {
        'user_id': 'u-1',
        'username': 'analyst',
        'permissions': {'ai_decisions.approve': true},
      };
      w.authAdapter
        ..enqueueJson(200, {
          'access_token': 'a1',
          'refresh_token': 'r1',
          'user': userPayload,
        }) // login
        ..enqueueJson(200, userPayload); // /api/auth/me — fresh read, re-gates

      await w.client.signIn(
        usernameOrEmail: 'analyst@corp.example',
        password: 'hunter2',
      );

      final profile = await w.client.currentUser();
      expect(profile.userId, 'u-1');
      expect(profile.hasPermission('ai_decisions.approve'), isTrue);
    });
  });
}
