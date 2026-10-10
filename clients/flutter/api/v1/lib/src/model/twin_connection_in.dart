//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/twin_process_ref.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_connection_in.g.dart';

/// One connection observation.  A connection belongs to its device — named directly by ``device`` or, when the source could attribute it, implied by the owning ``process`` (whose ``device`` is the connection's device). Naming neither is the one shape the twin cannot place, so it is refused here.
///
/// Properties:
/// * [attributes] 
/// * [connectionType] 
/// * [device] - device_key, or the hostname the device was observed under; implied by `process` when omitted, and when both are given they must resolve to the same device
/// * [direction] 
/// * [localIp] 
/// * [localPort] 
/// * [process] 
/// * [protocol] 
/// * [remoteIp] 
/// * [remotePort] 
/// * [startedAt] 
/// * [state] 
@BuiltValue()
abstract class TwinConnectionIn implements Built<TwinConnectionIn, TwinConnectionInBuilder> {
  @BuiltValueField(wireName: r'attributes')
  BuiltMap<String, JsonObject?>? get attributes;

  @BuiltValueField(wireName: r'connection_type')
  TwinConnectionInConnectionTypeEnum get connectionType;
  // enum connectionTypeEnum {  socket,  stream,  session,  };

  /// device_key, or the hostname the device was observed under; implied by `process` when omitted, and when both are given they must resolve to the same device
  @BuiltValueField(wireName: r'device')
  String? get device;

  @BuiltValueField(wireName: r'direction')
  TwinConnectionInDirectionEnum? get direction;
  // enum directionEnum {  inbound,  outbound,  };

  @BuiltValueField(wireName: r'local_ip')
  String? get localIp;

  @BuiltValueField(wireName: r'local_port')
  int? get localPort;

  @BuiltValueField(wireName: r'process')
  TwinProcessRef? get process;

  @BuiltValueField(wireName: r'protocol')
  String? get protocol;

  @BuiltValueField(wireName: r'remote_ip')
  String? get remoteIp;

  @BuiltValueField(wireName: r'remote_port')
  int? get remotePort;

  @BuiltValueField(wireName: r'started_at')
  DateTime? get startedAt;

  @BuiltValueField(wireName: r'state')
  String? get state;

  TwinConnectionIn._();

  factory TwinConnectionIn([void updates(TwinConnectionInBuilder b)]) = _$TwinConnectionIn;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinConnectionInBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinConnectionIn> get serializer => _$TwinConnectionInSerializer();
}

class _$TwinConnectionInSerializer implements PrimitiveSerializer<TwinConnectionIn> {
  @override
  final Iterable<Type> types = const [TwinConnectionIn, _$TwinConnectionIn];

  @override
  final String wireName = r'TwinConnectionIn';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinConnectionIn object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.attributes != null) {
      yield r'attributes';
      yield serializers.serialize(
        object.attributes,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    yield r'connection_type';
    yield serializers.serialize(
      object.connectionType,
      specifiedType: const FullType(TwinConnectionInConnectionTypeEnum),
    );
    if (object.device != null) {
      yield r'device';
      yield serializers.serialize(
        object.device,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.direction != null) {
      yield r'direction';
      yield serializers.serialize(
        object.direction,
        specifiedType: const FullType.nullable(TwinConnectionInDirectionEnum),
      );
    }
    if (object.localIp != null) {
      yield r'local_ip';
      yield serializers.serialize(
        object.localIp,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.localPort != null) {
      yield r'local_port';
      yield serializers.serialize(
        object.localPort,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.process != null) {
      yield r'process';
      yield serializers.serialize(
        object.process,
        specifiedType: const FullType.nullable(TwinProcessRef),
      );
    }
    if (object.protocol != null) {
      yield r'protocol';
      yield serializers.serialize(
        object.protocol,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.remoteIp != null) {
      yield r'remote_ip';
      yield serializers.serialize(
        object.remoteIp,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.remotePort != null) {
      yield r'remote_port';
      yield serializers.serialize(
        object.remotePort,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.startedAt != null) {
      yield r'started_at';
      yield serializers.serialize(
        object.startedAt,
        specifiedType: const FullType.nullable(DateTime),
      );
    }
    if (object.state != null) {
      yield r'state';
      yield serializers.serialize(
        object.state,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinConnectionIn object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinConnectionInBuilder result,
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
        case r'connection_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(TwinConnectionInConnectionTypeEnum),
          ) as TwinConnectionInConnectionTypeEnum;
          result.connectionType = valueDes;
          break;
        case r'device':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.device = valueDes;
          break;
        case r'direction':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(TwinConnectionInDirectionEnum),
          ) as TwinConnectionInDirectionEnum?;
          if (valueDes == null) continue;
          result.direction = valueDes;
          break;
        case r'local_ip':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.localIp = valueDes;
          break;
        case r'local_port':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.localPort = valueDes;
          break;
        case r'process':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(TwinProcessRef),
          ) as TwinProcessRef?;
          if (valueDes == null) continue;
          result.process.replace(valueDes);
          break;
        case r'protocol':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.protocol = valueDes;
          break;
        case r'remote_ip':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.remoteIp = valueDes;
          break;
        case r'remote_port':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.remotePort = valueDes;
          break;
        case r'started_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(DateTime),
          ) as DateTime?;
          if (valueDes == null) continue;
          result.startedAt = valueDes;
          break;
        case r'state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.state = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinConnectionIn deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinConnectionInBuilder();
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


class TwinConnectionInConnectionTypeEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'socket')
  static const TwinConnectionInConnectionTypeEnum socket = _$twinConnectionInConnectionTypeEnum_socket;
  @BuiltValueEnumConst(wireName: r'stream')
  static const TwinConnectionInConnectionTypeEnum stream = _$twinConnectionInConnectionTypeEnum_stream;
  @BuiltValueEnumConst(wireName: r'session')
  static const TwinConnectionInConnectionTypeEnum session = _$twinConnectionInConnectionTypeEnum_session;

  static Serializer<TwinConnectionInConnectionTypeEnum> get serializer => _$twinConnectionInConnectionTypeEnumSerializer;

  const TwinConnectionInConnectionTypeEnum._(String name): super(name);

  static BuiltSet<TwinConnectionInConnectionTypeEnum> get values => _$twinConnectionInConnectionTypeEnumValues;
  static TwinConnectionInConnectionTypeEnum valueOf(String name) => _$twinConnectionInConnectionTypeEnumValueOf(name);
}

class TwinConnectionInDirectionEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'inbound')
  static const TwinConnectionInDirectionEnum inbound = _$twinConnectionInDirectionEnum_inbound;
  @BuiltValueEnumConst(wireName: r'outbound')
  static const TwinConnectionInDirectionEnum outbound = _$twinConnectionInDirectionEnum_outbound;

  static Serializer<TwinConnectionInDirectionEnum> get serializer => _$twinConnectionInDirectionEnumSerializer;

  const TwinConnectionInDirectionEnum._(String name): super(name);

  static BuiltSet<TwinConnectionInDirectionEnum> get values => _$twinConnectionInDirectionEnumValues;
  static TwinConnectionInDirectionEnum valueOf(String name) => _$twinConnectionInDirectionEnumValueOf(name);
}

