# vigil_api_v1.api.FindingsApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1Findings**](FindingsApi.md#getapiv1findings) | **GET** /api/v1/findings | Get Findings
[**getApiV1FindingsFindingId**](FindingsApi.md#getapiv1findingsfindingid) | **GET** /api/v1/findings/{finding_id} | Get Finding
[**getApiV1FindingsStatsSummary**](FindingsApi.md#getapiv1findingsstatssummary) | **GET** /api/v1/findings/stats/summary | Get Findings Summary
[**patchApiV1FindingsFindingId**](FindingsApi.md#patchapiv1findingsfindingid) | **PATCH** /api/v1/findings/{finding_id} | Update Finding


# **getApiV1Findings**
> FindingListResponse getApiV1Findings(severity, dataSource, clusterId, minAnomalyScore, status, search, offset, limit, sortBy, sortOrder, exclusions, authorization)

Get Findings

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getFindingsApi();
final String severity = severity_example; // String | 
final String dataSource = dataSource_example; // String | 
final int clusterId = 56; // int | 
final num minAnomalyScore = 8.14; // num | 
final String status = status_example; // String | 
final String search = search_example; // String | Text search across finding IDs, descriptions, entity context
final int offset = 56; // int | 
final int limit = 56; // int | 
final String sortBy = sortBy_example; // String | 
final String sortOrder = sortOrder_example; // String | 
final String exclusions = exclusions_example; // String | Findings naming an analyst-excluded IP: include them (default), hide them, or return only them. Each finding carries `excluded_ips`.
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1Findings(severity, dataSource, clusterId, minAnomalyScore, status, search, offset, limit, sortBy, sortOrder, exclusions, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling FindingsApi->getApiV1Findings: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **severity** | **String**|  | [optional] 
 **dataSource** | **String**|  | [optional] 
 **clusterId** | **int**|  | [optional] 
 **minAnomalyScore** | **num**|  | [optional] 
 **status** | **String**|  | [optional] 
 **search** | **String**| Text search across finding IDs, descriptions, entity context | [optional] 
 **offset** | **int**|  | [optional] [default to 0]
 **limit** | **int**|  | [optional] [default to 100]
 **sortBy** | **String**|  | [optional] [default to 'timestamp']
 **sortOrder** | **String**|  | [optional] [default to 'desc']
 **exclusions** | **String**| Findings naming an analyst-excluded IP: include them (default), hide them, or return only them. Each finding carries `excluded_ips`. | [optional] [default to 'include']
 **authorization** | **String**|  | [optional] 

### Return type

[**FindingListResponse**](FindingListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1FindingsFindingId**
> FindingRecord getApiV1FindingsFindingId(findingId, authorization)

Get Finding

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getFindingsApi();
final String findingId = findingId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1FindingsFindingId(findingId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling FindingsApi->getApiV1FindingsFindingId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **findingId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**FindingRecord**](FindingRecord.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1FindingsStatsSummary**
> FindingsSummaryResponse getApiV1FindingsStatsSummary(exclusions, authorization)

Get Findings Summary

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getFindingsApi();
final String exclusions = exclusions_example; // String | Count findings naming an analyst-excluded IP (include, the default), leave them out (hide), or count only them (only).
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1FindingsStatsSummary(exclusions, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling FindingsApi->getApiV1FindingsStatsSummary: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **exclusions** | **String**| Count findings naming an analyst-excluded IP (include, the default), leave them out (hide), or count only them (only). | [optional] [default to 'include']
 **authorization** | **String**|  | [optional] 

### Return type

[**FindingsSummaryResponse**](FindingsSummaryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **patchApiV1FindingsFindingId**
> FindingUpdateResponse patchApiV1FindingsFindingId(findingId, findingUpdate, authorization)

Update Finding

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getFindingsApi();
final String findingId = findingId_example; // String | 
final FindingUpdate findingUpdate = ; // FindingUpdate | 
final String authorization = authorization_example; // String | 

try {
    final response = api.patchApiV1FindingsFindingId(findingId, findingUpdate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling FindingsApi->patchApiV1FindingsFindingId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **findingId** | **String**|  | 
 **findingUpdate** | [**FindingUpdate**](FindingUpdate.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**FindingUpdateResponse**](FindingUpdateResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

