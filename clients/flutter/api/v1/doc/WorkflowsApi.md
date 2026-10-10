# vigil_api_v1.api.WorkflowsApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1Workflows**](WorkflowsApi.md#getapiv1workflows) | **GET** /api/v1/workflows | List Workflows
[**getApiV1WorkflowsWorkflowId**](WorkflowsApi.md#getapiv1workflowsworkflowid) | **GET** /api/v1/workflows/{workflow_id} | Get Workflow


# **getApiV1Workflows**
> WorkflowListResponse getApiV1Workflows(authorization)

List Workflows

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getWorkflowsApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1Workflows(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling WorkflowsApi->getApiV1Workflows: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**WorkflowListResponse**](WorkflowListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1WorkflowsWorkflowId**
> WorkflowDetailResponse getApiV1WorkflowsWorkflowId(workflowId, authorization)

Get Workflow

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getWorkflowsApi();
final String workflowId = workflowId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1WorkflowsWorkflowId(workflowId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling WorkflowsApi->getApiV1WorkflowsWorkflowId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **workflowId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**WorkflowDetailResponse**](WorkflowDetailResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

