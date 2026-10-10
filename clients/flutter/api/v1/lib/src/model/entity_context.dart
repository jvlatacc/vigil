//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/source_evidence.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'entity_context.g.dart';

/// Free-form entity context; ``source_evidence`` is the one named key.
///
/// Properties:
/// * [sourceEvidence] 
@BuiltValue()
abstract class EntityContext implements Built<EntityContext, EntityContextBuilder> {
  @BuiltValueField(wireName: r'source_evidence')
  SourceEvidence? get sourceEvidence;

  EntityContext._();

  factory EntityContext([void updates(EntityContextBuilder b)]) = _$EntityContext;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(EntityContextBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<EntityContext> get serializer => _$EntityContextSerializer();
}

class _$EntityContextSerializer implements PrimitiveSerializer<EntityContext> {
  @override
  final Iterable<Type> types = const [EntityContext, _$EntityContext];

  @override
  final String wireName = r'EntityContext';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    EntityContext object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.sourceEvidence != null) {
      yield r'source_evidence';
      yield serializers.serialize(
        object.sourceEvidence,
        specifiedType: const FullType.nullable(SourceEvidence),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    EntityContext object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required EntityContextBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'source_evidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(SourceEvidence),
          ) as SourceEvidence?;
          if (valueDes == null) continue;
          result.sourceEvidence.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  EntityContext deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = EntityContextBuilder();
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


