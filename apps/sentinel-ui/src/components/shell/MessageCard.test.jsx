import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageCard, renderMinimalMarkdown } from './MessageCard';

function mk(overrides = {}) {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    title: 'Hello',
    body: 'Body text',
    category: 'info',
    pinned: false,
    published_at: '2026-06-14T20:00:00Z',
    ...overrides,
  };
}

describe('MessageCard', () => {
  it('renders the title and category label', () => {
    render(<MessageCard message={mk({ category: 'release' })} />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Release')).toBeInTheDocument();
  });

  it('renders a pin glyph when pinned', () => {
    render(<MessageCard message={mk({ pinned: true })} />);
    expect(screen.getByLabelText('Pinned')).toBeInTheDocument();
  });

  it('omits the pin glyph when not pinned', () => {
    render(<MessageCard message={mk({ pinned: false })} />);
    expect(screen.queryByLabelText('Pinned')).toBeNull();
  });

  it('splits body on newlines into paragraphs', () => {
    const { container } = render(
      <MessageCard message={mk({ body: 'one\n\ntwo\nthree' })} />,
    );
    const paragraphs = container.querySelectorAll('p');
    expect(paragraphs.length).toBe(3);
  });

  it('falls back to "Info" label for unknown category', () => {
    // The route validates category against the allowed set, but render is
    // defensive: an unknown one renders as the literal string, not a crash.
    render(<MessageCard message={mk({ category: 'bogus' })} />);
    expect(screen.getByText('bogus')).toBeInTheDocument();
  });
});

describe('renderMinimalMarkdown', () => {
  function renderInDom(nodes) {
    // Wrap in a div for getByText / queries via container
    const { container } = render(<div>{nodes}</div>);
    return container.firstChild;
  }

  it('returns empty array for empty/non-string input', () => {
    expect(renderMinimalMarkdown('')).toEqual([]);
    expect(renderMinimalMarkdown(null)).toEqual([]);
    expect(renderMinimalMarkdown(undefined)).toEqual([]);
  });

  it('renders bold via **bold**', () => {
    const div = renderInDom(renderMinimalMarkdown('hello **world**'));
    const strong = div.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe('world');
  });

  it('renders italic via *italic*', () => {
    const div = renderInDom(renderMinimalMarkdown('hello *world*'));
    const em = div.querySelector('em');
    expect(em).not.toBeNull();
    expect(em.textContent).toBe('world');
  });

  it('renders a safe https link', () => {
    const div = renderInDom(
      renderMinimalMarkdown('See [docs](https://example.com)'),
    );
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('https://example.com');
    expect(a.getAttribute('target')).toBe('_blank');
    expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    expect(a.textContent).toBe('docs');
  });

  it('renders a mailto link', () => {
    const div = renderInDom(
      renderMinimalMarkdown('Email [russ](mailto:r@example.com)'),
    );
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('mailto:r@example.com');
  });

  it('refuses javascript: URLs (renders label as text only)', () => {
    const div = renderInDom(
      renderMinimalMarkdown('click [me](javascript:alert(1))'),
    );
    const a = div.querySelector('a');
    expect(a).toBeNull();
    // The label still appears as text
    expect(div.textContent).toContain('me');
  });

  it('refuses data: URLs (renders label as text only)', () => {
    const div = renderInDom(
      renderMinimalMarkdown('open [x](data:text/html,evil)'),
    );
    expect(div.querySelector('a')).toBeNull();
    expect(div.textContent).toContain('x');
  });

  it('refuses file: URLs (renders label as text only)', () => {
    const div = renderInDom(
      renderMinimalMarkdown('see [x](file:///etc/passwd)'),
    );
    expect(div.querySelector('a')).toBeNull();
  });
});
