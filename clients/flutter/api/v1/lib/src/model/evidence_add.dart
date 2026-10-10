//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'evidence_add.g.dart';

/// Add evidence to case.
///
/// Properties:
/// * [collectedBy] 
/// * [description] 
/// * [evidenceType] 
/// * [filePath] 
/// * [name] 
/// * [source_] 
/// * [tags] 
@BuiltValue()
abstract class EvidenceAdd implements Built<EvidenceAdd, EvidenceAddBuilder> {
  @BuiltValueField(wireName: r'collected_by')
  String get collectedBy;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'evidence_type')
  String get evidenceType;

  @BuiltValueField(wireName: r'file_path')
  String? get filePath;

  @BuiltValueField(wireName: r'name')
  String get name;

  @BuiltValueField(wireName: r'source')
  String? get source_;

  @BuiltValueField(wireName: r'tags')
  BuiltList<String>? get tags;

  EvidenceAdd._();

  factory EvidenceAdd([void updates(EvidenceAddBuilder b)]) = _$EvidenceAdd;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(EvidenceAddBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<EvidenceAdd> get serializer => _$EvidenceAddSerializer();
}

class _$EvidenceAddSerializer implements PrimitiveSerializer<EvidenceAdd> {
  @override
  final Iterable<Type> types = const [EvidenceAdd, _$EvidenceAdd];

  @override
  final String wireName = r'EvidenceAdd';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    EvidenceAdd object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'collected_by';
    yield serializers.serialize(
      object.collectedBy,
      specifiedType: const FullType(String),
    );
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'evidence_type';
    yield serializers.serialize(
      object.evidenceType,
      specifiedType: const FullType(String),
    );
    if (object.filePath != null) {
      yield r'file_path';
      yield serializers.serialize(
        object.filePath,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'name';
    yield serializers.serialize(
      object.name,
      specifiedType: const FullType(String),
    );
    if (object.source_ != null) {
      yield r'source';
      yield serializers.serialize(
        object.source_,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.tags != null) {
      yield r'tags';
      yield serializers.serialize(
        object.tags,
        specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    EvidenceAdd object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required EvidenceAddBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'collected_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.collectedBy = valueDes;
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'evidence_type':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.evidenceType = valueDes;
          break;
        case r'file_path':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.filePath = valueDes;
          break;
        case r'name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.name = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.source_ = valueDes;
          break;
        case r'tags':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.tags.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  EvidenceAdd deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = EvidenceAddBuilder();
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


