//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'breaker_status_response.g.dart';

/// Frozen shape of one breaker observation (mirrors ``BreakerStatus``).
///
/// Properties:
/// * [counters] 
/// * [escalationFired] 
/// * [openedAt] 
/// * [reason] 
/// * [rule] 
/// * [secondsLeft] 
/// * [state] 
/// * [store] 
@BuiltValue()
abstract class BreakerStatusResponse implements Built<BreakerStatusResponse, BreakerStatusResponseBuilder> {
  @BuiltValueField(wireName: r'counters')
  BuiltMap<String, BuiltMap<String, num>>? get counters;

  @BuiltValueField(wireName: r'escalation_fired')
  bool? get escalationFired;

  @BuiltValueField(wireName: r'opened_at')
  num? get openedAt;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  @BuiltValueField(wireName: r'rule')
  String? get rule;

  @BuiltValueField(wireName: r'seconds_left')
  int? get secondsLeft;

  @BuiltValueField(wireName: r'state')
  String get state;

  @BuiltValueField(wireName: r'store')
  String? get store;

  BreakerStatusResponse._();

  factory BreakerStatusResponse([void updates(BreakerStatusResponseBuilder b)]) = _$BreakerStatusResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BreakerStatusResponseBuilder b) => b
      ..escalationFired = false
      ..store = 'redis';

  @BuiltValueSerializer(custom: true)
  static Serializer<BreakerStatusResponse> get serializer => _$BreakerStatusResponseSerializer();
}

class _$BreakerStatusResponseSerializer implements PrimitiveSerializer<BreakerStatusResponse> {
  @override
  final Iterable<Type> types = const [BreakerStatusResponse, _$BreakerStatusResponse];

  @override
  final String wireName = r'BreakerStatusResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BreakerStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.counters != null) {
      yield r'counters';
      yield serializers.serialize(
        object.counters,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(BuiltMap, [FullType(String), FullType(num)])]),
      );
    }
    if (object.escalationFired != null) {
      yield r'escalation_fired';
      yield serializers.serialize(
        object.escalationFired,
        specifiedType: const FullType(bool),
      );
    }
    if (object.openedAt != null) {
      yield r'opened_at';
      yield serializers.serialize(
        object.openedAt,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.reason != null) {
      yield r'reason';
      yield serializers.serialize(
        object.reason,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rule != null) {
      yield r'rule';
      yield serializers.serialize(
        object.rule,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.secondsLeft != null) {
      yield r'seconds_left';
      yield serializers.serialize(
        object.secondsLeft,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'state';
    yield serializers.serialize(
      object.state,
      specifiedType: const FullType(String),
    );
    if (object.store != null) {
      yield r'store';
      yield serializers.serialize(
        object.store,
        specifiedType: const FullType(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    BreakerStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required BreakerStatusResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'counters':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(BuiltMap, [FullType(String), FullType(num)])]),
          ) as BuiltMap<String, BuiltMap<String, num>>?;
          if (valueDes == null) continue;
          result.counters.replace(valueDes);
          break;
        case r'escalation_fired':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.escalationFired = valueDes;
          break;
        case r'opened_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.openedAt = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reason = valueDes;
          break;
        case r'rule':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rule = valueDes;
          break;
        case r'seconds_left':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.secondsLeft = valueDes;
          break;
        case r'state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.state = valueDes;
          break;
        case r'store':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.store = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BreakerStatusResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BreakerStatusResponseBuilder();
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


