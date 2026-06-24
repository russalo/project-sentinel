import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

beforeEach(() => {
  useChatStore.setState({ checkRequest: null, levelUp: null });
});

describe('chatStore.setCheckRequest — malformed-LLM-output hardening (PR #146)', () => {
  it('accepts a well-formed check request (effectDie null for a non-combat check)', () => {
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
      effectDie: null,
    });
  });

  it('passes effect_die through as effectDie on an attack (RFC-0007)', () => {
    useChatStore.getState().setCheckRequest({
      stat: 'body',
      target: 55,
      label: 'Strike the ghoul',
      effect_die: '1d8',
    });
    expect(useChatStore.getState().checkRequest.effectDie).toBe('1d8');
  });

  it('drops a non-string effect_die (treated as a non-combat check)', () => {
    useChatStore.getState().setCheckRequest({ stat: 'body', target: 55, effect_die: 8 });
    expect(useChatStore.getState().checkRequest.effectDie).toBeNull();
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
      effectDie: null,
    });
  });

  it('clearCheckRequest resets to null', () => {
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 100 });
    useChatStore.getState().clearCheckRequest();
    expect(useChatStore.getState().checkRequest).toBeNull();
  });
});

describe('chatStore.setLevelUp — malformed-LLM-output hardening (RFC-0009)', () => {
  it('accepts a well-formed level-up proposal (to_level → toLevel)', () => {
    useChatStore.getState().setLevelUp({ to_level: 3 });
    expect(useChatStore.getState().levelUp).toEqual({ toLevel: 3 });
  });

  it('rejects a non-integer / non-positive to_level', () => {
    useChatStore.getState().setLevelUp({ to_level: 'three' });
    expect(useChatStore.getState().levelUp).toBeNull();
    useChatStore.getState().setLevelUp({ to_level: 0 });
    expect(useChatStore.getState().levelUp).toBeNull();
    useChatStore.getState().setLevelUp({ to_level: -1 });
    expect(useChatStore.getState().levelUp).toBeNull();
    useChatStore.getState().setLevelUp({}); // missing
    expect(useChatStore.getState().levelUp).toBeNull();
  });

  it('rejects null / non-object', () => {
    useChatStore.getState().setLevelUp(null);
    expect(useChatStore.getState().levelUp).toBeNull();
    useChatStore.getState().setLevelUp('nonsense');
    expect(useChatStore.getState().levelUp).toBeNull();
  });

  it('clearLevelUp resets to null', () => {
    useChatStore.getState().setLevelUp({ to_level: 2 });
    useChatStore.getState().clearLevelUp();
    expect(useChatStore.getState().levelUp).toBeNull();
  });
});
