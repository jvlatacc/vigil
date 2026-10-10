// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'source_evidence.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const SourceEvidenceProvenanceEnum _$sourceEvidenceProvenanceEnum_embedded =
    const SourceEvidenceProvenanceEnum._('embedded');
const SourceEvidenceProvenanceEnum _$sourceEvidenceProvenanceEnum_joined =
    const SourceEvidenceProvenanceEnum._('joined');

SourceEvidenceProvenanceEnum _$sourceEvidenceProvenanceEnumValueOf(
    String name) {
  switch (name) {
    case 'embedded':
      return _$sourceEvidenceProvenanceEnum_embedded;
    case 'joined':
      return _$sourceEvidenceProvenanceEnum_joined;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<SourceEvidenceProvenanceEnum>
    _$sourceEvidenceProvenanceEnumValues =
    BuiltSet<SourceEvidenceProvenanceEnum>(const <SourceEvidenceProvenanceEnum>[
  _$sourceEvidenceProvenanceEnum_embedded,
  _$sourceEvidenceProvenanceEnum_joined,
]);

const SourceEvidenceStatusEnum _$sourceEvidenceStatusEnum_available =
    const SourceEvidenceStatusEnum._('available');
const SourceEvidenceStatusEnum _$sourceEvidenceStatusEnum_notInArtifact =
    const SourceEvidenceStatusEnum._('notInArtifact');
const SourceEvidenceStatusEnum _$sourceEvidenceStatusEnum_redacted =
    const SourceEvidenceStatusEnum._('redacted');
const SourceEvidenceStatusEnum _$sourceEvidenceStatusEnum_invalid =
    const SourceEvidenceStatusEnum._('invalid');

SourceEvidenceStatusEnum _$sourceEvidenceStatusEnumValueOf(String name) {
  switch (name) {
    case 'available':
      return _$sourceEvidenceStatusEnum_available;
    case 'notInArtifact':
      return _$sourceEvidenceStatusEnum_notInArtifact;
    case 'redacted':
      return _$sourceEvidenceStatusEnum_redacted;
    case 'invalid':
      return _$sourceEvidenceStatusEnum_invalid;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<SourceEvidenceStatusEnum> _$sourceEvidenceStatusEnumValues =
    BuiltSet<SourceEvidenceStatusEnum>(const <SourceEvidenceStatusEnum>[
  _$sourceEvidenceStatusEnum_available,
  _$sourceEvidenceStatusEnum_notInArtifact,
  _$sourceEvidenceStatusEnum_redacted,
  _$sourceEvidenceStatusEnum_invalid,
]);

const SourceEvidenceTelemetryKindEnum
    _$sourceEvidenceTelemetryKindEnum_netflow =
    const SourceEvidenceTelemetryKindEnum._('netflow');
const SourceEvidenceTelemetryKindEnum _$sourceEvidenceTelemetryKindEnum_dns =
    const SourceEvidenceTelemetryKindEnum._('dns');
const SourceEvidenceTelemetryKindEnum
    _$sourceEvidenceTelemetryKindEnum_httpSession =
    const SourceEvidenceTelemetryKindEnum._('httpSession');
const SourceEvidenceTelemetryKindEnum
    _$sourceEvidenceTelemetryKindEnum_genericLog =
    const SourceEvidenceTelemetryKindEnum._('genericLog');

SourceEvidenceTelemetryKindEnum _$sourceEvidenceTelemetryKindEnumValueOf(
    String name) {
  switch (name) {
    case 'netflow':
      return _$sourceEvidenceTelemetryKindEnum_netflow;
    case 'dns':
      return _$sourceEvidenceTelemetryKindEnum_dns;
    case 'httpSession':
      return _$sourceEvidenceTelemetryKindEnum_httpSession;
    case 'genericLog':
      return _$sourceEvidenceTelemetryKindEnum_genericLog;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<SourceEvidenceTelemetryKindEnum>
    _$sourceEvidenceTelemetryKindEnumValues = BuiltSet<
        SourceEvidenceTelemetryKindEnum>(const <SourceEvidenceTelemetryKindEnum>[
  _$sourceEvidenceTelemetryKindEnum_netflow,
  _$sourceEvidenceTelemetryKindEnum_dns,
  _$sourceEvidenceTelemetryKindEnum_httpSession,
  _$sourceEvidenceTelemetryKindEnum_genericLog,
]);

const SourceEvidenceVersionEnum _$sourceEvidenceVersionEnum_number1 =
    const SourceEvidenceVersionEnum._('number1');

SourceEvidenceVersionEnum _$sourceEvidenceVersionEnumValueOf(String name) {
  switch (name) {
    case 'number1':
      return _$sourceEvidenceVersionEnum_number1;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<SourceEvidenceVersionEnum> _$sourceEvidenceVersionEnumValues =
    BuiltSet<SourceEvidenceVersionEnum>(const <SourceEvidenceVersionEnum>[
  _$sourceEvidenceVersionEnum_number1,
]);

Serializer<SourceEvidenceProvenanceEnum>
    _$sourceEvidenceProvenanceEnumSerializer =
    _$SourceEvidenceProvenanceEnumSerializer();
Serializer<SourceEvidenceStatusEnum> _$sourceEvidenceStatusEnumSerializer =
    _$SourceEvidenceStatusEnumSerializer();
Serializer<SourceEvidenceTelemetryKindEnum>
    _$sourceEvidenceTelemetryKindEnumSerializer =
    _$SourceEvidenceTelemetryKindEnumSerializer();
Serializer<SourceEvidenceVersionEnum> _$sourceEvidenceVersionEnumSerializer =
    _$SourceEvidenceVersionEnumSerializer();

class _$SourceEvidenceProvenanceEnumSerializer
    implements PrimitiveSerializer<SourceEvidenceProvenanceEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'embedded': 'embedded',
    'joined': 'joined',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'embedded': 'embedded',
    'joined': 'joined',
  };

  @override
  final Iterable<Type> types = const <Type>[SourceEvidenceProvenanceEnum];
  @override
  final String wireName = 'SourceEvidenceProvenanceEnum';

  @override
  Object serialize(Serializers serializers, SourceEvidenceProvenanceEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  SourceEvidenceProvenanceEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      SourceEvidenceProvenanceEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$SourceEvidenceStatusEnumSerializer
    implements PrimitiveSerializer<SourceEvidenceStatusEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'available': 'available',
    'notInArtifact': 'not_in_artifact',
    'redacted': 'redacted',
    'invalid': 'invalid',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'available': 'available',
    'not_in_artifact': 'notInArtifact',
    'redacted': 'redacted',
    'invalid': 'invalid',
  };

  @override
  final Iterable<Type> types = const <Type>[SourceEvidenceStatusEnum];
  @override
  final String wireName = 'SourceEvidenceStatusEnum';

  @override
  Object serialize(Serializers serializers, SourceEvidenceStatusEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  SourceEvidenceStatusEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      SourceEvidenceStatusEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$SourceEvidenceTelemetryKindEnumSerializer
    implements PrimitiveSerializer<SourceEvidenceTelemetryKindEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'netflow': 'netflow',
    'dns': 'dns',
    'httpSession': 'http_session',
    'genericLog': 'generic_log',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'netflow': 'netflow',
    'dns': 'dns',
    'http_session': 'httpSession',
    'generic_log': 'genericLog',
  };

  @override
  final Iterable<Type> types = const <Type>[SourceEvidenceTelemetryKindEnum];
  @override
  final String wireName = 'SourceEvidenceTelemetryKindEnum';

  @override
  Object serialize(
          Serializers serializers, SourceEvidenceTelemetryKindEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  SourceEvidenceTelemetryKindEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      SourceEvidenceTelemetryKindEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$SourceEvidenceVersionEnumSerializer
    implements PrimitiveSerializer<SourceEvidenceVersionEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'number1': 1,
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    1: 'number1',
  };

  @override
  final Iterable<Type> types = const <Type>[SourceEvidenceVersionEnum];
  @override
  final String wireName = 'SourceEvidenceVersionEnum';

  @override
  Object serialize(Serializers serializers, SourceEvidenceVersionEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  SourceEvidenceVersionEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      SourceEvidenceVersionEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$SourceEvidence extends SourceEvidence {
  @override
  final bool? payloadIncluded;
  @override
  final SourceEvidenceProvenanceEnum provenance;
  @override
  final String? rawText;
  @override
  final bool? rawTextTruncated;
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? records;
  @override
  final String schemaId;
  @override
  final SourceEvidenceStatusEnum status;
  @override
  final SourceEvidenceTelemetryKindEnum telemetryKind;
  @override
  final int? totalRecords;
  @override
  final bool? truncated;
  @override
  final SourceEvidenceVersionEnum version;

  factory _$SourceEvidence([void Function(SourceEvidenceBuilder)? updates]) =>
      (SourceEvidenceBuilder()..update(updates))._build();

  _$SourceEvidence._(
      {this.payloadIncluded,
      required this.provenance,
      this.rawText,
      this.rawTextTruncated,
      this.records,
      required this.schemaId,
      required this.status,
      required this.telemetryKind,
      this.totalRecords,
      this.truncated,
      required this.version})
      : super._();
  @override
  SourceEvidence rebuild(void Function(SourceEvidenceBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SourceEvidenceBuilder toBuilder() => SourceEvidenceBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SourceEvidence &&
        payloadIncluded == other.payloadIncluded &&
        provenance == other.provenance &&
        rawText == other.rawText &&
        rawTextTruncated == other.rawTextTruncated &&
        records == other.records &&
        schemaId == other.schemaId &&
        status == other.status &&
        telemetryKind == other.telemetryKind &&
        totalRecords == other.totalRecords &&
        truncated == other.truncated &&
        version == other.version;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, payloadIncluded.hashCode);
    _$hash = $jc(_$hash, provenance.hashCode);
    _$hash = $jc(_$hash, rawText.hashCode);
    _$hash = $jc(_$hash, rawTextTruncated.hashCode);
    _$hash = $jc(_$hash, records.hashCode);
    _$hash = $jc(_$hash, schemaId.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, telemetryKind.hashCode);
    _$hash = $jc(_$hash, totalRecords.hashCode);
    _$hash = $jc(_$hash, truncated.hashCode);
    _$hash = $jc(_$hash, version.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SourceEvidence')
          ..add('payloadIncluded', payloadIncluded)
          ..add('provenance', provenance)
          ..add('rawText', rawText)
          ..add('rawTextTruncated', rawTextTruncated)
          ..add('records', records)
          ..add('schemaId', schemaId)
          ..add('status', status)
          ..add('telemetryKind', telemetryKind)
          ..add('totalRecords', totalRecords)
          ..add('truncated', truncated)
          ..add('version', version))
        .toString();
  }
}

class SourceEvidenceBuilder
    implements Builder<SourceEvidence, SourceEvidenceBuilder> {
  _$SourceEvidence? _$v;

  bool? _payloadIncluded;
  bool? get payloadIncluded => _$this._payloadIncluded;
  set payloadIncluded(bool? payloadIncluded) =>
      _$this._payloadIncluded = payloadIncluded;

  SourceEvidenceProvenanceEnum? _provenance;
  SourceEvidenceProvenanceEnum? get provenance => _$this._provenance;
  set provenance(SourceEvidenceProvenanceEnum? provenance) =>
      _$this._provenance = provenance;

  String? _rawText;
  String? get rawText => _$this._rawText;
  set rawText(String? rawText) => _$this._rawText = rawText;

  bool? _rawTextTruncated;
  bool? get rawTextTruncated => _$this._rawTextTruncated;
  set rawTextTruncated(bool? rawTextTruncated) =>
      _$this._rawTextTruncated = rawTextTruncated;

  ListBuilder<BuiltMap<String, JsonObject?>>? _records;
  ListBuilder<BuiltMap<String, JsonObject?>> get records =>
      _$this._records ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set records(ListBuilder<BuiltMap<String, JsonObject?>>? records) =>
      _$this._records = records;

  String? _schemaId;
  String? get schemaId => _$this._schemaId;
  set schemaId(String? schemaId) => _$this._schemaId = schemaId;

  SourceEvidenceStatusEnum? _status;
  SourceEvidenceStatusEnum? get status => _$this._status;
  set status(SourceEvidenceStatusEnum? status) => _$this._status = status;

  SourceEvidenceTelemetryKindEnum? _telemetryKind;
  SourceEvidenceTelemetryKindEnum? get telemetryKind => _$this._telemetryKind;
  set telemetryKind(SourceEvidenceTelemetryKindEnum? telemetryKind) =>
      _$this._telemetryKind = telemetryKind;

  int? _totalRecords;
  int? get totalRecords => _$this._totalRecords;
  set totalRecords(int? totalRecords) => _$this._totalRecords = totalRecords;

  bool? _truncated;
  bool? get truncated => _$this._truncated;
  set truncated(bool? truncated) => _$this._truncated = truncated;

  SourceEvidenceVersionEnum? _version;
  SourceEvidenceVersionEnum? get version => _$this._version;
  set version(SourceEvidenceVersionEnum? version) => _$this._version = version;

  SourceEvidenceBuilder() {
    SourceEvidence._defaults(this);
  }

  SourceEvidenceBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _payloadIncluded = $v.payloadIncluded;
      _provenance = $v.provenance;
      _rawText = $v.rawText;
      _rawTextTruncated = $v.rawTextTruncated;
      _records = $v.records?.toBuilder();
      _schemaId = $v.schemaId;
      _status = $v.status;
      _telemetryKind = $v.telemetryKind;
      _totalRecords = $v.totalRecords;
      _truncated = $v.truncated;
      _version = $v.version;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SourceEvidence other) {
    _$v = other as _$SourceEvidence;
  }

  @override
  void update(void Function(SourceEvidenceBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SourceEvidence build() => _build();

  _$SourceEvidence _build() {
    _$SourceEvidence _$result;
    try {
      _$result = _$v ??
          _$SourceEvidence._(
            payloadIncluded: payloadIncluded,
            provenance: BuiltValueNullFieldError.checkNotNull(
                provenance, r'SourceEvidence', 'provenance'),
            rawText: rawText,
            rawTextTruncated: rawTextTruncated,
            records: _records?.build(),
            schemaId: BuiltValueNullFieldError.checkNotNull(
                schemaId, r'SourceEvidence', 'schemaId'),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'SourceEvidence', 'status'),
            telemetryKind: BuiltValueNullFieldError.checkNotNull(
                telemetryKind, r'SourceEvidence', 'telemetryKind'),
            totalRecords: totalRecords,
            truncated: truncated,
            version: BuiltValueNullFieldError.checkNotNull(
                version, r'SourceEvidence', 'version'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'records';
        _records?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SourceEvidence', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
