// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'status_breakdown_row.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$StatusBreakdownRow extends StatusBreakdownRow {
  @override
  final int count;
  @override
  final String status;

  factory _$StatusBreakdownRow(
          [void Function(StatusBreakdownRowBuilder)? updates]) =>
      (StatusBreakdownRowBuilder()..update(updates))._build();

  _$StatusBreakdownRow._({required this.count, required this.status})
      : super._();
  @override
  StatusBreakdownRow rebuild(
          void Function(StatusBreakdownRowBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  StatusBreakdownRowBuilder toBuilder() =>
      StatusBreakdownRowBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is StatusBreakdownRow &&
        count == other.count &&
        status == other.status;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'StatusBreakdownRow')
          ..add('count', count)
          ..add('status', status))
        .toString();
  }
}

class StatusBreakdownRowBuilder
    implements Builder<StatusBreakdownRow, StatusBreakdownRowBuilder> {
  _$StatusBreakdownRow? _$v;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  StatusBreakdownRowBuilder() {
    StatusBreakdownRow._defaults(this);
  }

  StatusBreakdownRowBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _count = $v.count;
      _status = $v.status;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(StatusBreakdownRow other) {
    _$v = other as _$StatusBreakdownRow;
  }

  @override
  void update(void Function(StatusBreakdownRowBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  StatusBreakdownRow build() => _build();

  _$StatusBreakdownRow _build() {
    final _$result = _$v ??
        _$StatusBreakdownRow._(
          count: BuiltValueNullFieldError.checkNotNull(
              count, r'StatusBreakdownRow', 'count'),
          status: BuiltValueNullFieldError.checkNotNull(
              status, r'StatusBreakdownRow', 'status'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
