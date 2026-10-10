//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/needs_you_item.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'needs_you_response.g.dart';

/// NeedsYouResponse
///
/// Properties:
/// * [count] 
/// * [items] 
@BuiltValue()
abstract class NeedsYouResponse implements Built<NeedsYouResponse, NeedsYouResponseBuilder> {
  @BuiltValueField(wireName: r'count')
  int get count;

  @BuiltValueField(wireName: r'items')
  BuiltList<NeedsYouItem>? get items;

  NeedsYouResponse._();

  factory NeedsYouResponse([void updates(NeedsYouResponseBuilder b)]) = _$NeedsYouResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(NeedsYouResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<NeedsYouResponse> get serializer => _$NeedsYouResponseSerializer();
}

class _$NeedsYouResponseSerializer implements PrimitiveSerializer<NeedsYouResponse> {
  @override
  final Iterable<Type> types = const [NeedsYouResponse, _$NeedsYouResponse];

  @override
  final String wireName = r'NeedsYouResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    NeedsYouResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'count';
    yield serializers.serialize(
      object.count,
      specifiedType: const FullType(int),
    );
    if (object.items != null) {
      yield r'items';
      yield serializers.serialize(
        object.items,
        specifiedType: const FullType(BuiltList, [FullType(NeedsYouItem)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    NeedsYouResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required NeedsYouResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.count = valueDes;
          break;
        case r'items':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(NeedsYouItem)]),
          ) as BuiltList<NeedsYouItem>?;
          if (valueDes == null) continue;
          result.items.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  NeedsYouResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = NeedsYouResponseBuilder();
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


