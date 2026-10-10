//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/case_queue_strip.dart';
import 'package:vigil_api_v1/src/model/case_queue_item.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_list_response.g.dart';

/// CaseListResponse
///
/// Properties:
/// * [cases] 
/// * [hasMore] 
/// * [limit] 
/// * [offset] 
/// * [strip] 
/// * [total] 
@BuiltValue()
abstract class CaseListResponse implements Built<CaseListResponse, CaseListResponseBuilder> {
  @BuiltValueField(wireName: r'cases')
  BuiltList<CaseQueueItem> get cases;

  @BuiltValueField(wireName: r'has_more')
  bool get hasMore;

  @BuiltValueField(wireName: r'limit')
  int get limit;

  @BuiltValueField(wireName: r'offset')
  int get offset;

  @BuiltValueField(wireName: r'strip')
  CaseQueueStrip get strip;

  @BuiltValueField(wireName: r'total')
  int get total;

  CaseListResponse._();

  factory CaseListResponse([void updates(CaseListResponseBuilder b)]) = _$CaseListResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseListResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseListResponse> get serializer => _$CaseListResponseSerializer();
}

class _$CaseListResponseSerializer implements PrimitiveSerializer<CaseListResponse> {
  @override
  final Iterable<Type> types = const [CaseListResponse, _$CaseListResponse];

  @override
  final String wireName = r'CaseListResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'cases';
    yield serializers.serialize(
      object.cases,
      specifiedType: const FullType(BuiltList, [FullType(CaseQueueItem)]),
    );
    yield r'has_more';
    yield serializers.serialize(
      object.hasMore,
      specifiedType: const FullType(bool),
    );
    yield r'limit';
    yield serializers.serialize(
      object.limit,
      specifiedType: const FullType(int),
    );
    yield r'offset';
    yield serializers.serialize(
      object.offset,
      specifiedType: const FullType(int),
    );
    yield r'strip';
    yield serializers.serialize(
      object.strip,
      specifiedType: const FullType(CaseQueueStrip),
    );
    yield r'total';
    yield serializers.serialize(
      object.total,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseListResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseListResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(CaseQueueItem)]),
          ) as BuiltList<CaseQueueItem>;
          result.cases.replace(valueDes);
          break;
        case r'has_more':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.hasMore = valueDes;
          break;
        case r'limit':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.limit = valueDes;
          break;
        case r'offset':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.offset = valueDes;
          break;
        case r'strip':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CaseQueueStrip),
          ) as CaseQueueStrip;
          result.strip.replace(valueDes);
          break;
        case r'total':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.total = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseListResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseListResponseBuilder();
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


