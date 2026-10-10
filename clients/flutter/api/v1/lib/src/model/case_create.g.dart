// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_create.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseCreate extends CaseCreate {
  @override
  final String? description;
  @override
  final BuiltList<String> findingIds;
  @override
  final String? priority;
  @override
  final String? status;
  @override
  final String title;

  factory _$CaseCreate([void Function(CaseCreateBuilder)? updates]) =>
      (CaseCreateBuilder()..update(updates))._build();

  _$CaseCreate._(
      {this.description,
      required this.findingIds,
      this.priority,
      this.status,
      required this.title})
      : super._();
  @override
  CaseCreate rebuild(void Function(CaseCreateBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseCreateBuilder toBuilder() => CaseCreateBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseCreate &&
        description == other.description &&
        findingIds == other.findingIds &&
        priority == other.priority &&
        status == other.status &&
        title == other.title;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, findingIds.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseCreate')
          ..add('description', description)
          ..add('findingIds', findingIds)
          ..add('priority', priority)
          ..add('status', status)
          ..add('title', title))
        .toString();
  }
}

class CaseCreateBuilder implements Builder<CaseCreate, CaseCreateBuilder> {
  _$CaseCreate? _$v;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  ListBuilder<String>? _findingIds;
  ListBuilder<String> get findingIds =>
      _$this._findingIds ??= ListBuilder<String>();
  set findingIds(ListBuilder<String>? findingIds) =>
      _$this._findingIds = findingIds;

  String? _priority;
  String? get priority => _$this._priority;
  set priority(String? priority) => _$this._priority = priority;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  CaseCreateBuilder() {
    CaseCreate._defaults(this);
  }

  CaseCreateBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _description = $v.description;
      _findingIds = $v.findingIds.toBuilder();
      _priority = $v.priority;
      _status = $v.status;
      _title = $v.title;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseCreate other) {
    _$v = other as _$CaseCreate;
  }

  @override
  void update(void Function(CaseCreateBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseCreate build() => _build();

  _$CaseCreate _build() {
    _$CaseCreate _$result;
    try {
      _$result = _$v ??
          _$CaseCreate._(
            description: description,
            findingIds: findingIds.build(),
            priority: priority,
            status: status,
            title: BuiltValueNullFieldError.checkNotNull(
                title, r'CaseCreate', 'title'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'findingIds';
        findingIds.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseCreate', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
