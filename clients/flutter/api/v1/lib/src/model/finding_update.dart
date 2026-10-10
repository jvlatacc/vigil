//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'finding_update.g.dart';

/// Schema for updating a finding.
///
/// Properties:
/// * [anomalyScore] 
/// * [clusterId] 
/// * [entityContext] 
/// * [evidenceLinks] 
/// * [mitrePredictions] 
/// * [predictedTechniques] 
/// * [severity] 
/// * [status] 
@BuiltValue()
abstract class FindingUpdate implements Built<FindingUpdate, FindingUpdateBuilder> {
  @BuiltValueField(wireName: r'anomaly_score')
  num? get anomalyScore;

  @BuiltValueField(wireName: r'cluster_id')
  String? get clusterId;

  @BuiltValueField(wireName: r'entity_context')
  BuiltMap<String, JsonObject?>? get entityContext;

  @BuiltValueField(wireName: r'evidence_links')
  BuiltList<String>? get evidenceLinks;

  @BuiltValueField(wireName: r'mitre_predictions')
  BuiltMap<String, num>? get mitrePredictions;

  @BuiltValueField(wireName: r'predicted_techniques')
  BuiltList<BuiltMap<String, JsonObject?>>? get predictedTechniques;

  @BuiltValueField(wireName: r'severity')
  String? get severity;

  @BuiltValueField(wireName: r'status')
  String? get status;

  FindingUpdate._();

  factory FindingUpdate([void updates(FindingUpdateBuilder b)]) = _$FindingUpdate;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(FindingUpdateBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<FindingUpdate> get serializer => _$FindingUpdateSerializer();
}

class _$FindingUpdateSerializer implements PrimitiveSerializer<FindingUpdate> {
  @override
  final Iterable<Type> types = const [FindingUpdate, _$FindingUpdate];

  @override
  final String wireName = r'FindingUpdate';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    FindingUpdate object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
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
    if (object.entityContext != null) {
      yield r'entity_context';
      yield serializers.serialize(
        object.entityContext,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    if (object.evidenceLinks != null) {
      yield r'evidence_links';
      yield serializers.serialize(
        object.evidenceLinks,
        specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
      );
    }
    if (object.mitrePredictions != null) {
      yield r'mitre_predictions';
      yield serializers.serialize(
        object.mitrePredictions,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(num)]),
      );
    }
    if (object.predictedTechniques != null) {
      yield r'predicted_techniques';
      yield serializers.serialize(
        object.predictedTechniques,
        specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
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
  }

  @override
  Object serialize(
    Serializers serializers,
    FindingUpdate object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required FindingUpdateBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
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
        case r'entity_context':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.entityContext.replace(valueDes);
          break;
        case r'evidence_links':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.evidenceLinks.replace(valueDes);
          break;
        case r'mitre_predictions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(num)]),
          ) as BuiltMap<String, num>?;
          if (valueDes == null) continue;
          result.mitrePredictions.replace(valueDes);
          break;
        case r'predicted_techniques':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.predictedTechniques.replace(valueDes);
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
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  FindingUpdate deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = FindingUpdateBuilder();
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


