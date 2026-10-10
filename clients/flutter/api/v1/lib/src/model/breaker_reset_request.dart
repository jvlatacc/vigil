//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'breaker_reset_request.g.dart';

/// BreakerResetRequest
///
/// Properties:
/// * [reason] - Why the breaker is being manually reset; recorded in the config audit log.
@BuiltValue()
abstract class BreakerResetRequest implements Built<BreakerResetRequest, BreakerResetRequestBuilder> {
  /// Why the breaker is being manually reset; recorded in the config audit log.
  @BuiltValueField(wireName: r'reason')
  String get reason;

  BreakerResetRequest._();

  factory BreakerResetRequest([void updates(BreakerResetRequestBuilder b)]) = _$BreakerResetRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BreakerResetRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<BreakerResetRequest> get serializer => _$BreakerResetRequestSerializer();
}

class _$BreakerResetRequestSerializer implements PrimitiveSerializer<BreakerResetRequest> {
  @override
  final Iterable<Type> types = const [BreakerResetRequest, _$BreakerResetRequest];

  @override
  final String wireName = r'BreakerResetRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BreakerResetRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'reason';
    yield serializers.serialize(
      object.reason,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    BreakerResetRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required BreakerResetRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.reason = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BreakerResetRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BreakerResetRequestBuilder();
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


