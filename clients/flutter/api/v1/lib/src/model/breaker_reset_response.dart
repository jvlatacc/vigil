//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/breaker_status_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'breaker_reset_response.g.dart';

/// BreakerResetResponse
///
/// Properties:
/// * [after] 
/// * [before] 
/// * [rule] 
@BuiltValue()
abstract class BreakerResetResponse implements Built<BreakerResetResponse, BreakerResetResponseBuilder> {
  @BuiltValueField(wireName: r'after')
  BreakerStatusResponse get after;

  @BuiltValueField(wireName: r'before')
  BreakerStatusResponse get before;

  @BuiltValueField(wireName: r'rule')
  String? get rule;

  BreakerResetResponse._();

  factory BreakerResetResponse([void updates(BreakerResetResponseBuilder b)]) = _$BreakerResetResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BreakerResetResponseBuilder b) => b
      ..rule = 'response.breaker_reset=manual';

  @BuiltValueSerializer(custom: true)
  static Serializer<BreakerResetResponse> get serializer => _$BreakerResetResponseSerializer();
}

class _$BreakerResetResponseSerializer implements PrimitiveSerializer<BreakerResetResponse> {
  @override
  final Iterable<Type> types = const [BreakerResetResponse, _$BreakerResetResponse];

  @override
  final String wireName = r'BreakerResetResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BreakerResetResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'after';
    yield serializers.serialize(
      object.after,
      specifiedType: const FullType(BreakerStatusResponse),
    );
    yield r'before';
    yield serializers.serialize(
      object.before,
      specifiedType: const FullType(BreakerStatusResponse),
    );
    if (object.rule != null) {
      yield r'rule';
      yield serializers.serialize(
        object.rule,
        specifiedType: const FullType(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    BreakerResetResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required BreakerResetResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'after':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BreakerStatusResponse),
          ) as BreakerStatusResponse;
          result.after.replace(valueDes);
          break;
        case r'before':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BreakerStatusResponse),
          ) as BreakerStatusResponse;
          result.before.replace(valueDes);
          break;
        case r'rule':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rule = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BreakerResetResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BreakerResetResponseBuilder();
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


