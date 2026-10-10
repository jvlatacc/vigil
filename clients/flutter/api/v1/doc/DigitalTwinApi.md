# vigil_api_v1.api.DigitalTwinApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1DigitalTwinDevices**](DigitalTwinApi.md#getapiv1digitaltwindevices) | **GET** /api/v1/digital-twin/devices | Get Devices
[**getApiV1DigitalTwinGraph**](DigitalTwinApi.md#getapiv1digitaltwingraph) | **GET** /api/v1/digital-twin/graph | Get Graph
[**postApiV1DigitalTwinIngest**](DigitalTwinApi.md#postapiv1digitaltwiningest) | **POST** /api/v1/digital-twin/ingest | Ingest Observations


# **getApiV1DigitalTwinDevices**
> TwinDeviceListResponse getApiV1DigitalTwinDevices(authorization)

Get Devices

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getDigitalTwinApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1DigitalTwinDevices(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DigitalTwinApi->getApiV1DigitalTwinDevices: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**TwinDeviceListResponse**](TwinDeviceListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1DigitalTwinGraph**
> TwinGraphPayload getApiV1DigitalTwinGraph(since, deviceId, authorization)

Get Graph

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getDigitalTwinApi();
final DateTime since = 2013-10-20T19:20:30+01:00; // DateTime | Keep only entities re-observed at or after this instant.
final String deviceId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | Scope the graph to one device: its processes and connections, with talks-to edges only to remotes the scoped payload still names.
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1DigitalTwinGraph(since, deviceId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DigitalTwinApi->getApiV1DigitalTwinGraph: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **since** | **DateTime**| Keep only entities re-observed at or after this instant. | [optional] 
 **deviceId** | **String**| Scope the graph to one device: its processes and connections, with talks-to edges only to remotes the scoped payload still names. | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**TwinGraphPayload**](TwinGraphPayload.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1DigitalTwinIngest**
> TwinIngestResult postApiV1DigitalTwinIngest(twinIngestBatch, authorization)

Ingest Observations

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getDigitalTwinApi();
final TwinIngestBatch twinIngestBatch = ; // TwinIngestBatch | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1DigitalTwinIngest(twinIngestBatch, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DigitalTwinApi->postApiV1DigitalTwinIngest: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **twinIngestBatch** | [**TwinIngestBatch**](TwinIngestBatch.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**TwinIngestResult**](TwinIngestResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

