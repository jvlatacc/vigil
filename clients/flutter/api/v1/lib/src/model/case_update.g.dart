// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_update.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseUpdate extends CaseUpdate {
  @override
  final String? assignee;
  @override
  final String? description;
  @override
  final String? notes;
  @override
  final String? priority;
  @override
  final String? status;
  @override
  final String? title;

  factory _$CaseUpdate([void Function(CaseUpdateBuilder)? updates]) =>
      (CaseUpdateBuilder()..update(updates))._build();

  _$CaseUpdate._(
      {this.assignee,
      this.description,
      this.notes,
      this.priority,
      this.status,
      this.title})
      : super._();
  @override
  CaseUpdate rebuild(void Function(CaseUpdateBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseUpdateBuilder toBuilder() => CaseUpdateBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseUpdate &&
        assignee == other.assignee &&
        description == other.description &&
        notes == other.notes &&
        priority == other.priority &&
        status == other.status &&
        title == other.title;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, assignee.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, notes.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseUpdate')
          ..add('assignee', assignee)
          ..add('description', description)
          ..add('notes', notes)
          ..add('priority', priority)
          ..add('status', status)
          ..add('title', title))
        .toString();
  }
}

class CaseUpdateBuilder implements Builder<CaseUpdate, CaseUpdateBuilder> {
  _$CaseUpdate? _$v;

  String? _assignee;
  String? get assignee => _$this._assignee;
  set assignee(String? assignee) => _$this._assignee = assignee;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  String? _notes;
  String? get notes => _$this._notes;
  set notes(String? notes) => _$this._notes = notes;

  String? _priority;
  String? get priority => _$this._priority;
  set priority(String? priority) => _$this._priority = priority;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  CaseUpdateBuilder() {
    CaseUpdate._defaults(this);
  }

  CaseUpdateBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _assignee = $v.assignee;
      _description = $v.description;
      _notes = $v.notes;
      _priority = $v.priority;
      _status = $v.status;
      _title = $v.title;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseUpdate other) {
    _$v = other as _$CaseUpdate;
  }

  @override
  void update(void Function(CaseUpdateBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseUpdate build() => _build();

  _$CaseUpdate _build() {
    final _$result = _$v ??
        _$CaseUpdate._(
          assignee: assignee,
          description: description,
          notes: notes,
          priority: priority,
          status: status,
          title: title,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
