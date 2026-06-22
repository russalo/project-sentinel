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

  it('renders an in-page anchor link without target=_blank', () => {
    const div = renderInDom(renderInline('jump to [section](#creating-your-world)'));
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('#creating-your-world');
    expect(a.getAttribute('target')).toBeNull();
    expect(a.textContent).toBe('section');
  });

  it('renders a mailto link', () => {
    const div = renderInDom(renderInline('Email [russ](mailto:r@example.com)'));
    const a = div.querySelector('a');
    expect(a).not.toBeNull();
    expect(a.getAttribute('href')).toBe('mailto:r@example.com');
  });

  it('refuses javascript: URLs', () => {
    const div = renderInDom(renderInline('click [me](javascript:alert(1))'));
    expect(div.querySelector('a')).toBeNull();
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
    const strong = div.querySelector('a strong');
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe('bold');
  });

  it('code inside a link label still renders', () => {
    const div = renderInDom(renderInline('see [the `code` doc](https://example.com)'));
    const code = div.querySelector('a code');
    expect(code).not.toBeNull();
    expect(code.textContent).toBe('code');
  });

  it('renders ![alt](path) as <img>', () => {
    const div = renderInDom(renderInline('![Vitals diagram](guide/vitals.png)'));
    const img = div.querySelector('img');
    expect(img).not.toBeNull();
    expect(img.getAttribute('alt')).toBe('Vitals diagram');
    // Default Vite BASE_URL during tests is `/`, so the path is `/guide/vitals.png`.
    expect(img.getAttribute('src')).toBe('/guide/vitals.png');
  });

  it('image accepts an absolute URL untouched', () => {
    const div = renderInDom(renderInline('![](https://example.com/x.png)'));
    const img = div.querySelector('img');
    expect(img.getAttribute('src')).toBe('https://example.com/x.png');
  });

  it('image accepts an absolute path untouched (no double-prefix)', () => {
    const div = renderInDom(renderInline('![](/guide/abs.png)'));
    const img = div.querySelector('img');
    expect(img.getAttribute('src')).toBe('/guide/abs.png');
  });

  it('image with empty alt is allowed', () => {
    const div = renderInDom(renderInline('![](guide/x.png)'));
    const img = div.querySelector('img');
    expect(img.getAttribute('alt')).toBe('');
  });
});

describe('renderInline — odd-index defensive check (bot finding regression)', () => {
  // gemini-medium on PR #140: `String.split` with a capturing regex returns
  // alternating non-match (even indices) and match (odd indices) parts.
  // The old code checked startsWith('*') / startsWith('`') on every part,
  // which could in principle false-positive on literal markers in
  // non-match text. The fix wraps emphasis/code only on odd indices.
  //
  // Constructing an input where the OLD code false-positives is hard
  // because the regex tries each alternation in order at every position,
  // so most "literal-marker" cases are already disambiguated. The
  // remaining tests verify the rule didn't break valid emphasis/code —
  // see the renderInline test suite above for the full coverage.

  it('a valid single-asterisk pair still renders as <em>', () => {
    const div = renderInDom(renderInline('a *foo* b'));
    expect(div.querySelector('em')?.textContent).toBe('foo');
  });

  it('a valid backtick pair still renders as <code>', () => {
    const div = renderInDom(renderInline('see `code` here'));
    expect(div.querySelector('code')?.textContent).toBe('code');
  });
});

