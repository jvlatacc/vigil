// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'workflow_detail_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$WorkflowDetailResponse extends WorkflowDetailResponse {
  @override
  final BuiltMap<String, JsonObject?>? agent;
  @override
  final BuiltList<String>? agents;
  @override
  final String body;
  @override
  final BuiltMap<String, String>? checkpoints;
  @override
  final String? description;
  @override
  final bool huntLike;
  @override
  final String id;
  @override
  final String name;
  @override
  final BuiltList<String>? objectives;
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? phases;
  @override
  final String runKind;
  @override
  final String source_;
  @override
  final BuiltList<String>? toolsUsed;
  @override
  final BuiltList<String>? triggerExamples;
  @override
  final String? useCase;
  @override
  final int? version;

  factory _$WorkflowDetailResponse(
          [void Function(WorkflowDetailResponseBuilder)? updates]) =>
      (WorkflowDetailResponseBuilder()..update(updates))._build();

  _$WorkflowDetailResponse._(
      {this.agent,
      this.agents,
      required this.body,
      this.checkpoints,
      this.description,
      required this.huntLike,
      required this.id,
      required this.name,
      this.objectives,
      this.phases,
      required this.runKind,
      required this.source_,
      this.toolsUsed,
      this.triggerExamples,
      this.useCase,
      this.version})
      : super._();
  @override
  WorkflowDetailResponse rebuild(
          void Function(WorkflowDetailResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  WorkflowDetailResponseBuilder toBuilder() =>
      WorkflowDetailResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is WorkflowDetailResponse &&
        agent == other.agent &&
        agents == other.agents &&
        body == other.body &&
        checkpoints == other.checkpoints &&
        description == other.description &&
        huntLike == other.huntLike &&
        id == other.id &&
        name == other.name &&
        objectives == other.objectives &&
        phases == other.phases &&
        runKind == other.runKind &&
        source_ == other.source_ &&
        toolsUsed == other.toolsUsed &&
        triggerExamples == other.triggerExamples &&
        useCase == other.useCase &&
        version == other.version;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, agent.hashCode);
    _$hash = $jc(_$hash, agents.hashCode);
    _$hash = $jc(_$hash, body.hashCode);
    _$hash = $jc(_$hash, checkpoints.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, huntLike.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, objectives.hashCode);
    _$hash = $jc(_$hash, phases.hashCode);
    _$hash = $jc(_$hash, runKind.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, toolsUsed.hashCode);
    _$hash = $jc(_$hash, triggerExamples.hashCode);
    _$hash = $jc(_$hash, useCase.hashCode);
    _$hash = $jc(_$hash, version.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'WorkflowDetailResponse')
          ..add('agent', agent)
          ..add('agents', agents)
          ..add('body', body)
          ..add('checkpoints', checkpoints)
          ..add('description', description)
          ..add('huntLike', huntLike)
          ..add('id', id)
          ..add('name', name)
          ..add('objectives', objectives)
          ..add('phases', phases)
          ..add('runKind', runKind)
          ..add('source_', source_)
          ..add('toolsUsed', toolsUsed)
          ..add('triggerExamples', triggerExamples)
          ..add('useCase', useCase)
          ..add('version', version))
        .toString();
  }
}

