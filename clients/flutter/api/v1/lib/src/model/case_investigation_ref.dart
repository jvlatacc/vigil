//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_investigation_ref.g.dart';

/// One run on the case page: an investigation, or a run started on the case with no investigation row (``investigation_id`` null). Newest first.
///
/// Properties:
/// * [budgetHealth] 
/// * [costUsd] 
/// * [createdAt] 
/// * [investigationId] 
/// * [iterationCount] 
/// * [live] 
/// * [maxCostUsd] 
/// * [runId] 
/// * [status] 
/// * [workflowId] 
@BuiltValue()
abstract class CaseInvestigationRef implements Built<CaseInvestigationRef, CaseInvestigationRefBuilder> {
  @BuiltValueField(wireName: r'budget_health')
  String? get budgetHealth;

  @BuiltValueField(wireName: r'cost_usd')
  num? get costUsd;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'investigation_id')
  String? get investigationId;

  @BuiltValueField(wireName: r'iteration_count')
  int? get iterationCount;

  @BuiltValueField(wireName: r'live')
  bool? get live;

  @BuiltValueField(wireName: r'max_cost_usd')
  num? get maxCostUsd;

  @BuiltValueField(wireName: r'run_id')
  String get runId;

  @BuiltValueField(wireName: r'status')
  String get status;

  @BuiltValueField(wireName: r'workflow_id')
  String get workflowId;

  CaseInvestigationRef._();

  factory CaseInvestigationRef([void updates(CaseInvestigationRefBuilder b)]) = _$CaseInvestigationRef;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseInvestigationRefBuilder b) => b
      ..budgetHealth = 'healthy'
      ..costUsd = 0
      ..iterationCount = 0
      ..live = false
      ..maxCostUsd = 0;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseInvestigationRef> get serializer => _$CaseInvestigationRefSerializer();
}

class _$CaseInvestigationRefSerializer implements PrimitiveSerializer<CaseInvestigationRef> {
  @override
  final Iterable<Type> types = const [CaseInvestigationRef, _$CaseInvestigationRef];

  @override
  final String wireName = r'CaseInvestigationRef';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseInvestigationRef object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.budgetHealth != null) {
      yield r'budget_health';
      yield serializers.serialize(
        object.budgetHealth,
        specifiedType: const FullType(String),
      );
    }
    if (object.costUsd != null) {
      yield r'cost_usd';
      yield serializers.serialize(
        object.costUsd,
        specifiedType: const FullType(num),
      );
    }
    if (object.createdAt != null) {
      yield r'created_at';
      yield serializers.serialize(
        object.createdAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.investigationId != null) {
      yield r'investigation_id';
      yield serializers.serialize(
        object.investigationId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.iterationCount != null) {
      yield r'iteration_count';
      yield serializers.serialize(
        object.iterationCount,
        specifiedType: const FullType(int),
      );
    }
    if (object.live != null) {
      yield r'live';
      yield serializers.serialize(
        object.live,
        specifiedType: const FullType(bool),
      );
    }
    if (object.maxCostUsd != null) {
      yield r'max_cost_usd';
      yield serializers.serialize(
        object.maxCostUsd,
        specifiedType: const FullType(num),
      );
    }
    yield r'run_id';
    yield serializers.serialize(
      object.runId,
      specifiedType: const FullType(String),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(String),
    );
    yield r'workflow_id';
    yield serializers.serialize(
      object.workflowId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseInvestigationRef object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseInvestigationRefBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'budget_health':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.budgetHealth = valueDes;
          break;
        case r'cost_usd':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.costUsd = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'investigation_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.investigationId = valueDes;
          break;
        case r'iteration_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.iterationCount = valueDes;
          break;
        case r'live':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.live = valueDes;
          break;
        case r'max_cost_usd':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.maxCostUsd = valueDes;
          break;
        case r'run_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.runId = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.status = valueDes;
          break;
        case r'workflow_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
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
  CaseInvestigationRef deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseInvestigationRefBuilder();
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


