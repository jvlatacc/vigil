import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for WorkflowsApi
void main() {
  final instance = VigilApiV1().getWorkflowsApi();

  group(WorkflowsApi, () {
    // List Workflows
    //
    //Future<WorkflowListResponse> getApiV1Workflows({ String authorization }) async
    test('test getApiV1Workflows', () async {
      // TODO
    });

    // Get Workflow
    //
    //Future<WorkflowDetailResponse> getApiV1WorkflowsWorkflowId(String workflowId, { String authorization }) async
    test('test getApiV1WorkflowsWorkflowId', () async {
      // TODO
    });

  });
}
