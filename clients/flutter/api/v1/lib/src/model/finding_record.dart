//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/entity_context.dart';
import 'package:one_of/any_of.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'finding_record.g.dart';

/// A finding as the API returns it.  ``FindingSchema`` stays in the storage tier, which may not import the findings domain, so the evidence type is narrowed here.
///
/// Properties:
/// * [aiEnrichment] 
/// * [anomalyScore] 
/// * [clusterId] 
/// * [createdAt] 
/// * [dataSource] 
/// * [description] 
/// * [entityContext] 
/// * [evidenceLinks] 
/// * [excludedIps] 
/// * [externalId] 
/// * [findingId] 
/// * [mitrePredictions] 
/// * [severity] 
/// * [status] 
/// * [timestamp] 
/// * [title] 
/// * [updatedAt] 
@BuiltValue()
abstract class FindingRecord implements Built<FindingRecord, FindingRecordBuilder> {
  @BuiltValueField(wireName: r'ai_enrichment')
  AnyOf? get aiEnrichment;

  @BuiltValueField(wireName: r'anomaly_score')
  num? get anomalyScore;

  @BuiltValueField(wireName: r'cluster_id')
  String? get clusterId;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'data_source')
  String? get dataSource;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'entity_context')
  EntityContext? get entityContext;

  @BuiltValueField(wireName: r'evidence_links')
  AnyOf? get evidenceLinks;

  @BuiltValueField(wireName: r'excluded_ips')
  BuiltList<String>? get excludedIps;

  @BuiltValueField(wireName: r'external_id')
  String? get externalId;

  @BuiltValueField(wireName: r'finding_id')
  String? get findingId;

  @BuiltValueField(wireName: r'mitre_predictions')
  AnyOf? get mitrePredictions;

  @BuiltValueField(wireName: r'severity')
  String? get severity;

  @BuiltValueField(wireName: r'status')
  String? get status;

  @BuiltValueField(wireName: r'timestamp')
  String? get timestamp;

  @BuiltValueField(wireName: r'title')
  String? get title;

  @BuiltValueField(wireName: r'updated_at')
  String? get updatedAt;

  FindingRecord._();

  factory FindingRecord([void updates(FindingRecordBuilder b)]) = _$FindingRecord;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(FindingRecordBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<FindingRecord> get serializer => _$FindingRecordSerializer();
}

class _$FindingRecordSerializer implements PrimitiveSerializer<FindingRecord> {
  @override
  final Iterable<Type> types = const [FindingRecord, _$FindingRecord];

  @override
  final String wireName = r'FindingRecord';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    FindingRecord object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.aiEnrichment != null) {
      yield r'ai_enrichment';
      yield serializers.serialize(
        object.aiEnrichment,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.anomalyScore != null) {
      yield r'anomaly_score';
      yield serializers.serialize(
        object.anomalyScore,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.clusterId != null) {
      yield r'cluster_id';
      yield serializers.serialize(
        object.clusterId,
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
    if (object.dataSource != null) {
      yield r'data_source';
      yield serializers.serialize(
        object.dataSource,
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
    if (object.entityContext != null) {
      yield r'entity_context';
      yield serializers.serialize(
        object.entityContext,
        specifiedType: const FullType.nullable(EntityContext),
      );
    }
    if (object.evidenceLinks != null) {
      yield r'evidence_links';
      yield serializers.serialize(
        object.evidenceLinks,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.excludedIps != null) {
      yield r'excluded_ips';
      yield serializers.serialize(
        object.excludedIps,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.externalId != null) {
      yield r'external_id';
      yield serializers.serialize(
        object.externalId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.findingId != null) {
      yield r'finding_id';
      yield serializers.serialize(
        object.findingId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.mitrePredictions != null) {
      yield r'mitre_predictions';
      yield serializers.serialize(
        object.mitrePredictions,
        specifiedType: const FullType.nullable(AnyOf),
      );
    }
    if (object.severity != null) {
      yield r'severity';
      yield serializers.serialize(
        object.severity,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.status != null) {
      yield r'status';
      yield serializers.serialize(
        object.status,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.timestamp != null) {
      yield r'timestamp';
      yield serializers.serialize(
        object.timestamp,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.title != null) {
      yield r'title';
      yield serializers.serialize(
        object.title,
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
  }

  @override
  Object serialize(
    Serializers serializers,
    FindingRecord object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required FindingRecordBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'ai_enrichment':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.aiEnrichment = valueDes;
          break;
        case r'anomaly_score':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.anomalyScore = valueDes;
          break;
        case r'cluster_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.clusterId = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'data_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.dataSource = valueDes;
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'entity_context':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(EntityContext),
          ) as EntityContext?;
          if (valueDes == null) continue;
          result.entityContext = valueDes.toBuilder();
          break;
        case r'evidence_links':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.evidenceLinks = valueDes;
          break;
        case r'excluded_ips':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.excludedIps.replace(valueDes);
          break;
        case r'external_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.externalId = valueDes;
          break;
        case r'finding_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.findingId = valueDes;
          break;
        case r'mitre_predictions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(AnyOf),
          ) as AnyOf?;
          if (valueDes == null) continue;
          result.mitrePredictions = valueDes;
          break;
        case r'severity':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.severity = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.status = valueDes;
          break;
        case r'timestamp':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.timestamp = valueDes;
          break;
        case r'title':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.title = valueDes;
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
  FindingRecord deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = FindingRecordBuilder();
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


