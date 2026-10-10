//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'status_breakdown_row.g.dart';

/// StatusBreakdownRow
///
/// Properties:
/// * [count] 
/// * [status] 
@BuiltValue()
abstract class StatusBreakdownRow implements Built<StatusBreakdownRow, StatusBreakdownRowBuilder> {
  @BuiltValueField(wireName: r'count')
  int get count;

  @BuiltValueField(wireName: r'status')
  String get status;

  StatusBreakdownRow._();

  factory StatusBreakdownRow([void updates(StatusBreakdownRowBuilder b)]) = _$StatusBreakdownRow;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(StatusBreakdownRowBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<StatusBreakdownRow> get serializer => _$StatusBreakdownRowSerializer();
}

class _$StatusBreakdownRowSerializer implements PrimitiveSerializer<StatusBreakdownRow> {
  @override
  final Iterable<Type> types = const [StatusBreakdownRow, _$StatusBreakdownRow];

  @override
  final String wireName = r'StatusBreakdownRow';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    StatusBreakdownRow object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    StatusBreakdownRow object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required StatusBreakdownRowBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.count = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.status = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  StatusBreakdownRow deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = StatusBreakdownRowBuilder();
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


