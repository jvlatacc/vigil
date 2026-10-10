// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_evidence_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseEvidenceListResponse extends CaseEvidenceListResponse {
  @override
  final BuiltList<CaseEvidenceSchema> evidence;

  factory _$CaseEvidenceListResponse(
          [void Function(CaseEvidenceListResponseBuilder)? updates]) =>
      (CaseEvidenceListResponseBuilder()..update(updates))._build();

  _$CaseEvidenceListResponse._({required this.evidence}) : super._();
  @override
  CaseEvidenceListResponse rebuild(
          void Function(CaseEvidenceListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseEvidenceListResponseBuilder toBuilder() =>
      CaseEvidenceListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseEvidenceListResponse && evidence == other.evidence;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, evidence.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseEvidenceListResponse')
          ..add('evidence', evidence))
        .toString();
  }
}

class CaseEvidenceListResponseBuilder
    implements
        Builder<CaseEvidenceListResponse, CaseEvidenceListResponseBuilder> {
  _$CaseEvidenceListResponse? _$v;

  ListBuilder<CaseEvidenceSchema>? _evidence;
  ListBuilder<CaseEvidenceSchema> get evidence =>
      _$this._evidence ??= ListBuilder<CaseEvidenceSchema>();
  set evidence(ListBuilder<CaseEvidenceSchema>? evidence) =>
      _$this._evidence = evidence;

  CaseEvidenceListResponseBuilder() {
    CaseEvidenceListResponse._defaults(this);
  }

  CaseEvidenceListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _evidence = $v.evidence.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseEvidenceListResponse other) {
    _$v = other as _$CaseEvidenceListResponse;
  }

  @override
  void update(void Function(CaseEvidenceListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseEvidenceListResponse build() => _build();

  _$CaseEvidenceListResponse _build() {
    _$CaseEvidenceListResponse _$result;
    try {
      _$result = _$v ??
          _$CaseEvidenceListResponse._(
            evidence: evidence.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'evidence';
        evidence.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseEvidenceListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
