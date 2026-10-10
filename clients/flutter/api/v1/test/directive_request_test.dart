import 'package:test/test.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

// tests for DirectiveRequest
void main() {
  final instance = DirectiveRequestBuilder();
  // TODO add properties to the builder and call build()

  group(DirectiveRequest, () {
    // Who is steering. Defaults to the session user.
    // String actor
    test('to test the property `actor`', () async {
      // TODO
    });

    // Any of checkpoint_id, entity_key, question_id, hypothesis_id, tenant, revoke, grant.
    // BuiltMap<String, JsonObject> fields
    test('to test the property `fields`', () async {
      // TODO
    });

    // One of note, lead, abort, extend, conclude, approve, reject, benign, gap, boost.
    // String kind
    test('to test the property `kind`', () async {
      // TODO
    });

    // What the operator is telling the run.
    // String text (default value: '')
    test('to test the property `text`', () async {
      // TODO
    });

  });
}
