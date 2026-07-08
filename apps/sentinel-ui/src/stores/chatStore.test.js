import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

beforeEach(() => {
  useChatStore.setState({ checkRequest: null, levelUp: null, rollResult: null });
});

describe('chatStore.clearMessages — full reset of turn-ephemeral state (inter-world bleed guard, PR #154)', () => {
  it('clears the per-turn DM affordances so they cannot bleed across a world switch', () => {
    // Seed world A's ephemeral state.
    useChatStore.setState({
      checkRequest: { stat: 'body', target: 80, label: 'x', prompt: '', effectDie: null },
      suggestedActions: [{ label: 'flee', tone: 'cautious' }],
      levelUp: { toLevel: 2 },
      rollResult: { stat: 'body', total: 77, margin: -3 },
    });
    // Switching/loading a world calls clearMessages — none of A's state may survive.
    useChatStore.getState().clearMessages();
    const s = useChatStore.getState();
    expect(s.checkRequest).toBeNull();
    expect(s.suggestedActions).toEqual([]);
    expect(s.levelUp).toBeNull();
    expect(s.rollResult).toBeNull();
  });
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
      kind: 'skill',
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
      kind: 'skill',
    });
  });

  it('carries kind: "death_save" through (RFC-0014)', () => {
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 60, kind: 'death_save', label: 'Cling to life' });
    expect(useChatStore.getState().checkRequest.kind).toBe('death_save');
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 60, kind: 'nonsense' });
    expect(useChatStore.getState().checkRequest.kind).toBe('skill');
  });

  it('clearCheckRequest resets to null', () => {
    useChatStore.getState().setCheckRequest({ stat: 'will', target: 100 });
    useChatStore.getState().clearCheckRequest();
    expect(useChatStore.getState().checkRequest).toBeNull();
  });
});

describe('chatStore.rollResult — revealed roll + the player-paced lock (PR #152 follow-up)', () => {
  const roll = { stat: 'body', rolled: 47, bonus: 30, total: 77, target: 80, margin: -3 };

  it('defaults to null (no pending roll)', () => {
    expect(useChatStore.getState().rollResult).toBeNull();
  });

  it('setRollResult stores the revealed roll (the single source of truth for "pending")', () => {
    useChatStore.getState().setRollResult(roll);
    expect(useChatStore.getState().rollResult).toEqual(roll);
  });

  it('clearCheckRequest clears the revealed roll (so the lock can never get stuck)', () => {
    useChatStore.getState().setRollResult(roll);
    useChatStore.getState().clearCheckRequest();
    expect(useChatStore.getState().rollResult).toBeNull();
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

  it('rejects a to_level above the v0.1 1..5 cap (impossible advancement)', () => {
    useChatStore.getState().setLevelUp({ to_level: 6 });
    expect(useChatStore.getState().levelUp).toBeNull();
    useChatStore.getState().setLevelUp({ to_level: 99 });
    expect(useChatStore.getState().levelUp).toBeNull();
    // 5 is the cap and still accepted.
    useChatStore.getState().setLevelUp({ to_level: 5 });
    expect(useChatStore.getState().levelUp).toEqual({ toLevel: 5 });
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
