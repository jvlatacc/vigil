// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'needs_you_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$NeedsYouResponse extends NeedsYouResponse {
  @override
  final int count;
  @override
  final BuiltList<NeedsYouItem>? items;

  factory _$NeedsYouResponse(
          [void Function(NeedsYouResponseBuilder)? updates]) =>
      (NeedsYouResponseBuilder()..update(updates))._build();

  _$NeedsYouResponse._({required this.count, this.items}) : super._();
  @override
  NeedsYouResponse rebuild(void Function(NeedsYouResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  NeedsYouResponseBuilder toBuilder() =>
      NeedsYouResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is NeedsYouResponse &&
        count == other.count &&
        items == other.items;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jc(_$hash, items.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'NeedsYouResponse')
          ..add('count', count)
          ..add('items', items))
        .toString();
  }
}

class NeedsYouResponseBuilder
    implements Builder<NeedsYouResponse, NeedsYouResponseBuilder> {
  _$NeedsYouResponse? _$v;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  ListBuilder<NeedsYouItem>? _items;
  ListBuilder<NeedsYouItem> get items =>
      _$this._items ??= ListBuilder<NeedsYouItem>();
  set items(ListBuilder<NeedsYouItem>? items) => _$this._items = items;

  NeedsYouResponseBuilder() {
    NeedsYouResponse._defaults(this);
  }

  NeedsYouResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _count = $v.count;
      _items = $v.items?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(NeedsYouResponse other) {
    _$v = other as _$NeedsYouResponse;
  }

  @override
  void update(void Function(NeedsYouResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  NeedsYouResponse build() => _build();

  _$NeedsYouResponse _build() {
    _$NeedsYouResponse _$result;
    try {
      _$result = _$v ??
          _$NeedsYouResponse._(
            count: BuiltValueNullFieldError.checkNotNull(
                count, r'NeedsYouResponse', 'count'),
            items: _items?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'items';
        _items?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'NeedsYouResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
