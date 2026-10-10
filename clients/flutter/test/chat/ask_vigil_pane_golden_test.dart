import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/chat/ask_vigil_pane.dart';

import '../helpers/chat_stub.dart';
import '../helpers/wired_vigil.dart';
import 'ask_vigil_pane_test.dart' show ScriptedStream, pumpPane, renderedText;

/// A golden capture of the Ask Vigil pane mid-turn — the streaming state
/// native windows cannot show in a browser. Regenerate with:
///   flutter test --update-goldens test/chat/ask_vigil_pane_golden_test.dart
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // Same loaders as the design goldens — the bundled static TTFs must
    // actually load or the capture silently falls back to the Ahem font.
    Future<void> load(String family, List<String> files) async {
      final loader = FontLoader(family);
      for (final file in files) {
        loader.addFont(rootBundle.load('assets/fonts/$file'));
      }
      await loader.load();
    }

    await load('Plus Jakarta Sans', [
      'plus-jakarta-sans-400.ttf',
      'plus-jakarta-sans-500.ttf',
      'plus-jakarta-sans-600.ttf',
      'plus-jakarta-sans-700.ttf',
    ]);
    await load('Roboto Mono', [
      'roboto-mono-400.ttf',
      'roboto-mono-500.ttf',
    ]);
  });

  testWidgets('the streaming state — partial answer mid-turn', (tester) async {
    final stream = ScriptedStream();
    final session = stubChatSession(handler: (options, request) {
      if (request.path.contains('/api/conversations')) {
        return json(200, {'conversations': []});
      }
      return stream.body;
    });
    await pumpPane(tester, session);

    await tester.enterText(
        find.byType(TextField), 'what does isolating web-prod-3 touch?');
    await tester.pump();
    await tester.tap(find.byKey(const Key('ask-send')));
    await tester.pump(const Duration(milliseconds: 16));

    // First markdown chunk lands; the stream stays open — the capture is
    // the incremental state: partial answer, streaming indicator, stop.
    stream.add(sseFrame({
      'type': 'text',
      'content': '**Isolate `web-prod-3`** — holding at 0.88 confidence, '
          'below the 0.90 auto-approve line.\n\n'
          '- Host: `web-prod-3` (production web tier)\n'
          '- Proposed action is reversible\n'
          '- Approval routes to **Needs you**',
    }));
    await tester.pump(const Duration(milliseconds: 16));
    expect(renderedText(tester), contains('auto-approve line'),
        reason: 'the capture shows the mid-turn transcript');

    await expectLater(
      find.byType(AskVigilPane),
      matchesGoldenFile('goldens/ask-vigil-streaming.png'),
    );

    // End the turn cleanly so no stream work outlives the test.
    await stream.close();
    await tester.pumpAndSettle();
  });
}
