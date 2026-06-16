import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { renderInline, renderMarkdown, renderMinimalMarkdown } from './minimalMarkdown';

function renderInDom(nodes) {
  const { container } = render(<div>{nodes}</div>);
  return container.firstChild;
}

describe('renderInline (a.k.a. renderMinimalMarkdown — back-compat alias)', () => {
  it('exports the back-compat alias pointing at renderInline', () => {
    expect(renderMinimalMarkdown).toBe(renderInline);
  });

  it('returns empty array for empty / non-string input', () => {
    expect(renderInline('')).toEqual([]);
    expect(renderInline(null)).toEqual([]);
    expect(renderInline(undefined)).toEqual([]);
  });

  it('renders **bold**', () => {
    const div = renderInDom(renderInline('hello **world**'));
    const strong = div.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe('world');
  });

  it('renders *italic*', () => {
    const div = renderInDom(renderInline('hello *world*'));
    const em = div.querySelector('em');
    expect(em).not.toBeNull();
    expect(em.textContent).toBe('world');
  });

  it('renders ***bold-italic***', () => {
    const div = renderInDom(renderInline('hello ***world***'));
    const strong = div.querySelector('strong');
    const em = div.querySelector('em');
    expect(strong).not.toBeNull();
    expect(em).not.toBeNull();
    expect(strong.textContent).toBe('world');
  });

  it('renders `code` spans', () => {
    const div = renderInDom(renderInline('see `pnpm build` then ship'));
    const code = div.querySelector('code');
    expect(code).not.toBeNull();
    expect(code.textContent).toBe('pnpm build');
  });

  it('renders a safe https link with target=_blank + rel=noopener noreferrer', () => {
    const div = renderInDom(renderInline('See [docs](https://example.com)'));
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('https://example.com');
    expect(a.getAttribute('target')).toBe('_blank');
    expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    expect(a.textContent).toBe('docs');
  });

  it('renders a mailto link', () => {
    const div = renderInDom(renderInline('Email [russ](mailto:r@example.com)'));
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('mailto:r@example.com');
  });

  it('refuses javascript: URLs (renders label as text only)', () => {
    const div = renderInDom(renderInline('click [me](javascript:alert(1))'));
    expect(div.querySelector('a')).toBeNull();
    expect(div.textContent).toContain('me');
  });

  it('refuses data: URLs', () => {
    const div = renderInDom(renderInline('open [x](data:text/html,evil)'));
    expect(div.querySelector('a')).toBeNull();
  });

  it('refuses file: URLs', () => {
    const div = renderInDom(renderInline('see [x](file:///etc/passwd)'));
    expect(div.querySelector('a')).toBeNull();
  });

  it('emphasis inside a link label still renders', () => {
    const div = renderInDom(renderInline('see [the **bold** doc](https://example.com)'));
    const a = div.querySelector('a');
    const strong = a.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe('bold');
  });

  it('code inside a link label still renders', () => {
    const div = renderInDom(renderInline('see [the `code` doc](https://example.com)'));
    const a = div.querySelector('a');
    const code = a.querySelector('code');
    expect(code).not.toBeNull();
    expect(code.textContent).toBe('code');
  });
});

