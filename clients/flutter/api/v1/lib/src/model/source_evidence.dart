//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'source_evidence.g.dart';

/// The envelope ``normalize_source_evidence`` returns.  Payload fields are present only when ``status`` is ``available``; list responses drop ``records``/``raw_text`` and set ``payload_included: false``.
///
/// Properties:
/// * [payloadIncluded] 
/// * [provenance] 
/// * [rawText] 
/// * [rawTextTruncated] 
/// * [records] 
/// * [schemaId] 
/// * [status] 
/// * [telemetryKind] 
/// * [totalRecords] 
/// * [truncated] 
/// * [version] 
@BuiltValue()
abstract class SourceEvidence implements Built<SourceEvidence, SourceEvidenceBuilder> {
  @BuiltValueField(wireName: r'payload_included')
  bool? get payloadIncluded;

  @BuiltValueField(wireName: r'provenance')
  SourceEvidenceProvenanceEnum get provenance;
  // enum provenanceEnum {  embedded,  joined,  };

  @BuiltValueField(wireName: r'raw_text')
  String? get rawText;

  @BuiltValueField(wireName: r'raw_text_truncated')
  bool? get rawTextTruncated;

  @BuiltValueField(wireName: r'records')
  BuiltList<BuiltMap<String, JsonObject?>>? get records;

  @BuiltValueField(wireName: r'schema_id')
  String get schemaId;

  @BuiltValueField(wireName: r'status')
  SourceEvidenceStatusEnum get status;
  // enum statusEnum {  available,  not_in_artifact,  redacted,  invalid,  };

  @BuiltValueField(wireName: r'telemetry_kind')
  SourceEvidenceTelemetryKindEnum get telemetryKind;
  // enum telemetryKindEnum {  netflow,  dns,  http_session,  generic_log,  };

  @BuiltValueField(wireName: r'total_records')
  int? get totalRecords;

  @BuiltValueField(wireName: r'truncated')
  bool? get truncated;

  @BuiltValueField(wireName: r'version')
  SourceEvidenceVersionEnum get version;
  // enum versionEnum {  1,  };

  SourceEvidence._();

  factory SourceEvidence([void updates(SourceEvidenceBuilder b)]) = _$SourceEvidence;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SourceEvidenceBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SourceEvidence> get serializer => _$SourceEvidenceSerializer();
}

class _$SourceEvidenceSerializer implements PrimitiveSerializer<SourceEvidence> {
  @override
  final Iterable<Type> types = const [SourceEvidence, _$SourceEvidence];

  @override
  final String wireName = r'SourceEvidence';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SourceEvidence object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.payloadIncluded != null) {
      yield r'payload_included';
      yield serializers.serialize(
        object.payloadIncluded,
        specifiedType: const FullType.nullable(bool),
      );
    }
    yield r'provenance';
    yield serializers.serialize(
      object.provenance,
      specifiedType: const FullType(SourceEvidenceProvenanceEnum),
    );
    if (object.rawText != null) {
      yield r'raw_text';
      yield serializers.serialize(
        object.rawText,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rawTextTruncated != null) {
      yield r'raw_text_truncated';
      yield serializers.serialize(
        object.rawTextTruncated,
        specifiedType: const FullType.nullable(bool),
      );
    }
    if (object.records != null) {
      yield r'records';
      yield serializers.serialize(
        object.records,
        specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
      );
    }
    yield r'schema_id';
    yield serializers.serialize(
      object.schemaId,
      specifiedType: const FullType(String),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(SourceEvidenceStatusEnum),
    );
    yield r'telemetry_kind';
    yield serializers.serialize(
      object.telemetryKind,
      specifiedType: const FullType(SourceEvidenceTelemetryKindEnum),
    );
    if (object.totalRecords != null) {
      yield r'total_records';
      yield serializers.serialize(
        object.totalRecords,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.truncated != null) {
      yield r'truncated';
      yield serializers.serialize(
        object.truncated,
        specifiedType: const FullType.nullable(bool),
      );
    }
    yield r'version';
    yield serializers.serialize(
      object.version,
      specifiedType: const FullType(SourceEvidenceVersionEnum),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SourceEvidence object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required SourceEvidenceBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'payload_included':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.payloadIncluded = valueDes;
          break;
        case r'provenance':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(SourceEvidenceProvenanceEnum),
          ) as SourceEvidenceProvenanceEnum;
          result.provenance = valueDes;
          break;
        case r'raw_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rawText = valueDes;
          break;
        case r'raw_text_truncated':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.rawTextTruncated = valueDes;
          break;
        case r'records':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.records.replace(valueDes);
          break;
        case r'schema_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.schemaId = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(SourceEvidenceStatusEnum),
          ) as SourceEvidenceStatusEnum;
          result.status = valueDes;
          break;
        case r'telemetry_kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(SourceEvidenceTelemetryKindEnum),
          ) as SourceEvidenceTelemetryKindEnum;
          result.telemetryKind = valueDes;
          break;
        case r'total_records':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.totalRecords = valueDes;
          break;
        case r'truncated':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.truncated = valueDes;
          break;
        case r'version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(SourceEvidenceVersionEnum),
          ) as SourceEvidenceVersionEnum;
          result.version = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SourceEvidence deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SourceEvidenceBuilder();
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


class SourceEvidenceProvenanceEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'embedded')
  static const SourceEvidenceProvenanceEnum embedded = _$sourceEvidenceProvenanceEnum_embedded;
  @BuiltValueEnumConst(wireName: r'joined')
  static const SourceEvidenceProvenanceEnum joined = _$sourceEvidenceProvenanceEnum_joined;

  static Serializer<SourceEvidenceProvenanceEnum> get serializer => _$sourceEvidenceProvenanceEnumSerializer;

  const SourceEvidenceProvenanceEnum._(String name): super(name);

  static BuiltSet<SourceEvidenceProvenanceEnum> get values => _$sourceEvidenceProvenanceEnumValues;
  static SourceEvidenceProvenanceEnum valueOf(String name) => _$sourceEvidenceProvenanceEnumValueOf(name);
}

class SourceEvidenceStatusEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'available')
  static const SourceEvidenceStatusEnum available = _$sourceEvidenceStatusEnum_available;
  @BuiltValueEnumConst(wireName: r'not_in_artifact')
  static const SourceEvidenceStatusEnum notInArtifact = _$sourceEvidenceStatusEnum_notInArtifact;
  @BuiltValueEnumConst(wireName: r'redacted')
  static const SourceEvidenceStatusEnum redacted = _$sourceEvidenceStatusEnum_redacted;
  @BuiltValueEnumConst(wireName: r'invalid')
  static const SourceEvidenceStatusEnum invalid = _$sourceEvidenceStatusEnum_invalid;

  static Serializer<SourceEvidenceStatusEnum> get serializer => _$sourceEvidenceStatusEnumSerializer;

  const SourceEvidenceStatusEnum._(String name): super(name);

  static BuiltSet<SourceEvidenceStatusEnum> get values => _$sourceEvidenceStatusEnumValues;
  static SourceEvidenceStatusEnum valueOf(String name) => _$sourceEvidenceStatusEnumValueOf(name);
}

class SourceEvidenceTelemetryKindEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'netflow')
  static const SourceEvidenceTelemetryKindEnum netflow = _$sourceEvidenceTelemetryKindEnum_netflow;
  @BuiltValueEnumConst(wireName: r'dns')
  static const SourceEvidenceTelemetryKindEnum dns = _$sourceEvidenceTelemetryKindEnum_dns;
  @BuiltValueEnumConst(wireName: r'http_session')
  static const SourceEvidenceTelemetryKindEnum httpSession = _$sourceEvidenceTelemetryKindEnum_httpSession;
  @BuiltValueEnumConst(wireName: r'generic_log')
  static const SourceEvidenceTelemetryKindEnum genericLog = _$sourceEvidenceTelemetryKindEnum_genericLog;

  static Serializer<SourceEvidenceTelemetryKindEnum> get serializer => _$sourceEvidenceTelemetryKindEnumSerializer;

  const SourceEvidenceTelemetryKindEnum._(String name): super(name);

  static BuiltSet<SourceEvidenceTelemetryKindEnum> get values => _$sourceEvidenceTelemetryKindEnumValues;
  static SourceEvidenceTelemetryKindEnum valueOf(String name) => _$sourceEvidenceTelemetryKindEnumValueOf(name);
}

class SourceEvidenceVersionEnum extends EnumClass {

  @BuiltValueEnumConst(wireNumber: 1)
  static const SourceEvidenceVersionEnum number1 = _$sourceEvidenceVersionEnum_number1;

  static Serializer<SourceEvidenceVersionEnum> get serializer => _$sourceEvidenceVersionEnumSerializer;

  const SourceEvidenceVersionEnum._(String name): super(name);

  static BuiltSet<SourceEvidenceVersionEnum> get values => _$sourceEvidenceVersionEnumValues;
  static SourceEvidenceVersionEnum valueOf(String name) => _$sourceEvidenceVersionEnumValueOf(name);
}

