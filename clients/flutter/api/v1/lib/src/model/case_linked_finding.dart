//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_linked_finding.g.dart';

/// One finding the case already links, and the source door when one exists.
///
/// Properties:
/// * [description] 
/// * [findingId] 
/// * [sourceLink] 
/// * [title] 
@BuiltValue()
abstract class CaseLinkedFinding implements Built<CaseLinkedFinding, CaseLinkedFindingBuilder> {
  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'finding_id')
  String get findingId;

  @BuiltValueField(wireName: r'source_link')
  String? get sourceLink;

  @BuiltValueField(wireName: r'title')
  String? get title;

  CaseLinkedFinding._();

  factory CaseLinkedFinding([void updates(CaseLinkedFindingBuilder b)]) = _$CaseLinkedFinding;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseLinkedFindingBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseLinkedFinding> get serializer => _$CaseLinkedFindingSerializer();
}

class _$CaseLinkedFindingSerializer implements PrimitiveSerializer<CaseLinkedFinding> {
  @override
  final Iterable<Type> types = const [CaseLinkedFinding, _$CaseLinkedFinding];

  @override
  final String wireName = r'CaseLinkedFinding';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseLinkedFinding object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'finding_id';
    yield serializers.serialize(
      object.findingId,
      specifiedType: const FullType(String),
    );
    if (object.sourceLink != null) {
      yield r'source_link';
      yield serializers.serialize(
        object.sourceLink,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.title != null) {
      yield r'title';
      yield serializers.serialize(
        object.title,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseLinkedFinding object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseLinkedFindingBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'finding_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.findingId = valueDes;
          break;
        case r'source_link':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.sourceLink = valueDes;
          break;
        case r'title':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.title = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseLinkedFinding deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseLinkedFindingBuilder();
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


