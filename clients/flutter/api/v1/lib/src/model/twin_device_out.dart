//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_device_out.g.dart';

/// A device as the API returns it — physical identity plus last-known state.
///
/// Properties:
/// * [attributes] 
/// * [deviceKey] 
/// * [deviceType] 
/// * [firstSeen] 
/// * [hostname] 
/// * [id] 
/// * [ipAddress] 
/// * [lastSeen] 
/// * [macAddress] 
/// * [osInfo] 
/// * [serialNumber] 
/// * [source_] 
@BuiltValue()
abstract class TwinDeviceOut implements Built<TwinDeviceOut, TwinDeviceOutBuilder> {
  @BuiltValueField(wireName: r'attributes')
  BuiltMap<String, JsonObject?>? get attributes;

  @BuiltValueField(wireName: r'device_key')
  String get deviceKey;

  @BuiltValueField(wireName: r'device_type')
  String get deviceType;

  @BuiltValueField(wireName: r'first_seen')
  String get firstSeen;

  @BuiltValueField(wireName: r'hostname')
  String? get hostname;

  @BuiltValueField(wireName: r'id')
  JsonObject? get id;

  @BuiltValueField(wireName: r'ip_address')
  String? get ipAddress;

  @BuiltValueField(wireName: r'last_seen')
  String get lastSeen;

  @BuiltValueField(wireName: r'mac_address')
  String? get macAddress;

  @BuiltValueField(wireName: r'os_info')
  String? get osInfo;

  @BuiltValueField(wireName: r'serial_number')
  String? get serialNumber;

  @BuiltValueField(wireName: r'source')
  String get source_;

  TwinDeviceOut._();

  factory TwinDeviceOut([void updates(TwinDeviceOutBuilder b)]) = _$TwinDeviceOut;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinDeviceOutBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinDeviceOut> get serializer => _$TwinDeviceOutSerializer();
}

class _$TwinDeviceOutSerializer implements PrimitiveSerializer<TwinDeviceOut> {
  @override
  final Iterable<Type> types = const [TwinDeviceOut, _$TwinDeviceOut];

  @override
  final String wireName = r'TwinDeviceOut';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinDeviceOut object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.attributes != null) {
      yield r'attributes';
      yield serializers.serialize(
        object.attributes,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    yield r'device_key';
    yield serializers.serialize(
      object.deviceKey,
      specifiedType: const FullType(String),
    );
    yield r'device_type';
    yield serializers.serialize(
      object.deviceType,
      specifiedType: const FullType(String),
    );
    yield r'first_seen';
    yield serializers.serialize(
      object.firstSeen,
      specifiedType: const FullType(String),
    );
    if (object.hostname != null) {
      yield r'hostname';
      yield serializers.serialize(
        object.hostname,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'id';
    yield object.id == null ? null : serializers.serialize(
      object.id,
      specifiedType: const FullType.nullable(JsonObject),
    );
    if (object.ipAddress != null) {
      yield r'ip_address';
      yield serializers.serialize(
        object.ipAddress,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'last_seen';
    yield serializers.serialize(
      object.lastSeen,
      specifiedType: const FullType(String),
    );
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
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinDeviceOut object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinDeviceOutBuilder result,
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
        case r'device_key':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.deviceKey = valueDes;
          break;
        case r'device_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.deviceType = valueDes;
          break;
        case r'first_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.firstSeen = valueDes;
          break;
        case r'hostname':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.hostname = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(JsonObject),
          ) as JsonObject?;
          if (valueDes == null) continue;
          result.id = valueDes;
          break;
        case r'ip_address':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.ipAddress = valueDes;
          break;
        case r'last_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.lastSeen = valueDes;
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
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinDeviceOut deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinDeviceOutBuilder();
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


