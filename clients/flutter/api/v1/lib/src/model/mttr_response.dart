//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'mttr_response.g.dart';

/// MttrResponse
///
/// Properties:
/// * [averageMttrHours] 
/// * [averageMttrSeconds] 
/// * [mttrByPriority] 
/// * [totalCases] 
/// * [trendData] 
@BuiltValue()
abstract class MttrResponse implements Built<MttrResponse, MttrResponseBuilder> {
  @BuiltValueField(wireName: r'average_mttr_hours')
  num? get averageMttrHours;

  @BuiltValueField(wireName: r'average_mttr_seconds')
  num? get averageMttrSeconds;

  @BuiltValueField(wireName: r'mttr_by_priority')
  BuiltMap<String, num?>? get mttrByPriority;

  @BuiltValueField(wireName: r'total_cases')
  int get totalCases;

  @BuiltValueField(wireName: r'trend_data')
  BuiltList<BuiltMap<String, JsonObject?>>? get trendData;

  MttrResponse._();

  factory MttrResponse([void updates(MttrResponseBuilder b)]) = _$MttrResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(MttrResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<MttrResponse> get serializer => _$MttrResponseSerializer();
}

class _$MttrResponseSerializer implements PrimitiveSerializer<MttrResponse> {
  @override
  final Iterable<Type> types = const [MttrResponse, _$MttrResponse];

  @override
  final String wireName = r'MttrResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    MttrResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.averageMttrHours != null) {
      yield r'average_mttr_hours';
      yield serializers.serialize(
        object.averageMttrHours,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.averageMttrSeconds != null) {
      yield r'average_mttr_seconds';
      yield serializers.serialize(
        object.averageMttrSeconds,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.mttrByPriority != null) {
      yield r'mttr_by_priority';
      yield serializers.serialize(
        object.mttrByPriority,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType.nullable(num)]),
      );
    }
    yield r'total_cases';
    yield serializers.serialize(
      object.totalCases,
      specifiedType: const FullType(int),
    );
    if (object.trendData != null) {
      yield r'trend_data';
      yield serializers.serialize(
        object.trendData,
        specifiedType: const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    MttrResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required MttrResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'average_mttr_hours':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.averageMttrHours = valueDes;
          break;
        case r'average_mttr_seconds':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.averageMttrSeconds = valueDes;
          break;
        case r'mttr_by_priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(num)]),
          ) as BuiltMap<String, num?>?;
          if (valueDes == null) continue;
          result.mttrByPriority.replace(valueDes);
          break;
        case r'total_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.totalCases = valueDes;
          break;
        case r'trend_data':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.trendData.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  MttrResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = MttrResponseBuilder();
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


