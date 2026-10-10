import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for CaseMetricsApi
void main() {
  final instance = VigilApiV1().getCaseMetricsApi();

  group(CaseMetricsApi, () {
    // Get Breached Cases
    //
    //Future<BreachedCasesResponse> getApiV1CasesMetricsBreached({ String authorization }) async
    test('test getApiV1CasesMetricsBreached', () async {
      // TODO
    });

    // Get By Priority
    //
    //Future<ByPriorityResponse> getApiV1CasesMetricsByPriority({ DateTime startDate, DateTime endDate, String authorization }) async
    test('test getApiV1CasesMetricsByPriority', () async {
      // TODO
    });

    // Get By Status
    //
    //Future<ByStatusResponse> getApiV1CasesMetricsByStatus({ DateTime startDate, DateTime endDate, String authorization }) async
    test('test getApiV1CasesMetricsByStatus', () async {
      // TODO
    });

    // Get Mttd
    //
    //Future<MttdResponse> getApiV1CasesMetricsMttd({ DateTime startDate, DateTime endDate, String priority, String authorization }) async
    test('test getApiV1CasesMetricsMttd', () async {
      // TODO
    });

    // Get Mttr
    //
    //Future<MttrResponse> getApiV1CasesMetricsMttr({ DateTime startDate, DateTime endDate, String priority, String authorization }) async
    test('test getApiV1CasesMetricsMttr', () async {
      // TODO
    });

    // Get Summary
    //
    //Future<CaseMetricsSummaryResponse> getApiV1CasesMetricsSummary({ DateTime startDate, DateTime endDate, String authorization }) async
    test('test getApiV1CasesMetricsSummary', () async {
      // TODO
    });

  });
}
