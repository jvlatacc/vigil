// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finding_update_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$FindingUpdateResponse extends FindingUpdateResponse {
  @override
  final BuiltMap<String, JsonObject?>? finding;
  @override
  final bool success;
  @override
  final BuiltList<String>? updatedFields;

  factory _$FindingUpdateResponse(
          [void Function(FindingUpdateResponseBuilder)? updates]) =>
      (FindingUpdateResponseBuilder()..update(updates))._build();

  _$FindingUpdateResponse._(
      {this.finding, required this.success, this.updatedFields})
      : super._();
  @override
  FindingUpdateResponse rebuild(
          void Function(FindingUpdateResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  FindingUpdateResponseBuilder toBuilder() =>
      FindingUpdateResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is FindingUpdateResponse &&
        finding == other.finding &&
        success == other.success &&
        updatedFields == other.updatedFields;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, finding.hashCode);
    _$hash = $jc(_$hash, success.hashCode);
    _$hash = $jc(_$hash, updatedFields.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'FindingUpdateResponse')
          ..add('finding', finding)
          ..add('success', success)
          ..add('updatedFields', updatedFields))
        .toString();
  }
}

class FindingUpdateResponseBuilder
    implements Builder<FindingUpdateResponse, FindingUpdateResponseBuilder> {
  _$FindingUpdateResponse? _$v;

  MapBuilder<String, JsonObject?>? _finding;
  MapBuilder<String, JsonObject?> get finding =>
      _$this._finding ??= MapBuilder<String, JsonObject?>();
  set finding(MapBuilder<String, JsonObject?>? finding) =>
      _$this._finding = finding;

  bool? _success;
  bool? get success => _$this._success;
  set success(bool? success) => _$this._success = success;

  ListBuilder<String>? _updatedFields;
  ListBuilder<String> get updatedFields =>
      _$this._updatedFields ??= ListBuilder<String>();
  set updatedFields(ListBuilder<String>? updatedFields) =>
      _$this._updatedFields = updatedFields;

  FindingUpdateResponseBuilder() {
    FindingUpdateResponse._defaults(this);
  }

  FindingUpdateResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _finding = $v.finding?.toBuilder();
      _success = $v.success;
      _updatedFields = $v.updatedFields?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(FindingUpdateResponse other) {
    _$v = other as _$FindingUpdateResponse;
  }

  @override
  void update(void Function(FindingUpdateResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  FindingUpdateResponse build() => _build();

  _$FindingUpdateResponse _build() {
    _$FindingUpdateResponse _$result;
    try {
      _$result = _$v ??
          _$FindingUpdateResponse._(
            finding: _finding?.build(),
            success: BuiltValueNullFieldError.checkNotNull(
                success, r'FindingUpdateResponse', 'success'),
            updatedFields: _updatedFields?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'finding';
        _finding?.build();

        _$failedField = 'updatedFields';
        _updatedFields?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'FindingUpdateResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
