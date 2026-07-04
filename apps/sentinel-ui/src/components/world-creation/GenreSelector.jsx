import { useEffect, useState } from 'react';

import fantasyTile from '../../assets/generated/genre-fantasy.webp';
import scifiTile from '../../assets/generated/genre-sci-fi.webp';
import westernTile from '../../assets/generated/genre-western.webp';
import horrorTile from '../../assets/generated/genre-horror.webp';
import cyberpunkTile from '../../assets/generated/genre-cyberpunk.webp';

import fantasyMotion from '../../assets/generated/genre-fantasy.mp4';
import scifiMotion from '../../assets/generated/genre-sci-fi.mp4';
import westernMotion from '../../assets/generated/genre-western.mp4';
import horrorMotion from '../../assets/generated/genre-horror.mp4';
import cyberpunkMotion from '../../assets/generated/genre-cyberpunk.mp4';

// A5 genre tiles, keyed by the genre slug the form uses (WorldCreation GENRES).
// A genre with no tile falls back to a plain swatch, so adding a genre never
// breaks the selector before its art exists. The still (.webp) doubles as the
// motion tile's poster/fallback; the loop (.mp4) is an ambient animation of the
// same emblem, locked to the same framing so there is no layout shift or jump.
const GENRE_TILES = {
  fantasy: fantasyTile,
  'sci-fi': scifiTile,
  western: westernTile,
  horror: horrorTile,
  cyberpunk: cyberpunkTile,
};

const GENRE_MOTION = {
  fantasy: fantasyMotion,
  'sci-fi': scifiMotion,
  western: westernMotion,
  horror: horrorMotion,
  cyberpunk: cyberpunkMotion,
};

// Respect the OS "reduce motion" setting: opted-out users get the still tile,
// never the autoplaying loop. Reacts to live changes to the media query.
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

// Capitalize each hyphen-separated part: "sci-fi" → "Sci-Fi", "fantasy" → "Fantasy".
const titleCase = (s) =>
  s
    .split('-')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('-');

export function GenreSelector({ value, onChange, genres = [] }) {
  const reducedMotion = usePrefersReducedMotion();
  return (
    <div>
      <label className="block text-amber font-cinzel text-sm mb-3">GENRE</label>
      <div className="grid grid-cols-3 gap-2">
        {genres.map((genre) => {
          const selected = value === genre;
          const tile = GENRE_TILES[genre];
          const motion = GENRE_MOTION[genre];
          // width/height set so the tile reserves space (no layout shift).
          const mediaClass = `aspect-square w-full object-cover transition-opacity ${
            selected ? 'opacity-100' : 'opacity-70 group-hover:opacity-100'
          }`;
          return (
            <button
              key={genre}
              type="button"
              onClick={() => onChange(genre)}
              aria-pressed={selected}
              className={`group relative overflow-hidden rounded border transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber ${
                selected
                  ? 'border-amber ring-1 ring-amber'
                  : 'border-border hover:border-amber/60'
              }`}
            >
              {tile ? (
                motion && !reducedMotion ? (
                  <video
                    src={motion}
                    poster={tile}
                    width={512}
                    height={512}
                    autoPlay
                    muted
                    loop
                    playsInline
                    aria-hidden="true"
                    className={mediaClass}
                  />
                ) : (
                  <img
                    src={tile}
                    alt=""
                    width={512}
                    height={512}
                    className={mediaClass}
                  />
                )
              ) : (
                <div className="aspect-square w-full bg-border" />
              )}
              <span
                className={`block py-1 text-center text-xs font-cinzel ${
                  selected ? 'bg-amber text-void' : 'bg-codex text-ink'
                }`}
              >
                {titleCase(genre)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
