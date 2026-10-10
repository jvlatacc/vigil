//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/priority_breakdown_row.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'by_priority_response.g.dart';

/// ByPriorityResponse
///
/// Properties:
/// * [priorityBreakdown] 
@BuiltValue()
abstract class ByPriorityResponse implements Built<ByPriorityResponse, ByPriorityResponseBuilder> {
  @BuiltValueField(wireName: r'priority_breakdown')
  BuiltList<PriorityBreakdownRow>? get priorityBreakdown;

  ByPriorityResponse._();

  factory ByPriorityResponse([void updates(ByPriorityResponseBuilder b)]) = _$ByPriorityResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ByPriorityResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ByPriorityResponse> get serializer => _$ByPriorityResponseSerializer();
}

class _$ByPriorityResponseSerializer implements PrimitiveSerializer<ByPriorityResponse> {
  @override
  final Iterable<Type> types = const [ByPriorityResponse, _$ByPriorityResponse];

  @override
  final String wireName = r'ByPriorityResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ByPriorityResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.priorityBreakdown != null) {
      yield r'priority_breakdown';
      yield serializers.serialize(
        object.priorityBreakdown,
        specifiedType: const FullType(BuiltList, [FullType(PriorityBreakdownRow)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ByPriorityResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ByPriorityResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'priority_breakdown':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(PriorityBreakdownRow)]),
          ) as BuiltList<PriorityBreakdownRow>?;
          if (valueDes == null) continue;
          result.priorityBreakdown.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ByPriorityResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ByPriorityResponseBuilder();
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


