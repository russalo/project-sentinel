import { useUIStore } from '../../stores/uiStore';

export function CharacterList({ characters }) {
  const { setSelectedEntity } = useUIStore();

  return (
    <div>
      <h3 className="text-amber font-cinzel text-sm mb-2">◉ CHARACTERS</h3>
      {characters.length === 0 ? (
        <p className="text-dust text-xs">No one knows your name yet...</p>
      ) : (
        <ul className="text-xs text-ink space-y-1">
          {characters.map((char, i) => (
            <li
              key={char.unique_id ?? char.name ?? i}
              className="hover:text-amber cursor-pointer transition-colors animate-fade-in"
              onClick={() => setSelectedEntity(char, 'character')}
            >
              ◎ {char.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
