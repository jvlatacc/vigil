import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';


/// tests for BreakerApi
void main() {
  final instance = VigilApiV1().getBreakerApi();

  group(BreakerApi, () {
    // Breaker Status
    //
    //Future<BreakerStatusResponse> getApiV1ResponseBreaker({ String authorization }) async
    test('test getApiV1ResponseBreaker', () async {
      // TODO
    });

    // Breaker Reset
    //
    //Future<BreakerResetResponse> postApiV1ResponseBreakerReset(BreakerResetRequest breakerResetRequest, { String authorization }) async
    test('test postApiV1ResponseBreakerReset', () async {
      // TODO
    });

  });
}
