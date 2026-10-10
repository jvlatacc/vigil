//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_queue_item.g.dart';

/// One row of the case queue.  ``case_id`` and ``title`` stay so callers that only need a picker (the workflow start dialog) can keep reading the list.
///
/// Properties:
/// * [ageSeconds] 
/// * [assignee] 
/// * [budgetHealth] 
/// * [caseId] 
/// * [combinedState] 
/// * [commentCount] 
/// * [costUsd] 
/// * [findingsCount] 
/// * [healthStatus] 
/// * [iterationCount] 
/// * [lastActivity] 
/// * [maxCostUsd] 
/// * [needsYou] 
/// * [priority] 
/// * [slaSecondsLeft] 
/// * [title] 
/// * [workflowId] 
@BuiltValue()
abstract class CaseQueueItem implements Built<CaseQueueItem, CaseQueueItemBuilder> {
  @BuiltValueField(wireName: r'age_seconds')
  num get ageSeconds;

  @BuiltValueField(wireName: r'assignee')
  String? get assignee;

  @BuiltValueField(wireName: r'budget_health')
  String? get budgetHealth;

  @BuiltValueField(wireName: r'case_id')
  String get caseId;

  @BuiltValueField(wireName: r'combined_state')
  String get combinedState;

  @BuiltValueField(wireName: r'comment_count')
  int? get commentCount;

  @BuiltValueField(wireName: r'cost_usd')
  num? get costUsd;

  @BuiltValueField(wireName: r'findings_count')
  int? get findingsCount;

  @BuiltValueField(wireName: r'health_status')
  String? get healthStatus;

  @BuiltValueField(wireName: r'iteration_count')
  int? get iterationCount;

  @BuiltValueField(wireName: r'last_activity')
  DateTime? get lastActivity;

  @BuiltValueField(wireName: r'max_cost_usd')
  num? get maxCostUsd;

  @BuiltValueField(wireName: r'needs_you')
  bool? get needsYou;

  @BuiltValueField(wireName: r'priority')
  String? get priority;

  @BuiltValueField(wireName: r'sla_seconds_left')
  num? get slaSecondsLeft;

  @BuiltValueField(wireName: r'title')
  String get title;

  @BuiltValueField(wireName: r'workflow_id')
  String? get workflowId;

  CaseQueueItem._();

  factory CaseQueueItem([void updates(CaseQueueItemBuilder b)]) = _$CaseQueueItem;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseQueueItemBuilder b) => b
      ..commentCount = 0
      ..findingsCount = 0
      ..needsYou = false;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseQueueItem> get serializer => _$CaseQueueItemSerializer();
}

class _$CaseQueueItemSerializer implements PrimitiveSerializer<CaseQueueItem> {
  @override
  final Iterable<Type> types = const [CaseQueueItem, _$CaseQueueItem];

  @override
  final String wireName = r'CaseQueueItem';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseQueueItem object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'age_seconds';
    yield serializers.serialize(
      object.ageSeconds,
      specifiedType: const FullType(num),
    );
    if (object.assignee != null) {
      yield r'assignee';
      yield serializers.serialize(
        object.assignee,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.budgetHealth != null) {
      yield r'budget_health';
      yield serializers.serialize(
        object.budgetHealth,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'case_id';
    yield serializers.serialize(
      object.caseId,
      specifiedType: const FullType(String),
    );
    yield r'combined_state';
    yield serializers.serialize(
      object.combinedState,
      specifiedType: const FullType(String),
    );
    if (object.commentCount != null) {
      yield r'comment_count';
      yield serializers.serialize(
        object.commentCount,
        specifiedType: const FullType(int),
      );
    }
    if (object.costUsd != null) {
      yield r'cost_usd';
      yield serializers.serialize(
        object.costUsd,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.findingsCount != null) {
      yield r'findings_count';
      yield serializers.serialize(
        object.findingsCount,
        specifiedType: const FullType(int),
      );
    }
    if (object.healthStatus != null) {
      yield r'health_status';
      yield serializers.serialize(
        object.healthStatus,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.iterationCount != null) {
      yield r'iteration_count';
      yield serializers.serialize(
        object.iterationCount,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.lastActivity != null) {
      yield r'last_activity';
      yield serializers.serialize(
        object.lastActivity,
        specifiedType: const FullType.nullable(DateTime),
      );
    }
    if (object.maxCostUsd != null) {
      yield r'max_cost_usd';
      yield serializers.serialize(
        object.maxCostUsd,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.needsYou != null) {
      yield r'needs_you';
      yield serializers.serialize(
        object.needsYou,
        specifiedType: const FullType(bool),
      );
    }
    if (object.priority != null) {
      yield r'priority';
      yield serializers.serialize(
        object.priority,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.slaSecondsLeft != null) {
      yield r'sla_seconds_left';
      yield serializers.serialize(
        object.slaSecondsLeft,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'title';
    yield serializers.serialize(
      object.title,
      specifiedType: const FullType(String),
    );
    if (object.workflowId != null) {
      yield r'workflow_id';
      yield serializers.serialize(
        object.workflowId,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseQueueItem object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseQueueItemBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'age_seconds':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.ageSeconds = valueDes;
          break;
        case r'assignee':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.assignee = valueDes;
          break;
        case r'budget_health':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.budgetHealth = valueDes;
          break;
        case r'case_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.caseId = valueDes;
          break;
        case r'combined_state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.combinedState = valueDes;
          break;
        case r'comment_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.commentCount = valueDes;
          break;
        case r'cost_usd':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.costUsd = valueDes;
          break;
        case r'findings_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.findingsCount = valueDes;
          break;
        case r'health_status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.healthStatus = valueDes;
          break;
        case r'iteration_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.iterationCount = valueDes;
          break;
        case r'last_activity':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(DateTime),
          ) as DateTime?;
          if (valueDes == null) continue;
          result.lastActivity = valueDes;
          break;
        case r'max_cost_usd':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.maxCostUsd = valueDes;
          break;
        case r'needs_you':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.needsYou = valueDes;
          break;
        case r'priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.priority = valueDes;
          break;
        case r'sla_seconds_left':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.slaSecondsLeft = valueDes;
          break;
        case r'title':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.title = valueDes;
          break;
        case r'workflow_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.workflowId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseQueueItem deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseQueueItemBuilder();
    final serializedList = (serialized as Iterable<Object?>).toList();
    final unhandled = <Object?>[];
    _deserializeProperties(
      serializers,
      serialized,
      specifiedType: specifiedType,
      serializedList: serializedList,
      unhandled: unhandled,
      result: result,
    );
    return result.build();
  }
}


