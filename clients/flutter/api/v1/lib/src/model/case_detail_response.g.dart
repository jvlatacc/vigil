// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_detail_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseDetailResponse extends CaseDetailResponse {
  @override
  final BuiltList<JsonObject?>? activities;
  @override
  final String? assignee;
  @override
  final String? caseId;
  @override
  final CaseClosureView? closure;
  @override
  final String combinedState;
  @override
  final String? createdAt;
  @override
  final String? description;
  @override
  final BuiltList<String>? findingIds;
  @override
  final BuiltList<CaseInvestigationRef>? investigations;
  @override
  final BuiltList<CaseLinkedFinding>? linkedFindings;
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

  factory _$CaseDetailResponse(
          [void Function(CaseDetailResponseBuilder)? updates]) =>
      (CaseDetailResponseBuilder()..update(updates))._build();

  _$CaseDetailResponse._(
      {this.activities,
      this.assignee,
      this.caseId,
      this.closure,
      required this.combinedState,
      this.createdAt,
      this.description,
      this.findingIds,
      this.investigations,
      this.linkedFindings,
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
  CaseDetailResponse rebuild(
          void Function(CaseDetailResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseDetailResponseBuilder toBuilder() =>
      CaseDetailResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseDetailResponse &&
        activities == other.activities &&
        assignee == other.assignee &&
        caseId == other.caseId &&
        closure == other.closure &&
        combinedState == other.combinedState &&
        createdAt == other.createdAt &&
        description == other.description &&
        findingIds == other.findingIds &&
        investigations == other.investigations &&
        linkedFindings == other.linkedFindings &&
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
    _$hash = $jc(_$hash, closure.hashCode);
    _$hash = $jc(_$hash, combinedState.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, findingIds.hashCode);
    _$hash = $jc(_$hash, investigations.hashCode);
    _$hash = $jc(_$hash, linkedFindings.hashCode);
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
    return (newBuiltValueToStringHelper(r'CaseDetailResponse')
          ..add('activities', activities)
          ..add('assignee', assignee)
          ..add('caseId', caseId)
          ..add('closure', closure)
          ..add('combinedState', combinedState)
          ..add('createdAt', createdAt)
          ..add('description', description)
          ..add('findingIds', findingIds)
          ..add('investigations', investigations)
          ..add('linkedFindings', linkedFindings)
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

class CaseDetailResponseBuilder
    implements Builder<CaseDetailResponse, CaseDetailResponseBuilder> {
  _$CaseDetailResponse? _$v;

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

  CaseClosureViewBuilder? _closure;
  CaseClosureViewBuilder get closure =>
      _$this._closure ??= CaseClosureViewBuilder();
  set closure(CaseClosureViewBuilder? closure) => _$this._closure = closure;

  String? _combinedState;
  String? get combinedState => _$this._combinedState;
  set combinedState(String? combinedState) =>
      _$this._combinedState = combinedState;

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

  ListBuilder<CaseInvestigationRef>? _investigations;
  ListBuilder<CaseInvestigationRef> get investigations =>
      _$this._investigations ??= ListBuilder<CaseInvestigationRef>();
  set investigations(ListBuilder<CaseInvestigationRef>? investigations) =>
      _$this._investigations = investigations;

  ListBuilder<CaseLinkedFinding>? _linkedFindings;
  ListBuilder<CaseLinkedFinding> get linkedFindings =>
      _$this._linkedFindings ??= ListBuilder<CaseLinkedFinding>();
  set linkedFindings(ListBuilder<CaseLinkedFinding>? linkedFindings) =>
      _$this._linkedFindings = linkedFindings;

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

  CaseDetailResponseBuilder() {
    CaseDetailResponse._defaults(this);
  }

  CaseDetailResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _activities = $v.activities?.toBuilder();
      _assignee = $v.assignee;
      _caseId = $v.caseId;
      _closure = $v.closure?.toBuilder();
      _combinedState = $v.combinedState;
      _createdAt = $v.createdAt;
      _description = $v.description;
      _findingIds = $v.findingIds?.toBuilder();
      _investigations = $v.investigations?.toBuilder();
      _linkedFindings = $v.linkedFindings?.toBuilder();
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
  void replace(CaseDetailResponse other) {
    _$v = other as _$CaseDetailResponse;
  }

  @override
  void update(void Function(CaseDetailResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseDetailResponse build() => _build();

  _$CaseDetailResponse _build() {
    _$CaseDetailResponse _$result;
    try {
      _$result = _$v ??
          _$CaseDetailResponse._(
            activities: _activities?.build(),
            assignee: assignee,
            caseId: caseId,
            closure: _closure?.build(),
            combinedState: BuiltValueNullFieldError.checkNotNull(
                combinedState, r'CaseDetailResponse', 'combinedState'),
            createdAt: createdAt,
            description: description,
            findingIds: _findingIds?.build(),
            investigations: _investigations?.build(),
            linkedFindings: _linkedFindings?.build(),
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

        _$failedField = 'closure';
        _closure?.build();

        _$failedField = 'findingIds';
        _findingIds?.build();
        _$failedField = 'investigations';
        _investigations?.build();
        _$failedField = 'linkedFindings';
        _linkedFindings?.build();
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
            r'CaseDetailResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
