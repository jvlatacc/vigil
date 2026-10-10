//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'run_status_response.g.dart';

/// RunStatusResponse
///
/// Properties:
/// * [events] - Events on the ledger, so progress is visible.
/// * [outcome] 
/// * [reason] 
/// * [runId] 
/// * [status] - queued, running or terminal.
@BuiltValue()
abstract class RunStatusResponse implements Built<RunStatusResponse, RunStatusResponseBuilder> {
  /// Events on the ledger, so progress is visible.
  @BuiltValueField(wireName: r'events')
  int get events;

  @BuiltValueField(wireName: r'outcome')
  String? get outcome;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  @BuiltValueField(wireName: r'run_id')
  String get runId;

  /// queued, running or terminal.
  @BuiltValueField(wireName: r'status')
  String get status;

  RunStatusResponse._();

  factory RunStatusResponse([void updates(RunStatusResponseBuilder b)]) = _$RunStatusResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RunStatusResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RunStatusResponse> get serializer => _$RunStatusResponseSerializer();
}

class _$RunStatusResponseSerializer implements PrimitiveSerializer<RunStatusResponse> {
  @override
  final Iterable<Type> types = const [RunStatusResponse, _$RunStatusResponse];

  @override
  final String wireName = r'RunStatusResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RunStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'events';
    yield serializers.serialize(
      object.events,
      specifiedType: const FullType(int),
    );
    if (object.outcome != null) {
      yield r'outcome';
      yield serializers.serialize(
        object.outcome,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.reason != null) {
      yield r'reason';
      yield serializers.serialize(
        object.reason,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'run_id';
    yield serializers.serialize(
      object.runId,
      specifiedType: const FullType(String),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    RunStatusResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required RunStatusResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'events':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.events = valueDes;
          break;
        case r'outcome':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.outcome = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reason = valueDes;
          break;
        case r'run_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.runId = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.status = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RunStatusResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RunStatusResponseBuilder();
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


