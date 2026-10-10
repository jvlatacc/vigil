# vigil_api_v1.model.StartRunRequest

## Load the model package
```dart
import 'package:vigil_api_v1/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**arch** | **String** | Arch file path; empty routes through the run-kind registry. | [optional] [default to '']
**config** | **String** | Path to the deployment config. | 
**overrides** | [**BuiltMap&lt;String, JsonObject&gt;**](JsonObject.md) |  | [optional] 
**playbook** | **String** | Path to the playbook: the scenario as data. | 
**prompt** | **String** | What the run is being asked to do. | [optional] [default to '']
**runKind** | **String** | One of hunt, root_cause, adjudicate, investigate, compose, chat. | [optional] [default to 'hunt']
**tenantId** | **String** |  | [optional] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


