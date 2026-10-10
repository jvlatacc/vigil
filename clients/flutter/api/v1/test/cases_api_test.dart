import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for CasesApi
void main() {
  final instance = VigilApiV1().getCasesApi();

  group(CasesApi, () {
    // Remove Finding From Case
    //
    //Future<CaseSchema> deleteApiV1CasesCaseIdFindingsFindingId(String caseId, String findingId, { String authorization }) async
    test('test deleteApiV1CasesCaseIdFindingsFindingId', () async {
      // TODO
    });

    // Get Cases
    //
    //Future<CaseListResponse> getApiV1Cases({ String state, String workflow, String priority, String dataSource, bool slaAtRisk, String assignee, bool closed, String query, bool needsYou, String kind, int limit, int offset, String authorization }) async
    test('test getApiV1Cases', () async {
      // TODO
    });

    // Get Case
    //
    //Future<CaseDetailResponse> getApiV1CasesCaseId(String caseId, { String authorization }) async
    test('test getApiV1CasesCaseId', () async {
      // TODO
    });

    // Get Evidence
    //
    //Future<CaseEvidenceListResponse> getApiV1CasesCaseIdEvidence(String caseId, { String evidenceType, String authorization }) async
    test('test getApiV1CasesCaseIdEvidence', () async {
      // TODO
    });

    // Get Iocs
    //
    //Future<CaseIOCListResponse> getApiV1CasesCaseIdIocs(String caseId, { String iocType, String authorization }) async
    test('test getApiV1CasesCaseIdIocs', () async {
      // TODO
    });

    // Export Iocs
    //
    //Future<CaseIOCExportResponse> getApiV1CasesCaseIdIocsExport(String caseId, { String format, String authorization }) async
    test('test getApiV1CasesCaseIdIocsExport', () async {
      // TODO
    });

    // Get Cases Summary
    //
    //Future<CaseSummaryResponse> getApiV1CasesStatsSummary({ String authorization }) async
    test('test getApiV1CasesStatsSummary', () async {
      // TODO
    });

    // Update Case
    //
    //Future<CaseSuccessResponse> patchApiV1CasesCaseId(String caseId, CaseUpdate caseUpdate, { String authorization }) async
    test('test patchApiV1CasesCaseId', () async {
      // TODO
    });

    // Create Case
    //
    //Future<CaseSchema> postApiV1Cases(CaseCreate caseCreate, { String authorization }) async
    test('test postApiV1Cases', () async {
      // TODO
    });

    // Close Case
    //
    //Future<CaseCloseResponse> postApiV1CasesCaseIdClose(String caseId, ClosureInfo closureInfo, { String authorization }) async
    test('test postApiV1CasesCaseIdClose', () async {
      // TODO
    });

    // Add Evidence
    //
    //Future<CaseEvidenceSchema> postApiV1CasesCaseIdEvidence(String caseId, EvidenceAdd evidenceAdd, { String authorization }) async
    test('test postApiV1CasesCaseIdEvidence', () async {
      // TODO
    });

    // Add Finding To Case
    //
    //Future<CaseSchema> postApiV1CasesCaseIdFindingsFindingId(String caseId, String findingId, { String authorization }) async
    test('test postApiV1CasesCaseIdFindingsFindingId', () async {
      // TODO
    });

    // Add Ioc
    //
    //Future<CaseIOCSchema> postApiV1CasesCaseIdIocs(String caseId, IOCAdd iOCAdd, { String authorization }) async
    test('test postApiV1CasesCaseIdIocs', () async {
      // TODO
    });

    // Bulk Add Iocs
    //
    //Future<CaseIOCBulkResponse> postApiV1CasesCaseIdIocsBulk(String caseId, IOCBulkAdd iOCBulkAdd, { String authorization }) async
    test('test postApiV1CasesCaseIdIocsBulk', () async {
      // TODO
    });

    // Merge Cases
    //
    //Future<CaseMergeResponse> postApiV1CasesCaseIdMerge(String caseId, MergeRequest mergeRequest, { String authorization }) async
    test('test postApiV1CasesCaseIdMerge', () async {
      // TODO
    });

    // Search Cases
    //
    //Future<CaseSearchResponse> postApiV1CasesSearch(SearchRequest searchRequest, { String authorization }) async
    test('test postApiV1CasesSearch', () async {
      // TODO
    });

  });
}
