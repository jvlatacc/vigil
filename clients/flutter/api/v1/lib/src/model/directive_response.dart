//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'directive_response.g.dart';

/// DirectiveResponse
///
/// Properties:
/// * [createdAt] 
/// * [directiveId] 
/// * [kind] 
@BuiltValue()
abstract class DirectiveResponse implements Built<DirectiveResponse, DirectiveResponseBuilder> {
  @BuiltValueField(wireName: r'created_at')
  String get createdAt;

  @BuiltValueField(wireName: r'directive_id')
  String get directiveId;

  @BuiltValueField(wireName: r'kind')
  String get kind;

  DirectiveResponse._();

  factory DirectiveResponse([void updates(DirectiveResponseBuilder b)]) = _$DirectiveResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(DirectiveResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<DirectiveResponse> get serializer => _$DirectiveResponseSerializer();
}

class _$DirectiveResponseSerializer implements PrimitiveSerializer<DirectiveResponse> {
  @override
  final Iterable<Type> types = const [DirectiveResponse, _$DirectiveResponse];

  @override
  final String wireName = r'DirectiveResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    DirectiveResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(String),
    );
    yield r'directive_id';
    yield serializers.serialize(
      object.directiveId,
      specifiedType: const FullType(String),
    );
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    DirectiveResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required DirectiveResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.createdAt = valueDes;
          break;
        case r'directive_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.directiveId = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.kind = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  DirectiveResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = DirectiveResponseBuilder();
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


