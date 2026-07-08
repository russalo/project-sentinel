import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { GenreSelector } from './GenreSelector';

const GENRES = ['fantasy', 'sci-fi', 'western', 'horror', 'cyberpunk'];

afterEach(() => {
  // Tests that stub matchMedia clean up after themselves; jsdom's default is
  // no matchMedia at all, which the component treats as "motion allowed".
  delete window.matchMedia;
});

// Force prefers-reduced-motion to a fixed value by stubbing matchMedia.
function stubReducedMotion(reduce) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: reduce,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
}

describe('GenreSelector', () => {
  it('renders a title-cased button for each genre', () => {
    render(<GenreSelector value="fantasy" onChange={() => {}} genres={GENRES} />);
    expect(screen.getByRole('button', { name: /Fantasy/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sci-Fi/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cyberpunk/ })).toBeInTheDocument();
  });

  it('marks the selected genre with aria-pressed', () => {
    render(<GenreSelector value="horror" onChange={() => {}} genres={GENRES} />);
    expect(screen.getByRole('button', { name: /Horror/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: /Fantasy/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('calls onChange with the genre slug when a tile is clicked', async () => {
    const onChange = vi.fn();
    render(<GenreSelector value="fantasy" onChange={onChange} genres={GENRES} />);
    await userEvent.click(screen.getByRole('button', { name: /Western/ }));
    expect(onChange).toHaveBeenCalledWith('western');
  });

  it('renders an autoplaying muted looping video per genre when motion is allowed', () => {
    const { container } = render(
      <GenreSelector value="fantasy" onChange={() => {}} genres={GENRES} />,
    );
    const videos = container.querySelectorAll('video');
    expect(videos).toHaveLength(GENRES.length);
    const v = videos[0];
    expect(v).toHaveAttribute('src');
    expect(v).toHaveAttribute('poster'); // the still doubles as poster/fallback
    expect(v.muted).toBe(true);
    expect(v).toHaveAttribute('loop');
    expect(v).toHaveAttribute('playsInline');
    // Decorative — the button label carries the accessible name.
    expect(v).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('falls back to the still image (no video) when reduced motion is preferred', () => {
    stubReducedMotion(true);
    const { container } = render(
      <GenreSelector value="fantasy" onChange={() => {}} genres={GENRES} />,
    );
    expect(container.querySelectorAll('video')).toHaveLength(0);
    expect(container.querySelectorAll('img')).toHaveLength(GENRES.length);
  });

  it('renders a plain swatch for a genre that has no tile', () => {
    const { container } = render(
      <GenreSelector value="fantasy" onChange={() => {}} genres={['mystery']} />,
    );
    // No art of either kind for an unknown genre — just the fallback swatch.
    expect(container.querySelectorAll('video')).toHaveLength(0);
    expect(container.querySelectorAll('img')).toHaveLength(0);
    expect(screen.getByRole('button', { name: /Mystery/ })).toBeInTheDocument();
  });
});
