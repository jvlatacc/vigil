import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for AgentRunsApi
void main() {
  final instance = VigilApiV1().getAgentRunsApi();

  group(AgentRunsApi, () {
    // List Runs
    //
    //Future<RunListResponse> getApiV1AgentRuns({ String status, int limit, int offset, String authorization }) async
    test('test getApiV1AgentRuns', () async {
      // TODO
    });

    // Get Run
    //
    //Future<RunStatusResponse> getApiV1AgentRunsRunId(String runId, { String authorization }) async
    test('test getApiV1AgentRunsRunId', () async {
      // TODO
    });

    // Start Run
    //
    //Future<StartRunResponse> postApiV1AgentRuns(StartRunRequest startRunRequest, { String authorization }) async
    test('test postApiV1AgentRuns', () async {
      // TODO
    });

    // Queue Directive
    //
    //Future<DirectiveResponse> postApiV1AgentRunsRunIdDirectives(String runId, DirectiveRequest directiveRequest, { String authorization }) async
    test('test postApiV1AgentRunsRunIdDirectives', () async {
      // TODO
    });

  });
}
