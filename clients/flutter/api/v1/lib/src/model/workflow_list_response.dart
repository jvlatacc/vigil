//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'workflow_list_response.g.dart';

/// WorkflowListResponse
///
/// Properties:
/// * [count] 
/// * [workflows] 
@BuiltValue()
abstract class WorkflowListResponse implements Built<WorkflowListResponse, WorkflowListResponseBuilder> {
  @BuiltValueField(wireName: r'count')
  int get count;

  @BuiltValueField(wireName: r'workflows')
  BuiltList<BuiltMap<String, JsonObject?>>? get workflows;

  WorkflowListResponse._();

  factory WorkflowListResponse([void updates(WorkflowListResponseBuilder b)]) = _$WorkflowListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(WorkflowListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<WorkflowListResponse> get serializer => _$WorkflowListResponseSerializer();
}

class _$WorkflowListResponseSerializer implements PrimitiveSerializer<WorkflowListResponse> {
  @override
  final Iterable<Type> types = const [WorkflowListResponse, _$WorkflowListResponse];

  @override
  final String wireName = r'WorkflowListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    WorkflowListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
    if (object.workflows != null) {
      yield r'workflows';
      yield serializers.serialize(
        object.workflows,
        specifiedType: const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    WorkflowListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required WorkflowListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.count = valueDes;
          break;
        case r'workflows':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.workflows.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  WorkflowListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = WorkflowListResponseBuilder();
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


