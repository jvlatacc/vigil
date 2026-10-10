//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/pending_action_response.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'approval_action_result.g.dart';

/// ApprovalActionResult
///
/// Properties:
/// * [action] 
/// * [resumeResult] 
@BuiltValue()
abstract class ApprovalActionResult implements Built<ApprovalActionResult, ApprovalActionResultBuilder> {
  @BuiltValueField(wireName: r'action')
  PendingActionResponse get action;

  @BuiltValueField(wireName: r'resume_result')
  BuiltMap<String, JsonObject?>? get resumeResult;

  ApprovalActionResult._();

  factory ApprovalActionResult([void updates(ApprovalActionResultBuilder b)]) = _$ApprovalActionResult;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApprovalActionResultBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApprovalActionResult> get serializer => _$ApprovalActionResultSerializer();
}

class _$ApprovalActionResultSerializer implements PrimitiveSerializer<ApprovalActionResult> {
  @override
  final Iterable<Type> types = const [ApprovalActionResult, _$ApprovalActionResult];

  @override
  final String wireName = r'ApprovalActionResult';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApprovalActionResult object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'action';
    yield serializers.serialize(
      object.action,
      specifiedType: const FullType(PendingActionResponse),
    );
    if (object.resumeResult != null) {
      yield r'resume_result';
      yield serializers.serialize(
        object.resumeResult,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ApprovalActionResult object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ApprovalActionResultBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'action':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(PendingActionResponse),
          ) as PendingActionResponse;
          result.action.replace(valueDes);
          break;
        case r'resume_result':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.resumeResult.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApprovalActionResult deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApprovalActionResultBuilder();
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


