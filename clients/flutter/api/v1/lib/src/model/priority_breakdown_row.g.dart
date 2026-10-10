// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'priority_breakdown_row.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PriorityBreakdownRow extends PriorityBreakdownRow {
  @override
  final int closedCount;
  @override
  final int count;
  @override
  final String priority;

  factory _$PriorityBreakdownRow(
          [void Function(PriorityBreakdownRowBuilder)? updates]) =>
      (PriorityBreakdownRowBuilder()..update(updates))._build();

  _$PriorityBreakdownRow._(
      {required this.closedCount, required this.count, required this.priority})
      : super._();
  @override
  PriorityBreakdownRow rebuild(
          void Function(PriorityBreakdownRowBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PriorityBreakdownRowBuilder toBuilder() =>
      PriorityBreakdownRowBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PriorityBreakdownRow &&
        closedCount == other.closedCount &&
        count == other.count &&
        priority == other.priority;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, closedCount.hashCode);
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PriorityBreakdownRow')
          ..add('closedCount', closedCount)
          ..add('count', count)
          ..add('priority', priority))
        .toString();
  }
}

class PriorityBreakdownRowBuilder
    implements Builder<PriorityBreakdownRow, PriorityBreakdownRowBuilder> {
  _$PriorityBreakdownRow? _$v;

  int? _closedCount;
  int? get closedCount => _$this._closedCount;
  set closedCount(int? closedCount) => _$this._closedCount = closedCount;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  String? _priority;
  String? get priority => _$this._priority;
  set priority(String? priority) => _$this._priority = priority;

  PriorityBreakdownRowBuilder() {
    PriorityBreakdownRow._defaults(this);
  }

  PriorityBreakdownRowBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _closedCount = $v.closedCount;
      _count = $v.count;
      _priority = $v.priority;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PriorityBreakdownRow other) {
    _$v = other as _$PriorityBreakdownRow;
  }

  @override
  void update(void Function(PriorityBreakdownRowBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PriorityBreakdownRow build() => _build();

  _$PriorityBreakdownRow _build() {
    final _$result = _$v ??
        _$PriorityBreakdownRow._(
          closedCount: BuiltValueNullFieldError.checkNotNull(
              closedCount, r'PriorityBreakdownRow', 'closedCount'),
          count: BuiltValueNullFieldError.checkNotNull(
              count, r'PriorityBreakdownRow', 'count'),
          priority: BuiltValueNullFieldError.checkNotNull(
              priority, r'PriorityBreakdownRow', 'priority'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
