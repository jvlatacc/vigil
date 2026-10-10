//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/case_closure_view.dart';
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/case_linked_finding.dart';
import 'package:vigil_api_v1/src/model/case_investigation_ref.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'case_detail_response.g.dart';

/// ``GET /cases/{id}`` — the case, its combined state, and the runs on it.
///
/// Properties:
/// * [activities] 
/// * [assignee] 
/// * [caseId] 
/// * [closure] 
/// * [combinedState] 
/// * [createdAt] 
/// * [description] 
/// * [findingIds] 
/// * [investigations] 
/// * [linkedFindings] 
/// * [mitreTechniques] 
/// * [notes] 
/// * [priority] 
/// * [resolutionSteps] 
/// * [status] 
/// * [tags] 
/// * [timeline] 
/// * [title] 
/// * [updatedAt] 
@BuiltValue()
abstract class CaseDetailResponse implements Built<CaseDetailResponse, CaseDetailResponseBuilder> {
  @BuiltValueField(wireName: r'activities')
  BuiltList<JsonObject?>? get activities;

  @BuiltValueField(wireName: r'assignee')
  String? get assignee;

  @BuiltValueField(wireName: r'case_id')
  String? get caseId;

  @BuiltValueField(wireName: r'closure')
  CaseClosureView? get closure;

  @BuiltValueField(wireName: r'combined_state')
  String get combinedState;

  @BuiltValueField(wireName: r'created_at')
  String? get createdAt;

  @BuiltValueField(wireName: r'description')
  String? get description;

  @BuiltValueField(wireName: r'finding_ids')
  BuiltList<String>? get findingIds;

  @BuiltValueField(wireName: r'investigations')
  BuiltList<CaseInvestigationRef>? get investigations;

  @BuiltValueField(wireName: r'linked_findings')
  BuiltList<CaseLinkedFinding>? get linkedFindings;

  @BuiltValueField(wireName: r'mitre_techniques')
  BuiltList<String>? get mitreTechniques;

  @BuiltValueField(wireName: r'notes')
  BuiltList<JsonObject?>? get notes;

  @BuiltValueField(wireName: r'priority')
  String? get priority;

  @BuiltValueField(wireName: r'resolution_steps')
  BuiltList<JsonObject?>? get resolutionSteps;

  @BuiltValueField(wireName: r'status')
  String? get status;

  @BuiltValueField(wireName: r'tags')
  BuiltList<String>? get tags;

  @BuiltValueField(wireName: r'timeline')
  BuiltList<JsonObject?>? get timeline;

  @BuiltValueField(wireName: r'title')
  String? get title;

  @BuiltValueField(wireName: r'updated_at')
  String? get updatedAt;

  CaseDetailResponse._();

  factory CaseDetailResponse([void updates(CaseDetailResponseBuilder b)]) = _$CaseDetailResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CaseDetailResponseBuilder b) => b
      ..activities = ListBuilder()
      ..investigations = ListBuilder()
      ..linkedFindings = ListBuilder()
      ..mitreTechniques = ListBuilder()
      ..notes = ListBuilder()
      ..resolutionSteps = ListBuilder()
      ..tags = ListBuilder()
      ..timeline = ListBuilder();

  @BuiltValueSerializer(custom: true)
  static Serializer<CaseDetailResponse> get serializer => _$CaseDetailResponseSerializer();
}

class _$CaseDetailResponseSerializer implements PrimitiveSerializer<CaseDetailResponse> {
  @override
  final Iterable<Type> types = const [CaseDetailResponse, _$CaseDetailResponse];

