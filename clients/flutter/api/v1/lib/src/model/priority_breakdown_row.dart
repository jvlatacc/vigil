//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'priority_breakdown_row.g.dart';

/// PriorityBreakdownRow
///
/// Properties:
/// * [closedCount] 
/// * [count] 
/// * [priority] 
@BuiltValue()
abstract class PriorityBreakdownRow implements Built<PriorityBreakdownRow, PriorityBreakdownRowBuilder> {
  @BuiltValueField(wireName: r'closed_count')
  int get closedCount;

  @BuiltValueField(wireName: r'count')
  int get count;

  @BuiltValueField(wireName: r'priority')
  String get priority;

  PriorityBreakdownRow._();

  factory PriorityBreakdownRow([void updates(PriorityBreakdownRowBuilder b)]) = _$PriorityBreakdownRow;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PriorityBreakdownRowBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PriorityBreakdownRow> get serializer => _$PriorityBreakdownRowSerializer();
}

class _$PriorityBreakdownRowSerializer implements PrimitiveSerializer<PriorityBreakdownRow> {
  @override
  final Iterable<Type> types = const [PriorityBreakdownRow, _$PriorityBreakdownRow];

  @override
  final String wireName = r'PriorityBreakdownRow';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PriorityBreakdownRow object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'closed_count';
    yield serializers.serialize(
      object.closedCount,
      specifiedType: const FullType(int),
    );
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
    yield r'priority';
    yield serializers.serialize(
      object.priority,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PriorityBreakdownRow object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required PriorityBreakdownRowBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'closed_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.closedCount = valueDes;
          break;
        case r'count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.count = valueDes;
          break;
        case r'priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.priority = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PriorityBreakdownRow deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PriorityBreakdownRowBuilder();
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


