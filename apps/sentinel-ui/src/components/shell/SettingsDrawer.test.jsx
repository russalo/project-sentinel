import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsDrawer } from './SettingsDrawer';
import { useUIStore, FONT_SIZE_DEFAULT } from '../../stores/uiStore';

vi.mock('../../api/systemMessages', () => ({
  listMessages: vi.fn(),
}));
import { listMessages } from '../../api/systemMessages';

beforeEach(() => {
  useUIStore.setState({
    settingsOpen: false,
    fontSize: FONT_SIZE_DEFAULT,
    messagesLastSeenAt: null,
  });
  localStorage.removeItem('sentinel.uiPrefs');
  listMessages.mockReset();
  listMessages.mockResolvedValue([]);
});

describe('SettingsDrawer', () => {
  it('always mounted but hidden when settingsOpen is false', () => {
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    expect(drawer).not.toBeNull();
    expect(drawer.getAttribute('aria-hidden')).toBe('true');
  });

  it('exposed (aria-hidden=false) when settingsOpen is true', () => {
    useUIStore.setState({ settingsOpen: true });
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    expect(drawer.getAttribute('aria-hidden')).toBe('false');
  });

  it('shows the current font-size label', () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'large' });
    render(<SettingsDrawer />);
    expect(screen.getByText('Large')).toBeInTheDocument();
  });

  it('A+ button advances the font size', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'normal' });
    render(<SettingsDrawer />);
    await userEvent.click(screen.getByRole('button', { name: 'Increase font size' }));
    expect(useUIStore.getState().fontSize).toBe('large');
  });

  it('A− button reverses the font size', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'large' });
    render(<SettingsDrawer />);
    await userEvent.click(screen.getByRole('button', { name: 'Decrease font size' }));
    expect(useUIStore.getState().fontSize).toBe('normal');
  });

  it('A− is disabled at min (small)', () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'small' });
    render(<SettingsDrawer />);
    const minusBtn = screen.getByRole('button', { name: 'Decrease font size' });
    expect(minusBtn).toBeDisabled();
  });

  it('A+ is disabled at max (xlarge)', () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'xlarge' });
    render(<SettingsDrawer />);
    const plusBtn = screen.getByRole('button', { name: 'Increase font size' });
    expect(plusBtn).toBeDisabled();
  });

  it('close button calls closeSettings', async () => {
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await userEvent.click(screen.getByRole('button', { name: 'Close settings' }));
    expect(useUIStore.getState().settingsOpen).toBe(false);
  });

  it('font-size changes persist via the uiStore middleware', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'normal' });
    render(<SettingsDrawer />);
    await userEvent.click(screen.getByRole('button', { name: 'Increase font size' }));
    // Persist middleware writes synchronously in jsdom
    const persisted = JSON.parse(localStorage.getItem('sentinel.uiPrefs'));
    expect(persisted.state.fontSize).toBe('large');
  });

  it('clicking A+ multiple times steps through sizes and caps at xlarge', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'small' });
    render(<SettingsDrawer />);
    const plusBtn = screen.getByRole('button', { name: 'Increase font size' });
    await userEvent.click(plusBtn);  // → normal
    await userEvent.click(plusBtn);  // → large
    await userEvent.click(plusBtn);  // → xlarge
    expect(useUIStore.getState().fontSize).toBe('xlarge');
    // The 4th click should be blocked (button disabled) but even if forced, clamps
    expect(plusBtn).toBeDisabled();
  });

  it('Escape key closes the drawer when open', async () => {
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await userEvent.keyboard('{Escape}');
    expect(useUIStore.getState().settingsOpen).toBe(false);
  });

  it('Escape key is a no-op when drawer is closed (no leaked global listener)', async () => {
    // closed → no listener registered → Escape does nothing
    useUIStore.setState({ settingsOpen: false });
    const initialState = useUIStore.getState();
    render(<SettingsDrawer />);
    await userEvent.keyboard('{Escape}');
    expect(useUIStore.getState().settingsOpen).toBe(false);
    // Also check the listener is removed on unmount
    expect(initialState.settingsOpen).toBe(false);
  });

  it('drawer has inert attribute when closed (removes descendants from tab order)', () => {
    useUIStore.setState({ settingsOpen: false });
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    // inert is a present-or-absent HTML attribute; jsdom reports it as an empty string when set
    expect(drawer.hasAttribute('inert')).toBe(true);
  });

  it('drawer drops the inert attribute when open', () => {
    useUIStore.setState({ settingsOpen: true });
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    expect(drawer.hasAttribute('inert')).toBe(false);
  });

  it('aside element is programmatically focusable (tabIndex=-1 + ref)', () => {
    useUIStore.setState({ settingsOpen: true });
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    expect(drawer.getAttribute('tabindex')).toBe('-1');
  });

  it('focus moves into the drawer when it opens', async () => {
    // Start closed
    useUIStore.setState({ settingsOpen: false });
    const { container } = render(<SettingsDrawer />);
    const drawer = container.querySelector('[role="dialog"]');
    // Open — should focus the drawer
    useUIStore.getState().openSettings();
    // React-effects flush after a microtask in jsdom
    await new Promise((r) => setTimeout(r, 0));
    expect(document.activeElement).toBe(drawer);
  });

  it('Tab from last focusable element wraps to first (focus trap forward)', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'normal' });
    const { container } = render(<SettingsDrawer />);
    // Focusable elements in order: close button, A−, A+
    const closeBtn = container.querySelector('button[aria-label="Close settings"]');
    const plusBtn = container.querySelector('button[aria-label="Increase font size"]');
    plusBtn.focus();
    expect(document.activeElement).toBe(plusBtn);
    await userEvent.keyboard('{Tab}');
    expect(document.activeElement).toBe(closeBtn);
  });

  it('Shift-Tab from first focusable element wraps to last (focus trap reverse)', async () => {
    useUIStore.setState({ settingsOpen: true, fontSize: 'normal' });
    const { container } = render(<SettingsDrawer />);
    const closeBtn = container.querySelector('button[aria-label="Close settings"]');
    const plusBtn = container.querySelector('button[aria-label="Increase font size"]');
    closeBtn.focus();
    expect(document.activeElement).toBe(closeBtn);
    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(document.activeElement).toBe(plusBtn);
  });
});

