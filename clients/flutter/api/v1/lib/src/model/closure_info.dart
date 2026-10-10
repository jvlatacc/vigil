//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/closure_category.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'closure_info.g.dart';

/// Close case with metadata.  No ``closed_by``: who closed it is the authenticated principal, not something a client says about itself. Episodic memory reads it as Trust (#733), and a client-supplied name would let any caller claim an analyst concluded.
///
/// Properties:
/// * [closureCategory] 
/// * [closureNotes] 
/// * [executiveSummary] 
/// * [falsePositiveReason] 
/// * [lessonsLearned] 
/// * [recommendations] 
/// * [rootCause] 
@BuiltValue()
abstract class ClosureInfo implements Built<ClosureInfo, ClosureInfoBuilder> {
  @BuiltValueField(wireName: r'closure_category')
  ClosureCategory get closureCategory;
  // enum closureCategoryEnum {  resolved,  false_positive,  duplicate,  unable_to_resolve,  unspecified,  };

  @BuiltValueField(wireName: r'closure_notes')
  String? get closureNotes;

  @BuiltValueField(wireName: r'executive_summary')
  String? get executiveSummary;

  @BuiltValueField(wireName: r'false_positive_reason')
  String? get falsePositiveReason;

  @BuiltValueField(wireName: r'lessons_learned')
  String? get lessonsLearned;

  @BuiltValueField(wireName: r'recommendations')
  String? get recommendations;

  @BuiltValueField(wireName: r'root_cause')
  String? get rootCause;

  ClosureInfo._();

  factory ClosureInfo([void updates(ClosureInfoBuilder b)]) = _$ClosureInfo;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ClosureInfoBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ClosureInfo> get serializer => _$ClosureInfoSerializer();
}

class _$ClosureInfoSerializer implements PrimitiveSerializer<ClosureInfo> {
  @override
  final Iterable<Type> types = const [ClosureInfo, _$ClosureInfo];

  @override
  final String wireName = r'ClosureInfo';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ClosureInfo object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'closure_category';
    yield serializers.serialize(
      object.closureCategory,
      specifiedType: const FullType(ClosureCategory),
    );
    if (object.closureNotes != null) {
      yield r'closure_notes';
      yield serializers.serialize(
        object.closureNotes,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.executiveSummary != null) {
      yield r'executive_summary';
      yield serializers.serialize(
        object.executiveSummary,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.falsePositiveReason != null) {
      yield r'false_positive_reason';
      yield serializers.serialize(
        object.falsePositiveReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.lessonsLearned != null) {
      yield r'lessons_learned';
      yield serializers.serialize(
        object.lessonsLearned,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.recommendations != null) {
      yield r'recommendations';
      yield serializers.serialize(
        object.recommendations,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rootCause != null) {
      yield r'root_cause';
      yield serializers.serialize(
        object.rootCause,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ClosureInfo object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ClosureInfoBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'closure_category':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ClosureCategory),
          ) as ClosureCategory;
          result.closureCategory = valueDes;
          break;
        case r'closure_notes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.closureNotes = valueDes;
          break;
        case r'executive_summary':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.executiveSummary = valueDes;
          break;
        case r'false_positive_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.falsePositiveReason = valueDes;
          break;
        case r'lessons_learned':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.lessonsLearned = valueDes;
          break;
        case r'recommendations':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.recommendations = valueDes;
          break;
        case r'root_cause':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rootCause = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ClosureInfo deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ClosureInfoBuilder();
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


