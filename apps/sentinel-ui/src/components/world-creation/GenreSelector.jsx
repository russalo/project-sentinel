import fantasyTile from '../../assets/generated/genre-fantasy.webp';
import scifiTile from '../../assets/generated/genre-sci-fi.webp';
import westernTile from '../../assets/generated/genre-western.webp';
import horrorTile from '../../assets/generated/genre-horror.webp';
import cyberpunkTile from '../../assets/generated/genre-cyberpunk.webp';

// A5 genre tiles, keyed by the genre slug the form uses (WorldCreation GENRES).
// A genre with no tile falls back to a plain swatch, so adding a genre never
// breaks the selector before its art exists.
const GENRE_TILES = {
  fantasy: fantasyTile,
  'sci-fi': scifiTile,
  western: westernTile,
  horror: horrorTile,
  cyberpunk: cyberpunkTile,
};

// Capitalize each hyphen-separated part: "sci-fi" → "Sci-Fi", "fantasy" → "Fantasy".
const titleCase = (s) =>
  s
    .split('-')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('-');

export function GenreSelector({ value, onChange, genres = [] }) {
  return (
    <div>
      <label className="block text-amber font-cinzel text-sm mb-3">GENRE</label>
      <div className="grid grid-cols-3 gap-2">
        {genres.map((genre) => {
          const selected = value === genre;
          const tile = GENRE_TILES[genre];
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
                // width/height set so the tile reserves space (no layout shift).
                <img
                  src={tile}
                  alt=""
                  width={512}
                  height={512}
                  className={`aspect-square w-full object-cover transition-opacity ${
                    selected ? 'opacity-100' : 'opacity-70 group-hover:opacity-100'
                  }`}
                />
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
