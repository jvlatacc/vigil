//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/case_schema.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_merge_response.g.dart';

/// CaseMergeResponse
///
/// Properties:
/// * [findingsMoved] 
/// * [message] 
/// * [sourceCaseStatus] 
/// * [success] 
/// * [targetCase] 
@BuiltValue()
abstract class CaseMergeResponse implements Built<CaseMergeResponse, CaseMergeResponseBuilder> {
  @BuiltValueField(wireName: r'findings_moved')
  int? get findingsMoved;

  @BuiltValueField(wireName: r'message')
  String get message;

  @BuiltValueField(wireName: r'source_case_status')
  String get sourceCaseStatus;

  @BuiltValueField(wireName: r'success')
  bool get success;

  @BuiltValueField(wireName: r'target_case')
  CaseSchema? get targetCase;

  CaseMergeResponse._();

  factory CaseMergeResponse([void updates(CaseMergeResponseBuilder b)]) = _$CaseMergeResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseMergeResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseMergeResponse> get serializer => _$CaseMergeResponseSerializer();
}

class _$CaseMergeResponseSerializer implements PrimitiveSerializer<CaseMergeResponse> {
  @override
  final Iterable<Type> types = const [CaseMergeResponse, _$CaseMergeResponse];

  @override
  final String wireName = r'CaseMergeResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseMergeResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.findingsMoved != null) {
      yield r'findings_moved';
      yield serializers.serialize(
        object.findingsMoved,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'message';
    yield serializers.serialize(
      object.message,
      specifiedType: const FullType(String),
    );
    yield r'source_case_status';
    yield serializers.serialize(
      object.sourceCaseStatus,
      specifiedType: const FullType(String),
    );
    yield r'success';
    yield serializers.serialize(
      object.success,
      specifiedType: const FullType(bool),
    );
    if (object.targetCase != null) {
      yield r'target_case';
      yield serializers.serialize(
        object.targetCase,
        specifiedType: const FullType.nullable(CaseSchema),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseMergeResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseMergeResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'findings_moved':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.findingsMoved = valueDes;
          break;
        case r'message':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.message = valueDes;
          break;
        case r'source_case_status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.sourceCaseStatus = valueDes;
          break;
        case r'success':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.success = valueDes;
          break;
        case r'target_case':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(CaseSchema),
          ) as CaseSchema?;
          if (valueDes == null) continue;
          result.targetCase.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseMergeResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseMergeResponseBuilder();
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


