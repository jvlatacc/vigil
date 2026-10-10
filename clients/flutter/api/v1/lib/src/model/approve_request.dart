//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'approve_request.g.dart';

/// ApproveRequest
///
/// Properties:
/// * [approvedBy] - Identity of the approving analyst. Defaults to 'analyst'.
@BuiltValue()
abstract class ApproveRequest implements Built<ApproveRequest, ApproveRequestBuilder> {
  /// Identity of the approving analyst. Defaults to 'analyst'.
  @BuiltValueField(wireName: r'approved_by')
  String? get approvedBy;

  ApproveRequest._();

  factory ApproveRequest([void updates(ApproveRequestBuilder b)]) = _$ApproveRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApproveRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApproveRequest> get serializer => _$ApproveRequestSerializer();
}

class _$ApproveRequestSerializer implements PrimitiveSerializer<ApproveRequest> {
  @override
  final Iterable<Type> types = const [ApproveRequest, _$ApproveRequest];

  @override
  final String wireName = r'ApproveRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApproveRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.approvedBy != null) {
      yield r'approved_by';
      yield serializers.serialize(
        object.approvedBy,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ApproveRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ApproveRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'approved_by':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.approvedBy = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApproveRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApproveRequestBuilder();
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


