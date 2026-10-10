// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'merge_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$MergeRequest extends MergeRequest {
  @override
  final String? mergedBy;
  @override
  final String sourceCaseId;

  factory _$MergeRequest([void Function(MergeRequestBuilder)? updates]) =>
      (MergeRequestBuilder()..update(updates))._build();

  _$MergeRequest._({this.mergedBy, required this.sourceCaseId}) : super._();
  @override
  MergeRequest rebuild(void Function(MergeRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  MergeRequestBuilder toBuilder() => MergeRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is MergeRequest &&
        mergedBy == other.mergedBy &&
        sourceCaseId == other.sourceCaseId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, mergedBy.hashCode);
    _$hash = $jc(_$hash, sourceCaseId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'MergeRequest')
          ..add('mergedBy', mergedBy)
          ..add('sourceCaseId', sourceCaseId))
        .toString();
  }
}

class MergeRequestBuilder
    implements Builder<MergeRequest, MergeRequestBuilder> {
  _$MergeRequest? _$v;

  String? _mergedBy;
  String? get mergedBy => _$this._mergedBy;
  set mergedBy(String? mergedBy) => _$this._mergedBy = mergedBy;

  String? _sourceCaseId;
  String? get sourceCaseId => _$this._sourceCaseId;
  set sourceCaseId(String? sourceCaseId) => _$this._sourceCaseId = sourceCaseId;

  MergeRequestBuilder() {
    MergeRequest._defaults(this);
  }

  MergeRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _mergedBy = $v.mergedBy;
      _sourceCaseId = $v.sourceCaseId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(MergeRequest other) {
    _$v = other as _$MergeRequest;
  }

  @override
  void update(void Function(MergeRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  MergeRequest build() => _build();

  _$MergeRequest _build() {
    final _$result = _$v ??
        _$MergeRequest._(
          mergedBy: mergedBy,
          sourceCaseId: BuiltValueNullFieldError.checkNotNull(
              sourceCaseId, r'MergeRequest', 'sourceCaseId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
