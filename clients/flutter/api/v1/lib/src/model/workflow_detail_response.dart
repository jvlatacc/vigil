//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'workflow_detail_response.g.dart';

/// WorkflowDetailResponse
///
/// Properties:
/// * [agent] 
/// * [agents] 
/// * [body] 
/// * [checkpoints] 
/// * [description] 
/// * [huntLike] 
/// * [id] 
/// * [name] 
/// * [objectives] 
/// * [phases] 
/// * [runKind] 
/// * [source_] 
/// * [toolsUsed] 
/// * [triggerExamples] 
/// * [useCase] 
/// * [version] 
@BuiltValue()
abstract class WorkflowDetailResponse implements Built<WorkflowDetailResponse, WorkflowDetailResponseBuilder> {
  @BuiltValueField(wireName: r'agent')
  BuiltMap<String, JsonObject?>? get agent;

  @BuiltValueField(wireName: r'agents')
  BuiltList<String>? get agents;

  @BuiltValueField(wireName: r'body')
  String get body;

  @BuiltValueField(wireName: r'checkpoints')
  BuiltMap<String, String>? get checkpoints;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'hunt_like')
  bool get huntLike;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'name')
  String get name;

  @BuiltValueField(wireName: r'objectives')
  BuiltList<String>? get objectives;

  @BuiltValueField(wireName: r'phases')
  BuiltList<BuiltMap<String, JsonObject?>>? get phases;

  @BuiltValueField(wireName: r'run_kind')
  String get runKind;

  @BuiltValueField(wireName: r'source')
  String get source_;

  @BuiltValueField(wireName: r'tools_used')
  BuiltList<String>? get toolsUsed;

  @BuiltValueField(wireName: r'trigger_examples')
  BuiltList<String>? get triggerExamples;

  @BuiltValueField(wireName: r'use_case')
  String? get useCase;

  @BuiltValueField(wireName: r'version')
  int? get version;

  WorkflowDetailResponse._();

  factory WorkflowDetailResponse([void updates(WorkflowDetailResponseBuilder b)]) = _$WorkflowDetailResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(WorkflowDetailResponseBuilder b) => b
      ..description = ''
      ..version = 1;

  @BuiltValueSerializer(custom: true)
  static Serializer<WorkflowDetailResponse> get serializer => _$WorkflowDetailResponseSerializer();
}

class _$WorkflowDetailResponseSerializer implements PrimitiveSerializer<WorkflowDetailResponse> {
  @override
  final Iterable<Type> types = const [WorkflowDetailResponse, _$WorkflowDetailResponse];

  @override
  final String wireName = r'WorkflowDetailResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    WorkflowDetailResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.agent != null) {
      yield r'agent';
      yield serializers.serialize(
        object.agent,
        specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    if (object.agents != null) {
      yield r'agents';
      yield serializers.serialize(
        object.agents,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    yield r'body';
    yield serializers.serialize(
      object.body,
      specifiedType: const FullType(String),
    );
    if (object.checkpoints != null) {
      yield r'checkpoints';
      yield serializers.serialize(
        object.checkpoints,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType(String)]),
      );
    }
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType(String),
      );
    }
    yield r'hunt_like';
    yield serializers.serialize(
      object.huntLike,
      specifiedType: const FullType(bool),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'name';
    yield serializers.serialize(
      object.name,
      specifiedType: const FullType(String),
    );
    if (object.objectives != null) {
      yield r'objectives';
      yield serializers.serialize(
        object.objectives,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.phases != null) {
      yield r'phases';
      yield serializers.serialize(
        object.phases,
        specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
      );
    }
    yield r'run_kind';
    yield serializers.serialize(
      object.runKind,
      specifiedType: const FullType(String),
    );
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
    if (object.toolsUsed != null) {
      yield r'tools_used';
      yield serializers.serialize(
        object.toolsUsed,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.triggerExamples != null) {
      yield r'trigger_examples';
      yield serializers.serialize(
        object.triggerExamples,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.useCase != null) {
      yield r'use_case';
      yield serializers.serialize(
        object.useCase,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.version != null) {
      yield r'version';
      yield serializers.serialize(
        object.version,
        specifiedType: const FullType(int),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    WorkflowDetailResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required WorkflowDetailResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'agent':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.agent.replace(valueDes);
          break;
        case r'agents':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.agents.replace(valueDes);
          break;
        case r'body':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.body = valueDes;
          break;
        case r'checkpoints':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType(String)]),
          ) as BuiltMap<String, String>?;
          if (valueDes == null) continue;
          result.checkpoints.replace(valueDes);
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'hunt_like':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.huntLike = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.name = valueDes;
          break;
        case r'objectives':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.objectives.replace(valueDes);
          break;
        case r'phases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.phases.replace(valueDes);
          break;
        case r'run_kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.runKind = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        case r'tools_used':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.toolsUsed.replace(valueDes);
          break;
        case r'trigger_examples':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.triggerExamples.replace(valueDes);
          break;
        case r'use_case':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.useCase = valueDes;
          break;
        case r'version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.version = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  WorkflowDetailResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = WorkflowDetailResponseBuilder();
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


