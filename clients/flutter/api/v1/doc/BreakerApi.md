# vigil_api_v1.api.BreakerApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getApiV1ResponseBreaker**](BreakerApi.md#getapiv1responsebreaker) | **GET** /api/v1/response/breaker | Breaker Status
[**postApiV1ResponseBreakerReset**](BreakerApi.md#postapiv1responsebreakerreset) | **POST** /api/v1/response/breaker/reset | Breaker Reset


# **getApiV1ResponseBreaker**
> BreakerStatusResponse getApiV1ResponseBreaker(authorization)

Breaker Status

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getBreakerApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1ResponseBreaker(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling BreakerApi->getApiV1ResponseBreaker: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**BreakerStatusResponse**](BreakerStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1ResponseBreakerReset**
> BreakerResetResponse postApiV1ResponseBreakerReset(breakerResetRequest, authorization)

Breaker Reset

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getBreakerApi();
final BreakerResetRequest breakerResetRequest = ; // BreakerResetRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1ResponseBreakerReset(breakerResetRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling BreakerApi->postApiV1ResponseBreakerReset: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **breakerResetRequest** | [**BreakerResetRequest**](BreakerResetRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**BreakerResetResponse**](BreakerResetResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

