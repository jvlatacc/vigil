// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_merge_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseMergeResponse extends CaseMergeResponse {
  @override
  final int? findingsMoved;
  @override
  final String message;
  @override
  final String sourceCaseStatus;
  @override
  final bool success;
  @override
  final CaseSchema? targetCase;

  factory _$CaseMergeResponse(
          [void Function(CaseMergeResponseBuilder)? updates]) =>
      (CaseMergeResponseBuilder()..update(updates))._build();

  _$CaseMergeResponse._(
      {this.findingsMoved,
      required this.message,
      required this.sourceCaseStatus,
      required this.success,
      this.targetCase})
      : super._();
  @override
  CaseMergeResponse rebuild(void Function(CaseMergeResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseMergeResponseBuilder toBuilder() =>
      CaseMergeResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseMergeResponse &&
        findingsMoved == other.findingsMoved &&
        message == other.message &&
        sourceCaseStatus == other.sourceCaseStatus &&
        success == other.success &&
        targetCase == other.targetCase;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, findingsMoved.hashCode);
    _$hash = $jc(_$hash, message.hashCode);
    _$hash = $jc(_$hash, sourceCaseStatus.hashCode);
    _$hash = $jc(_$hash, success.hashCode);
    _$hash = $jc(_$hash, targetCase.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseMergeResponse')
          ..add('findingsMoved', findingsMoved)
          ..add('message', message)
          ..add('sourceCaseStatus', sourceCaseStatus)
          ..add('success', success)
          ..add('targetCase', targetCase))
        .toString();
  }
}

class CaseMergeResponseBuilder
    implements Builder<CaseMergeResponse, CaseMergeResponseBuilder> {
  _$CaseMergeResponse? _$v;

  int? _findingsMoved;
  int? get findingsMoved => _$this._findingsMoved;
  set findingsMoved(int? findingsMoved) =>
      _$this._findingsMoved = findingsMoved;

  String? _message;
  String? get message => _$this._message;
  set message(String? message) => _$this._message = message;

  String? _sourceCaseStatus;
  String? get sourceCaseStatus => _$this._sourceCaseStatus;
  set sourceCaseStatus(String? sourceCaseStatus) =>
      _$this._sourceCaseStatus = sourceCaseStatus;

  bool? _success;
  bool? get success => _$this._success;
  set success(bool? success) => _$this._success = success;

  CaseSchemaBuilder? _targetCase;
  CaseSchemaBuilder get targetCase =>
      _$this._targetCase ??= CaseSchemaBuilder();
  set targetCase(CaseSchemaBuilder? targetCase) =>
      _$this._targetCase = targetCase;

  CaseMergeResponseBuilder() {
    CaseMergeResponse._defaults(this);
  }

  CaseMergeResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _findingsMoved = $v.findingsMoved;
      _message = $v.message;
      _sourceCaseStatus = $v.sourceCaseStatus;
      _success = $v.success;
      _targetCase = $v.targetCase?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseMergeResponse other) {
    _$v = other as _$CaseMergeResponse;
  }

  @override
  void update(void Function(CaseMergeResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseMergeResponse build() => _build();

  _$CaseMergeResponse _build() {
    _$CaseMergeResponse _$result;
    try {
      _$result = _$v ??
          _$CaseMergeResponse._(
            findingsMoved: findingsMoved,
            message: BuiltValueNullFieldError.checkNotNull(
                message, r'CaseMergeResponse', 'message'),
            sourceCaseStatus: BuiltValueNullFieldError.checkNotNull(
                sourceCaseStatus, r'CaseMergeResponse', 'sourceCaseStatus'),
            success: BuiltValueNullFieldError.checkNotNull(
                success, r'CaseMergeResponse', 'success'),
            targetCase: _targetCase?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'targetCase';
        _targetCase?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseMergeResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
