# vigil_api_v1.api.CasesApi

## Load the API package
```dart
import 'package:vigil_api_v1/api.dart';
```

All URIs are relative to *https://vigil.example.com*

Method | HTTP request | Description
------------- | ------------- | -------------
[**deleteApiV1CasesCaseIdFindingsFindingId**](CasesApi.md#deleteapiv1casescaseidfindingsfindingid) | **DELETE** /api/v1/cases/{case_id}/findings/{finding_id} | Remove Finding From Case
[**getApiV1Cases**](CasesApi.md#getapiv1cases) | **GET** /api/v1/cases | Get Cases
[**getApiV1CasesCaseId**](CasesApi.md#getapiv1casescaseid) | **GET** /api/v1/cases/{case_id} | Get Case
[**getApiV1CasesCaseIdEvidence**](CasesApi.md#getapiv1casescaseidevidence) | **GET** /api/v1/cases/{case_id}/evidence | Get Evidence
[**getApiV1CasesCaseIdIocs**](CasesApi.md#getapiv1casescaseidiocs) | **GET** /api/v1/cases/{case_id}/iocs | Get Iocs
[**getApiV1CasesCaseIdIocsExport**](CasesApi.md#getapiv1casescaseidiocsexport) | **GET** /api/v1/cases/{case_id}/iocs/export | Export Iocs
[**getApiV1CasesStatsSummary**](CasesApi.md#getapiv1casesstatssummary) | **GET** /api/v1/cases/stats/summary | Get Cases Summary
[**patchApiV1CasesCaseId**](CasesApi.md#patchapiv1casescaseid) | **PATCH** /api/v1/cases/{case_id} | Update Case
[**postApiV1Cases**](CasesApi.md#postapiv1cases) | **POST** /api/v1/cases | Create Case
[**postApiV1CasesCaseIdClose**](CasesApi.md#postapiv1casescaseidclose) | **POST** /api/v1/cases/{case_id}/close | Close Case
[**postApiV1CasesCaseIdEvidence**](CasesApi.md#postapiv1casescaseidevidence) | **POST** /api/v1/cases/{case_id}/evidence | Add Evidence
[**postApiV1CasesCaseIdFindingsFindingId**](CasesApi.md#postapiv1casescaseidfindingsfindingid) | **POST** /api/v1/cases/{case_id}/findings/{finding_id} | Add Finding To Case
[**postApiV1CasesCaseIdIocs**](CasesApi.md#postapiv1casescaseidiocs) | **POST** /api/v1/cases/{case_id}/iocs | Add Ioc
[**postApiV1CasesCaseIdIocsBulk**](CasesApi.md#postapiv1casescaseidiocsbulk) | **POST** /api/v1/cases/{case_id}/iocs/bulk | Bulk Add Iocs
[**postApiV1CasesCaseIdMerge**](CasesApi.md#postapiv1casescaseidmerge) | **POST** /api/v1/cases/{case_id}/merge | Merge Cases
[**postApiV1CasesSearch**](CasesApi.md#postapiv1casessearch) | **POST** /api/v1/cases/search | Search Cases


# **deleteApiV1CasesCaseIdFindingsFindingId**
> CaseSchema deleteApiV1CasesCaseIdFindingsFindingId(caseId, findingId, authorization)

Remove Finding From Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String findingId = findingId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.deleteApiV1CasesCaseIdFindingsFindingId(caseId, findingId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->deleteApiV1CasesCaseIdFindingsFindingId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **findingId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSchema**](CaseSchema.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1Cases**
> CaseListResponse getApiV1Cases(state, workflow, priority, dataSource, slaAtRisk, assignee, closed, query, needsYou, kind, limit, offset, authorization)

Get Cases

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String state = state_example; // String | 
final String workflow = workflow_example; // String | 
final String priority = priority_example; // String | 
final String dataSource = dataSource_example; // String | 
final bool slaAtRisk = true; // bool | 
final String assignee = assignee_example; // String | 
final bool closed = true; // bool | 
final String query = query_example; // String | 
final bool needsYou = true; // bool | 
final String kind = kind_example; // String | 
final int limit = 56; // int | 
final int offset = 56; // int | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1Cases(state, workflow, priority, dataSource, slaAtRisk, assignee, closed, query, needsYou, kind, limit, offset, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1Cases: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **state** | **String**|  | [optional] 
 **workflow** | **String**|  | [optional] 
 **priority** | **String**|  | [optional] 
 **dataSource** | **String**|  | [optional] 
 **slaAtRisk** | **bool**|  | [optional] [default to false]
 **assignee** | **String**|  | [optional] 
 **closed** | **bool**|  | [optional] 
 **query** | **String**|  | [optional] 
 **needsYou** | **bool**|  | [optional] [default to false]
 **kind** | **String**|  | [optional] 
 **limit** | **int**|  | [optional] [default to 100]
 **offset** | **int**|  | [optional] [default to 0]
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseListResponse**](CaseListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesCaseId**
> CaseDetailResponse getApiV1CasesCaseId(caseId, authorization)

Get Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesCaseId(caseId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1CasesCaseId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseDetailResponse**](CaseDetailResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesCaseIdEvidence**
> CaseEvidenceListResponse getApiV1CasesCaseIdEvidence(caseId, evidenceType, authorization)

Get Evidence

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String evidenceType = evidenceType_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesCaseIdEvidence(caseId, evidenceType, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1CasesCaseIdEvidence: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **evidenceType** | **String**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseEvidenceListResponse**](CaseEvidenceListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesCaseIdIocs**
> CaseIOCListResponse getApiV1CasesCaseIdIocs(caseId, iocType, authorization)

Get Iocs

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String iocType = iocType_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesCaseIdIocs(caseId, iocType, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1CasesCaseIdIocs: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **iocType** | **String**|  | [optional] 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseIOCListResponse**](CaseIOCListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesCaseIdIocsExport**
> CaseIOCExportResponse getApiV1CasesCaseIdIocsExport(caseId, format, authorization)

Export Iocs

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String format = format_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesCaseIdIocsExport(caseId, format, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1CasesCaseIdIocsExport: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **format** | **String**|  | [optional] [default to 'json']
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseIOCExportResponse**](CaseIOCExportResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiV1CasesStatsSummary**
> CaseSummaryResponse getApiV1CasesStatsSummary(authorization)

Get Cases Summary

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String authorization = authorization_example; // String | 

try {
    final response = api.getApiV1CasesStatsSummary(authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->getApiV1CasesStatsSummary: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSummaryResponse**](CaseSummaryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **patchApiV1CasesCaseId**
> CaseSuccessResponse patchApiV1CasesCaseId(caseId, caseUpdate, authorization)

Update Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final CaseUpdate caseUpdate = ; // CaseUpdate | 
final String authorization = authorization_example; // String | 

try {
    final response = api.patchApiV1CasesCaseId(caseId, caseUpdate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->patchApiV1CasesCaseId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **caseUpdate** | [**CaseUpdate**](CaseUpdate.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSuccessResponse**](CaseSuccessResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1Cases**
> CaseSchema postApiV1Cases(caseCreate, authorization)

Create Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final CaseCreate caseCreate = ; // CaseCreate | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1Cases(caseCreate, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1Cases: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseCreate** | [**CaseCreate**](CaseCreate.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSchema**](CaseSchema.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdClose**
> CaseCloseResponse postApiV1CasesCaseIdClose(caseId, closureInfo, authorization)

Close Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final ClosureInfo closureInfo = ; // ClosureInfo | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdClose(caseId, closureInfo, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdClose: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **closureInfo** | [**ClosureInfo**](ClosureInfo.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseCloseResponse**](CaseCloseResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdEvidence**
> CaseEvidenceSchema postApiV1CasesCaseIdEvidence(caseId, evidenceAdd, authorization)

Add Evidence

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final EvidenceAdd evidenceAdd = ; // EvidenceAdd | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdEvidence(caseId, evidenceAdd, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdEvidence: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **evidenceAdd** | [**EvidenceAdd**](EvidenceAdd.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseEvidenceSchema**](CaseEvidenceSchema.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdFindingsFindingId**
> CaseSchema postApiV1CasesCaseIdFindingsFindingId(caseId, findingId, authorization)

Add Finding To Case

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final String findingId = findingId_example; // String | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdFindingsFindingId(caseId, findingId, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdFindingsFindingId: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **findingId** | **String**|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSchema**](CaseSchema.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdIocs**
> CaseIOCSchema postApiV1CasesCaseIdIocs(caseId, iOCAdd, authorization)

Add Ioc

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final IOCAdd iOCAdd = ; // IOCAdd | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdIocs(caseId, iOCAdd, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdIocs: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **iOCAdd** | [**IOCAdd**](IOCAdd.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseIOCSchema**](CaseIOCSchema.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdIocsBulk**
> CaseIOCBulkResponse postApiV1CasesCaseIdIocsBulk(caseId, iOCBulkAdd, authorization)

Bulk Add Iocs

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final IOCBulkAdd iOCBulkAdd = ; // IOCBulkAdd | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdIocsBulk(caseId, iOCBulkAdd, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdIocsBulk: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **iOCBulkAdd** | [**IOCBulkAdd**](IOCBulkAdd.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseIOCBulkResponse**](CaseIOCBulkResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesCaseIdMerge**
> CaseMergeResponse postApiV1CasesCaseIdMerge(caseId, mergeRequest, authorization)

Merge Cases

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final String caseId = caseId_example; // String | 
final MergeRequest mergeRequest = ; // MergeRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesCaseIdMerge(caseId, mergeRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesCaseIdMerge: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **caseId** | **String**|  | 
 **mergeRequest** | [**MergeRequest**](MergeRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseMergeResponse**](CaseMergeResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **postApiV1CasesSearch**
> CaseSearchResponse postApiV1CasesSearch(searchRequest, authorization)

Search Cases

### Example
```dart
import 'package:vigil_api_v1/api.dart';

final api = VigilApiV1().getCasesApi();
final SearchRequest searchRequest = ; // SearchRequest | 
final String authorization = authorization_example; // String | 

try {
    final response = api.postApiV1CasesSearch(searchRequest, authorization);
    print(response);
} on DioException catch (e) {
    print('Exception when calling CasesApi->postApiV1CasesSearch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **searchRequest** | [**SearchRequest**](SearchRequest.md)|  | 
 **authorization** | **String**|  | [optional] 

### Return type

[**CaseSearchResponse**](CaseSearchResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

