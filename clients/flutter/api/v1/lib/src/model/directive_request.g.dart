// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'directive_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$DirectiveRequest extends DirectiveRequest {
  @override
  final String? actor;
  @override
  final BuiltMap<String, JsonObject?>? fields;
  @override
  final String kind;
  @override
  final String? text;

  factory _$DirectiveRequest(
          [void Function(DirectiveRequestBuilder)? updates]) =>
      (DirectiveRequestBuilder()..update(updates))._build();

  _$DirectiveRequest._({this.actor, this.fields, required this.kind, this.text})
      : super._();
  @override
  DirectiveRequest rebuild(void Function(DirectiveRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  DirectiveRequestBuilder toBuilder() =>
      DirectiveRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is DirectiveRequest &&
        actor == other.actor &&
        fields == other.fields &&
        kind == other.kind &&
        text == other.text;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, actor.hashCode);
    _$hash = $jc(_$hash, fields.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'DirectiveRequest')
          ..add('actor', actor)
          ..add('fields', fields)
          ..add('kind', kind)
          ..add('text', text))
        .toString();
  }
}

class DirectiveRequestBuilder
    implements Builder<DirectiveRequest, DirectiveRequestBuilder> {
  _$DirectiveRequest? _$v;

  String? _actor;
  String? get actor => _$this._actor;
  set actor(String? actor) => _$this._actor = actor;

  MapBuilder<String, JsonObject?>? _fields;
  MapBuilder<String, JsonObject?> get fields =>
      _$this._fields ??= MapBuilder<String, JsonObject?>();
  set fields(MapBuilder<String, JsonObject?>? fields) =>
      _$this._fields = fields;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  DirectiveRequestBuilder() {
    DirectiveRequest._defaults(this);
  }

  DirectiveRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _actor = $v.actor;
      _fields = $v.fields?.toBuilder();
      _kind = $v.kind;
      _text = $v.text;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(DirectiveRequest other) {
    _$v = other as _$DirectiveRequest;
  }

  @override
  void update(void Function(DirectiveRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  DirectiveRequest build() => _build();

  _$DirectiveRequest _build() {
    _$DirectiveRequest _$result;
    try {
      _$result = _$v ??
          _$DirectiveRequest._(
            actor: actor,
            fields: _fields?.build(),
            kind: BuiltValueNullFieldError.checkNotNull(
                kind, r'DirectiveRequest', 'kind'),
            text: text,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'fields';
        _fields?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'DirectiveRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
