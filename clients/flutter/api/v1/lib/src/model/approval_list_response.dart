//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/pending_action_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'approval_list_response.g.dart';

/// ApprovalListResponse
///
/// Properties:
/// * [actions] 
/// * [count] 
@BuiltValue()
abstract class ApprovalListResponse implements Built<ApprovalListResponse, ApprovalListResponseBuilder> {
  @BuiltValueField(wireName: r'actions')
  BuiltList<PendingActionResponse>? get actions;

  @BuiltValueField(wireName: r'count')
  int get count;

  ApprovalListResponse._();

  factory ApprovalListResponse([void updates(ApprovalListResponseBuilder b)]) = _$ApprovalListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApprovalListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApprovalListResponse> get serializer => _$ApprovalListResponseSerializer();
}

class _$ApprovalListResponseSerializer implements PrimitiveSerializer<ApprovalListResponse> {
  @override
  final Iterable<Type> types = const [ApprovalListResponse, _$ApprovalListResponse];

  @override
  final String wireName = r'ApprovalListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApprovalListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.actions != null) {
      yield r'actions';
      yield serializers.serialize(
        object.actions,
        specifiedType: const FullType(BuiltList, [FullType(PendingActionResponse)]),
      );
    }
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ApprovalListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ApprovalListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'actions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(PendingActionResponse)]),
          ) as BuiltList<PendingActionResponse>?;
          if (valueDes == null) continue;
          result.actions.replace(valueDes);
          break;
        case r'count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.count = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApprovalListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApprovalListResponseBuilder();
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


