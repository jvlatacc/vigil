# vigil_api_v1.model.BreakerStatusResponse

## Load the model package
```dart
import 'package:vigil_api_v1/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**counters** | [**BuiltMap&lt;String, BuiltMap&lt;String, num&gt;&gt;**](BuiltMap.md) |  | [optional] 
**escalationFired** | **bool** |  | [optional] [default to false]
**openedAt** | **num** |  | [optional] 
**reason** | **String** |  | [optional] 
**rule** | **String** |  | [optional] 
**secondsLeft** | **int** |  | [optional] 
**state** | **String** |  | 
**store** | **String** |  | [optional] [default to 'redis']

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


