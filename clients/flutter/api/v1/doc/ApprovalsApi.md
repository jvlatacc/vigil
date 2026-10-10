# vigil_api_v1.api.ApprovalsApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1Approvals**](ApprovalsApi.md#getapiv1approvals) | **GET** /api/v1/approvals | List Approvals
[**getApiV1ApprovalsActionId**](ApprovalsApi.md#getapiv1approvalsactionid) | **GET** /api/v1/approvals/{action_id} | Get Approval
[**getApiV1ApprovalsNeedsYou**](ApprovalsApi.md#getapiv1approvalsneedsyou) | **GET** /api/v1/approvals/needs-you | List Needs You
[**getApiV1ApprovalsPending**](ApprovalsApi.md#getapiv1approvalspending) | **GET** /api/v1/approvals/pending | List Pending Approvals
[**postApiV1ApprovalsActionIdApprove**](ApprovalsApi.md#postapiv1approvalsactionidapprove) | **POST** /api/v1/approvals/{action_id}/approve | Approve Action
[**postApiV1ApprovalsActionIdReject**](ApprovalsApi.md#postapiv1approvalsactionidreject) | **POST** /api/v1/approvals/{action_id}/reject | Reject Action


# **getApiV1Approvals**
> ApprovalListResponse getApiV1Approvals(status, workflowRunId, limit, authorization)

List Approvals

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String status = status_example; // String | Filter by status: pending | approved | rejected | executed | failed.
final String workflowRunId = workflowRunId_example; // String | Restrict to approvals linked to this workflow run.
final int limit = 56; // int | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1Approvals(status, workflowRunId, limit, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->getApiV1Approvals: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **status** | **String**| Filter by status: pending | approved | rejected | executed | failed. | [optional] 
 **workflowRunId** | **String**| Restrict to approvals linked to this workflow run. | [optional] 
 **limit** | **int**|  | [optional] [default to 100]
 **authorization** | **String**|  | [optional] 

### Return type

[**ApprovalListResponse**](ApprovalListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1ApprovalsActionId**
> PendingActionResponse getApiV1ApprovalsActionId(actionId, authorization)

Get Approval

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String actionId = actionId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1ApprovalsActionId(actionId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->getApiV1ApprovalsActionId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **actionId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**PendingActionResponse**](PendingActionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1ApprovalsNeedsYou**
> NeedsYouResponse getApiV1ApprovalsNeedsYou(caseId, authorization)

List Needs You

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String caseId = caseId_example; // String | Only items whose resolved case id is this one.
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1ApprovalsNeedsYou(caseId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->getApiV1ApprovalsNeedsYou: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**| Only items whose resolved case id is this one. | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**NeedsYouResponse**](NeedsYouResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1ApprovalsPending**
> BuiltMap<String, BuiltList<BuiltMap<String, JsonObject>>> getApiV1ApprovalsPending(authorization)

List Pending Approvals

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1ApprovalsPending(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->getApiV1ApprovalsPending: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**BuiltMap&lt;String, BuiltList&lt;BuiltMap&lt;String, JsonObject&gt;&gt;&gt;**](BuiltList.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1ApprovalsActionIdApprove**
> ApprovalActionResult postApiV1ApprovalsActionIdApprove(actionId, approveRequest, authorization)

Approve Action

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String actionId = actionId_example; // String | 
final ApproveRequest approveRequest = ; // ApproveRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1ApprovalsActionIdApprove(actionId, approveRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->postApiV1ApprovalsActionIdApprove: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **actionId** | **String**|  | 
 **approveRequest** | [**ApproveRequest**](ApproveRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**ApprovalActionResult**](ApprovalActionResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1ApprovalsActionIdReject**
> ApprovalActionResult postApiV1ApprovalsActionIdReject(actionId, rejectRequest, authorization)

Reject Action

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getApprovalsApi();
final String actionId = actionId_example; // String | 
final RejectRequest rejectRequest = ; // RejectRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1ApprovalsActionIdReject(actionId, rejectRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ApprovalsApi->postApiV1ApprovalsActionIdReject: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **actionId** | **String**|  | 
 **rejectRequest** | [**RejectRequest**](RejectRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**ApprovalActionResult**](ApprovalActionResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

