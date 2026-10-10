//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_import

import 'package:one_of_serializer/any_of_serializer.dart';
import 'package:one_of_serializer/one_of_serializer.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/serializer.dart';
import 'package:built_value/standard_json_plugin.dart';
import 'package:built_value/iso_8601_date_time_serializer.dart';
import 'package:vigil_api_v1/src/date_serializer.dart';
import 'package:vigil_api_v1/src/model/date.dart';

import 'package:vigil_api_v1/src/model/approval_action_result.dart';
import 'package:vigil_api_v1/src/model/approval_list_response.dart';
import 'package:vigil_api_v1/src/model/approve_request.dart';
import 'package:vigil_api_v1/src/model/breached_cases_response.dart';
import 'package:vigil_api_v1/src/model/breaker_reset_request.dart';
import 'package:vigil_api_v1/src/model/breaker_reset_response.dart';
import 'package:vigil_api_v1/src/model/breaker_status_response.dart';
import 'package:vigil_api_v1/src/model/by_priority_response.dart';
import 'package:vigil_api_v1/src/model/by_status_response.dart';
import 'package:vigil_api_v1/src/model/case_close_response.dart';
import 'package:vigil_api_v1/src/model/case_closure_info_schema.dart';
import 'package:vigil_api_v1/src/model/case_closure_view.dart';
import 'package:vigil_api_v1/src/model/case_create.dart';
import 'package:vigil_api_v1/src/model/case_detail_response.dart';
import 'package:vigil_api_v1/src/model/case_evidence_list_response.dart';
import 'package:vigil_api_v1/src/model/case_evidence_schema.dart';
import 'package:vigil_api_v1/src/model/case_ioc_bulk_response.dart';
import 'package:vigil_api_v1/src/model/case_ioc_export_response.dart';
import 'package:vigil_api_v1/src/model/case_ioc_list_response.dart';
import 'package:vigil_api_v1/src/model/case_ioc_schema.dart';
import 'package:vigil_api_v1/src/model/case_investigation_ref.dart';
import 'package:vigil_api_v1/src/model/case_linked_finding.dart';
import 'package:vigil_api_v1/src/model/case_list_response.dart';
import 'package:vigil_api_v1/src/model/case_merge_response.dart';
import 'package:vigil_api_v1/src/model/case_metrics_summary_response.dart';
import 'package:vigil_api_v1/src/model/case_queue_item.dart';
import 'package:vigil_api_v1/src/model/case_queue_strip.dart';
import 'package:vigil_api_v1/src/model/case_schema.dart';
import 'package:vigil_api_v1/src/model/case_search_response.dart';
import 'package:vigil_api_v1/src/model/case_success_response.dart';
import 'package:vigil_api_v1/src/model/case_summary_response.dart';
import 'package:vigil_api_v1/src/model/case_update.dart';
import 'package:vigil_api_v1/src/model/closure_category.dart';
import 'package:vigil_api_v1/src/model/closure_info.dart';
import 'package:vigil_api_v1/src/model/directive_request.dart';
import 'package:vigil_api_v1/src/model/directive_response.dart';
import 'package:vigil_api_v1/src/model/entity_context.dart';
import 'package:vigil_api_v1/src/model/evidence_add.dart';
import 'package:vigil_api_v1/src/model/finding_list_response.dart';
import 'package:vigil_api_v1/src/model/finding_record.dart';
import 'package:vigil_api_v1/src/model/finding_update.dart';
import 'package:vigil_api_v1/src/model/finding_update_response.dart';
import 'package:vigil_api_v1/src/model/findings_summary_response.dart';
import 'package:vigil_api_v1/src/model/http_validation_error.dart';
import 'package:vigil_api_v1/src/model/ioc_add.dart';
import 'package:vigil_api_v1/src/model/ioc_bulk_add.dart';
import 'package:vigil_api_v1/src/model/location_inner.dart';
import 'package:vigil_api_v1/src/model/merge_request.dart';
import 'package:vigil_api_v1/src/model/mttd_response.dart';
import 'package:vigil_api_v1/src/model/mttr_response.dart';
import 'package:vigil_api_v1/src/model/needs_you_item.dart';
import 'package:vigil_api_v1/src/model/needs_you_response.dart';
import 'package:vigil_api_v1/src/model/pending_action_response.dart';
import 'package:vigil_api_v1/src/model/priority_breakdown_row.dart';
import 'package:vigil_api_v1/src/model/reject_request.dart';
import 'package:vigil_api_v1/src/model/run_list_item.dart';
import 'package:vigil_api_v1/src/model/run_list_response.dart';
import 'package:vigil_api_v1/src/model/run_status_response.dart';
import 'package:vigil_api_v1/src/model/search_request.dart';
import 'package:vigil_api_v1/src/model/source_evidence.dart';
import 'package:vigil_api_v1/src/model/start_run_request.dart';
import 'package:vigil_api_v1/src/model/start_run_response.dart';
import 'package:vigil_api_v1/src/model/status_breakdown_row.dart';
import 'package:vigil_api_v1/src/model/twin_connection_in.dart';
import 'package:vigil_api_v1/src/model/twin_connection_out.dart';
import 'package:vigil_api_v1/src/model/twin_device_in.dart';
import 'package:vigil_api_v1/src/model/twin_device_list_response.dart';
import 'package:vigil_api_v1/src/model/twin_device_out.dart';
import 'package:vigil_api_v1/src/model/twin_edge_out.dart';
import 'package:vigil_api_v1/src/model/twin_graph_payload.dart';
import 'package:vigil_api_v1/src/model/twin_ingest_batch.dart';
import 'package:vigil_api_v1/src/model/twin_ingest_result.dart';
import 'package:vigil_api_v1/src/model/twin_process_in.dart';
import 'package:vigil_api_v1/src/model/twin_process_out.dart';
import 'package:vigil_api_v1/src/model/twin_process_ref.dart';
import 'package:vigil_api_v1/src/model/validation_error.dart';
import 'package:vigil_api_v1/src/model/workflow_detail_response.dart';
import 'package:vigil_api_v1/src/model/workflow_list_response.dart';

