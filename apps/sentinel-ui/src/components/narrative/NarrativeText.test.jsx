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

  it('coalesces trailing punctuation onto the action display (prevents orphan)', () => {
    // The narrative ends `...<action>flee</action>?` — without coalescing the
    // `?` lives in its own segment and can wrap to a new line when the
    // preceding action is long. The action button should DISPLAY 'flee?' but
    // the click label stays clean ('flee', no punctuation).
    render(<NarrativeText>{'Do you <action>flee</action>?'}</NarrativeText>);
    const btn = screen.getByRole('button', { name: 'Suggest action: flee' });
    expect(btn.textContent).toBe('flee?');
  });

  it('click label is unchanged when trailing punctuation is glued onto display', async () => {
    render(<NarrativeText>{'Do you <action>strike</action>?'}</NarrativeText>);
    await userEvent.click(screen.getByRole('button', { name: 'Suggest action: strike' }));
    // setInput should receive just 'strike' — NOT 'strike?'
    expect(useChatStore.getState().input).toBe('strike');
  });

  it('coalesces only the leading-punctuation prefix and keeps the rest as text', () => {
    // After an action: `<action>X</action>, then`
    // The `,` should glue onto the action, ` then` should remain as text.
    const { container } = render(
      <NarrativeText>{'You <action>flee</action>, then look back.'}</NarrativeText>,
    );
    const btn = screen.getByRole('button', { name: 'Suggest action: flee' });
    expect(btn.textContent).toBe('flee,');
    expect(container.textContent).toContain(' then look back.');
  });

  it('renders *word* markdown as italic <em>', () => {
    const { container } = render(<NarrativeText>{'You *must* hurry.'}</NarrativeText>);
    const em = container.querySelector('em');
    expect(em).not.toBeNull();
    expect(em.textContent).toBe('must');
    // Tailwind preflight wipes <em>'s default italic — verify the explicit
    // `italic` class is present so the word actually renders italic.
    expect(em.className).toContain('italic');
    // Surrounding text preserved
    expect(container.textContent).toBe('You must hurry.');
  });

  it('renders multi-word *phrases* as italic', () => {
    const { container } = render(
      <NarrativeText>{'Magic *of the old gods* lingers.'}</NarrativeText>,
    );
    const em = container.querySelector('em');
    expect(em.textContent).toBe('of the old gods');
  });

  it('does not crash on dangling single asterisks', () => {
    const { container } = render(
      <NarrativeText>{'A 5 * 7 multiplication keeps asterisks literal.'}</NarrativeText>,
    );
    // No <em> element — the dangling `*` should render literally.
    expect(container.querySelector('em')).toBeNull();
    expect(container.textContent).toContain('5 * 7');
  });

  it('handles emphasis inside narrative containing action tags', () => {
    const { container } = render(
      <NarrativeText>
        {'The *ancient* doors creak. Do you <action>enter</action>?'}
      </NarrativeText>,
    );
    expect(container.querySelector('em').textContent).toBe('ancient');
    const btn = screen.getByRole('button', { name: 'Suggest action: enter' });
    expect(btn.textContent).toBe('enter?');
  });
});
