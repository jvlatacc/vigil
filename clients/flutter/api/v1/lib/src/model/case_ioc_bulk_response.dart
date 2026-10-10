//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_ioc_bulk_response.g.dart';

/// CaseIOCBulkResponse
///
/// Properties:
/// * [added] 
@BuiltValue()
abstract class CaseIOCBulkResponse implements Built<CaseIOCBulkResponse, CaseIOCBulkResponseBuilder> {
  @BuiltValueField(wireName: r'added')
  int get added;

  CaseIOCBulkResponse._();

  factory CaseIOCBulkResponse([void updates(CaseIOCBulkResponseBuilder b)]) = _$CaseIOCBulkResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseIOCBulkResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseIOCBulkResponse> get serializer => _$CaseIOCBulkResponseSerializer();
}

class _$CaseIOCBulkResponseSerializer implements PrimitiveSerializer<CaseIOCBulkResponse> {
  @override
  final Iterable<Type> types = const [CaseIOCBulkResponse, _$CaseIOCBulkResponse];

  @override
  final String wireName = r'CaseIOCBulkResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseIOCBulkResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'added';
    yield serializers.serialize(
      object.added,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseIOCBulkResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseIOCBulkResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'added':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.added = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseIOCBulkResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseIOCBulkResponseBuilder();
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


