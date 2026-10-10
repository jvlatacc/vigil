// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'serializers.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

Serializers _$serializers = (Serializers().toBuilder()
      ..add(ApprovalActionResult.serializer)
      ..add(ApprovalListResponse.serializer)
      ..add(ApproveRequest.serializer)
      ..add(BreachedCasesResponse.serializer)
      ..add(BreakerResetRequest.serializer)
      ..add(BreakerResetResponse.serializer)
      ..add(BreakerStatusResponse.serializer)
      ..add(ByPriorityResponse.serializer)
      ..add(ByStatusResponse.serializer)
      ..add(CaseCloseResponse.serializer)
      ..add(CaseClosureInfoSchema.serializer)
      ..add(CaseClosureView.serializer)
      ..add(CaseCreate.serializer)
      ..add(CaseDetailResponse.serializer)
      ..add(CaseEvidenceListResponse.serializer)
      ..add(CaseEvidenceSchema.serializer)
      ..add(CaseIOCBulkResponse.serializer)
      ..add(CaseIOCExportResponse.serializer)
      ..add(CaseIOCListResponse.serializer)
      ..add(CaseIOCSchema.serializer)
      ..add(CaseInvestigationRef.serializer)
      ..add(CaseLinkedFinding.serializer)
      ..add(CaseListResponse.serializer)
      ..add(CaseMergeResponse.serializer)
      ..add(CaseMetricsSummaryResponse.serializer)
      ..add(CaseQueueItem.serializer)
      ..add(CaseQueueStrip.serializer)
      ..add(CaseSchema.serializer)
      ..add(CaseSearchResponse.serializer)
      ..add(CaseSuccessResponse.serializer)
      ..add(CaseSummaryResponse.serializer)
      ..add(CaseUpdate.serializer)
      ..add(ClosureCategory.serializer)
      ..add(ClosureInfo.serializer)
      ..add(DirectiveRequest.serializer)
      ..add(DirectiveResponse.serializer)
      ..add(EntityContext.serializer)
      ..add(EvidenceAdd.serializer)
      ..add(FindingListResponse.serializer)
      ..add(FindingRecord.serializer)
      ..add(FindingUpdate.serializer)
      ..add(FindingUpdateResponse.serializer)
      ..add(FindingsSummaryResponse.serializer)
      ..add(HTTPValidationError.serializer)
      ..add(IOCAdd.serializer)
      ..add(IOCBulkAdd.serializer)
      ..add(LocationInner.serializer)
      ..add(MergeRequest.serializer)
      ..add(MttdResponse.serializer)
      ..add(MttrResponse.serializer)
      ..add(NeedsYouItem.serializer)
      ..add(NeedsYouResponse.serializer)
      ..add(PendingActionResponse.serializer)
      ..add(PriorityBreakdownRow.serializer)
      ..add(RejectRequest.serializer)
      ..add(RunListItem.serializer)
      ..add(RunListResponse.serializer)
      ..add(RunStatusResponse.serializer)
      ..add(SearchRequest.serializer)
      ..add(SourceEvidence.serializer)
      ..add(SourceEvidenceProvenanceEnum.serializer)
      ..add(SourceEvidenceStatusEnum.serializer)
      ..add(SourceEvidenceTelemetryKindEnum.serializer)
      ..add(SourceEvidenceVersionEnum.serializer)
      ..add(StartRunRequest.serializer)
      ..add(StartRunResponse.serializer)
      ..add(StatusBreakdownRow.serializer)
      ..add(TwinConnectionIn.serializer)
      ..add(TwinConnectionInConnectionTypeEnum.serializer)
      ..add(TwinConnectionInDirectionEnum.serializer)
      ..add(TwinConnectionOut.serializer)
      ..add(TwinConnectionOutConnectionTypeEnum.serializer)
      ..add(TwinDeviceIn.serializer)
      ..add(TwinDeviceListResponse.serializer)
      ..add(TwinDeviceOut.serializer)
      ..add(TwinEdgeOut.serializer)
      ..add(TwinEdgeOutKindEnum.serializer)
      ..add(TwinGraphPayload.serializer)
      ..add(TwinIngestBatch.serializer)
      ..add(TwinIngestResult.serializer)
      ..add(TwinProcessIn.serializer)
      ..add(TwinProcessOut.serializer)
      ..add(TwinProcessRef.serializer)
      ..add(ValidationError.serializer)
      ..add(WorkflowDetailResponse.serializer)
      ..add(WorkflowListResponse.serializer)
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(CaseEvidenceSchema)]),
          () => ListBuilder<CaseEvidenceSchema>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(CaseIOCSchema)]),
          () => ListBuilder<CaseIOCSchema>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(CaseQueueItem)]),
          () => ListBuilder<CaseQueueItem>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(CaseSchema)]),
          () => ListBuilder<CaseSchema>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(FindingRecord)]),
          () => ListBuilder<FindingRecord>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(LocationInner)]),
          () => ListBuilder<LocationInner>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(NeedsYouItem)]),
          () => ListBuilder<NeedsYouItem>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType(PendingActionResponse)]),
          () => ListBuilder<PendingActionResponse>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType(PriorityBreakdownRow)]),
          () => ListBuilder<PriorityBreakdownRow>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(RunListItem)]),
          () => ListBuilder<RunListItem>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(StatusBreakdownRow)]),
          () => ListBuilder<StatusBreakdownRow>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinConnectionIn)]),
          () => ListBuilder<TwinConnectionIn>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinDeviceIn)]),
          () => ListBuilder<TwinDeviceIn>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinProcessIn)]),
          () => ListBuilder<TwinProcessIn>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinConnectionOut)]),
          () => ListBuilder<TwinConnectionOut>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinDeviceOut)]),
          () => ListBuilder<TwinDeviceOut>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinEdgeOut)]),
          () => ListBuilder<TwinEdgeOut>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinProcessOut)]),
          () => ListBuilder<TwinProcessOut>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(TwinDeviceOut)]),
          () => ListBuilder<TwinDeviceOut>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(ValidationError)]),
          () => ListBuilder<ValidationError>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType(CaseInvestigationRef)]),
          () => ListBuilder<CaseInvestigationRef>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(CaseLinkedFinding)]),
          () => ListBuilder<CaseLinkedFinding>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltList, const [const FullType.nullable(JsonObject)]),
          () => ListBuilder<JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType(
                BuiltMap, const [const FullType(String), const FullType(num)])
          ]),
          () => MapBuilder<String, BuiltMap<String, num>>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(int)]),
          () => MapBuilder<String, int>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(String)]),
          () => MapBuilder<String, String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(BuiltMap, const [
            const FullType(String),
            const FullType.nullable(JsonObject)
          ]),
          () => MapBuilder<String, JsonObject?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [const FullType(String)]),
          () => ListBuilder<String>())
      ..addBuilderFactory(
          const FullType(
              BuiltMap, const [const FullType(String), const FullType(num)]),
          () => MapBuilder<String, num>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>())
      ..addBuilderFactory(
          const FullType(BuiltMap,
              const [const FullType(String), const FullType.nullable(num)]),
          () => MapBuilder<String, num?>())
      ..addBuilderFactory(
          const FullType(BuiltMap,
              const [const FullType(String), const FullType.nullable(num)]),
          () => MapBuilder<String, num?>())
      ..addBuilderFactory(
          const FullType(BuiltList, const [
            const FullType(BuiltMap, const [
              const FullType(String),
              const FullType.nullable(JsonObject)
            ])
          ]),
          () => ListBuilder<BuiltMap<String, JsonObject?>>()))
    .build();

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
