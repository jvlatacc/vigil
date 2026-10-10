//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_metrics_summary_response.g.dart';

/// CaseMetricsSummaryResponse
///
/// Properties:
/// * [criticalCases] 
/// * [openCases] 
/// * [priorityBreakdown] 
/// * [resolvedCases] 
/// * [statusBreakdown] 
/// * [totalCases] 
@BuiltValue()
abstract class CaseMetricsSummaryResponse implements Built<CaseMetricsSummaryResponse, CaseMetricsSummaryResponseBuilder> {
  @BuiltValueField(wireName: r'critical_cases')
  int get criticalCases;

  @BuiltValueField(wireName: r'open_cases')
  int get openCases;

  @BuiltValueField(wireName: r'priority_breakdown')
  BuiltMap<String, int>? get priorityBreakdown;

  @BuiltValueField(wireName: r'resolved_cases')
  int get resolvedCases;

  @BuiltValueField(wireName: r'status_breakdown')
  BuiltMap<String, int>? get statusBreakdown;

  @BuiltValueField(wireName: r'total_cases')
  int get totalCases;

  CaseMetricsSummaryResponse._();

  factory CaseMetricsSummaryResponse([void updates(CaseMetricsSummaryResponseBuilder b)]) = _$CaseMetricsSummaryResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseMetricsSummaryResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseMetricsSummaryResponse> get serializer => _$CaseMetricsSummaryResponseSerializer();
}

class _$CaseMetricsSummaryResponseSerializer implements PrimitiveSerializer<CaseMetricsSummaryResponse> {
  @override
  final Iterable<Type> types = const [CaseMetricsSummaryResponse, _$CaseMetricsSummaryResponse];

  @override
  final String wireName = r'CaseMetricsSummaryResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseMetricsSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'critical_cases';
    yield serializers.serialize(
      object.criticalCases,
      specifiedType: const FullType(int),
    );
    yield r'open_cases';
    yield serializers.serialize(
      object.openCases,
      specifiedType: const FullType(int),
    );
    if (object.priorityBreakdown != null) {
      yield r'priority_breakdown';
      yield serializers.serialize(
        object.priorityBreakdown,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
      );
    }
    yield r'resolved_cases';
    yield serializers.serialize(
      object.resolvedCases,
      specifiedType: const FullType(int),
    );
    if (object.statusBreakdown != null) {
      yield r'status_breakdown';
      yield serializers.serialize(
        object.statusBreakdown,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(int)]),
      );
    }
    yield r'total_cases';
    yield serializers.serialize(
      object.totalCases,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseMetricsSummaryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseMetricsSummaryResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'critical_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.criticalCases = valueDes;
          break;
        case r'open_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.openCases = valueDes;
          break;
        case r'priority_breakdown':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>?;
          if (valueDes == null) continue;
          result.priorityBreakdown.replace(valueDes);
          break;
        case r'resolved_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.resolvedCases = valueDes;
          break;
        case r'status_breakdown':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(int)]),
          ) as BuiltMap<String, int>?;
          if (valueDes == null) continue;
          result.statusBreakdown.replace(valueDes);
          break;
        case r'total_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.totalCases = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseMetricsSummaryResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseMetricsSummaryResponseBuilder();
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


