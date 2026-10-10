// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'by_priority_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ByPriorityResponse extends ByPriorityResponse {
  @override
  final BuiltList<PriorityBreakdownRow>? priorityBreakdown;

  factory _$ByPriorityResponse(
          [void Function(ByPriorityResponseBuilder)? updates]) =>
      (ByPriorityResponseBuilder()..update(updates))._build();

  _$ByPriorityResponse._({this.priorityBreakdown}) : super._();
  @override
  ByPriorityResponse rebuild(
          void Function(ByPriorityResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ByPriorityResponseBuilder toBuilder() =>
      ByPriorityResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ByPriorityResponse &&
        priorityBreakdown == other.priorityBreakdown;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, priorityBreakdown.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ByPriorityResponse')
          ..add('priorityBreakdown', priorityBreakdown))
        .toString();
  }
}

class ByPriorityResponseBuilder
    implements Builder<ByPriorityResponse, ByPriorityResponseBuilder> {
  _$ByPriorityResponse? _$v;

  ListBuilder<PriorityBreakdownRow>? _priorityBreakdown;
  ListBuilder<PriorityBreakdownRow> get priorityBreakdown =>
      _$this._priorityBreakdown ??= ListBuilder<PriorityBreakdownRow>();
  set priorityBreakdown(ListBuilder<PriorityBreakdownRow>? priorityBreakdown) =>
      _$this._priorityBreakdown = priorityBreakdown;

  ByPriorityResponseBuilder() {
    ByPriorityResponse._defaults(this);
  }

  ByPriorityResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _priorityBreakdown = $v.priorityBreakdown?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ByPriorityResponse other) {
    _$v = other as _$ByPriorityResponse;
  }

  @override
  void update(void Function(ByPriorityResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ByPriorityResponse build() => _build();

  _$ByPriorityResponse _build() {
    _$ByPriorityResponse _$result;
    try {
      _$result = _$v ??
          _$ByPriorityResponse._(
            priorityBreakdown: _priorityBreakdown?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'priorityBreakdown';
        _priorityBreakdown?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ByPriorityResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