describe('renderMarkdown — block-level', () => {
  it('returns empty array for empty / non-string input', () => {
    expect(renderMarkdown('')).toEqual([]);
    expect(renderMarkdown(null)).toEqual([]);
    expect(renderMarkdown(undefined)).toEqual([]);
  });

  it('renders # heading as <h1>', () => {
    const div = renderInDom(renderMarkdown('# Sentinel Tester Guide'));
    const h1 = div.querySelector('h1');
    expect(h1).not.toBeNull();
    expect(h1.textContent).toBe('Sentinel Tester Guide');
  });

  it('renders ## heading as <h2>', () => {
    const div = renderInDom(renderMarkdown('## Creating your world'));
    const h2 = div.querySelector('h2');
    expect(h2).not.toBeNull();
    expect(h2.textContent).toBe('Creating your world');
  });

  it('renders ### heading as <h3>', () => {
    const div = renderInDom(renderMarkdown('### Top bar'));
    const h3 = div.querySelector('h3');
    expect(h3).not.toBeNull();
    expect(h3.textContent).toBe('Top bar');
  });

  it('renders a paragraph as <p>', () => {
    const div = renderInDom(renderMarkdown('Hello, world.'));
    const p = div.querySelector('p');
    expect(p).not.toBeNull();
    expect(p.textContent).toBe('Hello, world.');
  });

  it('coalesces consecutive non-blank lines into a single paragraph', () => {
    const div = renderInDom(renderMarkdown('line one\nline two\nline three'));
    const paragraphs = div.querySelectorAll('p');
    expect(paragraphs.length).toBe(1);
    expect(paragraphs[0].textContent).toBe('line one line two line three');
  });

  it('blank line separates paragraphs', () => {
    const div = renderInDom(renderMarkdown('first para\n\nsecond para'));
    const paragraphs = div.querySelectorAll('p');
    // The blockquote test below also asserts <p> count; this scope is just
    // the two top-level paragraphs.
    expect(paragraphs.length).toBe(2);
    expect(paragraphs[0].textContent).toBe('first para');
    expect(paragraphs[1].textContent).toBe('second para');
  });

  it('groups consecutive `- ` lines into a single <ul>', () => {
    const div = renderInDom(renderMarkdown('- one\n- two\n- three'));
    const ul = div.querySelector('ul');
    const items = div.querySelectorAll('li');
    expect(ul).not.toBeNull();
    expect(items.length).toBe(3);
    expect(items[0].textContent).toBe('one');
    expect(items[2].textContent).toBe('three');
  });

  it('list items support inline emphasis', () => {
    const div = renderInDom(renderMarkdown('- **bold** item\n- *italic* item'));
    const items = div.querySelectorAll('li');
    expect(items[0].querySelector('strong')).not.toBeNull();
    expect(items[1].querySelector('em')).not.toBeNull();
  });

  it('groups consecutive `> ` lines into a single <blockquote>', () => {
    const div = renderInDom(renderMarkdown('> first\n> second\n> third'));
    const blockquote = div.querySelector('blockquote');
    expect(blockquote).not.toBeNull();
    const paragraphs = blockquote.querySelectorAll('p');
    expect(paragraphs.length).toBe(3);
    expect(paragraphs[0].textContent).toBe('first');
  });

  it('blockquote supports inline emphasis and links', () => {
    const div = renderInDom(renderMarkdown('> **Cosmetic so far:** see [docs](https://example.com)'));
    const blockquote = div.querySelector('blockquote');
    expect(blockquote.querySelector('strong')).not.toBeNull();
    expect(blockquote.querySelector('a')).not.toBeNull();
  });

  it('handles a heading + paragraph + list in sequence (full mini-doc shape)', () => {
    const md = [
      '# Title',
      '',
      'Intro paragraph.',
      '',
      '## Section',
      '',
      '- one',
      '- two',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    expect(div.querySelector('h1').textContent).toBe('Title');
    expect(div.querySelector('h2').textContent).toBe('Section');
    expect(div.querySelectorAll('p').length).toBe(1);
    expect(div.querySelectorAll('li').length).toBe(2);
  });

  it('normalizes CRLF line endings', () => {
    const div = renderInDom(renderMarkdown('# Title\r\n\r\nBody.'));
    expect(div.querySelector('h1').textContent).toBe('Title');
    expect(div.querySelector('p').textContent).toBe('Body.');
  });

  it('a paragraph adjacent to a list/blockquote does NOT swallow them', () => {
    const md = 'A paragraph.\n- list item\n> quote line';
    const div = renderInDom(renderMarkdown(md));
    expect(div.querySelector('p').textContent).toBe('A paragraph.');
    expect(div.querySelector('ul')).not.toBeNull();
    expect(div.querySelector('blockquote')).not.toBeNull();
  });
});
