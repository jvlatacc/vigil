import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for FindingsApi
void main() {
  final instance = VigilApiV1().getFindingsApi();

  group(FindingsApi, () {
    // Get Findings
    //
    //Future<FindingListResponse> getApiV1Findings({ String severity, String dataSource, int clusterId, num minAnomalyScore, String status, String search, int offset, int limit, String sortBy, String sortOrder, String exclusions, String authorization }) async
    test('test getApiV1Findings', () async {
      // TODO
    });

    // Get Finding
    //
    //Future<FindingRecord> getApiV1FindingsFindingId(String findingId, { String authorization }) async
    test('test getApiV1FindingsFindingId', () async {
      // TODO
    });

    // Get Findings Summary
    //
    //Future<FindingsSummaryResponse> getApiV1FindingsStatsSummary({ String exclusions, String authorization }) async
    test('test getApiV1FindingsStatsSummary', () async {
      // TODO
    });

    // Update Finding
    //
    //Future<FindingUpdateResponse> patchApiV1FindingsFindingId(String findingId, FindingUpdate findingUpdate, { String authorization }) async
    test('test patchApiV1FindingsFindingId', () async {
      // TODO
    });

  });
}
