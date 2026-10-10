// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_schema.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseSchema extends CaseSchema {
  @override
  final BuiltList<JsonObject?>? activities;
  @override
  final String? assignee;
  @override
  final String? caseId;
  @override
  final String? createdAt;
  @override
  final String? description;
  @override
  final BuiltList<String>? findingIds;
  @override
  final BuiltList<String>? mitreTechniques;
  @override
  final BuiltList<JsonObject?>? notes;
  @override
  final String? priority;
  @override
  final BuiltList<JsonObject?>? resolutionSteps;
  @override
  final String? status;
  @override
  final BuiltList<String>? tags;
  @override
  final BuiltList<JsonObject?>? timeline;
  @override
  final String? title;
  @override
  final String? updatedAt;

  factory _$CaseSchema([void Function(CaseSchemaBuilder)? updates]) =>
      (CaseSchemaBuilder()..update(updates))._build();

  _$CaseSchema._(
      {this.activities,
      this.assignee,
      this.caseId,
      this.createdAt,
      this.description,
      this.findingIds,
      this.mitreTechniques,
      this.notes,
      this.priority,
      this.resolutionSteps,
      this.status,
      this.tags,
      this.timeline,
      this.title,
      this.updatedAt})
      : super._();
  @override
  CaseSchema rebuild(void Function(CaseSchemaBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseSchemaBuilder toBuilder() => CaseSchemaBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseSchema &&
        activities == other.activities &&
        assignee == other.assignee &&
        caseId == other.caseId &&
        createdAt == other.createdAt &&
        description == other.description &&
        findingIds == other.findingIds &&
        mitreTechniques == other.mitreTechniques &&
        notes == other.notes &&
        priority == other.priority &&
        resolutionSteps == other.resolutionSteps &&
        status == other.status &&
        tags == other.tags &&
        timeline == other.timeline &&
        title == other.title &&
        updatedAt == other.updatedAt;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, activities.hashCode);
    _$hash = $jc(_$hash, assignee.hashCode);
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, findingIds.hashCode);
    _$hash = $jc(_$hash, mitreTechniques.hashCode);
    _$hash = $jc(_$hash, notes.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jc(_$hash, resolutionSteps.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jc(_$hash, timeline.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jc(_$hash, updatedAt.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseSchema')
          ..add('activities', activities)
          ..add('assignee', assignee)
          ..add('caseId', caseId)
          ..add('createdAt', createdAt)
          ..add('description', description)
          ..add('findingIds', findingIds)
          ..add('mitreTechniques', mitreTechniques)
          ..add('notes', notes)
          ..add('priority', priority)
          ..add('resolutionSteps', resolutionSteps)
          ..add('status', status)
          ..add('tags', tags)
          ..add('timeline', timeline)
          ..add('title', title)
          ..add('updatedAt', updatedAt))
        .toString();
  }
}

class CaseSchemaBuilder implements Builder<CaseSchema, CaseSchemaBuilder> {
  _$CaseSchema? _$v;

  ListBuilder<JsonObject?>? _activities;
  ListBuilder<JsonObject?> get activities =>
      _$this._activities ??= ListBuilder<JsonObject?>();
  set activities(ListBuilder<JsonObject?>? activities) =>
      _$this._activities = activities;

  String? _assignee;
  String? get assignee => _$this._assignee;
  set assignee(String? assignee) => _$this._assignee = assignee;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  ListBuilder<String>? _findingIds;
  ListBuilder<String> get findingIds =>
      _$this._findingIds ??= ListBuilder<String>();
  set findingIds(ListBuilder<String>? findingIds) =>
      _$this._findingIds = findingIds;

  ListBuilder<String>? _mitreTechniques;
  ListBuilder<String> get mitreTechniques =>
      _$this._mitreTechniques ??= ListBuilder<String>();
  set mitreTechniques(ListBuilder<String>? mitreTechniques) =>
      _$this._mitreTechniques = mitreTechniques;

  ListBuilder<JsonObject?>? _notes;
  ListBuilder<JsonObject?> get notes =>
      _$this._notes ??= ListBuilder<JsonObject?>();
  set notes(ListBuilder<JsonObject?>? notes) => _$this._notes = notes;

  String? _priority;
  String? get priority => _$this._priority;
  set priority(String? priority) => _$this._priority = priority;

  ListBuilder<JsonObject?>? _resolutionSteps;
  ListBuilder<JsonObject?> get resolutionSteps =>
      _$this._resolutionSteps ??= ListBuilder<JsonObject?>();
  set resolutionSteps(ListBuilder<JsonObject?>? resolutionSteps) =>
      _$this._resolutionSteps = resolutionSteps;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  ListBuilder<JsonObject?>? _timeline;
  ListBuilder<JsonObject?> get timeline =>
      _$this._timeline ??= ListBuilder<JsonObject?>();
  set timeline(ListBuilder<JsonObject?>? timeline) =>
      _$this._timeline = timeline;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  String? _updatedAt;
  String? get updatedAt => _$this._updatedAt;
  set updatedAt(String? updatedAt) => _$this._updatedAt = updatedAt;

  CaseSchemaBuilder() {
    CaseSchema._defaults(this);
  }

  CaseSchemaBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _activities = $v.activities?.toBuilder();
      _assignee = $v.assignee;
      _caseId = $v.caseId;
      _createdAt = $v.createdAt;
      _description = $v.description;
      _findingIds = $v.findingIds?.toBuilder();
      _mitreTechniques = $v.mitreTechniques?.toBuilder();
      _notes = $v.notes?.toBuilder();
      _priority = $v.priority;
      _resolutionSteps = $v.resolutionSteps?.toBuilder();
      _status = $v.status;
      _tags = $v.tags?.toBuilder();
      _timeline = $v.timeline?.toBuilder();
      _title = $v.title;
      _updatedAt = $v.updatedAt;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseSchema other) {
    _$v = other as _$CaseSchema;
  }

  @override
  void update(void Function(CaseSchemaBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseSchema build() => _build();

  _$CaseSchema _build() {
    _$CaseSchema _$result;
    try {
      _$result = _$v ??
          _$CaseSchema._(
            activities: _activities?.build(),
            assignee: assignee,
            caseId: caseId,
            createdAt: createdAt,
            description: description,
            findingIds: _findingIds?.build(),
            mitreTechniques: _mitreTechniques?.build(),
            notes: _notes?.build(),
            priority: priority,
            resolutionSteps: _resolutionSteps?.build(),
            status: status,
            tags: _tags?.build(),
            timeline: _timeline?.build(),
            title: title,
            updatedAt: updatedAt,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'activities';
        _activities?.build();

        _$failedField = 'findingIds';
        _findingIds?.build();
        _$failedField = 'mitreTechniques';
        _mitreTechniques?.build();
        _$failedField = 'notes';
        _notes?.build();

        _$failedField = 'resolutionSteps';
        _resolutionSteps?.build();

        _$failedField = 'tags';
        _tags?.build();
        _$failedField = 'timeline';
        _timeline?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseSchema', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