part 'serializers.g.dart';

@SerializersFor([
  ApprovalActionResult,
  ApprovalListResponse,
  ApproveRequest,
  BreachedCasesResponse,
  BreakerResetRequest,
  BreakerResetResponse,
  BreakerStatusResponse,
  ByPriorityResponse,
  ByStatusResponse,
  CaseCloseResponse,
  CaseClosureInfoSchema,
  CaseClosureView,
  CaseCreate,
  CaseDetailResponse,
  CaseEvidenceListResponse,
  CaseEvidenceSchema,
  CaseIOCBulkResponse,
  CaseIOCExportResponse,
  CaseIOCListResponse,
  CaseIOCSchema,
  CaseInvestigationRef,
  CaseLinkedFinding,
  CaseListResponse,
  CaseMergeResponse,
  CaseMetricsSummaryResponse,
  CaseQueueItem,
  CaseQueueStrip,
  CaseSchema,
  CaseSearchResponse,
  CaseSuccessResponse,
  CaseSummaryResponse,
  CaseUpdate,
  ClosureCategory,
  ClosureInfo,
  DirectiveRequest,
  DirectiveResponse,
  EntityContext,
  EvidenceAdd,
  FindingListResponse,
  FindingRecord,
  FindingUpdate,
  FindingUpdateResponse,
  FindingsSummaryResponse,
  HTTPValidationError,
  IOCAdd,
  IOCBulkAdd,
  LocationInner,
  MergeRequest,
  MttdResponse,
  MttrResponse,
  NeedsYouItem,
  NeedsYouResponse,
  PendingActionResponse,
  PriorityBreakdownRow,
  RejectRequest,
  RunListItem,
  RunListResponse,
  RunStatusResponse,
  SearchRequest,
  SourceEvidence,
  StartRunRequest,
  StartRunResponse,
  StatusBreakdownRow,
  TwinConnectionIn,
  TwinConnectionOut,
  TwinDeviceIn,
  TwinDeviceListResponse,
  TwinDeviceOut,
  TwinEdgeOut,
  TwinGraphPayload,
  TwinIngestBatch,
  TwinIngestResult,
  TwinProcessIn,
  TwinProcessOut,
  TwinProcessRef,
  ValidationError,
  WorkflowDetailResponse,
  WorkflowListResponse,
])
Serializers serializers = (_$serializers.toBuilder()
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(String)]),
        () => MapBuilder<String, String>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseInvestigationRef)]),
        () => ListBuilder<CaseInvestigationRef>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(PendingActionResponse)]),
        () => ListBuilder<PendingActionResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(BuiltMap, [FullType(String), FullType(num)])]),
        () => MapBuilder<String, BuiltMap<String, num>>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinDeviceIn)]),
        () => ListBuilder<TwinDeviceIn>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinEdgeOut)]),
        () => ListBuilder<TwinEdgeOut>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(num)]),
        () => MapBuilder<String, num>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseLinkedFinding)]),
        () => ListBuilder<CaseLinkedFinding>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseSchema)]),
        () => ListBuilder<CaseSchema>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(NeedsYouItem)]),
        () => ListBuilder<NeedsYouItem>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType(JsonObject)])]),
        () => ListBuilder<BuiltMap<String, JsonObject>>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinDeviceOut)]),
        () => ListBuilder<TwinDeviceOut>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(LocationInner)]),
        () => ListBuilder<LocationInner>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(int)]),
        () => MapBuilder<String, int>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinConnectionOut)]),
        () => ListBuilder<TwinConnectionOut>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseQueueItem)]),
        () => ListBuilder<CaseQueueItem>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(PriorityBreakdownRow)]),
        () => ListBuilder<PriorityBreakdownRow>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinProcessOut)]),
        () => ListBuilder<TwinProcessOut>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(BuiltList)]),
        () => MapBuilder<String, BuiltList>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(StatusBreakdownRow)]),
        () => ListBuilder<StatusBreakdownRow>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType.nullable(JsonObject)]),
        () => ListBuilder<JsonObject>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinConnectionIn)]),
        () => ListBuilder<TwinConnectionIn>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseEvidenceSchema)]),
        () => ListBuilder<CaseEvidenceSchema>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(FindingRecord)]),
        () => ListBuilder<FindingRecord>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CaseIOCSchema)]),
        () => ListBuilder<CaseIOCSchema>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(RunListItem)]),
        () => ListBuilder<RunListItem>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType.nullable(num)]),
        () => MapBuilder<String, num?>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
        () => MapBuilder<String, JsonObject?>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(ValidationError)]),
        () => ListBuilder<ValidationError>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TwinProcessIn)]),
        () => ListBuilder<TwinProcessIn>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(String)]),
        () => ListBuilder<String>(),
      )
      ..add(const OneOfSerializer())
      ..add(const AnyOfSerializer())
      ..add(const DateSerializer())
      ..add(Iso8601DateTimeSerializer())
    ).build();

Serializers standardSerializers =
    (serializers.toBuilder()..addPlugin(StandardJsonPlugin())).build();
