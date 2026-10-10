//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'closure_category.g.dart';

/// What closing the Case determined.  ``UNSPECIFIED`` is the one that is not a determination. It exists because the console closes a Case by setting its status and asks for no category, and the alternative to recording that plainly is either dropping the close from memory or picking a determination on the analyst's behalf. Recorded, it reads as what it is — closed, no reason stated — and becomes an inconclusive Verdict rather than a claim nobody made.
class ClosureCategory extends EnumClass {

  @BuiltValueEnumConst(wireName: r'resolved')
  static const ClosureCategory resolved = _$resolved;
  @BuiltValueEnumConst(wireName: r'false_positive')
  static const ClosureCategory falsePositive = _$falsePositive;
  @BuiltValueEnumConst(wireName: r'duplicate')
  static const ClosureCategory duplicate = _$duplicate;
  @BuiltValueEnumConst(wireName: r'unable_to_resolve')
  static const ClosureCategory unableToResolve = _$unableToResolve;
  @BuiltValueEnumConst(wireName: r'unspecified')
  static const ClosureCategory unspecified = _$unspecified;

  static Serializer<ClosureCategory> get serializer => _$closureCategorySerializer;

  const ClosureCategory._(String name): super(name);

  static BuiltSet<ClosureCategory> get values => _$values;
  static ClosureCategory valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class ClosureCategoryMixin = Object with _$ClosureCategoryMixin;

