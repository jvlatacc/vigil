import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for ApprovalsApi
void main() {
  final instance = VigilApiV1().getApprovalsApi();

  group(ApprovalsApi, () {
    // List Approvals
    //
    //Future<ApprovalListResponse> getApiV1Approvals({ String status, String workflowRunId, int limit, String authorization }) async
    test('test getApiV1Approvals', () async {
      // TODO
    });

    // Get Approval
    //
    //Future<PendingActionResponse> getApiV1ApprovalsActionId(String actionId, { String authorization }) async
    test('test getApiV1ApprovalsActionId', () async {
      // TODO
    });

    // List Needs You
    //
    //Future<NeedsYouResponse> getApiV1ApprovalsNeedsYou({ String caseId, String authorization }) async
    test('test getApiV1ApprovalsNeedsYou', () async {
      // TODO
    });

    // List Pending Approvals
    //
    //Future<BuiltMap<String, BuiltList<BuiltMap<String, JsonObject>>>> getApiV1ApprovalsPending({ String authorization }) async
    test('test getApiV1ApprovalsPending', () async {
      // TODO
    });

    // Approve Action
    //
    //Future<ApprovalActionResult> postApiV1ApprovalsActionIdApprove(String actionId, ApproveRequest approveRequest, { String authorization }) async
    test('test postApiV1ApprovalsActionIdApprove', () async {
      // TODO
    });

    // Reject Action
    //
    //Future<ApprovalActionResult> postApiV1ApprovalsActionIdReject(String actionId, RejectRequest rejectRequest, { String authorization }) async
    test('test postApiV1ApprovalsActionIdReject', () async {
      // TODO
    });

  });
}
