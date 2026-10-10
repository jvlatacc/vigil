//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_closure_view.g.dart';

/// What the closed summary shows. ``verdict`` is the stated reason.
///
/// Properties:
/// * [closedAt] 
/// * [closedBy] 
/// * [closedByKind] 
/// * [closureCategory] 
/// * [verdict] 
@BuiltValue()
abstract class CaseClosureView implements Built<CaseClosureView, CaseClosureViewBuilder> {
  @BuiltValueField(wireName: r'closed_at')
  String? get closedAt;

  @BuiltValueField(wireName: r'closed_by')
  String get closedBy;

  @BuiltValueField(wireName: r'closed_by_kind')
  String get closedByKind;

  @BuiltValueField(wireName: r'closure_category')
  String get closureCategory;

  @BuiltValueField(wireName: r'verdict')
  String? get verdict;

  CaseClosureView._();

  factory CaseClosureView([void updates(CaseClosureViewBuilder b)]) = _$CaseClosureView;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseClosureViewBuilder b) => b
      ..verdict = '';

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseClosureView> get serializer => _$CaseClosureViewSerializer();
}

class _$CaseClosureViewSerializer implements PrimitiveSerializer<CaseClosureView> {
  @override
  final Iterable<Type> types = const [CaseClosureView, _$CaseClosureView];

  @override
  final String wireName = r'CaseClosureView';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseClosureView object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.closedAt != null) {
      yield r'closed_at';
      yield serializers.serialize(
        object.closedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'closed_by';
    yield serializers.serialize(
      object.closedBy,
      specifiedType: const FullType(String),
    );
    yield r'closed_by_kind';
    yield serializers.serialize(
      object.closedByKind,
      specifiedType: const FullType(String),
    );
    yield r'closure_category';
    yield serializers.serialize(
      object.closureCategory,
      specifiedType: const FullType(String),
    );
    if (object.verdict != null) {
      yield r'verdict';
      yield serializers.serialize(
        object.verdict,
        specifiedType: const FullType(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseClosureView object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseClosureViewBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'closed_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closedAt = valueDes;
          break;
        case r'closed_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.closedBy = valueDes;
          break;
        case r'closed_by_kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.closedByKind = valueDes;
          break;
        case r'closure_category':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.closureCategory = valueDes;
          break;
        case r'verdict':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.verdict = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseClosureView deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseClosureViewBuilder();
    final serializedList = (serialized as Iterable<Object?>).toList();
    final unhandled = <Object?>[];
    _deserializeProperties(
      serializers,
      serialized,
      specifiedType: specifiedType,
      serializedList: serializedList,
      unhandled: unhandled,
      result: result,
    );
    return result.build();
  }
}


