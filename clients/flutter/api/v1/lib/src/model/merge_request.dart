//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'merge_request.g.dart';

/// Merge another case into this one.
///
/// Properties:
/// * [mergedBy] 
/// * [sourceCaseId] 
@BuiltValue()
abstract class MergeRequest implements Built<MergeRequest, MergeRequestBuilder> {
  @BuiltValueField(wireName: r'merged_by')
  String? get mergedBy;

  @BuiltValueField(wireName: r'source_case_id')
  String get sourceCaseId;

  MergeRequest._();

  factory MergeRequest([void updates(MergeRequestBuilder b)]) = _$MergeRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(MergeRequestBuilder b) => b
      ..mergedBy = 'system';

  @BuiltValueSerializer(custom: true)
  static Serializer<MergeRequest> get serializer => _$MergeRequestSerializer();
}

class _$MergeRequestSerializer implements PrimitiveSerializer<MergeRequest> {
  @override
  final Iterable<Type> types = const [MergeRequest, _$MergeRequest];

  @override
  final String wireName = r'MergeRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    MergeRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.mergedBy != null) {
      yield r'merged_by';
      yield serializers.serialize(
        object.mergedBy,
        specifiedType: const FullType(String),
      );
    }
    yield r'source_case_id';
    yield serializers.serialize(
      object.sourceCaseId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    MergeRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required MergeRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'merged_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.mergedBy = valueDes;
          break;
        case r'source_case_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.sourceCaseId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  MergeRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = MergeRequestBuilder();
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


