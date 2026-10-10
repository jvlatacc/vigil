//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/twin_device_out.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_device_list_response.g.dart';

/// The flat device list tables and debugging read; ``device_key`` is here.
///
/// Properties:
/// * [devices] 
/// * [total] 
@BuiltValue()
abstract class TwinDeviceListResponse implements Built<TwinDeviceListResponse, TwinDeviceListResponseBuilder> {
  @BuiltValueField(wireName: r'devices')
  BuiltList<TwinDeviceOut>? get devices;

  @BuiltValueField(wireName: r'total')
  int get total;

  TwinDeviceListResponse._();

  factory TwinDeviceListResponse([void updates(TwinDeviceListResponseBuilder b)]) = _$TwinDeviceListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinDeviceListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinDeviceListResponse> get serializer => _$TwinDeviceListResponseSerializer();
}

class _$TwinDeviceListResponseSerializer implements PrimitiveSerializer<TwinDeviceListResponse> {
  @override
  final Iterable<Type> types = const [TwinDeviceListResponse, _$TwinDeviceListResponse];

  @override
  final String wireName = r'TwinDeviceListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinDeviceListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.devices != null) {
      yield r'devices';
      yield serializers.serialize(
        object.devices,
        specifiedType: const FullType(BuiltList, [FullType(TwinDeviceOut)]),
      );
    }
    yield r'total';
    yield serializers.serialize(
      object.total,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinDeviceListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinDeviceListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'devices':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinDeviceOut)]),
          ) as BuiltList<TwinDeviceOut>?;
          if (valueDes == null) continue;
          result.devices.replace(valueDes);
          break;
        case r'total':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.total = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinDeviceListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinDeviceListResponseBuilder();
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


