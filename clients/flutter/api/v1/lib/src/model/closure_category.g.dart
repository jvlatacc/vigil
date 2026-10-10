// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'closure_category.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const ClosureCategory _$resolved = const ClosureCategory._('resolved');
const ClosureCategory _$falsePositive =
    const ClosureCategory._('falsePositive');
const ClosureCategory _$duplicate = const ClosureCategory._('duplicate');
const ClosureCategory _$unableToResolve =
    const ClosureCategory._('unableToResolve');
const ClosureCategory _$unspecified = const ClosureCategory._('unspecified');

ClosureCategory _$valueOf(String name) {
  switch (name) {
    case 'resolved':
      return _$resolved;
    case 'falsePositive':
      return _$falsePositive;
    case 'duplicate':
      return _$duplicate;
    case 'unableToResolve':
      return _$unableToResolve;
    case 'unspecified':
      return _$unspecified;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<ClosureCategory> _$values =
    BuiltSet<ClosureCategory>(const <ClosureCategory>[
  _$resolved,
  _$falsePositive,
  _$duplicate,
  _$unableToResolve,
  _$unspecified,
]);

class _$ClosureCategoryMeta {
  const _$ClosureCategoryMeta();
  ClosureCategory get resolved => _$resolved;
  ClosureCategory get falsePositive => _$falsePositive;
  ClosureCategory get duplicate => _$duplicate;
  ClosureCategory get unableToResolve => _$unableToResolve;
  ClosureCategory get unspecified => _$unspecified;
  ClosureCategory valueOf(String name) => _$valueOf(name);
  BuiltSet<ClosureCategory> get values => _$values;
}

abstract class _$ClosureCategoryMixin {
  // ignore: non_constant_identifier_names
  _$ClosureCategoryMeta get ClosureCategory => const _$ClosureCategoryMeta();
}

Serializer<ClosureCategory> _$closureCategorySerializer =
    _$ClosureCategorySerializer();

class _$ClosureCategorySerializer
    implements PrimitiveSerializer<ClosureCategory> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'resolved': 'resolved',
    'falsePositive': 'false_positive',
    'duplicate': 'duplicate',
    'unableToResolve': 'unable_to_resolve',
    'unspecified': 'unspecified',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'resolved': 'resolved',
    'false_positive': 'falsePositive',
    'duplicate': 'duplicate',
    'unable_to_resolve': 'unableToResolve',
    'unspecified': 'unspecified',
  };

  @override
  final Iterable<Type> types = const <Type>[ClosureCategory];
  @override
  final String wireName = 'ClosureCategory';

  @override
  Object serialize(Serializers serializers, ClosureCategory object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  ClosureCategory deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      ClosureCategory.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
