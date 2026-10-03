import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { emitAuthChange } from '@/authEvents';
import {
  appendChatMessage,
  getChatMessages,
  startNewChat,
} from '@/utils/chatConversation';

// Exercises the chat module's auth-change subscriber directly, independent of
// api.setAuthToken (whose end-to-end behaviour is covered in api.test.ts).
describe('chat conversation auth-change subscriber', () => {
  const message = { role: 'user' as const, content: 'What is my ISA worth?' };

  beforeEach(() => {
    startNewChat();
    appendChatMessage(message);
  });

  afterEach(() => {
    startNewChat();
  });

  it('clears the conversation on a logout event', () => {
    emitAuthChange({ previousToken: 'token-for-user-a', nextToken: null });

    expect(getChatMessages()).toEqual([]);
    expect(sessionStorage.getItem('allotmint.chat.messages')).toBe('[]');
  });

  it('keeps the conversation when a token is applied from null', () => {
    emitAuthChange({ previousToken: null, nextToken: 'token-for-user-a' });

    expect(getChatMessages()).toEqual([message]);
  });

  it('keeps the conversation on a token refresh', () => {
    emitAuthChange({
      previousToken: 'token-for-user-a',
      nextToken: 'refreshed-token-for-user-a',
    });

    expect(getChatMessages()).toEqual([message]);
  });
});
