# vigil_api_v1.api.CaseMetricsApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1CasesMetricsBreached**](CaseMetricsApi.md#getapiv1casesmetricsbreached) | **GET** /api/v1/cases/metrics/breached | Get Breached Cases
[**getApiV1CasesMetricsByPriority**](CaseMetricsApi.md#getapiv1casesmetricsbypriority) | **GET** /api/v1/cases/metrics/by-priority | Get By Priority
[**getApiV1CasesMetricsByStatus**](CaseMetricsApi.md#getapiv1casesmetricsbystatus) | **GET** /api/v1/cases/metrics/by-status | Get By Status
[**getApiV1CasesMetricsMttd**](CaseMetricsApi.md#getapiv1casesmetricsmttd) | **GET** /api/v1/cases/metrics/mttd | Get Mttd
[**getApiV1CasesMetricsMttr**](CaseMetricsApi.md#getapiv1casesmetricsmttr) | **GET** /api/v1/cases/metrics/mttr | Get Mttr
[**getApiV1CasesMetricsSummary**](CaseMetricsApi.md#getapiv1casesmetricssummary) | **GET** /api/v1/cases/metrics/summary | Get Summary


# **getApiV1CasesMetricsBreached**
> BreachedCasesResponse getApiV1CasesMetricsBreached(authorization)

Get Breached Cases

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsBreached(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsBreached: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**BreachedCasesResponse**](BreachedCasesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesMetricsByPriority**
> ByPriorityResponse getApiV1CasesMetricsByPriority(startDate, endDate, authorization)

Get By Priority

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final DateTime startDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final DateTime endDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsByPriority(startDate, endDate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsByPriority: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startDate** | **DateTime**|  | [optional] 
 **endDate** | **DateTime**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**ByPriorityResponse**](ByPriorityResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesMetricsByStatus**
> ByStatusResponse getApiV1CasesMetricsByStatus(startDate, endDate, authorization)

Get By Status

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final DateTime startDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final DateTime endDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsByStatus(startDate, endDate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsByStatus: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startDate** | **DateTime**|  | [optional] 
 **endDate** | **DateTime**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**ByStatusResponse**](ByStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesMetricsMttd**
> MttdResponse getApiV1CasesMetricsMttd(startDate, endDate, priority, authorization)

Get Mttd

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final DateTime startDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final DateTime endDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final String priority = priority_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsMttd(startDate, endDate, priority, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsMttd: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startDate** | **DateTime**|  | [optional] 
 **endDate** | **DateTime**|  | [optional] 
 **priority** | **String**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**MttdResponse**](MttdResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesMetricsMttr**
> MttrResponse getApiV1CasesMetricsMttr(startDate, endDate, priority, authorization)

Get Mttr

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final DateTime startDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final DateTime endDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final String priority = priority_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsMttr(startDate, endDate, priority, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsMttr: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startDate** | **DateTime**|  | [optional] 
 **endDate** | **DateTime**|  | [optional] 
 **priority** | **String**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**MttrResponse**](MttrResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesMetricsSummary**
> CaseMetricsSummaryResponse getApiV1CasesMetricsSummary(startDate, endDate, authorization)

Get Summary

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCaseMetricsApi();
final DateTime startDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final DateTime endDate = 2013-10-20T19:20:30+01:00; // DateTime | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesMetricsSummary(startDate, endDate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CaseMetricsApi->getApiV1CasesMetricsSummary: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **startDate** | **DateTime**|  | [optional] 
 **endDate** | **DateTime**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseMetricsSummaryResponse**](CaseMetricsSummaryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

