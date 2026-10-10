//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/run_list_item.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'run_list_response.g.dart';

/// RunListResponse
///
/// Properties:
/// * [count] - Number of runs in this page.
/// * [runs] 
@BuiltValue()
abstract class RunListResponse implements Built<RunListResponse, RunListResponseBuilder> {
  /// Number of runs in this page.
  @BuiltValueField(wireName: r'count')
  int get count;

  @BuiltValueField(wireName: r'runs')
  BuiltList<RunListItem> get runs;

  RunListResponse._();

  factory RunListResponse([void updates(RunListResponseBuilder b)]) = _$RunListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RunListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RunListResponse> get serializer => _$RunListResponseSerializer();
}

class _$RunListResponseSerializer implements PrimitiveSerializer<RunListResponse> {
  @override
  final Iterable<Type> types = const [RunListResponse, _$RunListResponse];

  @override
  final String wireName = r'RunListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RunListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
    yield r'runs';
    yield serializers.serialize(
      object.runs,
      specifiedType: const FullType(BuiltList, [FullType(RunListItem)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    RunListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required RunListResponseBuilder result,
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
        case r'runs':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(RunListItem)]),
          ) as BuiltList<RunListItem>;
          result.runs.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RunListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RunListResponseBuilder();
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


