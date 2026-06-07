import { describe, it, expect } from 'vitest';
import { parseActionTags, extractActionLabels } from './parseActionTags';

describe('parseActionTags', () => {
  it('returns empty array for empty input', () => {
    expect(parseActionTags('')).toEqual([]);
    expect(parseActionTags(null)).toEqual([]);
    expect(parseActionTags(undefined)).toEqual([]);
  });

  it('returns single text segment for prose with no tags', () => {
    const result = parseActionTags('The wind howls across the dunes.');
    expect(result).toEqual([
      { type: 'text', content: 'The wind howls across the dunes.' },
    ]);
  });

  it('parses a single action tag in the middle of text', () => {
    const result = parseActionTags('Do you <action>strike</action> or flee?');
    expect(result).toEqual([
      { type: 'text', content: 'Do you ' },
      { type: 'action', label: 'strike' },
      { type: 'text', content: ' or flee?' },
    ]);
  });

  it('parses multiple action tags in one string', () => {
    const result = parseActionTags(
      'Do you <action>strike with shadow magic</action>, let <action>Thalia\'s arrow find its mark</action>, or <action>use the key</action>?',
    );
    // 3 actions + 4 text runs ('Do you ', ', let ', ', or ', '?') = 7 segments
    expect(result).toHaveLength(7);
    expect(result.filter((s) => s.type === 'action').map((s) => s.label)).toEqual([
      'strike with shadow magic',
      "Thalia's arrow find its mark",
      'use the key',
    ]);
  });

  it('parses action tag at start of string', () => {
    const result = parseActionTags('<action>look around</action> the room is dim');
    expect(result).toEqual([
      { type: 'action', label: 'look around' },
      { type: 'text', content: ' the room is dim' },
    ]);
  });

  it('parses action tag at end of string', () => {
    const result = parseActionTags('What now? <action>wait</action>');
    expect(result).toEqual([
      { type: 'text', content: 'What now? ' },
      { type: 'action', label: 'wait' },
    ]);
  });

  it('drops empty action tags', () => {
    const result = parseActionTags('Choice: <action></action> or <action>flee</action>?');
    expect(result.filter((s) => s.type === 'action').map((s) => s.label)).toEqual(['flee']);
  });

  it('trims whitespace inside action tags', () => {
    const result = parseActionTags('Do you <action>  strike  </action>?');
    expect(result.find((s) => s.type === 'action').label).toBe('strike');
  });

  it('leaves a half-written opening tag as plain text (streaming case)', () => {
    // Mid-stream, the closing tag hasn't arrived yet. The renderer briefly
    // shows the raw text until the next token completes the tag — acceptable
    // graceful degradation per the design.
    const result = parseActionTags('Do you <action>strike with shadow ');
    expect(result.length).toBe(1);
    expect(result[0].type).toBe('text');
    expect(result[0].content).toContain('<action>strike with shadow');
  });

  it('handles multi-line action labels', () => {
    const text = 'Do you <action>strike\nwith\nfury</action>?';
    const result = parseActionTags(text);
    expect(result.find((s) => s.type === 'action').label).toBe('strike\nwith\nfury');
  });

  it('is safe across repeated invocations (no regex state bleed)', () => {
    // Global regexes carry lastIndex across calls — parseActionTags clones the
    // regex per call to avoid that footgun. Verify by calling twice.
    const text = 'Do you <action>strike</action>?';
    const first = parseActionTags(text);
    const second = parseActionTags(text);
    expect(first).toEqual(second);
    expect(first.filter((s) => s.type === 'action')).toHaveLength(1);
    expect(second.filter((s) => s.type === 'action')).toHaveLength(1);
  });
});

describe('extractActionLabels', () => {
  it('returns labels in document order', () => {
    expect(
      extractActionLabels(
        'A <action>first</action> then <action>second</action> finally <action>third</action>.',
      ),
    ).toEqual(['first', 'second', 'third']);
  });

  it('returns empty array when no tags', () => {
    expect(extractActionLabels('plain prose')).toEqual([]);
  });

  it('returns empty array for empty input', () => {
    expect(extractActionLabels('')).toEqual([]);
  });
});
