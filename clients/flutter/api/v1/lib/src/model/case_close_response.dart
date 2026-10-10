//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/case_closure_info_schema.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_close_response.g.dart';

/// CaseCloseResponse
///
/// Properties:
/// * [closure] 
/// * [success] 
@BuiltValue()
abstract class CaseCloseResponse implements Built<CaseCloseResponse, CaseCloseResponseBuilder> {
  @BuiltValueField(wireName: r'closure')
  CaseClosureInfoSchema get closure;

  @BuiltValueField(wireName: r'success')
  bool get success;

  CaseCloseResponse._();

  factory CaseCloseResponse([void updates(CaseCloseResponseBuilder b)]) = _$CaseCloseResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseCloseResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseCloseResponse> get serializer => _$CaseCloseResponseSerializer();
}

class _$CaseCloseResponseSerializer implements PrimitiveSerializer<CaseCloseResponse> {
  @override
  final Iterable<Type> types = const [CaseCloseResponse, _$CaseCloseResponse];

  @override
  final String wireName = r'CaseCloseResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseCloseResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'closure';
    yield serializers.serialize(
      object.closure,
      specifiedType: const FullType(CaseClosureInfoSchema),
    );
    yield r'success';
    yield serializers.serialize(
      object.success,
      specifiedType: const FullType(bool),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseCloseResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseCloseResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'closure':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CaseClosureInfoSchema),
          ) as CaseClosureInfoSchema;
          result.closure.replace(valueDes);
          break;
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
  CaseCloseResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseCloseResponseBuilder();
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


