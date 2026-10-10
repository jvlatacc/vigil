//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'directive_request.g.dart';

/// DirectiveRequest
///
/// Properties:
/// * [actor] - Who is steering. Defaults to the session user.
/// * [fields] - Any of checkpoint_id, entity_key, question_id, hypothesis_id, tenant, revoke, grant.
/// * [kind] - One of note, lead, abort, extend, conclude, approve, reject, benign, gap, boost.
/// * [text] - What the operator is telling the run.
@BuiltValue()
abstract class DirectiveRequest implements Built<DirectiveRequest, DirectiveRequestBuilder> {
  /// Who is steering. Defaults to the session user.
  @BuiltValueField(wireName: r'actor')
  String? get actor;

  /// Any of checkpoint_id, entity_key, question_id, hypothesis_id, tenant, revoke, grant.
  @BuiltValueField(wireName: r'fields')
  BuiltMap<String, JsonObject?>? get fields;

  /// One of note, lead, abort, extend, conclude, approve, reject, benign, gap, boost.
  @BuiltValueField(wireName: r'kind')
  String get kind;

  /// What the operator is telling the run.
  @BuiltValueField(wireName: r'text')
  String? get text;

  DirectiveRequest._();

  factory DirectiveRequest([void updates(DirectiveRequestBuilder b)]) = _$DirectiveRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(DirectiveRequestBuilder b) => b
      ..text = '';

  @BuiltValueSerializer(custom: true)
  static Serializer<DirectiveRequest> get serializer => _$DirectiveRequestSerializer();
}

class _$DirectiveRequestSerializer implements PrimitiveSerializer<DirectiveRequest> {
  @override
  final Iterable<Type> types = const [DirectiveRequest, _$DirectiveRequest];

  @override
  final String wireName = r'DirectiveRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    DirectiveRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.actor != null) {
      yield r'actor';
      yield serializers.serialize(
        object.actor,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.fields != null) {
      yield r'fields';
      yield serializers.serialize(
        object.fields,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(String),
    );
    if (object.text != null) {
      yield r'text';
      yield serializers.serialize(
        object.text,
        specifiedType: const FullType(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    DirectiveRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required DirectiveRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'actor':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.actor = valueDes;
          break;
        case r'fields':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.fields.replace(valueDes);
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.kind = valueDes;
          break;
        case r'text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.text = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  DirectiveRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = DirectiveRequestBuilder();
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


