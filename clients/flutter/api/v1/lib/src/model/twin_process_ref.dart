//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_process_ref.g.dart';

/// Names an already-observed process by its natural key.
///
/// Properties:
/// * [device] - device_key of the device the process ran on, or the hostname the device was observed under
/// * [name] 
/// * [pid] 
@BuiltValue()
abstract class TwinProcessRef implements Built<TwinProcessRef, TwinProcessRefBuilder> {
  /// device_key of the device the process ran on, or the hostname the device was observed under
  @BuiltValueField(wireName: r'device')
  String get device;

  @BuiltValueField(wireName: r'name')
  String get name;

  @BuiltValueField(wireName: r'pid')
  int get pid;

  TwinProcessRef._();

  factory TwinProcessRef([void updates(TwinProcessRefBuilder b)]) = _$TwinProcessRef;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinProcessRefBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinProcessRef> get serializer => _$TwinProcessRefSerializer();
}

class _$TwinProcessRefSerializer implements PrimitiveSerializer<TwinProcessRef> {
  @override
  final Iterable<Type> types = const [TwinProcessRef, _$TwinProcessRef];

  @override
  final String wireName = r'TwinProcessRef';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinProcessRef object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'device';
    yield serializers.serialize(
      object.device,
      specifiedType: const FullType(String),
    );
    yield r'name';
    yield serializers.serialize(
      object.name,
      specifiedType: const FullType(String),
    );
    yield r'pid';
    yield serializers.serialize(
      object.pid,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinProcessRef object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinProcessRefBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'device':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.device = valueDes;
          break;
        case r'name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.name = valueDes;
          break;
        case r'pid':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pid = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinProcessRef deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinProcessRefBuilder();
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


