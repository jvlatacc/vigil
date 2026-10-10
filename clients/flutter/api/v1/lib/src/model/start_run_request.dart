//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'start_run_request.g.dart';

/// StartRunRequest
///
/// Properties:
/// * [arch] - Arch file path; empty routes through the run-kind registry.
/// * [config] - Path to the deployment config.
/// * [overrides] 
/// * [playbook] - Path to the playbook: the scenario as data.
/// * [prompt] - What the run is being asked to do.
/// * [runKind] - One of hunt, root_cause, adjudicate, investigate, compose, chat.
/// * [tenantId] 
@BuiltValue()
abstract class StartRunRequest implements Built<StartRunRequest, StartRunRequestBuilder> {
  /// Arch file path; empty routes through the run-kind registry.
  @BuiltValueField(wireName: r'arch')
  String? get arch;

  /// Path to the deployment config.
  @BuiltValueField(wireName: r'config')
  String get config;

  @BuiltValueField(wireName: r'overrides')
  BuiltMap<String, JsonObject?>? get overrides;

  /// Path to the playbook: the scenario as data.
  @BuiltValueField(wireName: r'playbook')
  String get playbook;

  /// What the run is being asked to do.
  @BuiltValueField(wireName: r'prompt')
  String? get prompt;

  /// One of hunt, root_cause, adjudicate, investigate, compose, chat.
  @BuiltValueField(wireName: r'run_kind')
  String? get runKind;

  @BuiltValueField(wireName: r'tenant_id')
  String? get tenantId;

  StartRunRequest._();

  factory StartRunRequest([void updates(StartRunRequestBuilder b)]) = _$StartRunRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(StartRunRequestBuilder b) => b
      ..arch = ''
      ..prompt = ''
      ..runKind = 'hunt';

  @BuiltValueSerializer(custom: true)
  static Serializer<StartRunRequest> get serializer => _$StartRunRequestSerializer();
}

class _$StartRunRequestSerializer implements PrimitiveSerializer<StartRunRequest> {
  @override
  final Iterable<Type> types = const [StartRunRequest, _$StartRunRequest];

  @override
  final String wireName = r'StartRunRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    StartRunRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.arch != null) {
      yield r'arch';
      yield serializers.serialize(
        object.arch,
        specifiedType: const FullType(String),
      );
    }
    yield r'config';
    yield serializers.serialize(
      object.config,
      specifiedType: const FullType(String),
    );
    if (object.overrides != null) {
      yield r'overrides';
      yield serializers.serialize(
        object.overrides,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    yield r'playbook';
    yield serializers.serialize(
      object.playbook,
      specifiedType: const FullType(String),
    );
    if (object.prompt != null) {
      yield r'prompt';
      yield serializers.serialize(
        object.prompt,
        specifiedType: const FullType(String),
      );
    }
    if (object.runKind != null) {
      yield r'run_kind';
      yield serializers.serialize(
        object.runKind,
        specifiedType: const FullType(String),
      );
    }
    if (object.tenantId != null) {
      yield r'tenant_id';
      yield serializers.serialize(
        object.tenantId,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    StartRunRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required StartRunRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'arch':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.arch = valueDes;
          break;
        case r'config':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.config = valueDes;
          break;
        case r'overrides':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.overrides.replace(valueDes);
          break;
        case r'playbook':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.playbook = valueDes;
          break;
        case r'prompt':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.prompt = valueDes;
          break;
        case r'run_kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.runKind = valueDes;
          break;
        case r'tenant_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.tenantId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  StartRunRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = StartRunRequestBuilder();
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


