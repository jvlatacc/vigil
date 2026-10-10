//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/case_evidence_schema.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_evidence_list_response.g.dart';

/// CaseEvidenceListResponse
///
/// Properties:
/// * [evidence] 
@BuiltValue()
abstract class CaseEvidenceListResponse implements Built<CaseEvidenceListResponse, CaseEvidenceListResponseBuilder> {
  @BuiltValueField(wireName: r'evidence')
  BuiltList<CaseEvidenceSchema> get evidence;

  CaseEvidenceListResponse._();

  factory CaseEvidenceListResponse([void updates(CaseEvidenceListResponseBuilder b)]) = _$CaseEvidenceListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseEvidenceListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseEvidenceListResponse> get serializer => _$CaseEvidenceListResponseSerializer();
}

class _$CaseEvidenceListResponseSerializer implements PrimitiveSerializer<CaseEvidenceListResponse> {
  @override
  final Iterable<Type> types = const [CaseEvidenceListResponse, _$CaseEvidenceListResponse];

  @override
  final String wireName = r'CaseEvidenceListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseEvidenceListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'evidence';
    yield serializers.serialize(
      object.evidence,
      specifiedType: const FullType(BuiltList, [FullType(CaseEvidenceSchema)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseEvidenceListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseEvidenceListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'evidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(CaseEvidenceSchema)]),
          ) as BuiltList<CaseEvidenceSchema>;
          result.evidence.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseEvidenceListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseEvidenceListResponseBuilder();
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


