//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/status_breakdown_row.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'by_status_response.g.dart';

/// ByStatusResponse
///
/// Properties:
/// * [statusBreakdown] 
@BuiltValue()
abstract class ByStatusResponse implements Built<ByStatusResponse, ByStatusResponseBuilder> {
  @BuiltValueField(wireName: r'status_breakdown')
  BuiltList<StatusBreakdownRow>? get statusBreakdown;

  ByStatusResponse._();

  factory ByStatusResponse([void updates(ByStatusResponseBuilder b)]) = _$ByStatusResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ByStatusResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ByStatusResponse> get serializer => _$ByStatusResponseSerializer();
}

class _$ByStatusResponseSerializer implements PrimitiveSerializer<ByStatusResponse> {
  @override
  final Iterable<Type> types = const [ByStatusResponse, _$ByStatusResponse];

  @override
  final String wireName = r'ByStatusResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ByStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.statusBreakdown != null) {
      yield r'status_breakdown';
      yield serializers.serialize(
        object.statusBreakdown,
        specifiedType: const FullType(BuiltList, [FullType(StatusBreakdownRow)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ByStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ByStatusResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'status_breakdown':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(StatusBreakdownRow)]),
          ) as BuiltList<StatusBreakdownRow>?;
          if (valueDes == null) continue;
          result.statusBreakdown.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ByStatusResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ByStatusResponseBuilder();
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


