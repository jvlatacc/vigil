// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'ioc_add.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IOCAdd extends IOCAdd {
  @override
  final num? confidence;
  @override
  final String? context;
  @override
  final String iocType;
  @override
  final String? source_;
  @override
  final BuiltList<String>? tags;
  @override
  final String? threatLevel;
  @override
  final String value;

  factory _$IOCAdd([void Function(IOCAddBuilder)? updates]) =>
      (IOCAddBuilder()..update(updates))._build();

  _$IOCAdd._(
      {this.confidence,
      this.context,
      required this.iocType,
      this.source_,
      this.tags,
      this.threatLevel,
      required this.value})
      : super._();
  @override
  IOCAdd rebuild(void Function(IOCAddBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IOCAddBuilder toBuilder() => IOCAddBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IOCAdd &&
        confidence == other.confidence &&
        context == other.context &&
        iocType == other.iocType &&
        source_ == other.source_ &&
        tags == other.tags &&
        threatLevel == other.threatLevel &&
        value == other.value;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, context.hashCode);
    _$hash = $jc(_$hash, iocType.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jc(_$hash, threatLevel.hashCode);
    _$hash = $jc(_$hash, value.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IOCAdd')
          ..add('confidence', confidence)
          ..add('context', context)
          ..add('iocType', iocType)
          ..add('source_', source_)
          ..add('tags', tags)
          ..add('threatLevel', threatLevel)
          ..add('value', value))
        .toString();
  }
}

class IOCAddBuilder implements Builder<IOCAdd, IOCAddBuilder> {
  _$IOCAdd? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _context;
  String? get context => _$this._context;
  set context(String? context) => _$this._context = context;

  String? _iocType;
  String? get iocType => _$this._iocType;
  set iocType(String? iocType) => _$this._iocType = iocType;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  String? _threatLevel;
  String? get threatLevel => _$this._threatLevel;
  set threatLevel(String? threatLevel) => _$this._threatLevel = threatLevel;

  String? _value;
  String? get value => _$this._value;
  set value(String? value) => _$this._value = value;

  IOCAddBuilder() {
    IOCAdd._defaults(this);
  }

  IOCAddBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confidence = $v.confidence;
      _context = $v.context;
      _iocType = $v.iocType;
      _source_ = $v.source_;
      _tags = $v.tags?.toBuilder();
      _threatLevel = $v.threatLevel;
      _value = $v.value;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IOCAdd other) {
    _$v = other as _$IOCAdd;
  }

  @override
  void update(void Function(IOCAddBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IOCAdd build() => _build();

  _$IOCAdd _build() {
    _$IOCAdd _$result;
    try {
      _$result = _$v ??
          _$IOCAdd._(
            confidence: confidence,
            context: context,
            iocType: BuiltValueNullFieldError.checkNotNull(
                iocType, r'IOCAdd', 'iocType'),
            source_: source_,
            tags: _tags?.build(),
            threatLevel: threatLevel,
            value: BuiltValueNullFieldError.checkNotNull(
                value, r'IOCAdd', 'value'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'tags';
        _tags?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'IOCAdd', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
