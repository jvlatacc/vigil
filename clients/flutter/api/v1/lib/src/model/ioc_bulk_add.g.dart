// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'ioc_bulk_add.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IOCBulkAdd extends IOCBulkAdd {
  @override
  final BuiltList<BuiltMap<String, JsonObject?>> iocs;

  factory _$IOCBulkAdd([void Function(IOCBulkAddBuilder)? updates]) =>
      (IOCBulkAddBuilder()..update(updates))._build();

  _$IOCBulkAdd._({required this.iocs}) : super._();
  @override
  IOCBulkAdd rebuild(void Function(IOCBulkAddBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IOCBulkAddBuilder toBuilder() => IOCBulkAddBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IOCBulkAdd && iocs == other.iocs;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, iocs.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IOCBulkAdd')..add('iocs', iocs))
        .toString();
  }
}

class IOCBulkAddBuilder implements Builder<IOCBulkAdd, IOCBulkAddBuilder> {
  _$IOCBulkAdd? _$v;

  ListBuilder<BuiltMap<String, JsonObject?>>? _iocs;
  ListBuilder<BuiltMap<String, JsonObject?>> get iocs =>
      _$this._iocs ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set iocs(ListBuilder<BuiltMap<String, JsonObject?>>? iocs) =>
      _$this._iocs = iocs;

  IOCBulkAddBuilder() {
    IOCBulkAdd._defaults(this);
  }

  IOCBulkAddBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _iocs = $v.iocs.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IOCBulkAdd other) {
    _$v = other as _$IOCBulkAdd;
  }

  @override
  void update(void Function(IOCBulkAddBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IOCBulkAdd build() => _build();

  _$IOCBulkAdd _build() {
    _$IOCBulkAdd _$result;
    try {
      _$result = _$v ??
          _$IOCBulkAdd._(
            iocs: iocs.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'iocs';
        iocs.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'IOCBulkAdd', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
