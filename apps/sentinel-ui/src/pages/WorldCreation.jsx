import { useEffect, useCallback, useState } from 'react';
import { useLocation } from 'wouter';
import { apiClient } from '../api/client';
import { useWorldCreationStore } from '../stores/worldCreationStore';
import { usePlayerStore } from '../stores/playerStore';
import { useChatStore } from '../stores/chatStore';
import { GenreSelector } from '../components/world-creation/GenreSelector';
import { ToneSelector } from '../components/world-creation/ToneSelector';
import { RegionSelector } from '../components/world-creation/RegionSelector';
import { PersonaSelector } from '../components/world-creation/PersonaSelector';
import { MoodSelector } from '../components/world-creation/MoodSelector';
import { WorldModifiers } from '../components/world-creation/WorldModifiers';
import { LiveSeedPreview } from '../components/world-creation/LiveSeedPreview';

// Mock personas
const MOCK_PERSONAS = [
  { id: 'oracle', name: 'Oracle', compatibleGenres: ['fantasy', 'sci-fi', 'horror'], moods: ['neutral', 'ominous', 'lore-heavy'] },
  { id: 'chronicler', name: 'The Chronicler', compatibleGenres: ['fantasy', 'historical'], moods: ['neutral', 'gritty', 'lore-heavy'] },
  { id: 'cowboy', name: 'Cowboy Bob', compatibleGenres: ['western'], moods: ['gritty', 'humorous', 'fast-paced'] },
];

const GENRES = ['fantasy', 'sci-fi', 'western', 'horror', 'cyberpunk'];
const TONES = ['neutral', 'gritty', 'humorous', 'ominous', 'dark'];
const REGIONS = {
  fantasy: ['The Breach', 'Thornwatch', 'Crown City', 'The Wastes'],
  'sci-fi': ['Station Alpha', 'Mars Colony', 'Outer Ring', 'Asteroid Field'],
  western: ['Dusty Gulch', 'Frontier Town', 'Desert Wasteland', 'Gold Rush Camp'],
  horror: ['Abandoned Manor', 'Dark Forest', 'Cursed Village', 'Underground Tomb'],
  cyberpunk: ['Neon District', 'Corporate Tower', 'Undercity', 'Neural Net'],
};

async function generateSeedPreview(formData) {
  // Mock seed generation
  const parts = [
    formData.genre?.[0] || 'U',
    formData.tone?.[0] || 'N',
    formData.personaId?.substring(0, 3) || 'XXX',
    Math.random().toString(16).slice(2, 7),
  ];
  const abbreviated = parts.join('-').toUpperCase();

  return {
    publicFields: {
      worldName: formData.worldName || 'Unnamed World',
      genre: formData.genre || 'Unknown',
      tone: formData.tone || 'Neutral',
      startingRegion: formData.startingRegion || 'Unknown',
      personaName: MOCK_PERSONAS.find(p => p.id === formData.personaId)?.name || 'Unknown',
      mood: formData.mood || 'neutral',
      modifiers: {
        sandbox: formData.sandbox,
        permadeath: formData.permadeath,
      },
    },
    abbreviated,
  };
}

