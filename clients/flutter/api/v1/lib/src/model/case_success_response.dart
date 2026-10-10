//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_success_response.g.dart';

/// Mutation that only reports whether it landed.
///
/// Properties:
/// * [success] 
@BuiltValue()
abstract class CaseSuccessResponse implements Built<CaseSuccessResponse, CaseSuccessResponseBuilder> {
  @BuiltValueField(wireName: r'success')
  bool get success;

  CaseSuccessResponse._();

  factory CaseSuccessResponse([void updates(CaseSuccessResponseBuilder b)]) = _$CaseSuccessResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseSuccessResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseSuccessResponse> get serializer => _$CaseSuccessResponseSerializer();
}

class _$CaseSuccessResponseSerializer implements PrimitiveSerializer<CaseSuccessResponse> {
  @override
  final Iterable<Type> types = const [CaseSuccessResponse, _$CaseSuccessResponse];

  @override
  final String wireName = r'CaseSuccessResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseSuccessResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'success';
    yield serializers.serialize(
      object.success,
      specifiedType: const FullType(bool),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseSuccessResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseSuccessResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'success':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.success = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseSuccessResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseSuccessResponseBuilder();
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


