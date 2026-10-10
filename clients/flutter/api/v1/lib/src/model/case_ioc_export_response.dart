//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_ioc_export_response.g.dart';

/// CaseIOCExportResponse
///
/// Properties:
/// * [content] 
/// * [format] 
@BuiltValue()
abstract class CaseIOCExportResponse implements Built<CaseIOCExportResponse, CaseIOCExportResponseBuilder> {
  @BuiltValueField(wireName: r'content')
  JsonObject? get content;

  @BuiltValueField(wireName: r'format')
  String get format;

  CaseIOCExportResponse._();

  factory CaseIOCExportResponse([void updates(CaseIOCExportResponseBuilder b)]) = _$CaseIOCExportResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseIOCExportResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseIOCExportResponse> get serializer => _$CaseIOCExportResponseSerializer();
}

class _$CaseIOCExportResponseSerializer implements PrimitiveSerializer<CaseIOCExportResponse> {
  @override
  final Iterable<Type> types = const [CaseIOCExportResponse, _$CaseIOCExportResponse];

  @override
  final String wireName = r'CaseIOCExportResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseIOCExportResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'content';
    yield object.content == null ? null : serializers.serialize(
      object.content,
      specifiedType: const FullType.nullable(JsonObject),
    );
    yield r'format';
    yield serializers.serialize(
      object.format,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseIOCExportResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseIOCExportResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'content':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(JsonObject),
          ) as JsonObject?;
          if (valueDes == null) continue;
          result.content = valueDes;
          break;
        case r'format':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.format = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseIOCExportResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseIOCExportResponseBuilder();
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


