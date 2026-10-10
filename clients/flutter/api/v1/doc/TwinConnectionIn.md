# vigil_api_v1.model.TwinConnectionIn

## Load the model package
```dart
import 'package:vigil_api_v1/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**attributes** | [**BuiltMap&lt;String, JsonObject&gt;**](JsonObject.md) |  | [optional] 
**connectionType** | **String** |  | 
**device** | **String** | device_key, or the hostname the device was observed under; implied by `process` when omitted, and when both are given they must resolve to the same device | [optional] 
**direction** | **String** |  | [optional] 
**localIp** | **String** |  | [optional] 
**localPort** | **int** |  | [optional] 
**process** | [**TwinProcessRef**](TwinProcessRef.md) |  | [optional] 
**protocol** | **String** |  | [optional] 
**remoteIp** | **String** |  | [optional] 
**remotePort** | **int** |  | [optional] 
**startedAt** | [**DateTime**](DateTime.md) |  | [optional] 
**state** | **String** |  | [optional] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


