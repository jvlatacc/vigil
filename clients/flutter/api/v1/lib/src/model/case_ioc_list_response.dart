//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/case_ioc_schema.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_ioc_list_response.g.dart';

/// CaseIOCListResponse
///
/// Properties:
/// * [iocs] 
@BuiltValue()
abstract class CaseIOCListResponse implements Built<CaseIOCListResponse, CaseIOCListResponseBuilder> {
  @BuiltValueField(wireName: r'iocs')
  BuiltList<CaseIOCSchema> get iocs;

  CaseIOCListResponse._();

  factory CaseIOCListResponse([void updates(CaseIOCListResponseBuilder b)]) = _$CaseIOCListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseIOCListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseIOCListResponse> get serializer => _$CaseIOCListResponseSerializer();
}

class _$CaseIOCListResponseSerializer implements PrimitiveSerializer<CaseIOCListResponse> {
  @override
  final Iterable<Type> types = const [CaseIOCListResponse, _$CaseIOCListResponse];

  @override
  final String wireName = r'CaseIOCListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseIOCListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'iocs';
    yield serializers.serialize(
      object.iocs,
      specifiedType: const FullType(BuiltList, [FullType(CaseIOCSchema)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseIOCListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseIOCListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'iocs':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(CaseIOCSchema)]),
          ) as BuiltList<CaseIOCSchema>;
          result.iocs.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseIOCListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseIOCListResponseBuilder();
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


