// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'evidence_add.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$EvidenceAdd extends EvidenceAdd {
  @override
  final String collectedBy;
  @override
  final String? description;
  @override
  final String evidenceType;
  @override
  final String? filePath;
  @override
  final String name;
  @override
  final String? source_;
  @override
  final BuiltList<String>? tags;

  factory _$EvidenceAdd([void Function(EvidenceAddBuilder)? updates]) =>
      (EvidenceAddBuilder()..update(updates))._build();

  _$EvidenceAdd._(
      {required this.collectedBy,
      this.description,
      required this.evidenceType,
      this.filePath,
      required this.name,
      this.source_,
      this.tags})
      : super._();
  @override
  EvidenceAdd rebuild(void Function(EvidenceAddBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  EvidenceAddBuilder toBuilder() => EvidenceAddBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is EvidenceAdd &&
        collectedBy == other.collectedBy &&
        description == other.description &&
        evidenceType == other.evidenceType &&
        filePath == other.filePath &&
        name == other.name &&
        source_ == other.source_ &&
        tags == other.tags;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, collectedBy.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, evidenceType.hashCode);
    _$hash = $jc(_$hash, filePath.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'EvidenceAdd')
          ..add('collectedBy', collectedBy)
          ..add('description', description)
          ..add('evidenceType', evidenceType)
          ..add('filePath', filePath)
          ..add('name', name)
          ..add('source_', source_)
          ..add('tags', tags))
        .toString();
  }
}

class EvidenceAddBuilder implements Builder<EvidenceAdd, EvidenceAddBuilder> {
  _$EvidenceAdd? _$v;

  String? _collectedBy;
  String? get collectedBy => _$this._collectedBy;
  set collectedBy(String? collectedBy) => _$this._collectedBy = collectedBy;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  String? _evidenceType;
  String? get evidenceType => _$this._evidenceType;
  set evidenceType(String? evidenceType) => _$this._evidenceType = evidenceType;

  String? _filePath;
  String? get filePath => _$this._filePath;
  set filePath(String? filePath) => _$this._filePath = filePath;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  EvidenceAddBuilder() {
    EvidenceAdd._defaults(this);
  }

  EvidenceAddBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _collectedBy = $v.collectedBy;
      _description = $v.description;
      _evidenceType = $v.evidenceType;
      _filePath = $v.filePath;
      _name = $v.name;
      _source_ = $v.source_;
      _tags = $v.tags?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(EvidenceAdd other) {
    _$v = other as _$EvidenceAdd;
  }

  @override
  void update(void Function(EvidenceAddBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  EvidenceAdd build() => _build();

  _$EvidenceAdd _build() {
    _$EvidenceAdd _$result;
    try {
      _$result = _$v ??
          _$EvidenceAdd._(
            collectedBy: BuiltValueNullFieldError.checkNotNull(
                collectedBy, r'EvidenceAdd', 'collectedBy'),
            description: description,
            evidenceType: BuiltValueNullFieldError.checkNotNull(
                evidenceType, r'EvidenceAdd', 'evidenceType'),
            filePath: filePath,
            name: BuiltValueNullFieldError.checkNotNull(
                name, r'EvidenceAdd', 'name'),
            source_: source_,
            tags: _tags?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'tags';
        _tags?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'EvidenceAdd', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
