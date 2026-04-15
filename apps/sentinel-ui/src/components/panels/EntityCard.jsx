/**
 * EntityCard — pure component, no store wiring.
 * Renders a single entity's fields based on its type.
 *
 * Props:
 *   entity  {object}  — the entity dict from worldStore
 *   type    {string}  — 'character' | 'location' | 'faction' | 'item'
 *   onClose {func}    — optional; renders a close button if provided
 */

function Row({ label, value }) {
  if (value === null || value === undefined || value === '') return null;
  const display = Array.isArray(value) ? value.join(', ') : String(value);
  if (!display) return null;
  return (
    <div className="flex gap-2 text-xs leading-relaxed">
      <span className="text-ether shrink-0 w-24">{label}</span>
      <span className="text-ink">{display}</span>
    </div>
  );
}

function CharacterCard({ entity }) {
  return (
    <>
      <Row label="Role"       value={entity.role} />
      <Row label="Class"      value={entity.class ?? entity.class_name} />
      <Row label="Race"       value={entity.race} />
      <Row label="Level"      value={entity.level} />
      <Row label="Health"     value={entity.health !== undefined ? `${entity.health} / ${entity.maxHealth ?? entity.max_health ?? '?'}` : null} />
      <Row label="Status"     value={entity.status} />
      <Row label="Location"   value={entity.currentLocation ?? entity.current_location} />
      <Row label="Traits"     value={entity.traits} />
      <Row label="Description" value={entity.description} />
    </>
  );
}

function LocationCard({ entity }) {
  return (
    <>
      <Row label="Type"        value={entity.type} />
      <Row label="Region"      value={entity.region} />
      <Row label="Danger"      value={entity.danger !== undefined ? `${entity.danger}/10` : null} />
      <Row label="Discovered"  value={entity.discovered ? 'Yes' : 'No'} />
      <Row label="Features"    value={entity.notableFeatures ?? entity.notable_features} />
      <Row label="Description" value={entity.description} />
    </>
  );
}

function FactionCard({ entity }) {
  return (
    <>
      <Row label="Alignment"   value={entity.alignment} />
      <Row label="Power"       value={entity.power !== undefined ? `${entity.power}/10` : null} />
      <Row label="Relation"    value={entity.playerRelation ?? entity.player_relation} />
      <Row label="Goals"       value={entity.goals} />
      <Row label="Description" value={entity.description} />
    </>
  );
}

function ItemCard({ entity }) {
  return (
    <>
      <Row label="Type"        value={entity.type} />
      <Row label="Rarity"      value={entity.rarity} />
      <Row label="Magical"     value={entity.magical ? 'Yes' : entity.magical === false ? 'No' : null} />
      <Row label="Owned by"    value={entity.ownedBy ?? entity.owned_by} />
      <Row label="Location"    value={entity.location} />
      <Row label="Description" value={entity.description} />
    </>
  );
}

const CARD_COMPONENTS = {
  character: CharacterCard,
  location:  LocationCard,
  faction:   FactionCard,
  item:      ItemCard,
};

export function EntityCard({ entity, type, onClose }) {
  const CardBody = CARD_COMPONENTS[type];
  if (!entity || !CardBody) return null;

  return (
    <div className="p-4 text-sm">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-amber font-cinzel text-sm leading-tight">{entity.name}</div>
          <div className="text-ether text-xs capitalize mt-0.5">{type}</div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-ether hover:text-amber transition-colors text-xs ml-2 shrink-0"
            aria-label="Close"
          >
            ✕
          </button>
        )}
      </div>

      {/* Fields */}
      <div className="space-y-1.5 border-t border-border pt-3">
        <CardBody entity={entity} />
      </div>
    </div>
  );
}
