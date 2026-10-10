# vigil_api_v1.model.WorkflowDetailResponse

## Load the model package
```dart
import 'package:vigil_api_v1/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent** | [**BuiltMap&lt;String, JsonObject&gt;**](JsonObject.md) |  | [optional] 
**agents** | **BuiltList&lt;String&gt;** |  | [optional] 
**body** | **String** |  | 
**checkpoints** | **BuiltMap&lt;String, String&gt;** |  | [optional] 
**description** | **String** |  | [optional] [default to '']
**huntLike** | **bool** |  | 
**id** | **String** |  | 
**name** | **String** |  | 
**objectives** | **BuiltList&lt;String&gt;** |  | [optional] 
**phases** | [**BuiltList&lt;BuiltMap&lt;String, JsonObject&gt;&gt;**](BuiltMap.md) |  | [optional] 
**runKind** | **String** |  | 
**source_** | **String** |  | 
**toolsUsed** | **BuiltList&lt;String&gt;** |  | [optional] 
**triggerExamples** | **BuiltList&lt;String&gt;** |  | [optional] 
**useCase** | **String** |  | [optional] 
**version** | **int** |  | [optional] [default to 1]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


