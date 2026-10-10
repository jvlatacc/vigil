# vigil_api_v1.model.DirectiveRequest

## Load the model package
```dart
import 'package:vigil_api_v1/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**actor** | **String** | Who is steering. Defaults to the session user. | [optional] 
**fields** | [**BuiltMap&lt;String, JsonObject&gt;**](JsonObject.md) | Any of checkpoint_id, entity_key, question_id, hypothesis_id, tenant, revoke, grant. | [optional] 
**kind** | **String** | One of note, lead, abort, extend, conclude, approve, reject, benign, gap, boost. | 
**text** | **String** | What the operator is telling the run. | [optional] [default to '']

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


