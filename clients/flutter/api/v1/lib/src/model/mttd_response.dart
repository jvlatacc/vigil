//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'mttd_response.g.dart';

/// MttdResponse
///
/// Properties:
/// * [averageMttdHours] 
/// * [averageMttdSeconds] 
/// * [mttdByPriority] 
/// * [totalCases] 
@BuiltValue()
abstract class MttdResponse implements Built<MttdResponse, MttdResponseBuilder> {
  @BuiltValueField(wireName: r'average_mttd_hours')
  num? get averageMttdHours;

  @BuiltValueField(wireName: r'average_mttd_seconds')
  num? get averageMttdSeconds;

  @BuiltValueField(wireName: r'mttd_by_priority')
  BuiltMap<String, num?>? get mttdByPriority;

  @BuiltValueField(wireName: r'total_cases')
  int get totalCases;

  MttdResponse._();

  factory MttdResponse([void updates(MttdResponseBuilder b)]) = _$MttdResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(MttdResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<MttdResponse> get serializer => _$MttdResponseSerializer();
}

class _$MttdResponseSerializer implements PrimitiveSerializer<MttdResponse> {
  @override
  final Iterable<Type> types = const [MttdResponse, _$MttdResponse];

  @override
  final String wireName = r'MttdResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    MttdResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.averageMttdHours != null) {
      yield r'average_mttd_hours';
      yield serializers.serialize(
        object.averageMttdHours,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.averageMttdSeconds != null) {
      yield r'average_mttd_seconds';
      yield serializers.serialize(
        object.averageMttdSeconds,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.mttdByPriority != null) {
      yield r'mttd_by_priority';
      yield serializers.serialize(
        object.mttdByPriority,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType.nullable(num)]),
      );
    }
    yield r'total_cases';
    yield serializers.serialize(
      object.totalCases,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    MttdResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required MttdResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'average_mttd_hours':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.averageMttdHours = valueDes;
          break;
        case r'average_mttd_seconds':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.averageMttdSeconds = valueDes;
          break;
        case r'mttd_by_priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(num)]),
          ) as BuiltMap<String, num?>?;
          if (valueDes == null) continue;
          result.mttdByPriority.replace(valueDes);
          break;
        case r'total_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.totalCases = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  MttdResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = MttdResponseBuilder();
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


