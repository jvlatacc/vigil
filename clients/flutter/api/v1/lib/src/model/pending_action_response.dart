//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:one_of/any_of.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'pending_action_response.g.dart';

/// Frozen shape of an approval action (mirrors ``_pending_to_dict``).  Value types are permissive where the underlying dataclass carries open JSON (evidence, parameters, execution_result); the key set is the promise.
///
/// Properties:
/// * [actionId] 
/// * [actionType] 
/// * [approvedAt] 
/// * [approvedBy] 
/// * [confidence] 
/// * [createdAt] 
/// * [createdBy] 
/// * [description] 
/// * [evidence] 
/// * [executedAt] 
/// * [executionResult] 
/// * [idempotencyKey] 
/// * [parameters] 
/// * [reason] 
/// * [rejectionReason] 
/// * [requiresApproval] 
/// * [reversibility] 
/// * [status] 
/// * [target] 
/// * [title] 
/// * [workflowPhaseId] 
/// * [workflowRunId] 
@BuiltValue()
abstract class PendingActionResponse implements Built<PendingActionResponse, PendingActionResponseBuilder> {
  @BuiltValueField(wireName: r'action_id')
  String? get actionId;

  @BuiltValueField(wireName: r'action_type')
  String? get actionType;

  @BuiltValueField(wireName: r'approved_at')
  String? get approvedAt;

  @BuiltValueField(wireName: r'approved_by')
  String? get approvedBy;

  @BuiltValueField(wireName: r'confidence')
  num? get confidence;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'created_by')
  String? get createdBy;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'evidence')
  AnyOf? get evidence;

  @BuiltValueField(wireName: r'executed_at')
  String? get executedAt;

  @BuiltValueField(wireName: r'execution_result')
  AnyOf? get executionResult;

  @BuiltValueField(wireName: r'idempotency_key')
  String? get idempotencyKey;

  @BuiltValueField(wireName: r'parameters')
  AnyOf? get parameters;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  @BuiltValueField(wireName: r'rejection_reason')
  String? get rejectionReason;

  @BuiltValueField(wireName: r'requires_approval')
  bool? get requiresApproval;

  @BuiltValueField(wireName: r'reversibility')
  String? get reversibility;

  @BuiltValueField(wireName: r'status')
  String? get status;

  @BuiltValueField(wireName: r'target')
  AnyOf? get target;

  @BuiltValueField(wireName: r'title')
  String? get title;

  @BuiltValueField(wireName: r'workflow_phase_id')
  String? get workflowPhaseId;

  @BuiltValueField(wireName: r'workflow_run_id')
  String? get workflowRunId;

  PendingActionResponse._();

  factory PendingActionResponse([void updates(PendingActionResponseBuilder b)]) = _$PendingActionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PendingActionResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PendingActionResponse> get serializer => _$PendingActionResponseSerializer();
}

class _$PendingActionResponseSerializer implements PrimitiveSerializer<PendingActionResponse> {
  @override
  final Iterable<Type> types = const [PendingActionResponse, _$PendingActionResponse];

  @override
  final String wireName = r'PendingActionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PendingActionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.actionId != null) {
      yield r'action_id';
      yield serializers.serialize(
        object.actionId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.actionType != null) {
      yield r'action_type';
      yield serializers.serialize(
        object.actionType,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.approvedAt != null) {
      yield r'approved_at';
      yield serializers.serialize(
        object.approvedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.approvedBy != null) {
      yield r'approved_by';
      yield serializers.serialize(
        object.approvedBy,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.confidence != null) {
      yield r'confidence';
      yield serializers.serialize(
        object.confidence,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.createdAt != null) {
      yield r'created_at';
      yield serializers.serialize(
        object.createdAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.createdBy != null) {
      yield r'created_by';
      yield serializers.serialize(
        object.createdBy,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.evidence != null) {
      yield r'evidence';
      yield serializers.serialize(
        object.evidence,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.executedAt != null) {
      yield r'executed_at';
      yield serializers.serialize(
        object.executedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.executionResult != null) {
      yield r'execution_result';
      yield serializers.serialize(
        object.executionResult,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.idempotencyKey != null) {
      yield r'idempotency_key';
      yield serializers.serialize(
        object.idempotencyKey,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.parameters != null) {
      yield r'parameters';
      yield serializers.serialize(
        object.parameters,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.reason != null) {
      yield r'reason';
      yield serializers.serialize(
        object.reason,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rejectionReason != null) {
      yield r'rejection_reason';
      yield serializers.serialize(
        object.rejectionReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.requiresApproval != null) {
      yield r'requires_approval';
      yield serializers.serialize(
        object.requiresApproval,
        specifiedType: const FullType.nullable(bool),
      );
    }
    if (object.reversibility != null) {
      yield r'reversibility';
      yield serializers.serialize(
        object.reversibility,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.status != null) {
      yield r'status';
      yield serializers.serialize(
        object.status,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.target != null) {
      yield r'target';
      yield serializers.serialize(
        object.target,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.title != null) {
      yield r'title';
      yield serializers.serialize(
        object.title,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.workflowPhaseId != null) {
      yield r'workflow_phase_id';
      yield serializers.serialize(
        object.workflowPhaseId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.workflowRunId != null) {
      yield r'workflow_run_id';
      yield serializers.serialize(
        object.workflowRunId,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    PendingActionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required PendingActionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'action_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.actionId = valueDes;
          break;
        case r'action_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.actionType = valueDes;
          break;
        case r'approved_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.approvedAt = valueDes;
          break;
        case r'approved_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.approvedBy = valueDes;
          break;
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.confidence = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'created_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdBy = valueDes;
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'evidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.evidence = valueDes;
          break;
        case r'executed_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.executedAt = valueDes;
          break;
        case r'execution_result':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.executionResult = valueDes;
          break;
        case r'idempotency_key':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.idempotencyKey = valueDes;
          break;
        case r'parameters':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.parameters = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reason = valueDes;
          break;
        case r'rejection_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rejectionReason = valueDes;
          break;
        case r'requires_approval':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.requiresApproval = valueDes;
          break;
        case r'reversibility':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reversibility = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.status = valueDes;
          break;
        case r'target':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.target = valueDes;
          break;
        case r'title':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.title = valueDes;
          break;
        case r'workflow_phase_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.workflowPhaseId = valueDes;
          break;
        case r'workflow_run_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.workflowRunId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PendingActionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PendingActionResponseBuilder();
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