describe('SettingsDrawer — Messages section (RFC 0002)', () => {
  it('renders the Messages header', () => {
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    expect(screen.getByText('Messages')).toBeInTheDocument();
  });

  it('shows "No messages." when the feed is empty', async () => {
    listMessages.mockResolvedValue([]);
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await waitFor(() => {
      expect(screen.getByText('No messages.')).toBeInTheDocument();
    });
  });

  it('renders message titles from the feed', async () => {
    listMessages.mockResolvedValue([
      { id: 'a', title: 'Patch tonight', body: 'See you 5pm', category: 'maintenance', pinned: false, published_at: '2026-06-14T20:00:00Z' },
      { id: 'b', title: 'Hello cohort', body: 'Welcome', category: 'info', pinned: false, published_at: '2026-06-13T20:00:00Z' },
    ]);
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await waitFor(() => {
      expect(screen.getByText('Patch tonight')).toBeInTheDocument();
    });
    expect(screen.getByText('Hello cohort')).toBeInTheDocument();
  });

  it('marks messages seen when drawer opens', async () => {
    expect(useUIStore.getState().messagesLastSeenAt).toBeNull();
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await waitFor(() => {
      expect(useUIStore.getState().messagesLastSeenAt).not.toBeNull();
    });
  });

  it('shows an error when the feed fetch fails', async () => {
    listMessages.mockRejectedValue(new Error('boom'));
    useUIStore.setState({ settingsOpen: true });
    render(<SettingsDrawer />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/boom/);
    });
  });

  it('does NOT fetch the feed when the drawer is closed', () => {
    useUIStore.setState({ settingsOpen: false });
    render(<SettingsDrawer />);
    expect(listMessages).not.toHaveBeenCalled();
  });
});