  @override
  final String wireName = r'CaseDetailResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CaseDetailResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.activities != null) {
      yield r'activities';
      yield serializers.serialize(
        object.activities,
        specifiedType: const FullType(BuiltList, [FullType.nullable(JsonObject)]),
      );
    }
    if (object.assignee != null) {
      yield r'assignee';
      yield serializers.serialize(
        object.assignee,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.caseId != null) {
      yield r'case_id';
      yield serializers.serialize(
        object.caseId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.closure != null) {
      yield r'closure';
      yield serializers.serialize(
        object.closure,
        specifiedType: const FullType.nullable(CaseClosureView),
      );
    }
    yield r'combined_state';
    yield serializers.serialize(
      object.combinedState,
      specifiedType: const FullType(String),
    );
    if (object.createdAt != null) {
      yield r'created_at';
      yield serializers.serialize(
        object.createdAt,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.description != null) {
      yield r'description';
      yield serializers.serialize(
        object.description,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.findingIds != null) {
      yield r'finding_ids';
      yield serializers.serialize(
        object.findingIds,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.investigations != null) {
      yield r'investigations';
      yield serializers.serialize(
        object.investigations,
        specifiedType: const FullType(BuiltList, [FullType(CaseInvestigationRef)]),
      );
    }
    if (object.linkedFindings != null) {
      yield r'linked_findings';
      yield serializers.serialize(
        object.linkedFindings,
        specifiedType: const FullType(BuiltList, [FullType(CaseLinkedFinding)]),
      );
    }
    if (object.mitreTechniques != null) {
      yield r'mitre_techniques';
      yield serializers.serialize(
        object.mitreTechniques,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.notes != null) {
      yield r'notes';
      yield serializers.serialize(
        object.notes,
        specifiedType: const FullType(BuiltList, [FullType.nullable(JsonObject)]),
      );
    }
    if (object.priority != null) {
      yield r'priority';
      yield serializers.serialize(
        object.priority,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.resolutionSteps != null) {
      yield r'resolution_steps';
      yield serializers.serialize(
        object.resolutionSteps,
        specifiedType: const FullType(BuiltList, [FullType.nullable(JsonObject)]),
      );
    }
    if (object.status != null) {
      yield r'status';
      yield serializers.serialize(
        object.status,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.tags != null) {
      yield r'tags';
      yield serializers.serialize(
        object.tags,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    if (object.timeline != null) {
      yield r'timeline';
      yield serializers.serialize(
        object.timeline,
        specifiedType: const FullType(BuiltList, [FullType.nullable(JsonObject)]),
      );
    }
    if (object.title != null) {
      yield r'title';
      yield serializers.serialize(
        object.title,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.updatedAt != null) {
      yield r'updated_at';
      yield serializers.serialize(
        object.updatedAt,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CaseDetailResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required CaseDetailResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'activities':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType.nullable(JsonObject)]),
          ) as BuiltList<JsonObject?>?;
          if (valueDes == null) continue;
          result.activities.replace(valueDes);
          break;
        case r'assignee':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.assignee = valueDes;
          break;
        case r'case_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.caseId = valueDes;
          break;
        case r'closure':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(CaseClosureView),
          ) as CaseClosureView?;
          if (valueDes == null) continue;
          result.closure.replace(valueDes);
          break;
        case r'combined_state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.combinedState = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.createdAt = valueDes;
          break;
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.description = valueDes;
          break;
        case r'finding_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.findingIds.replace(valueDes);
          break;
        case r'investigations':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(CaseInvestigationRef)]),
          ) as BuiltList<CaseInvestigationRef>?;
          if (valueDes == null) continue;
          result.investigations.replace(valueDes);
          break;
        case r'linked_findings':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(CaseLinkedFinding)]),
          ) as BuiltList<CaseLinkedFinding>?;
          if (valueDes == null) continue;
          result.linkedFindings.replace(valueDes);
          break;
        case r'mitre_techniques':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.mitreTechniques.replace(valueDes);
          break;
        case r'notes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType.nullable(JsonObject)]),
          ) as BuiltList<JsonObject?>?;
          if (valueDes == null) continue;
          result.notes.replace(valueDes);
          break;
        case r'priority':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.priority = valueDes;
          break;
        case r'resolution_steps':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType.nullable(JsonObject)]),
          ) as BuiltList<JsonObject?>?;
          if (valueDes == null) continue;
          result.resolutionSteps.replace(valueDes);
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.status = valueDes;
          break;
        case r'tags':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.tags.replace(valueDes);
          break;
        case r'timeline':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType.nullable(JsonObject)]),
          ) as BuiltList<JsonObject?>?;
          if (valueDes == null) continue;
          result.timeline.replace(valueDes);
          break;
        case r'title':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.title = valueDes;
          break;
        case r'updated_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.updatedAt = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CaseDetailResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CaseDetailResponseBuilder();
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


