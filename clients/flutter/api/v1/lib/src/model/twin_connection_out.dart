//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:one_of/any_of.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_connection_out.g.dart';

/// A connection as the API returns it — the identifying 5-tuple included.
///
/// Properties:
/// * [attributes] 
/// * [connectionType] 
/// * [deviceId] 
/// * [direction] 
/// * [firstSeen] 
/// * [id] 
/// * [lastSeen] 
/// * [localIp] 
/// * [localPort] 
/// * [processId] 
/// * [protocol] 
/// * [remoteIp] 
/// * [remotePort] 
/// * [source_] 
/// * [startedAt] 
/// * [state] 
@BuiltValue()
abstract class TwinConnectionOut implements Built<TwinConnectionOut, TwinConnectionOutBuilder> {
  @BuiltValueField(wireName: r'attributes')
  BuiltMap<String, JsonObject?>? get attributes;

  @BuiltValueField(wireName: r'connection_type')
  TwinConnectionOutConnectionTypeEnum get connectionType;
  // enum connectionTypeEnum {  socket,  stream,  session,  };

  @BuiltValueField(wireName: r'device_id')
  JsonObject? get deviceId;

  @BuiltValueField(wireName: r'direction')
  String? get direction;

  @BuiltValueField(wireName: r'first_seen')
  String get firstSeen;

  @BuiltValueField(wireName: r'id')
  JsonObject? get id;

  @BuiltValueField(wireName: r'last_seen')
  String get lastSeen;

  @BuiltValueField(wireName: r'local_ip')
  String? get localIp;

  @BuiltValueField(wireName: r'local_port')
  int? get localPort;

  @BuiltValueField(wireName: r'process_id')
  AnyOf? get processId;

  @BuiltValueField(wireName: r'protocol')
  String? get protocol;

  @BuiltValueField(wireName: r'remote_ip')
  String? get remoteIp;

  @BuiltValueField(wireName: r'remote_port')
  int? get remotePort;

  @BuiltValueField(wireName: r'source')
  String get source_;

  @BuiltValueField(wireName: r'started_at')
  String? get startedAt;

  @BuiltValueField(wireName: r'state')
  String? get state;

  TwinConnectionOut._();

  factory TwinConnectionOut([void updates(TwinConnectionOutBuilder b)]) = _$TwinConnectionOut;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinConnectionOutBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinConnectionOut> get serializer => _$TwinConnectionOutSerializer();
}

class _$TwinConnectionOutSerializer implements PrimitiveSerializer<TwinConnectionOut> {
  @override
  final Iterable<Type> types = const [TwinConnectionOut, _$TwinConnectionOut];

  @override
  final String wireName = r'TwinConnectionOut';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinConnectionOut object, {
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
      specifiedType: const FullType(TwinConnectionOutConnectionTypeEnum),
    );
    yield r'device_id';
    yield object.deviceId == null ? null : serializers.serialize(
      object.deviceId,
      specifiedType: const FullType.nullable(JsonObject),
    );
    if (object.direction != null) {
      yield r'direction';
      yield serializers.serialize(
        object.direction,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'first_seen';
    yield serializers.serialize(
      object.firstSeen,
      specifiedType: const FullType(String),
    );
    yield r'id';
    yield object.id == null ? null : serializers.serialize(
      object.id,
      specifiedType: const FullType.nullable(JsonObject),
    );
    yield r'last_seen';
    yield serializers.serialize(
      object.lastSeen,
      specifiedType: const FullType(String),
    );
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
    if (object.processId != null) {
      yield r'process_id';
      yield serializers.serialize(
        object.processId,
        specifiedType: const FullType.nullable(AnyOf),
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
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
    if (object.startedAt != null) {
      yield r'started_at';
      yield serializers.serialize(
        object.startedAt,
        specifiedType: const FullType.nullable(String),
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
    TwinConnectionOut object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinConnectionOutBuilder result,
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
            specifiedType: const FullType(TwinConnectionOutConnectionTypeEnum),
          ) as TwinConnectionOutConnectionTypeEnum;
          result.connectionType = valueDes;
          break;
        case r'device_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(JsonObject),
          ) as JsonObject?;
          if (valueDes == null) continue;
          result.deviceId = valueDes;
          break;
        case r'direction':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.direction = valueDes;
          break;
        case r'first_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.firstSeen = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(JsonObject),
          ) as JsonObject?;
          if (valueDes == null) continue;
          result.id = valueDes;
          break;
        case r'last_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.lastSeen = valueDes;
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
        case r'process_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.processId = valueDes;
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
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        case r'started_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
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
  TwinConnectionOut deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinConnectionOutBuilder();
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


class TwinConnectionOutConnectionTypeEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'socket')
  static const TwinConnectionOutConnectionTypeEnum socket = _$twinConnectionOutConnectionTypeEnum_socket;
  @BuiltValueEnumConst(wireName: r'stream')
  static const TwinConnectionOutConnectionTypeEnum stream = _$twinConnectionOutConnectionTypeEnum_stream;
  @BuiltValueEnumConst(wireName: r'session')
  static const TwinConnectionOutConnectionTypeEnum session = _$twinConnectionOutConnectionTypeEnum_session;

  static Serializer<TwinConnectionOutConnectionTypeEnum> get serializer => _$twinConnectionOutConnectionTypeEnumSerializer;

  const TwinConnectionOutConnectionTypeEnum._(String name): super(name);

  static BuiltSet<TwinConnectionOutConnectionTypeEnum> get values => _$twinConnectionOutConnectionTypeEnumValues;
  static TwinConnectionOutConnectionTypeEnum valueOf(String name) => _$twinConnectionOutConnectionTypeEnumValueOf(name);
}

