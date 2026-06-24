import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

beforeEach(() => {
  useChatStore.setState({ checkRequest: null });
});

describe('chatStore.setCheckRequest — malformed-LLM-output hardening (PR #146)', () => {
  it('accepts a well-formed check request (weaponDie null for a non-combat check)', () => {
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
      weaponDie: null,
    });
  });

  it('passes weapon_die through as weaponDie on an attack (RFC-0007)', () => {
    useChatStore.getState().setCheckRequest({
      stat: 'body',
      target: 55,
      label: 'Strike the ghoul',
      weapon_die: '1d8',
    });
    expect(useChatStore.getState().checkRequest.weaponDie).toBe('1d8');
  });

  it('drops a non-string weapon_die (treated as a non-combat check)', () => {
    useChatStore.getState().setCheckRequest({ stat: 'body', target: 55, weapon_die: 8 });
    expect(useChatStore.getState().checkRequest.weaponDie).toBeNull();
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
      weaponDie: null,
    });
  });

  it('clearCheckRequest resets to null', () => {
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 100 });
    useChatStore.getState().clearCheckRequest();
    expect(useChatStore.getState().checkRequest).toBeNull();
  });
});