describe('renderMarkdown — block-level', () => {
  it('returns empty array for empty / non-string input', () => {
    expect(renderMarkdown('')).toEqual([]);
    expect(renderMarkdown(null)).toEqual([]);
    expect(renderMarkdown(undefined)).toEqual([]);
  });

  it('renders # heading as <h1> with anchor id', () => {
    const div = renderInDom(renderMarkdown('# Sentinel Tester Guide'));
    const h1 = div.querySelector('h1');
    expect(h1).not.toBeNull();
    expect(h1.textContent).toBe('Sentinel Tester Guide');
    expect(h1.getAttribute('id')).toBe('sentinel-tester-guide');
  });

  it('renders ## heading as <h2> with anchor id', () => {
    const div = renderInDom(renderMarkdown('## Creating your world'));
    const h2 = div.querySelector('h2');
    expect(h2.getAttribute('id')).toBe('creating-your-world');
  });

  it('renders ### heading as <h3> with anchor id', () => {
    const div = renderInDom(renderMarkdown('### Top bar'));
    const h3 = div.querySelector('h3');
    expect(h3.getAttribute('id')).toBe('top-bar');
  });

  it('strips punctuation from anchor slugs', () => {
    const div = renderInDom(renderMarkdown("## What's on screen?"));
    const h2 = div.querySelector('h2');
    expect(h2.getAttribute('id')).toBe('whats-on-screen');
  });

  it('deduplicates anchor ids with suffixes when heading text repeats', () => {
    const div = renderInDom(
      renderMarkdown('## Section\n\nBody.\n\n## Section\n\nBody.'),
    );
    const h2s = div.querySelectorAll('h2');
    expect(h2s[0].getAttribute('id')).toBe('section');
    expect(h2s[1].getAttribute('id')).toBe('section-1');
  });

  it('renders a paragraph as <p>', () => {
    const div = renderInDom(renderMarkdown('Hello, world.'));
    const p = div.querySelector('p');
    expect(p.textContent).toBe('Hello, world.');
  });

  it('blank line separates paragraphs', () => {
    const div = renderInDom(renderMarkdown('first\n\nsecond'));
    expect(div.querySelectorAll('p').length).toBe(2);
  });

  it('groups consecutive `- ` lines into a single <ul>', () => {
    const div = renderInDom(renderMarkdown('- one\n- two\n- three'));
    expect(div.querySelector('ul')).not.toBeNull();
    expect(div.querySelectorAll('li').length).toBe(3);
  });

  it('list items support inline emphasis', () => {
    const div = renderInDom(renderMarkdown('- **bold** item\n- *italic* item'));
    const items = div.querySelectorAll('li');
    expect(items[0].querySelector('strong')).not.toBeNull();
    expect(items[1].querySelector('em')).not.toBeNull();
  });

  it('supports wrapped list continuations (bot finding regression)', () => {
    // The original tokenizer ended the list at the first non-`-` line.
    // The tester guide doc has bullets with indented continuations.
    const md = [
      '- **World name** — what you call this playthrough. Shows in the top',
      '  bar during play and in your worlds list.',
      '- **Character name** — who you play as.',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    const items = div.querySelectorAll('li');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('top bar during play');
    expect(items[0].textContent).toContain('worlds list');
  });

  it('renders ordered list (`1. item`) as <ol> (bot finding regression)', () => {
    const div = renderInDom(renderMarkdown('1. first\n2. second\n3. third'));
    expect(div.querySelector('ol')).not.toBeNull();
    expect(div.querySelector('ul')).toBeNull();
    const items = div.querySelectorAll('li');
    expect(items.length).toBe(3);
    expect(items[0].textContent).toBe('first');
  });

  it('ordered list supports wrapped continuations', () => {
    const md = [
      '1. **Decide what to do.** Type into the command bar, or click any',
      '   highlighted phrase / amber pill / always-available pill.',
      '2. **Send.** Press Enter or click the send button.',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    const items = div.querySelectorAll('li');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('highlighted phrase');
  });

  it('groups consecutive `> ` lines into a single <blockquote>', () => {
    const div = renderInDom(renderMarkdown('> first\n> second'));
    const bq = div.querySelector('blockquote');
    expect(bq).not.toBeNull();
    expect(bq.querySelectorAll('p').length).toBe(2);
  });

  it('blockquote supports inline links', () => {
    const div = renderInDom(
      renderMarkdown('> **Cosmetic so far:** see [docs](https://example.com)'),
    );
    const bq = div.querySelector('blockquote');
    expect(bq.querySelector('strong')).not.toBeNull();
    expect(bq.querySelector('a')).not.toBeNull();
  });

  it('renders {{toc}} as a nav with links to every ## heading', () => {
    const md = [
      '# Title',
      '',
      '{{toc}}',
      '',
      '## First section',
      '',
      'Content.',
      '',
      '## Second section',
      '',
      'More content.',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    const nav = div.querySelector('nav');
    expect(nav).not.toBeNull();
    expect(nav.getAttribute('aria-label')).toBe('Table of contents');
    const links = nav.querySelectorAll('a');
    expect(links.length).toBe(2);
    expect(links[0].getAttribute('href')).toBe('#first-section');
    expect(links[0].textContent).toBe('First section');
    expect(links[1].getAttribute('href')).toBe('#second-section');
  });

  it('{{toc}} lists only ## headings (h1 + h3 excluded)', () => {
    const md = [
      '# Title',
      '',
      '{{toc}}',
      '',
      '## A',
      '',
      '### A subsection',
      '',
      '## B',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    const links = div.querySelectorAll('nav a');
    expect(links.length).toBe(2);
    expect(links[0].textContent).toBe('A');
    expect(links[1].textContent).toBe('B');
  });

  it('{{toc}} renders nothing when there are no h2 headings', () => {
    const div = renderInDom(renderMarkdown('{{toc}}\n\nNo h2s here.'));
    expect(div.querySelector('nav')).toBeNull();
  });

  it('renders ![alt](path) at block level (image on its own line)', () => {
    const div = renderInDom(renderMarkdown('![World creation form](guide/creation.png)'));
    const img = div.querySelector('img');
    expect(img).not.toBeNull();
    expect(img.getAttribute('alt')).toBe('World creation form');
  });

  it('heading + paragraph + ordered list + image renders in order', () => {
    const md = [
      '# Title',
      '',
      'Intro paragraph.',
      '',
      '## Steps',
      '',
      '1. one',
      '2. two',
      '',
      '![diagram](guide/x.png)',
    ].join('\n');
    const div = renderInDom(renderMarkdown(md));
    expect(div.querySelector('h1').textContent).toBe('Title');
    expect(div.querySelector('h2').textContent).toBe('Steps');
    expect(div.querySelectorAll('ol li').length).toBe(2);
    expect(div.querySelector('img')).not.toBeNull();
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
