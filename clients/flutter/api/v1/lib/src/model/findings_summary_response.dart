//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'findings_summary_response.g.dart';

/// FindingsSummaryResponse
///
/// Properties:
/// * [byDataSource] 
/// * [bySeverity] 
/// * [total] 
@BuiltValue()
abstract class FindingsSummaryResponse implements Built<FindingsSummaryResponse, FindingsSummaryResponseBuilder> {
  @BuiltValueField(wireName: r'by_data_source')
  BuiltMap<String, int>? get byDataSource;

  @BuiltValueField(wireName: r'by_severity')
  BuiltMap<String, int>? get bySeverity;

  @BuiltValueField(wireName: r'total')
  int get total;

  FindingsSummaryResponse._();

  factory FindingsSummaryResponse([void updates(FindingsSummaryResponseBuilder b)]) = _$FindingsSummaryResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(FindingsSummaryResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<FindingsSummaryResponse> get serializer => _$FindingsSummaryResponseSerializer();
}

class _$FindingsSummaryResponseSerializer implements PrimitiveSerializer<FindingsSummaryResponse> {
  @override
  final Iterable<Type> types = const [FindingsSummaryResponse, _$FindingsSummaryResponse];

  @override
  final String wireName = r'FindingsSummaryResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    FindingsSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.byDataSource != null) {
      yield r'by_data_source';
      yield serializers.serialize(
        object.byDataSource,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
      );
    }
    if (object.bySeverity != null) {
      yield r'by_severity';
      yield serializers.serialize(
        object.bySeverity,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
      );
    }
    yield r'total';
    yield serializers.serialize(
      object.total,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    FindingsSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required FindingsSummaryResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'by_data_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>?;
          if (valueDes == null) continue;
          result.byDataSource.replace(valueDes);
          break;
        case r'by_severity':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>?;
          if (valueDes == null) continue;
          result.bySeverity.replace(valueDes);
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
  FindingsSummaryResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = FindingsSummaryResponseBuilder();
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


