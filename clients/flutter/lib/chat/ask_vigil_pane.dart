import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';
import 'chat_session.dart';
import 'markdown_text.dart';

/// The Ask Vigil surface — the console's chat dock, never "Chat".
///
/// The [ChatSession] is owned by the caller (the shell), so the dock on a
/// wide layout and the modal sheet on a phone share one live transcript.
class AskVigilPane extends StatefulWidget {
  const AskVigilPane({super.key, required this.session, this.onClose});

  final ChatSession session;

  /// The dock's close affordance — provided by the shell on wide layouts;
  /// the modal sheet closes itself on phones.
  final VoidCallback? onClose;

  @override
  State<AskVigilPane> createState() => _AskVigilPaneState();
}

class _AskVigilPaneState extends State<AskVigilPane> {
  final TextEditingController _draft = TextEditingController();
  final ScrollController _scroll = ScrollController();

  ChatSession get _session => widget.session;

  @override
  void initState() {
    super.initState();
    _session.addListener(_onSessionChanged);
    // The send button's enabled state is built from the draft text —
    // without this listener typing never re-enables it.
    _draft.addListener(_onDraftChanged);
    if (_session.conversations.isEmpty && _session.historyError == null) {
      _session.loadConversations();
    }
  }

  @override
  void dispose() {
    _session.removeListener(_onSessionChanged);
    _draft.removeListener(_onDraftChanged);
    _draft.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onDraftChanged() {
    if (mounted) setState(() {});
  }

  void _onSessionChanged() {
    if (!mounted) return;
    // Keep the newest turn in view as frames land (post-frame: the list
    // hasn't laid out the new content yet).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  void _send() {
    final text = _draft.text;
    _draft.clear();
    _session.send(text);
    FocusScope.of(context).unfocus();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return ListenableBuilder(
      listenable: _session,
      builder: (context, _) => Column(
        children: [
          _header(colors),
          Divider(height: 1, thickness: 1, color: colors.ln0),
          Expanded(child: _transcript(colors)),
          _composer(colors),
        ],
      ),
    );
  }

  Widget _header(VigilColors colors) {
    final session = _session;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          VigilIcon(VigilIcons.sparkle, size: 16, color: colors.ac),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              session.currentLabel,
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (session.historyLoading)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          IconButton(
            key: const Key('ask-picker'),
            tooltip: 'Conversations',
            icon: const VigilIcon(VigilIcons.history, size: 18),
            color: colors.tx2,
            onPressed:
                session.conversations.isEmpty && session.historyError == null
                    ? null
                    : () => _pickConversation(context),
          ),
          IconButton(
            key: const Key('ask-new'),
            tooltip: 'New conversation',
            icon: const VigilIcon(VigilIcons.plus, size: 18),
            color: colors.tx2,
            onPressed:
                session.entries.isEmpty ? null : session.startNewConversation,
          ),
          if (widget.onClose != null)
            IconButton(
              key: const Key('ask-dock-close'),
              tooltip: 'Close Ask Vigil',
              icon: const VigilIcon(VigilIcons.x, size: 18),
              color: colors.tx2,
              onPressed: widget.onClose,
            ),
        ],
      ),
    );
  }

  Future<void> _pickConversation(BuildContext context) async {
    final session = _session;
    final picked = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: context.vigilColors.bg1,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            ListTile(
              key: const Key('conversation-new'),
              leading: const VigilIcon(VigilIcons.plus, size: 18),
              title: const Text('New conversation'),
              onTap: () => Navigator.of(context).pop('new'),
            ),
            for (final conversation in session.conversations)
              ListTile(
                key: Key('conversation-${conversation.id}'),
                leading: const VigilIcon(VigilIcons.chat, size: 18),
                title: Text(
                  conversation.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(
                  '${conversation.messageCount} messages',
                  style: VigilTypography.meta,
                ),
                onTap: () => Navigator.of(context).pop(conversation.id),
              ),
          ],
        ),
      ),
    );
    if (!mounted || picked == null) return;
    if (picked == 'new') {
      _session.startNewConversation();
    } else {
      _session.openConversation(picked);
    }
  }

  Widget _transcript(VigilColors colors) {
    final session = _session;
    if (session.entries.isEmpty && !session.streaming) {
      return _emptyState(colors);
    }
    final streaming = session.streaming;
    return ListView.builder(
      key: const Key('ask-transcript'),
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      itemCount: session.entries.length + (streaming ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == session.entries.length) {
          // The turn in flight: markdown rendered as frames accumulate.
          return _streamingBlock(colors);
        }
        final entry = session.entries[index];
        return switch (entry.role) {
          ChatRole.user => _userRow(colors, entry),
          ChatRole.vigil => _vigilRow(colors, entry),
          ChatRole.error => _errorRow(colors, entry),
        };
      },
    );
  }

  Widget _emptyState(VigilColors colors) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          VigilIcon(VigilIcons.chat, size: 32, color: colors.tx3),
          const SizedBox(height: 12),
          Text(
            'Ask Vigil',
            style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              'Investigate alongside Vigil — ask about findings, cases, '
              'or what the agents are doing.',
              textAlign: TextAlign.center,
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          ),
        ],
      ),
    );
  }

  Widget _streamingBlock(VigilColors colors) {
    final session = _session;
    if (session.streamText.isEmpty) {
      // Waiting for the first frame — the turn was accepted.
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          key: const Key('ask-waiting'),
          children: [
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              session.toolProcessing
                  ? 'Vigil is using tools…'
                  : 'Vigil is thinking…',
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          ],
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: MarkdownText(
        session.streamText,
        key: const Key('ask-streaming-text'),
      ),
    );
  }

  Widget _userRow(VigilColors colors, ChatEntry entry) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        constraints: const BoxConstraints(maxWidth: 420),
        decoration: BoxDecoration(
          color: colors.acBg,
          border: Border.all(color: colors.acLn),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(entry.text,
            style: VigilTypography.body.copyWith(color: colors.tx0)),
      ),
    );
  }

  Widget _vigilRow(VigilColors colors, ChatEntry entry) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: MarkdownText(entry.text),
    );
  }

  Widget _errorRow(VigilColors colors, ChatEntry entry) {
    final retry = _session.retryText;
    return Container(
      key: const Key('ask-error'),
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colors.poorBg,
        border: Border.all(color: colors.poorLn),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VigilIcon(VigilIcons.warn, size: 14, color: colors.poor),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  entry.text,
                  style: VigilTypography.meta.copyWith(color: colors.tx0),
                ),
              ),
            ],
          ),
          if (retry != null)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                key: const Key('ask-retry'),
                onPressed: () => _session.send(retry),
                child: const Text('Retry'),
              ),
            ),
        ],
      ),
    );
  }

  Widget _composer(VigilColors colors) {
    final session = _session;
    final streaming = session.streaming;
    return Padding(
      padding: EdgeInsets.only(
        left: 12,
        right: 12,
        top: 8,
        bottom: 12 + MediaQuery.paddingOf(context).bottom,
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              key: const Key('ask-composer'),
              controller: _draft,
              enabled: !streaming,
              style: VigilTypography.body.copyWith(color: colors.tx0),
              decoration: InputDecoration(
                hintText: 'Ask Vigil…',
                hintStyle: VigilTypography.body.copyWith(color: colors.tx3),
                filled: true,
                fillColor: colors.bg2,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide(color: colors.ln1),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide(color: colors.ln1),
                ),
              ),
              onSubmitted: streaming ? null : (_) => _send(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            key: Key(streaming ? 'ask-stop' : 'ask-send'),
            tooltip: streaming ? 'Stop' : 'Send',
            style: IconButton.styleFrom(backgroundColor: colors.ac),
            icon: VigilIcon(streaming ? VigilIcons.stop : VigilIcons.send,
                size: 18, color: colors.acTx),
            onPressed: streaming
                ? session.stop
                : _draft.text.trim().isEmpty
                    ? null
                    : _send,
          ),
        ],
      ),
    );
  }
}
