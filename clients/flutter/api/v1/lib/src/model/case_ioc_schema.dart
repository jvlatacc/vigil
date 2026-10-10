//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:one_of/any_of.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_ioc_schema.g.dart';

/// CaseIOC.
///
/// Properties:
/// * [caseId] 
/// * [confidence] 
/// * [context] 
/// * [createdAt] 
/// * [enrichmentData] 
/// * [firstSeen] 
/// * [iocId] 
/// * [iocType] 
/// * [isActive] 
/// * [isFalsePositive] 
/// * [lastSeen] 
/// * [reputationScore] 
/// * [source_] 
/// * [tags] 
/// * [threatLevel] 
/// * [updatedAt] 
/// * [value] 
@BuiltValue()
abstract class CaseIOCSchema implements Built<CaseIOCSchema, CaseIOCSchemaBuilder> {
  @BuiltValueField(wireName: r'case_id')
  String? get caseId;

  @BuiltValueField(wireName: r'confidence')
  num? get confidence;

  @BuiltValueField(wireName: r'context')
  String? get context;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'enrichment_data')
  AnyOf? get enrichmentData;

  @BuiltValueField(wireName: r'first_seen')
  String? get firstSeen;

  @BuiltValueField(wireName: r'ioc_id')
  int? get iocId;

  @BuiltValueField(wireName: r'ioc_type')
  String? get iocType;

  @BuiltValueField(wireName: r'is_active')
  bool? get isActive;

  @BuiltValueField(wireName: r'is_false_positive')
  bool? get isFalsePositive;

  @BuiltValueField(wireName: r'last_seen')
  String? get lastSeen;

  @BuiltValueField(wireName: r'reputation_score')
  num? get reputationScore;

  @BuiltValueField(wireName: r'source')
  String? get source_;

  @BuiltValueField(wireName: r'tags')
  BuiltList<String>? get tags;

  @BuiltValueField(wireName: r'threat_level')
  String? get threatLevel;

  @BuiltValueField(wireName: r'updated_at')
  String? get updatedAt;

  @BuiltValueField(wireName: r'value')
  String? get value;

  CaseIOCSchema._();

  factory CaseIOCSchema([void updates(CaseIOCSchemaBuilder b)]) = _$CaseIOCSchema;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseIOCSchemaBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseIOCSchema> get serializer => _$CaseIOCSchemaSerializer();
}

class _$CaseIOCSchemaSerializer implements PrimitiveSerializer<CaseIOCSchema> {
  @override
  final Iterable<Type> types = const [CaseIOCSchema, _$CaseIOCSchema];

  @override
  final String wireName = r'CaseIOCSchema';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseIOCSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.caseId != null) {
      yield r'case_id';
      yield serializers.serialize(
        object.caseId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.confidence != null) {
      yield r'confidence';
      yield serializers.serialize(
        object.confidence,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.context != null) {
      yield r'context';
      yield serializers.serialize(
        object.context,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.createdAt != null) {
      yield r'created_at';
      yield serializers.serialize(
        object.createdAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.enrichmentData != null) {
      yield r'enrichment_data';
      yield serializers.serialize(
        object.enrichmentData,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.firstSeen != null) {
      yield r'first_seen';
      yield serializers.serialize(
        object.firstSeen,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.iocId != null) {
      yield r'ioc_id';
      yield serializers.serialize(
        object.iocId,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.iocType != null) {
      yield r'ioc_type';
      yield serializers.serialize(
        object.iocType,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.isActive != null) {
      yield r'is_active';
      yield serializers.serialize(
        object.isActive,
        specifiedType: const FullType.nullable(bool),
      );
    }
    if (object.isFalsePositive != null) {
      yield r'is_false_positive';
      yield serializers.serialize(
        object.isFalsePositive,
        specifiedType: const FullType.nullable(bool),
      );
    }
    if (object.lastSeen != null) {
      yield r'last_seen';
      yield serializers.serialize(
        object.lastSeen,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.reputationScore != null) {
      yield r'reputation_score';
      yield serializers.serialize(
        object.reputationScore,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.source_ != null) {
      yield r'source';
      yield serializers.serialize(
        object.source_,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.tags != null) {
      yield r'tags';
      yield serializers.serialize(
        object.tags,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.threatLevel != null) {
      yield r'threat_level';
      yield serializers.serialize(
        object.threatLevel,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.updatedAt != null) {
      yield r'updated_at';
      yield serializers.serialize(
        object.updatedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.value != null) {
      yield r'value';
      yield serializers.serialize(
        object.value,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseIOCSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseIOCSchemaBuilder result,
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
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.confidence = valueDes;
          break;
        case r'context':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.context = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'enrichment_data':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.enrichmentData = valueDes;
          break;
        case r'first_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.firstSeen = valueDes;
          break;
        case r'ioc_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.iocId = valueDes;
          break;
        case r'ioc_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.iocType = valueDes;
          break;
        case r'is_active':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.isActive = valueDes;
          break;
        case r'is_false_positive':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.isFalsePositive = valueDes;
          break;
        case r'last_seen':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.lastSeen = valueDes;
          break;
        case r'reputation_score':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.reputationScore = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.source_ = valueDes;
          break;
        case r'tags':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.tags.replace(valueDes);
          break;
        case r'threat_level':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.threatLevel = valueDes;
          break;
        case r'updated_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.updatedAt = valueDes;
          break;
        case r'value':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.value = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseIOCSchema deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseIOCSchemaBuilder();
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


