//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_closure_info_schema.g.dart';

/// CaseClosureInfo.
///
/// Properties:
/// * [caseId] 
/// * [closedAt] 
/// * [closedBy] 
/// * [closureCategory] 
/// * [closureNotes] 
/// * [contributingFactors] 
/// * [executiveSummary] 
/// * [falsePositiveReason] 
/// * [lessonsLearned] 
/// * [recommendations] 
/// * [recurrencePrevention] 
/// * [rootCause] 
@BuiltValue()
abstract class CaseClosureInfoSchema implements Built<CaseClosureInfoSchema, CaseClosureInfoSchemaBuilder> {
  @BuiltValueField(wireName: r'case_id')
  String? get caseId;

  @BuiltValueField(wireName: r'closed_at')
  String? get closedAt;

  @BuiltValueField(wireName: r'closed_by')
  String? get closedBy;

  @BuiltValueField(wireName: r'closure_category')
  String? get closureCategory;

  @BuiltValueField(wireName: r'closure_notes')
  String? get closureNotes;

  @BuiltValueField(wireName: r'contributing_factors')
  BuiltList<String>? get contributingFactors;

  @BuiltValueField(wireName: r'executive_summary')
  String? get executiveSummary;

  @BuiltValueField(wireName: r'false_positive_reason')
  String? get falsePositiveReason;

  @BuiltValueField(wireName: r'lessons_learned')
  String? get lessonsLearned;

  @BuiltValueField(wireName: r'recommendations')
  String? get recommendations;

  @BuiltValueField(wireName: r'recurrence_prevention')
  String? get recurrencePrevention;

  @BuiltValueField(wireName: r'root_cause')
  String? get rootCause;

  CaseClosureInfoSchema._();

  factory CaseClosureInfoSchema([void updates(CaseClosureInfoSchemaBuilder b)]) = _$CaseClosureInfoSchema;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseClosureInfoSchemaBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseClosureInfoSchema> get serializer => _$CaseClosureInfoSchemaSerializer();
}

class _$CaseClosureInfoSchemaSerializer implements PrimitiveSerializer<CaseClosureInfoSchema> {
  @override
  final Iterable<Type> types = const [CaseClosureInfoSchema, _$CaseClosureInfoSchema];

  @override
  final String wireName = r'CaseClosureInfoSchema';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseClosureInfoSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.caseId != null) {
      yield r'case_id';
      yield serializers.serialize(
        object.caseId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.closedAt != null) {
      yield r'closed_at';
      yield serializers.serialize(
        object.closedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.closedBy != null) {
      yield r'closed_by';
      yield serializers.serialize(
        object.closedBy,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.closureCategory != null) {
      yield r'closure_category';
      yield serializers.serialize(
        object.closureCategory,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.closureNotes != null) {
      yield r'closure_notes';
      yield serializers.serialize(
        object.closureNotes,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.contributingFactors != null) {
      yield r'contributing_factors';
      yield serializers.serialize(
        object.contributingFactors,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.executiveSummary != null) {
      yield r'executive_summary';
      yield serializers.serialize(
        object.executiveSummary,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.falsePositiveReason != null) {
      yield r'false_positive_reason';
      yield serializers.serialize(
        object.falsePositiveReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.lessonsLearned != null) {
      yield r'lessons_learned';
      yield serializers.serialize(
        object.lessonsLearned,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.recommendations != null) {
      yield r'recommendations';
      yield serializers.serialize(
        object.recommendations,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.recurrencePrevention != null) {
      yield r'recurrence_prevention';
      yield serializers.serialize(
        object.recurrencePrevention,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rootCause != null) {
      yield r'root_cause';
      yield serializers.serialize(
        object.rootCause,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseClosureInfoSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseClosureInfoSchemaBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'case_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.caseId = valueDes;
          break;
        case r'closed_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closedAt = valueDes;
          break;
        case r'closed_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closedBy = valueDes;
          break;
        case r'closure_category':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closureCategory = valueDes;
          break;
        case r'closure_notes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closureNotes = valueDes;
          break;
        case r'contributing_factors':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.contributingFactors.replace(valueDes);
          break;
        case r'executive_summary':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.executiveSummary = valueDes;
          break;
        case r'false_positive_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.falsePositiveReason = valueDes;
          break;
        case r'lessons_learned':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.lessonsLearned = valueDes;
          break;
        case r'recommendations':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.recommendations = valueDes;
          break;
        case r'recurrence_prevention':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.recurrencePrevention = valueDes;
          break;
        case r'root_cause':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rootCause = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseClosureInfoSchema deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseClosureInfoSchemaBuilder();
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