class WorkflowDetailResponseBuilder
    implements Builder<WorkflowDetailResponse, WorkflowDetailResponseBuilder> {
  _$WorkflowDetailResponse? _$v;

  MapBuilder<String, JsonObject?>? _agent;
  MapBuilder<String, JsonObject?> get agent =>
      _$this._agent ??= MapBuilder<String, JsonObject?>();
  set agent(MapBuilder<String, JsonObject?>? agent) => _$this._agent = agent;

  ListBuilder<String>? _agents;
  ListBuilder<String> get agents => _$this._agents ??= ListBuilder<String>();
  set agents(ListBuilder<String>? agents) => _$this._agents = agents;

  String? _body;
  String? get body => _$this._body;
  set body(String? body) => _$this._body = body;

  MapBuilder<String, String>? _checkpoints;
  MapBuilder<String, String> get checkpoints =>
      _$this._checkpoints ??= MapBuilder<String, String>();
  set checkpoints(MapBuilder<String, String>? checkpoints) =>
      _$this._checkpoints = checkpoints;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  bool? _huntLike;
  bool? get huntLike => _$this._huntLike;
  set huntLike(bool? huntLike) => _$this._huntLike = huntLike;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  ListBuilder<String>? _objectives;
  ListBuilder<String> get objectives =>
      _$this._objectives ??= ListBuilder<String>();
  set objectives(ListBuilder<String>? objectives) =>
      _$this._objectives = objectives;

  ListBuilder<BuiltMap<String, JsonObject?>>? _phases;
  ListBuilder<BuiltMap<String, JsonObject?>> get phases =>
      _$this._phases ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set phases(ListBuilder<BuiltMap<String, JsonObject?>>? phases) =>
      _$this._phases = phases;

  String? _runKind;
  String? get runKind => _$this._runKind;
  set runKind(String? runKind) => _$this._runKind = runKind;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  ListBuilder<String>? _toolsUsed;
  ListBuilder<String> get toolsUsed =>
      _$this._toolsUsed ??= ListBuilder<String>();
  set toolsUsed(ListBuilder<String>? toolsUsed) =>
      _$this._toolsUsed = toolsUsed;

  ListBuilder<String>? _triggerExamples;
  ListBuilder<String> get triggerExamples =>
      _$this._triggerExamples ??= ListBuilder<String>();
  set triggerExamples(ListBuilder<String>? triggerExamples) =>
      _$this._triggerExamples = triggerExamples;

  String? _useCase;
  String? get useCase => _$this._useCase;
  set useCase(String? useCase) => _$this._useCase = useCase;

  int? _version;
  int? get version => _$this._version;
  set version(int? version) => _$this._version = version;

  WorkflowDetailResponseBuilder() {
    WorkflowDetailResponse._defaults(this);
  }

  WorkflowDetailResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _agent = $v.agent?.toBuilder();
      _agents = $v.agents?.toBuilder();
      _body = $v.body;
      _checkpoints = $v.checkpoints?.toBuilder();
      _description = $v.description;
      _huntLike = $v.huntLike;
      _id = $v.id;
      _name = $v.name;
      _objectives = $v.objectives?.toBuilder();
      _phases = $v.phases?.toBuilder();
      _runKind = $v.runKind;
      _source_ = $v.source_;
      _toolsUsed = $v.toolsUsed?.toBuilder();
      _triggerExamples = $v.triggerExamples?.toBuilder();
      _useCase = $v.useCase;
      _version = $v.version;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(WorkflowDetailResponse other) {
    _$v = other as _$WorkflowDetailResponse;
  }

  @override
  void update(void Function(WorkflowDetailResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  WorkflowDetailResponse build() => _build();

  _$WorkflowDetailResponse _build() {
    _$WorkflowDetailResponse _$result;
    try {
      _$result = _$v ??
          _$WorkflowDetailResponse._(
            agent: _agent?.build(),
            agents: _agents?.build(),
            body: BuiltValueNullFieldError.checkNotNull(
                body, r'WorkflowDetailResponse', 'body'),
            checkpoints: _checkpoints?.build(),
            description: description,
            huntLike: BuiltValueNullFieldError.checkNotNull(
                huntLike, r'WorkflowDetailResponse', 'huntLike'),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'WorkflowDetailResponse', 'id'),
            name: BuiltValueNullFieldError.checkNotNull(
                name, r'WorkflowDetailResponse', 'name'),
            objectives: _objectives?.build(),
            phases: _phases?.build(),
            runKind: BuiltValueNullFieldError.checkNotNull(
                runKind, r'WorkflowDetailResponse', 'runKind'),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'WorkflowDetailResponse', 'source_'),
            toolsUsed: _toolsUsed?.build(),
            triggerExamples: _triggerExamples?.build(),
            useCase: useCase,
            version: version,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'agent';
        _agent?.build();
        _$failedField = 'agents';
        _agents?.build();

        _$failedField = 'checkpoints';
        _checkpoints?.build();

        _$failedField = 'objectives';
        _objectives?.build();
        _$failedField = 'phases';
        _phases?.build();

        _$failedField = 'toolsUsed';
        _toolsUsed?.build();
        _$failedField = 'triggerExamples';
        _triggerExamples?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'WorkflowDetailResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
