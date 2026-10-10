# vigil_api_v1.api.AgentRunsApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1AgentRuns**](AgentRunsApi.md#getapiv1agentruns) | **GET** /api/v1/agent-runs | List Runs
[**getApiV1AgentRunsRunId**](AgentRunsApi.md#getapiv1agentrunsrunid) | **GET** /api/v1/agent-runs/{run_id} | Get Run
[**postApiV1AgentRuns**](AgentRunsApi.md#postapiv1agentruns) | **POST** /api/v1/agent-runs | Start Run
[**postApiV1AgentRunsRunIdDirectives**](AgentRunsApi.md#postapiv1agentrunsruniddirectives) | **POST** /api/v1/agent-runs/{run_id}/directives | Queue Directive


# **getApiV1AgentRuns**
> RunListResponse getApiV1AgentRuns(status, limit, offset, authorization)

List Runs

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getAgentRunsApi();
final String status = status_example; // String | 
final int limit = 56; // int | 
final int offset = 56; // int | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1AgentRuns(status, limit, offset, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AgentRunsApi->getApiV1AgentRuns: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **status** | **String**|  | [optional] 
 **limit** | **int**|  | [optional] [default to 50]
 **offset** | **int**|  | [optional] [default to 0]
 **authorization** | **String**|  | [optional] 

### Return type

[**RunListResponse**](RunListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1AgentRunsRunId**
> RunStatusResponse getApiV1AgentRunsRunId(runId, authorization)

Get Run

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getAgentRunsApi();
final String runId = runId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1AgentRunsRunId(runId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AgentRunsApi->getApiV1AgentRunsRunId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **runId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**RunStatusResponse**](RunStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1AgentRuns**
> StartRunResponse postApiV1AgentRuns(startRunRequest, authorization)

Start Run

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getAgentRunsApi();
final StartRunRequest startRunRequest = ; // StartRunRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1AgentRuns(startRunRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AgentRunsApi->postApiV1AgentRuns: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startRunRequest** | [**StartRunRequest**](StartRunRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**StartRunResponse**](StartRunResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1AgentRunsRunIdDirectives**
> DirectiveResponse postApiV1AgentRunsRunIdDirectives(runId, directiveRequest, authorization)

Queue Directive

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getAgentRunsApi();
final String runId = runId_example; // String | 
final DirectiveRequest directiveRequest = ; // DirectiveRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1AgentRunsRunIdDirectives(runId, directiveRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling AgentRunsApi->postApiV1AgentRunsRunIdDirectives: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **runId** | **String**|  | 
 **directiveRequest** | [**DirectiveRequest**](DirectiveRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**DirectiveResponse**](DirectiveResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

