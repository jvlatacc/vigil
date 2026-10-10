import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_api_v1/src/model/needs_you_response.dart';
import 'package:vigil_api_v1/src/model/pending_action_response.dart';
import 'package:vigil_api_v1/src/serializers.dart';

/// Fixtures shaped exactly like the frozen contract's schemas
/// (`core/api/v1/contract.snapshot.json`): NeedsYouItem (kind, source_id,
/// title, reason, created_at, reversibility required; case_id optional),
/// NeedsYouResponse (count required), PendingActionResponse (all fields
/// optional; open-JSON anyOf fields omitted here).
const needsYouJson = <String, dynamic>{
  'count': 2,
  'items': [
    {
      'kind': 'workflow_approval',
      'source_id': 'action-123',
      'title': 'Isolate host web-prod-3',
      'reason': 'Confidence below the 0.90 auto-approve line',
      'created_at': '2026-10-10T14:20:11Z',
      'reversibility': 'reversible',
      'case_id': 'case-77',
    },
    {
      'kind': 'workflow_approval',
      'source_id': 'action-124',
      'title': 'Quarantine mailbox j.doe',
      'reason': 'Irreversible action requires a person',
      'created_at': '2026-10-10T14:21:42Z',
      'reversibility': 'irreversible',
    },
  ],
};

const pendingActionJson = <String, dynamic>{
  'action_id': 'action-124',
  'action_type': 'quarantine_mailbox',
  'title': 'Quarantine mailbox j.doe',
  'description': 'Hold mail from the compromised address.',
  'confidence': 0.92,
  'reversibility': 'irreversible',
  'status': 'pending',
  'created_at': '2026-10-10T14:21:42Z',
  'created_by': 'daemon',
  'workflow_run_id': 'run-9f2',
  'workflow_phase_id': 'contain',
  'requires_approval': true,
  'reason': 'reversibility=irreversible forces manual approval',
};

void main() {
  final serializers = standardSerializers;

  group('contract round-trip (frozen /api/v1 shapes)', () {
    test('NeedsYouResponse decodes the needs-you payload', () {
      final res = serializers.deserializeWith(
          NeedsYouResponse.serializer, needsYouJson) as NeedsYouResponse;

      expect(res.count, 2);
      final items = res.items!.toList();
      expect(items, hasLength(2));
      expect(items[0].title, 'Isolate host web-prod-3');
      expect(items[0].reversibility, 'reversible');
      expect(items[0].caseId, 'case-77');
      // The second item omits the optional case_id.
      expect(items[1].caseId, isNull);
      expect(items[1].reversibility, 'irreversible');
    });

    test('PendingActionResponse decodes with snake_case wire names', () {
      final action = serializers.deserializeWith(
              PendingActionResponse.serializer, pendingActionJson)
          as PendingActionResponse;

      expect(action.actionId, 'action-124');
      expect(action.confidence, 0.92);
      expect(action.reversibility, 'irreversible');
      expect(action.workflowRunId, 'run-9f2');
      expect(action.requiresApproval, isTrue);
    });

    test('decode → encode → decode is stable for the needs-you payload', () {
      final first = serializers.deserializeWith(
          NeedsYouResponse.serializer, needsYouJson) as NeedsYouResponse;
      final encoded =
          serializers.serializeWith(NeedsYouResponse.serializer, first);

      final second = serializers.deserializeWith(NeedsYouResponse.serializer,
              Map<String, dynamic>.from(encoded as Map<Object?, Object?>))
          as NeedsYouResponse;

      expect(second.count, first.count);
      expect(
        second.items!.map((i) => i.sourceId).toList(),
        first.items!.map((i) => i.sourceId).toList(),
      );
      expect(
        second.items!.map((i) => i.reversibility).toList(),
        first.items!.map((i) => i.reversibility).toList(),
      );
      expect(second.items!.first.title, first.items!.first.title);
      expect(second.items!.first.createdAt, first.items!.first.createdAt);
      expect(second.items!.last.caseId, isNull);
    });

    test('decode → encode → decode is stable for a pending action', () {
      final first = serializers.deserializeWith(
              PendingActionResponse.serializer, pendingActionJson)
          as PendingActionResponse;
      final encoded =
          serializers.serializeWith(PendingActionResponse.serializer, first);

      final second = serializers.deserializeWith(
              PendingActionResponse.serializer,
              Map<String, dynamic>.from(encoded as Map<Object?, Object?>))
          as PendingActionResponse;

      final firstBack =
          serializers.serializeWith(PendingActionResponse.serializer, first);
      final secondBack =
          serializers.serializeWith(PendingActionResponse.serializer, second);
      expect(secondBack, firstBack);
      expect(second.confidence, 0.92);
      expect(second.actionType, 'quarantine_mailbox');
    });
  });
}
