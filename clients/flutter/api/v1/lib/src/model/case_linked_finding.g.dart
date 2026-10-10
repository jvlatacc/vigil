// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_linked_finding.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseLinkedFinding extends CaseLinkedFinding {
  @override
  final String? description;
  @override
  final String findingId;
  @override
  final String? sourceLink;
  @override
  final String? title;

  factory _$CaseLinkedFinding(
          [void Function(CaseLinkedFindingBuilder)? updates]) =>
      (CaseLinkedFindingBuilder()..update(updates))._build();

  _$CaseLinkedFinding._(
      {this.description, required this.findingId, this.sourceLink, this.title})
      : super._();
  @override
  CaseLinkedFinding rebuild(void Function(CaseLinkedFindingBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseLinkedFindingBuilder toBuilder() =>
      CaseLinkedFindingBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseLinkedFinding &&
        description == other.description &&
        findingId == other.findingId &&
        sourceLink == other.sourceLink &&
        title == other.title;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, findingId.hashCode);
    _$hash = $jc(_$hash, sourceLink.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseLinkedFinding')
          ..add('description', description)
          ..add('findingId', findingId)
          ..add('sourceLink', sourceLink)
          ..add('title', title))
        .toString();
  }
}

class CaseLinkedFindingBuilder
    implements Builder<CaseLinkedFinding, CaseLinkedFindingBuilder> {
  _$CaseLinkedFinding? _$v;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  String? _findingId;
  String? get findingId => _$this._findingId;
  set findingId(String? findingId) => _$this._findingId = findingId;

  String? _sourceLink;
  String? get sourceLink => _$this._sourceLink;
  set sourceLink(String? sourceLink) => _$this._sourceLink = sourceLink;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  CaseLinkedFindingBuilder() {
    CaseLinkedFinding._defaults(this);
  }

  CaseLinkedFindingBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _description = $v.description;
      _findingId = $v.findingId;
      _sourceLink = $v.sourceLink;
      _title = $v.title;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseLinkedFinding other) {
    _$v = other as _$CaseLinkedFinding;
  }

  @override
  void update(void Function(CaseLinkedFindingBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseLinkedFinding build() => _build();

  _$CaseLinkedFinding _build() {
    final _$result = _$v ??
        _$CaseLinkedFinding._(
          description: description,
          findingId: BuiltValueNullFieldError.checkNotNull(
              findingId, r'CaseLinkedFinding', 'findingId'),
          sourceLink: sourceLink,
          title: title,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
