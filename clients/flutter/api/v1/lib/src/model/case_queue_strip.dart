//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_queue_strip.g.dart';

/// Counts for the queue strip. Independent of the page filters.
///
/// Properties:
/// * [agentClosureShare] 
/// * [byState] 
/// * [closedToday] 
/// * [needsYou] 
/// * [slaAtRisk] 
@BuiltValue()
abstract class CaseQueueStrip implements Built<CaseQueueStrip, CaseQueueStripBuilder> {
  @BuiltValueField(wireName: r'agent_closure_share')
  num get agentClosureShare;

  @BuiltValueField(wireName: r'by_state')
  BuiltMap<String, int> get byState;

  @BuiltValueField(wireName: r'closed_today')
  int get closedToday;

  @BuiltValueField(wireName: r'needs_you')
  int get needsYou;

  @BuiltValueField(wireName: r'sla_at_risk')
  int get slaAtRisk;

  CaseQueueStrip._();

  factory CaseQueueStrip([void updates(CaseQueueStripBuilder b)]) = _$CaseQueueStrip;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseQueueStripBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseQueueStrip> get serializer => _$CaseQueueStripSerializer();
}

class _$CaseQueueStripSerializer implements PrimitiveSerializer<CaseQueueStrip> {
  @override
  final Iterable<Type> types = const [CaseQueueStrip, _$CaseQueueStrip];

  @override
  final String wireName = r'CaseQueueStrip';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseQueueStrip object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'agent_closure_share';
    yield serializers.serialize(
      object.agentClosureShare,
      specifiedType: const FullType(num),
    );
    yield r'by_state';
    yield serializers.serialize(
      object.byState,
      specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
    );
    yield r'closed_today';
    yield serializers.serialize(
      object.closedToday,
      specifiedType: const FullType(int),
    );
    yield r'needs_you';
    yield serializers.serialize(
      object.needsYou,
      specifiedType: const FullType(int),
    );
    yield r'sla_at_risk';
    yield serializers.serialize(
      object.slaAtRisk,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseQueueStrip object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseQueueStripBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'agent_closure_share':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.agentClosureShare = valueDes;
          break;
        case r'by_state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>;
          result.byState.replace(valueDes);
          break;
        case r'closed_today':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.closedToday = valueDes;
          break;
        case r'needs_you':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.needsYou = valueDes;
          break;
        case r'sla_at_risk':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.slaAtRisk = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseQueueStrip deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseQueueStripBuilder();
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


