import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for DigitalTwinApi
void main() {
  final instance = VigilApiV1().getDigitalTwinApi();

  group(DigitalTwinApi, () {
    // Get Devices
    //
    //Future<TwinDeviceListResponse> getApiV1DigitalTwinDevices({ String authorization }) async
    test('test getApiV1DigitalTwinDevices', () async {
      // TODO
    });

    // Get Graph
    //
    //Future<TwinGraphPayload> getApiV1DigitalTwinGraph({ DateTime since, String deviceId, String authorization }) async
    test('test getApiV1DigitalTwinGraph', () async {
      // TODO
    });

    // Ingest Observations
    //
    //Future<TwinIngestResult> postApiV1DigitalTwinIngest(TwinIngestBatch twinIngestBatch, { String authorization }) async
    test('test postApiV1DigitalTwinIngest', () async {
      // TODO
    });

  });
}
