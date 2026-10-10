// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'start_run_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$StartRunRequest extends StartRunRequest {
  @override
  final String? arch;
  @override
  final String config;
  @override
  final BuiltMap<String, JsonObject?>? overrides;
  @override
  final String playbook;
  @override
  final String? prompt;
  @override
  final String? runKind;
  @override
  final String? tenantId;

  factory _$StartRunRequest([void Function(StartRunRequestBuilder)? updates]) =>
      (StartRunRequestBuilder()..update(updates))._build();

  _$StartRunRequest._(
      {this.arch,
      required this.config,
      this.overrides,
      required this.playbook,
      this.prompt,
      this.runKind,
      this.tenantId})
      : super._();
  @override
  StartRunRequest rebuild(void Function(StartRunRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  StartRunRequestBuilder toBuilder() => StartRunRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is StartRunRequest &&
        arch == other.arch &&
        config == other.config &&
        overrides == other.overrides &&
        playbook == other.playbook &&
        prompt == other.prompt &&
        runKind == other.runKind &&
        tenantId == other.tenantId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, arch.hashCode);
    _$hash = $jc(_$hash, config.hashCode);
    _$hash = $jc(_$hash, overrides.hashCode);
    _$hash = $jc(_$hash, playbook.hashCode);
    _$hash = $jc(_$hash, prompt.hashCode);
    _$hash = $jc(_$hash, runKind.hashCode);
    _$hash = $jc(_$hash, tenantId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'StartRunRequest')
          ..add('arch', arch)
          ..add('config', config)
          ..add('overrides', overrides)
          ..add('playbook', playbook)
          ..add('prompt', prompt)
          ..add('runKind', runKind)
          ..add('tenantId', tenantId))
        .toString();
  }
}

class StartRunRequestBuilder
    implements Builder<StartRunRequest, StartRunRequestBuilder> {
  _$StartRunRequest? _$v;

  String? _arch;
  String? get arch => _$this._arch;
  set arch(String? arch) => _$this._arch = arch;

  String? _config;
  String? get config => _$this._config;
  set config(String? config) => _$this._config = config;

  MapBuilder<String, JsonObject?>? _overrides;
  MapBuilder<String, JsonObject?> get overrides =>
      _$this._overrides ??= MapBuilder<String, JsonObject?>();
  set overrides(MapBuilder<String, JsonObject?>? overrides) =>
      _$this._overrides = overrides;

  String? _playbook;
  String? get playbook => _$this._playbook;
  set playbook(String? playbook) => _$this._playbook = playbook;

  String? _prompt;
  String? get prompt => _$this._prompt;
  set prompt(String? prompt) => _$this._prompt = prompt;

  String? _runKind;
  String? get runKind => _$this._runKind;
  set runKind(String? runKind) => _$this._runKind = runKind;

  String? _tenantId;
  String? get tenantId => _$this._tenantId;
  set tenantId(String? tenantId) => _$this._tenantId = tenantId;

  StartRunRequestBuilder() {
    StartRunRequest._defaults(this);
  }

  StartRunRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _arch = $v.arch;
      _config = $v.config;
      _overrides = $v.overrides?.toBuilder();
      _playbook = $v.playbook;
      _prompt = $v.prompt;
      _runKind = $v.runKind;
      _tenantId = $v.tenantId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(StartRunRequest other) {
    _$v = other as _$StartRunRequest;
  }

  @override
  void update(void Function(StartRunRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  StartRunRequest build() => _build();

  _$StartRunRequest _build() {
    _$StartRunRequest _$result;
    try {
      _$result = _$v ??
          _$StartRunRequest._(
            arch: arch,
            config: BuiltValueNullFieldError.checkNotNull(
                config, r'StartRunRequest', 'config'),
            overrides: _overrides?.build(),
            playbook: BuiltValueNullFieldError.checkNotNull(
                playbook, r'StartRunRequest', 'playbook'),
            prompt: prompt,
            runKind: runKind,
            tenantId: tenantId,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'overrides';
        _overrides?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'StartRunRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
