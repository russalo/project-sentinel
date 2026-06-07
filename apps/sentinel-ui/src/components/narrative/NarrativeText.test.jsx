import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NarrativeText } from './NarrativeText';
import { useChatStore } from '../../stores/chatStore';

beforeEach(() => {
  // Reset the input state between tests so a click-asserts-setInput case
  // doesn't bleed into the next.
  useChatStore.setState({ input: '' });
});

describe('NarrativeText', () => {
  it('renders plain prose verbatim when there are no action tags', () => {
    render(<NarrativeText>The dust settles around you.</NarrativeText>);
    expect(screen.getByText('The dust settles around you.')).toBeInTheDocument();
  });

  it('renders action tags as clickable buttons', () => {
    render(
      <NarrativeText>
        {'Do you <action>strike</action> or <action>flee</action>?'}
      </NarrativeText>,
    );
    expect(screen.getByRole('button', { name: 'Suggest action: strike' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Suggest action: flee' })).toBeInTheDocument();
  });

  it('clicking an action button populates chatStore.input with the label', async () => {
    render(
      <NarrativeText>
        {'Do you <action>strike with shadow magic</action>?'}
      </NarrativeText>,
    );
    expect(useChatStore.getState().input).toBe('');
    await userEvent.click(
      screen.getByRole('button', { name: 'Suggest action: strike with shadow magic' }),
    );
    expect(useChatStore.getState().input).toBe('strike with shadow magic');
  });

  it('does NOT auto-submit on click — only populates input (no message added)', async () => {
    const initialMessagesLength = useChatStore.getState().messages.length;
    render(<NarrativeText>{'<action>flee</action>'}</NarrativeText>);
    await userEvent.click(screen.getByRole('button', { name: 'Suggest action: flee' }));
    expect(useChatStore.getState().messages.length).toBe(initialMessagesLength);
  });

  it('renders surrounding text between action tags as text segments', () => {
    const { container } = render(
      <NarrativeText>
        {'Do you <action>strike</action> or stand still?'}
      </NarrativeText>,
    );
    // The text run after the action span should be present in the DOM.
    expect(container.textContent).toContain('Do you ');
    expect(container.textContent).toContain(' or stand still?');
    expect(container.textContent).toContain('strike');
  });

  it('handles a non-string child gracefully (no crash)', () => {
    // Defensive — if a parent ever passes a non-string by mistake, we render
    // empty rather than throw.
    const { container } = render(<NarrativeText>{null}</NarrativeText>);
    expect(container.textContent).toBe('');
  });
});
