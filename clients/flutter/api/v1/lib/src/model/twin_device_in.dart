//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_device_in.g.dart';

/// One device observation.  The identity fields (``hostname``, ``mac_address``, ``serial_number``) are what the ingest derives the ``device_key`` from, so at least one is required; everything else is the last-known state of the machine.
///
/// Properties:
/// * [attributes] 
/// * [deviceType] 
/// * [hostname] 
/// * [ipAddress] 
/// * [macAddress] 
/// * [osInfo] 
/// * [serialNumber] 
@BuiltValue()
abstract class TwinDeviceIn implements Built<TwinDeviceIn, TwinDeviceInBuilder> {
  @BuiltValueField(wireName: r'attributes')
  BuiltMap<String, JsonObject?>? get attributes;

  @BuiltValueField(wireName: r'device_type')
  String? get deviceType;

  @BuiltValueField(wireName: r'hostname')
  String? get hostname;

  @BuiltValueField(wireName: r'ip_address')
  String? get ipAddress;

  @BuiltValueField(wireName: r'mac_address')
  String? get macAddress;

  @BuiltValueField(wireName: r'os_info')
  String? get osInfo;

  @BuiltValueField(wireName: r'serial_number')
  String? get serialNumber;

  TwinDeviceIn._();

  factory TwinDeviceIn([void updates(TwinDeviceInBuilder b)]) = _$TwinDeviceIn;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinDeviceInBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinDeviceIn> get serializer => _$TwinDeviceInSerializer();
}

class _$TwinDeviceInSerializer implements PrimitiveSerializer<TwinDeviceIn> {
  @override
  final Iterable<Type> types = const [TwinDeviceIn, _$TwinDeviceIn];

  @override
  final String wireName = r'TwinDeviceIn';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinDeviceIn object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.attributes != null) {
      yield r'attributes';
      yield serializers.serialize(
        object.attributes,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    if (object.deviceType != null) {
      yield r'device_type';
      yield serializers.serialize(
        object.deviceType,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.hostname != null) {
      yield r'hostname';
      yield serializers.serialize(
        object.hostname,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.ipAddress != null) {
      yield r'ip_address';
      yield serializers.serialize(
        object.ipAddress,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.macAddress != null) {
      yield r'mac_address';
      yield serializers.serialize(
        object.macAddress,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.osInfo != null) {
      yield r'os_info';
      yield serializers.serialize(
        object.osInfo,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.serialNumber != null) {
      yield r'serial_number';
      yield serializers.serialize(
        object.serialNumber,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinDeviceIn object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinDeviceInBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'attributes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.attributes.replace(valueDes);
          break;
        case r'device_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.deviceType = valueDes;
          break;
        case r'hostname':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.hostname = valueDes;
          break;
        case r'ip_address':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.ipAddress = valueDes;
          break;
        case r'mac_address':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.macAddress = valueDes;
          break;
        case r'os_info':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.osInfo = valueDes;
          break;
        case r'serial_number':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.serialNumber = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinDeviceIn deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinDeviceInBuilder();
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


