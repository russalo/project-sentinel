import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore, FONT_SIZES, FONT_SIZE_DEFAULT, FONT_SIZE_CLASS } from './uiStore';

beforeEach(() => {
  // Reset fontSize between tests (other slices are ephemeral / not load-bearing here)
  useUIStore.setState({ fontSize: FONT_SIZE_DEFAULT, settingsOpen: false });
  // Clear the persist key so a previous test's persisted value doesn't bleed in
  localStorage.removeItem('sentinel.uiPrefs');
});

describe('useUIStore — fontSize', () => {
  it('defaults to normal', () => {
    expect(useUIStore.getState().fontSize).toBe('normal');
  });

  it('FONT_SIZES enum ordered smallest-to-largest', () => {
    expect(FONT_SIZES).toEqual(['small', 'normal', 'large', 'xlarge']);
  });

  it('FONT_SIZE_CLASS maps each enum to a Tailwind text-* class', () => {
    expect(FONT_SIZE_CLASS.small).toBe('text-sm');
    expect(FONT_SIZE_CLASS.normal).toBe('text-base');
    expect(FONT_SIZE_CLASS.large).toBe('text-lg');
    expect(FONT_SIZE_CLASS.xlarge).toBe('text-xl');
  });

  it('setFontSize accepts valid sizes', () => {
    useUIStore.getState().setFontSize('large');
    expect(useUIStore.getState().fontSize).toBe('large');
    useUIStore.getState().setFontSize('small');
    expect(useUIStore.getState().fontSize).toBe('small');
  });

  it('setFontSize rejects invalid sizes silently (no throw, no state change)', () => {
    useUIStore.getState().setFontSize('normal');
    useUIStore.getState().setFontSize('huge');
    useUIStore.getState().setFontSize('');
    useUIStore.getState().setFontSize(null);
    useUIStore.getState().setFontSize(undefined);
    expect(useUIStore.getState().fontSize).toBe('normal');
  });

  it('stepFontSize(+1) advances one step', () => {
    useUIStore.setState({ fontSize: 'normal' });
    useUIStore.getState().stepFontSize(1);
    expect(useUIStore.getState().fontSize).toBe('large');
  });

  it('stepFontSize(-1) reverses one step', () => {
    useUIStore.setState({ fontSize: 'large' });
    useUIStore.getState().stepFontSize(-1);
    expect(useUIStore.getState().fontSize).toBe('normal');
  });

  it('stepFontSize clamps at min (small)', () => {
    useUIStore.setState({ fontSize: 'small' });
    useUIStore.getState().stepFontSize(-1);
    expect(useUIStore.getState().fontSize).toBe('small');
    // Multiple decrements stay at small
    useUIStore.getState().stepFontSize(-1);
    useUIStore.getState().stepFontSize(-1);
    expect(useUIStore.getState().fontSize).toBe('small');
  });

  it('stepFontSize clamps at max (xlarge)', () => {
    useUIStore.setState({ fontSize: 'xlarge' });
    useUIStore.getState().stepFontSize(1);
    expect(useUIStore.getState().fontSize).toBe('xlarge');
    useUIStore.getState().stepFontSize(1);
    useUIStore.getState().stepFontSize(1);
    expect(useUIStore.getState().fontSize).toBe('xlarge');
  });

  it('persists fontSize to localStorage under sentinel.uiPrefs', () => {
    useUIStore.getState().setFontSize('large');
    // Allow zustand persist to flush — it's synchronous in jsdom
    const raw = localStorage.getItem('sentinel.uiPrefs');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw);
    expect(parsed.state.fontSize).toBe('large');
  });

  it('does NOT persist ephemeral state (settingsOpen, leftPanelCollapsed, etc)', () => {
    useUIStore.getState().openSettings();
    useUIStore.getState().toggleLeftPanel();
    useUIStore.getState().setFontSize('large');
    const parsed = JSON.parse(localStorage.getItem('sentinel.uiPrefs'));
    // Only fontSize should be in the persisted state per partialize whitelist
    expect(Object.keys(parsed.state)).toEqual(['fontSize']);
    expect(parsed.state.settingsOpen).toBeUndefined();
    expect(parsed.state.leftPanelCollapsed).toBeUndefined();
  });
});

describe('useUIStore — settings drawer state', () => {
  it('settingsOpen defaults to false', () => {
    expect(useUIStore.getState().settingsOpen).toBe(false);
  });

  it('openSettings + closeSettings', () => {
    useUIStore.getState().openSettings();
    expect(useUIStore.getState().settingsOpen).toBe(true);
    useUIStore.getState().closeSettings();
    expect(useUIStore.getState().settingsOpen).toBe(false);
  });
});