export default function WorldCreation() {
  const [, navigate] = useLocation();
  const creation = useWorldCreationStore();
  const { setSessionId, setCharacter } = usePlayerStore();
  const { addMessage, clearMessages } = useChatStore();
  const [isGenerating, setIsGenerating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState(null);

  // Generate seed preview on form changes
  const updatePreview = useCallback(async () => {
    if (!creation.worldName || !creation.genre || !creation.personaId) return;

    setIsGenerating(true);
    const preview = await generateSeedPreview(creation);
    creation.setSeedPreview(preview.publicFields, preview.abbreviated);
    setIsGenerating(false);
  }, [creation]);

  useEffect(() => {
    const timer = setTimeout(updatePreview, 300);
    return () => clearTimeout(timer);
  }, [creation.worldName, creation.genre, creation.tone, creation.startingRegion, creation.personaId, creation.mood, creation.sandbox, creation.permadeath, updatePreview]);

  const canBegin = creation.worldName && creation.genre && creation.personaId;

  const handleBegin = async () => {
    if (!canBegin || isStarting) return;
    setIsStarting(true);
    setStartError(null);
    try {
      const data = await apiClient.post('/session/new', {
        worldName: creation.worldName,
        playerCharacterName: creation.characterName || 'Traveler',
        playerCharacterClass: creation.characterClass || 'Adventurer',
        genre: creation.genre,
        tone: creation.tone,
        startingRegion: creation.startingRegion,
        personaId: creation.personaId,
        mood: creation.mood,
        sandbox: creation.sandbox,
        permadeath: creation.permadeath,
      });

      setSessionId(data.sessionId);
      setCharacter(creation.characterName || 'Traveler', creation.characterClass || 'Adventurer');

      // Seed the chat with the opening DM narrative
      clearMessages();
      if (data.turns?.length > 0) {
        const opening = data.turns[0];
        addMessage({
          type: 'dm',
          content: opening.narrative,
          author: 'DM',
          timestamp: new Date(),
        });
      }

      creation.reset();
      navigate('/');
    } catch (err) {
      setStartError(err.message);
      setIsStarting(false);
    }
  };

  return (
    <div className="min-h-screen bg-void flex flex-col">
      {/* Header */}
      <header className="bg-codex border-b border-border px-6 py-4">
        <h1 className="font-cinzel text-2xl text-amber">⚔ SENTINEL</h1>
        <p className="text-dust text-sm mt-1">Forge a new world</p>
      </header>

      {/* Main content */}
      <div className="flex-1 flex gap-6 p-6 overflow-hidden">
        {/* Form */}
        <div className="flex-1 overflow-y-auto space-y-6 pr-4">
          {/* World Identity */}
          <div>
            <label className="block text-amber font-cinzel text-sm mb-2">WORLD NAME</label>
            <input
              type="text"
              value={creation.worldName}
              onChange={(e) => creation.setWorldName(e.target.value)}
              placeholder="e.g., The Shattered Expanse"
              className="w-full bg-void border border-border rounded px-3 py-2 text-ink placeholder-dust focus:outline-none focus:border-amber transition-colors"
            />
          </div>

          {/* Character */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-amber font-cinzel text-sm mb-2">CHARACTER NAME</label>
              <input
                type="text"
                value={creation.characterName}
                onChange={(e) => creation.setCharacterName(e.target.value)}
                placeholder="Your name"
                className="w-full bg-void border border-border rounded px-3 py-2 text-ink placeholder-dust focus:outline-none focus:border-amber transition-colors"
              />
            </div>
            <div>
              <label className="block text-amber font-cinzel text-sm mb-2">CLASS</label>
              <input
                type="text"
                value={creation.characterClass}
                onChange={(e) => creation.setCharacterClass(e.target.value)}
                placeholder="Warrior, Mage, etc"
                className="w-full bg-void border border-border rounded px-3 py-2 text-ink placeholder-dust focus:outline-none focus:border-amber transition-colors"
              />
            </div>
          </div>

          {/* Genre & Tone */}
          <GenreSelector value={creation.genre} onChange={creation.setGenre} genres={GENRES} />
          {creation.genre && <ToneSelector value={creation.tone} onChange={creation.setTone} tones={TONES} />}

          {/* Starting Region */}
          {creation.genre && (
            <RegionSelector
              value={creation.startingRegion}
              onChange={creation.setStartingRegion}
              regions={REGIONS[creation.genre] || []}
            />
          )}

          {/* Persona */}
          {creation.genre && (
            <PersonaSelector
              value={creation.personaId}
              onChange={(id) => {
                const persona = MOCK_PERSONAS.find(p => p.id === id);
                creation.setPersona(id, persona?.moods?.[0] || 'neutral');
              }}
              personas={MOCK_PERSONAS.filter(p => p.compatibleGenres.includes(creation.genre))}
            />
          )}

          {/* Mood */}
          {creation.personaId && (
            <MoodSelector
              value={creation.mood}
              onChange={creation.setMood}
              moods={MOCK_PERSONAS.find(p => p.id === creation.personaId)?.moods || []}
            />
          )}

          {/* Modifiers */}
          <WorldModifiers
            sandbox={creation.sandbox}
            permadeath={creation.permadeath}
            onChange={(s, p) => creation.setModifiers(s, p)}
          />

          {/* Begin Button */}
          {startError && (
            <p className="text-red-400 text-sm">{startError}</p>
          )}
          <button
            onClick={handleBegin}
            disabled={!canBegin || isStarting}
            className="w-full py-3 bg-amber text-void rounded font-medium hover:bg-amber/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-8"
          >
            {isStarting ? 'Forging your world...' : '✦ BEGIN JOURNEY'}
          </button>
        </div>

        {/* Seed Preview */}
        <div className="w-80 sticky top-6 h-fit">
          <LiveSeedPreview preview={creation.seedPreview} seed={creation.abbreviatedSeed} isGenerating={isGenerating} />
        </div>
      </div>
    </div>
  );
}
