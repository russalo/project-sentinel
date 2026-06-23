import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

beforeEach(() => {
  useChatStore.setState({ checkRequest: null });
});

describe('chatStore.setCheckRequest — malformed-LLM-output hardening (PR #146)', () => {
  it('accepts a well-formed check request', () => {
    useChatStore.getState().setCheckRequest({
      stat: 'body',
      target: 80,
      label: 'Force it',
      prompt: 'The iron is fast.',
    });
    expect(useChatStore.getState().checkRequest).toEqual({
      stat: 'body',
      target: 80,
      label: 'Force it',
      prompt: 'The iron is fast.',
    });
  });

  it('rejects an unrecognized stat', () => {
    useChatStore.getState().setCheckRequest({ stat: 'luck', target: 60 });
    expect(useChatStore.getState().checkRequest).toBeNull();
  });

  it('rejects a non-integer / missing target (would NaN the margin)', () => {
    useChatStore.getState().setCheckRequest({ stat: 'body', target: 'hard' });
    expect(useChatStore.getState().checkRequest).toBeNull();
    useChatStore.getState().setCheckRequest({ stat: 'body' });
    expect(useChatStore.getState().checkRequest).toBeNull();
    useChatStore.getState().setCheckRequest({ stat: 'body', target: 0 });
    expect(useChatStore.getState().checkRequest).toBeNull();
  });

  it('rejects null / non-object', () => {
    useChatStore.getState().setCheckRequest(null);
    expect(useChatStore.getState().checkRequest).toBeNull();
    useChatStore.getState().setCheckRequest('nonsense');
    expect(useChatStore.getState().checkRequest).toBeNull();
  });

  it('coerces non-string label/prompt to empty strings', () => {
    useChatStore.getState().setCheckRequest({ stat: 'mind', target: 40, label: 42, prompt: {} });
    expect(useChatStore.getState().checkRequest).toEqual({
      stat: 'mind',
      target: 40,
      label: '',
      prompt: '',
    });
  });

  it('clearCheckRequest resets to null', () => {
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 100 });
    useChatStore.getState().clearCheckRequest();
    expect(useChatStore.getState().checkRequest).toBeNull();
  });
});
