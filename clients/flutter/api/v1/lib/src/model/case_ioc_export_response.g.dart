// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_ioc_export_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseIOCExportResponse extends CaseIOCExportResponse {
  @override
  final JsonObject? content;
  @override
  final String format;

  factory _$CaseIOCExportResponse(
          [void Function(CaseIOCExportResponseBuilder)? updates]) =>
      (CaseIOCExportResponseBuilder()..update(updates))._build();

  _$CaseIOCExportResponse._({this.content, required this.format}) : super._();
  @override
  CaseIOCExportResponse rebuild(
          void Function(CaseIOCExportResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseIOCExportResponseBuilder toBuilder() =>
      CaseIOCExportResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseIOCExportResponse &&
        content == other.content &&
        format == other.format;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, content.hashCode);
    _$hash = $jc(_$hash, format.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseIOCExportResponse')
          ..add('content', content)
          ..add('format', format))
        .toString();
  }
}

class CaseIOCExportResponseBuilder
    implements Builder<CaseIOCExportResponse, CaseIOCExportResponseBuilder> {
  _$CaseIOCExportResponse? _$v;

  JsonObject? _content;
  JsonObject? get content => _$this._content;
  set content(JsonObject? content) => _$this._content = content;

  String? _format;
  String? get format => _$this._format;
  set format(String? format) => _$this._format = format;

  CaseIOCExportResponseBuilder() {
    CaseIOCExportResponse._defaults(this);
  }

  CaseIOCExportResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _content = $v.content;
      _format = $v.format;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseIOCExportResponse other) {
    _$v = other as _$CaseIOCExportResponse;
  }

  @override
  void update(void Function(CaseIOCExportResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseIOCExportResponse build() => _build();

  _$CaseIOCExportResponse _build() {
    final _$result = _$v ??
        _$CaseIOCExportResponse._(
          content: content,
          format: BuiltValueNullFieldError.checkNotNull(
              format, r'CaseIOCExportResponse', 'format'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
