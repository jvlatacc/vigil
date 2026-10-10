import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

// tests for StartRunRequest
void main() {
  final instance = StartRunRequestBuilder();
  // TODO add properties to the builder and call build()

  group(StartRunRequest, () {
    // Arch file path; empty routes through the run-kind registry.
    // String arch (default value: '')
    test('to test the property `arch`', () async {
      // TODO
    });

    // Path to the deployment config.
    // String config
    test('to test the property `config`', () async {
      // TODO
    });

    // BuiltMap<String, JsonObject> overrides
    test('to test the property `overrides`', () async {
      // TODO
    });

    // Path to the playbook: the scenario as data.
    // String playbook
    test('to test the property `playbook`', () async {
      // TODO
    });

    // What the run is being asked to do.
    // String prompt (default value: '')
    test('to test the property `prompt`', () async {
      // TODO
    });

    // One of hunt, root_cause, adjudicate, investigate, compose, chat.
    // String runKind (default value: 'hunt')
    test('to test the property `runKind`', () async {
      // TODO
    });

    // String tenantId
    test('to test the property `tenantId`', () async {
      // TODO
    });

  });
}
