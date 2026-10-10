import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'chat_api.dart';
import 'failures.dart';

enum ChatRole { user, vigil, error }

/// One transcript row. A [ChatRole.error] row carries the failure reason the
/// console would show; it is not sent back to the server as a turn.
class ChatEntry {
  const ChatEntry(this.role, this.text);

  final ChatRole role;
  final String text;
}

/// The state behind the Ask Vigil surface: transcript rows, the in-flight
/// stream's accumulated text, and the conversation history list.
///
/// Rendering is incremental — every [ChatTextChunk] appends to [streamText]
/// and notifies listeners, so the pane re-renders per frame rather than
/// buffered-at-end (the axios failure mode the console's `streamFetch`
/// explicitly works around). The server persists each turn; this class is
/// the view's state, never the record — reloading a conversation always
/// shows the server's truth.
class ChatSession extends ChangeNotifier {
  ChatSession({required VigilChatClient chat, Random? random})
      : _chat = chat,
        _random = random ?? Random.secure();

  final VigilChatClient _chat;
  final Random _random;

  final List<ChatEntry> _entries = [];
  final List<ConversationSummary> _conversations = [];
  StreamSubscription<ChatStreamEvent>? _sub;
  CancelToken? _cancel;
  Completer<void>? _pendingTurn;

  bool _streaming = false;
  String _streamText = '';
  bool _toolProcessing = false;
  bool _historyLoading = false;
  String? _historyError;
  String? _activeConversationId;
  String? _openTitle;

  List<ChatEntry> get entries => List.unmodifiable(_entries);
  List<ConversationSummary> get conversations =>
      List.unmodifiable(_conversations);
  bool get streaming => _streaming;
  bool get toolProcessing => _toolProcessing;

  /// The accumulating answer for the turn in flight — empty when idle.
  String get streamText => _streamText;
  bool get historyLoading => _historyLoading;
  String? get historyError => _historyError;
  String? get activeConversationId => _activeConversationId;

  /// The picker's label: the open conversation's title, or a new-turn hint.
  ///
  /// The title survives even when the picker list isn't loaded (opening a
  /// past conversation never required loading the list first).
  String get currentLabel {
    for (final c in _conversations) {
      if (c.id == _activeConversationId) return c.label;
    }
    return _openTitle ?? 'New conversation';
  }

