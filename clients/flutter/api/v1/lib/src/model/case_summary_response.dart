//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_summary_response.g.dart';

/// CaseSummaryResponse
///
/// Properties:
/// * [byPriority] 
/// * [byStatus] 
/// * [total] 
@BuiltValue()
abstract class CaseSummaryResponse implements Built<CaseSummaryResponse, CaseSummaryResponseBuilder> {
  @BuiltValueField(wireName: r'by_priority')
  BuiltMap<String, int> get byPriority;

  @BuiltValueField(wireName: r'by_status')
  BuiltMap<String, int> get byStatus;

  @BuiltValueField(wireName: r'total')
  int get total;

  CaseSummaryResponse._();

  factory CaseSummaryResponse([void updates(CaseSummaryResponseBuilder b)]) = _$CaseSummaryResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseSummaryResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseSummaryResponse> get serializer => _$CaseSummaryResponseSerializer();
}

class _$CaseSummaryResponseSerializer implements PrimitiveSerializer<CaseSummaryResponse> {
  @override
  final Iterable<Type> types = const [CaseSummaryResponse, _$CaseSummaryResponse];

  @override
  final String wireName = r'CaseSummaryResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'by_priority';
    yield serializers.serialize(
      object.byPriority,
      specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
    );
    yield r'by_status';
    yield serializers.serialize(
      object.byStatus,
      specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
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
    CaseSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseSummaryResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'by_priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>;
          result.byPriority.replace(valueDes);
          break;
        case r'by_status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>;
          result.byStatus.replace(valueDes);
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
  CaseSummaryResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseSummaryResponseBuilder();
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


