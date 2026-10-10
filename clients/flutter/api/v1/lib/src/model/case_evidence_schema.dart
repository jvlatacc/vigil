//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:one_of/any_of.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_evidence_schema.g.dart';

/// CaseEvidence.
///
/// Properties:
/// * [analysisResults] 
/// * [caseId] 
/// * [chainOfCustody] 
/// * [collectedAt] 
/// * [collectedBy] 
/// * [createdAt] 
/// * [description] 
/// * [evidenceId] 
/// * [evidenceType] 
/// * [fileHashMd5] 
/// * [fileHashSha256] 
/// * [filePath] 
/// * [fileSize] 
/// * [name] 
/// * [source_] 
/// * [tags] 
/// * [updatedAt] 
@BuiltValue()
abstract class CaseEvidenceSchema implements Built<CaseEvidenceSchema, CaseEvidenceSchemaBuilder> {
  @BuiltValueField(wireName: r'analysis_results')
  AnyOf? get analysisResults;

  @BuiltValueField(wireName: r'case_id')
  String? get caseId;

  @BuiltValueField(wireName: r'chain_of_custody')
  BuiltList<JsonObject?>? get chainOfCustody;

  @BuiltValueField(wireName: r'collected_at')
  String? get collectedAt;

  @BuiltValueField(wireName: r'collected_by')
  String? get collectedBy;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'evidence_id')
  int? get evidenceId;

  @BuiltValueField(wireName: r'evidence_type')
  String? get evidenceType;

  @BuiltValueField(wireName: r'file_hash_md5')
  String? get fileHashMd5;

  @BuiltValueField(wireName: r'file_hash_sha256')
  String? get fileHashSha256;

  @BuiltValueField(wireName: r'file_path')
  String? get filePath;

  @BuiltValueField(wireName: r'file_size')
  int? get fileSize;

  @BuiltValueField(wireName: r'name')
  String? get name;

  @BuiltValueField(wireName: r'source')
  String? get source_;

  @BuiltValueField(wireName: r'tags')
  BuiltList<String>? get tags;

  @BuiltValueField(wireName: r'updated_at')
  String? get updatedAt;

  CaseEvidenceSchema._();

  factory CaseEvidenceSchema([void updates(CaseEvidenceSchemaBuilder b)]) = _$CaseEvidenceSchema;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseEvidenceSchemaBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseEvidenceSchema> get serializer => _$CaseEvidenceSchemaSerializer();
}

class _$CaseEvidenceSchemaSerializer implements PrimitiveSerializer<CaseEvidenceSchema> {
  @override
  final Iterable<Type> types = const [CaseEvidenceSchema, _$CaseEvidenceSchema];

  @override
  final String wireName = r'CaseEvidenceSchema';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseEvidenceSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.analysisResults != null) {
      yield r'analysis_results';
      yield serializers.serialize(
        object.analysisResults,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.caseId != null) {
      yield r'case_id';
      yield serializers.serialize(
        object.caseId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.chainOfCustody != null) {
      yield r'chain_of_custody';
      yield serializers.serialize(
        object.chainOfCustody,
        specifiedType: const FullType(BuiltList, [FullType.nullable(JsonObject)]),
      );
    }
    if (object.collectedAt != null) {
      yield r'collected_at';
      yield serializers.serialize(
        object.collectedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.collectedBy != null) {
      yield r'collected_by';
      yield serializers.serialize(
        object.collectedBy,
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
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.evidenceId != null) {
      yield r'evidence_id';
      yield serializers.serialize(
        object.evidenceId,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.evidenceType != null) {
      yield r'evidence_type';
      yield serializers.serialize(
        object.evidenceType,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.fileHashMd5 != null) {
      yield r'file_hash_md5';
      yield serializers.serialize(
        object.fileHashMd5,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.fileHashSha256 != null) {
      yield r'file_hash_sha256';
      yield serializers.serialize(
        object.fileHashSha256,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.filePath != null) {
      yield r'file_path';
      yield serializers.serialize(
        object.filePath,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.fileSize != null) {
      yield r'file_size';
      yield serializers.serialize(
        object.fileSize,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.name != null) {
      yield r'name';
      yield serializers.serialize(
        object.name,
        specifiedType: const FullType.nullable(String),
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
    if (object.updatedAt != null) {
      yield r'updated_at';
      yield serializers.serialize(
        object.updatedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseEvidenceSchema object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseEvidenceSchemaBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'analysis_results':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.analysisResults = valueDes;
          break;
        case r'case_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.caseId = valueDes;
          break;
        case r'chain_of_custody':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType.nullable(JsonObject)]),
          ) as BuiltList<JsonObject?>?;
          if (valueDes == null) continue;
          result.chainOfCustody.replace(valueDes);
          break;
        case r'collected_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.collectedAt = valueDes;
          break;
        case r'collected_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.collectedBy = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'evidence_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.evidenceId = valueDes;
          break;
        case r'evidence_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.evidenceType = valueDes;
          break;
        case r'file_hash_md5':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.fileHashMd5 = valueDes;
          break;
        case r'file_hash_sha256':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.fileHashSha256 = valueDes;
          break;
        case r'file_path':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.filePath = valueDes;
          break;
        case r'file_size':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.fileSize = valueDes;
          break;
        case r'name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.name = valueDes;
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
        case r'updated_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.updatedAt = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseEvidenceSchema deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseEvidenceSchemaBuilder();
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