  /// Sends [text] as the user's turn and streams the answer.
  ///
  /// Prior turns (user and vigil, errors excluded — a failed turn never
  /// happened server-side) ride along as history, the console's `askedOf`
  /// mapping. On failure the error becomes a transcript row; nothing
  /// auto-retries — the pane offers the console's Retry affordance.
  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _streaming) return;
    _entries.add(ChatEntry(ChatRole.user, trimmed));
    _streaming = true;
    _streamText = '';
    _toolProcessing = false;
    notifyListeners();

    final sessionId = _activeConversationId ?? _newSessionId();
    final turns = [
      for (final e in _entries)
        if (e.role != ChatRole.error)
          ChatTurn(
            role: e.role == ChatRole.user ? 'user' : 'assistant',
            content: e.text,
          ),
    ];

    _cancel = CancelToken();
    final done = _pendingTurn = Completer<void>();
    _sub = _chat
        .streamTurn(turns: turns, sessionId: sessionId, cancelToken: _cancel)
        .listen(
      (event) {
        switch (event) {
          case ChatTextChunk(:final content):
            _streamText += content;
            _toolProcessing = false;
          case ChatToolProcessing():
            // Separate tool output from the prose preceding it.
            if (_streamText.isNotEmpty && !_streamText.endsWith('\n\n')) {
              _streamText += '\n\n';
            }
            _toolProcessing = true;
        }
        notifyListeners();
      },
      onError: (Object err) {
        _finishStream();
        _entries.add(ChatEntry(ChatRole.error, _failureText(err)));
        notifyListeners();
        _settleTurn();
      },
      onDone: () {
        // Capture the answer BEFORE _finishStream clears the buffer —
        // the committed row is the streamed answer, not the absence of it.
        final answer = _streamText;
        _finishStream();
        // The turn is durable server-side; a vigil row with nothing means
        // the model answered empty (the console's '_(no response)_').
        _entries.add(ChatEntry(
          ChatRole.vigil,
          answer.isEmpty ? '_(no response)_' : answer,
        ));
        _streamText = '';
        notifyListeners();
        _settleTurn();
        // Best-effort: the new conversation only exists server-side after
        // the turn; pick it up so the next picker open shows it.
        loadConversations();
      },
      cancelOnError: true,
    );
    return done.future;
  }

  /// Stops the in-flight turn — the console's abort: the partial answer is
  /// cleared, no error row, no vigil row (the server still persists what
  /// arrived, so reloading the conversation shows its truth).
  void stop() {
    _cancel?.cancel();
    _sub?.cancel();
    _sub = null;
    _finishStream();
    _settleTurn();
    notifyListeners();
  }

  /// Loads the conversation list for the picker. Failures surface as
  /// [historyError] — an honest error state in the picker, not an empty
  /// list that looks like "no history".
  Future<void> loadConversations() async {
    _historyLoading = true;
    _historyError = null;
    notifyListeners();
    try {
      final list = await _chat.conversations();
      _conversations
        ..clear()
        ..addAll(list);
    } on ChatFailure catch (e) {
      _historyError = e.message;
    } on Exception catch (e) {
      _historyError = e.toString();
    } finally {
      _historyLoading = false;
      notifyListeners();
    }
  }

  /// Opens a past conversation from the history list, replacing the local
  /// transcript with the server's messages.
  Future<void> openConversation(String id) async {
    if (_streaming) stop();
    _historyLoading = true;
    _historyError = null;
    notifyListeners();
    try {
      final conversation = await _chat.conversation(id);
      _activeConversationId = conversation.summary.id;
      _openTitle = conversation.summary.label;
      _entries
        ..clear()
        ..addAll([
          for (final m in conversation.messages)
            if ((m.content ?? '').trim().isNotEmpty)
              ChatEntry(
                m.role == 'user' ? ChatRole.user : ChatRole.vigil,
                m.content!,
              ),
        ]);
    } on ChatFailure catch (e) {
      _historyError = e.message;
    } on Exception catch (e) {
      _historyError = e.toString();
    } finally {
      _historyLoading = false;
      notifyListeners();
    }
  }

  /// Starts a new conversation — the transcript clears and the next send
  /// mints a fresh session id (the server creates the record on the turn).
  void startNewConversation() {
    if (_streaming) stop();
    _activeConversationId = null;
    _openTitle = null;
    _entries.clear();
    _streamText = '';
    _historyError = null;
    notifyListeners();
  }

  /// The text of the user turn a failed turn would retry (the console's
  /// `retryOf`); null when the last row isn't a failure after a user turn.
  String? get retryText {
    if (_entries.isEmpty) return null;
    final last = _entries.last;
    if (last.role != ChatRole.error || _entries.length < 2) return null;
    final previous = _entries[_entries.length - 2];
    return previous.role == ChatRole.user ? previous.text : null;
  }

  @override
  void dispose() {
    _cancel?.cancel();
    _sub?.cancel();
    _settleTurn();
    super.dispose();
  }

  /// Resolves the awaited [send] future exactly once — including the stop()
  /// and dispose() paths, which otherwise leave awaiters hung forever.
  void _settleTurn() {
    final pending = _pendingTurn;
    _pendingTurn = null;
    if (pending != null && !pending.isCompleted) pending.complete();
  }

  void _finishStream() {
    _streaming = false;
    _toolProcessing = false;
    _streamText = '';
    _cancel = null;
  }

  /// A failure the server sent is shown as is; only a failure to reach it
  /// blames the backend (the console's `reached` distinction).
  String _failureText(Object err) => switch (err) {
        ChatUnreachable(:final message) =>
          'Could not reach Vigil: $message. Is the backend running?',
        ChatRefusal(:final message) => message,
        ChatAuthRevoked(:final message) => message,
        _ => 'Could not reach Vigil: $err. Is the backend running?',
      };

  /// Session ids are the conversation ids server-side (claude.py:
  /// `session_id = request.session_id or uuid4()`). The console uses the
  /// browser's crypto.randomUUID; a random uuid here matches that shape.
  String _newSessionId() {
    final b = List<int>.generate(16, (_) => _random.nextInt(256));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    String hex(int i, int n) => b
        .sublist(i, i + n)
        .map((v) => v.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex(0, 4)}-${hex(4, 2)}-${hex(6, 2)}-${hex(8, 2)}-${hex(10, 6)}';
  }
}
