import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/approvals/approval_machine.dart';

void main() {
  group('cadence constants', () {
    test('match the console spec', () {
      expect(undoFuseLength, const Duration(seconds: 8));
      expect(holdConfirmLength, const Duration(milliseconds: 1600));
      expect(approvalsPollInterval, const Duration(seconds: 20));
      expect(staleAfterFailures, 2);
      expect(maxPollBackoff, const Duration(minutes: 5));
    });
  });

  group('nextPollDelay', () {
    test('healthy polls keep the exact 20 s base regardless of jitter', () {
      for (final jitter in [0.0, 0.25, 0.5, 0.99]) {
        expect(
          nextPollDelay(consecutiveFailures: 0, jitter01: jitter),
          const Duration(seconds: 20),
        );
      }
    });

    test('the first failure keeps the base cadence, ±20% jittered', () {
      expect(
        nextPollDelay(consecutiveFailures: 1, jitter01: 0.5),
        const Duration(seconds: 20),
      );
      expect(
        nextPollDelay(consecutiveFailures: 1, jitter01: 0.0),
        const Duration(seconds: 16),
      );
      expect(
        nextPollDelay(consecutiveFailures: 1, jitter01: 0.999999),
        const Duration(seconds: 24),
      );
    });

    test('growth doubles per extra failure inside a ±20% jitter band', () {
      expect(
        nextPollDelay(consecutiveFailures: 2, jitter01: 0.5),
        const Duration(seconds: 40),
      );
      expect(
        nextPollDelay(consecutiveFailures: 2, jitter01: 0.0),
        const Duration(seconds: 32),
      );
      expect(
        nextPollDelay(consecutiveFailures: 2, jitter01: 0.999999),
        const Duration(seconds: 48),
      );
      expect(
        nextPollDelay(consecutiveFailures: 3, jitter01: 0.5),
        const Duration(seconds: 80),
      );
    });

    test('caps at 5 minutes', () {
      expect(
        nextPollDelay(consecutiveFailures: 10, jitter01: 0.0),
        const Duration(minutes: 5),
      );
      expect(
        nextPollDelay(consecutiveFailures: 30, jitter01: 0.999999),
        const Duration(minutes: 5),
      );
    });

    test('clamps nonsense failure counts', () {
      expect(
        nextPollDelay(consecutiveFailures: -3, jitter01: 0.5),
        const Duration(seconds: 20),
      );
    });
  });

  group('isStale', () {
    test('two consecutive failures are a pattern, one is a blip', () {
      expect(isStale(0), isFalse);
      expect(isStale(1), isFalse);
      expect(isStale(2), isTrue);
      expect(isStale(5), isTrue);
    });
  });

  group('ApprovalFuse', () {
    final start = DateTime.utc(2026, 10, 10, 14, 22);

    test('runs for 8 s from its start', () {
      final fuse = ApprovalFuse(
        actionId: 'a-1',
        title: 'Isolate host',
        verb: FuseVerb.approve,
        startedAt: start,
      );
      expect(fuse.stageAt(start.add(const Duration(seconds: 7, milliseconds: 999))),
          FuseStage.running);
      expect(
          fuse.stageAt(start.add(undoFuseLength)), FuseStage.expired);
      expect(
        fuse.progressAt(start.add(const Duration(seconds: 4))),
        closeTo(0.5, 0.001),
      );
      // After expiry the remaining time is zero, never negative.
      expect(fuse.remainingAt(start.add(const Duration(seconds: 10))),
          Duration.zero);
      expect(fuse.progressAt(start.add(const Duration(seconds: 10))), 0);
    });

    test('carries the verb tenses the toast renders', () {
      expect(FuseVerb.approve.presentTense, 'Approving');
      expect(FuseVerb.approve.pastTense, 'Approved');
      expect(FuseVerb.reject.presentTense, 'Rejecting');
      expect(FuseVerb.reject.pastTense, 'Rejected');
    });
  });

  group('parseCreatedAt', () {
    test('reads naive API timestamps as UTC', () {
      final parsed = parseCreatedAt('2026-10-10T13:58:00');
      expect(parsed, DateTime.utc(2026, 10, 10, 13, 58));
      expect(parsed!.isUtc, isTrue);
    });

    test('passes zoned timestamps through', () {
      expect(parseCreatedAt('2026-10-10T13:58:00Z'),
          DateTime.utc(2026, 10, 10, 13, 58));
      expect(parseCreatedAt('2026-10-10T15:58:00+02:00'),
          DateTime.utc(2026, 10, 10, 13, 58));
    });

    test('null and garbage give null', () {
      expect(parseCreatedAt(null), isNull);
      expect(parseCreatedAt(''), isNull);
      expect(parseCreatedAt('not-a-time'), isNull);
    });
  });

  group('waitedLabel', () {
    final created = DateTime.utc(2026, 10, 10, 13, 58);
    String label(String iso, DateTime now) => waitedLabel(iso, now);

    test('the console wording', () {
      expect(label('2026-10-10T13:58:00', created),
          'Waited under a minute');
      expect(label('2026-10-10T13:58:00', created.add(const Duration(minutes: 12))),
          'Waited 12m');
      expect(label('2026-10-10T13:58:00', created.add(const Duration(minutes: 90))),
          'Waited 1h 30m');
      expect(label('2026-10-10T13:58:00', created.add(const Duration(hours: 3, minutes: 4))),
          'Waited 3h 4m');
    });

    test('unparseable stamps render nothing', () {
      expect(waitedLabel(null, created), '');
      expect(waitedLabel('garbage', created), '');
    });
  });

  group('dataAgeLabel', () {
    test('the stale banner wording', () {
      final now = DateTime.utc(2026, 10, 10, 14, 22);
      expect(dataAgeLabel(null, now), 'Checked never');
      expect(dataAgeLabel(now, now), 'Checked just now');
      expect(
          dataAgeLabel(now.subtract(const Duration(minutes: 4)), now),
          'Checked 4 min ago');
      expect(
          dataAgeLabel(
              now.subtract(const Duration(hours: 2, minutes: 5)), now),
          'Checked 2 h 5 min ago');
      expect(
          dataAgeLabel(now.subtract(const Duration(hours: 3)), now),
          'Checked 3 h ago');
    });
  });
}
