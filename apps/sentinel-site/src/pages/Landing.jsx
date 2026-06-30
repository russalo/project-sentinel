import { Link } from 'wouter'

const ALPHA_URL = 'https://sentinel.russalo.com/alpha/'

function Pitch({ title, children }) {
  return (
    <div className="bg-codex border border-border rounded-lg p-5">
      <h3 className="font-cinzel text-amber text-lg mb-2">{title}</h3>
      <p className="font-crimson text-dust leading-relaxed">{children}</p>
    </div>
  )
}

export default function Landing() {
  return (
    <main className="flex-1 w-full max-w-4xl mx-auto px-6 py-10 sm:py-16 animate-fade-in">
      {/* Hero */}
      <header className="text-center mb-12">
        <p className="font-mono text-xs tracking-[0.3em] uppercase text-leyline mb-4">
          Closed Alpha
        </p>
        <h1 className="font-cinzel text-4xl sm:text-6xl font-bold text-ink mb-4">
          Sentinel<span className="text-amber"> RPG</span>
        </h1>
        <p className="font-crimson text-xl sm:text-2xl text-dust max-w-2xl mx-auto">
          A persistent-world text RPG run by an AI Dungeon Master. Your world
          remembers everything.
        </p>
      </header>

      {/* The share card, used as the hero visual */}
      <div className="mb-12 rounded-xl overflow-hidden border border-border shadow-2xl">
        <img
          src="/og-image.png"
          alt="Project Sentinel — an AI Dungeon Master, a persistent-world text RPG"
          width={1200}
          height={630}
          className="w-full h-auto block"
        />
      </div>

      {/* CTA */}
      <div className="text-center mb-16">
        <a
          href={ALPHA_URL}
          className="inline-block font-cinzel text-lg bg-amber text-void px-8 py-3 rounded hover:bg-amber/90 transition-colors"
        >
          Enter the closed alpha →
        </a>
        <p className="font-sans text-sm text-dust mt-3">
          Invite required.{' '}
          <Link href="/guide" className="text-amber underline hover:text-amber/80">
            Read the player guide
          </Link>
          .
        </p>
      </div>

      {/* What it is */}
      <section className="grid gap-5 sm:grid-cols-3 mb-16">
        <Pitch title="A living world">
          Locations, characters, factions, and items persist turn to turn. The
          DM tracks canon so the world stays consistent as you play.
        </Pitch>
        <Pitch title="You write the story">
          Type what you do. The DM narrates the consequences, rolls when the
          stakes demand it, and never forgets what came before.
        </Pitch>
        <Pitch title="Yours to keep">
          Every world lives at its own URL. Close the tab, come back later, and
          pick up exactly where you left off.
        </Pitch>
      </section>

      <footer className="text-center font-mono text-xs text-dust border-t border-border pt-6">
        Project Sentinel · Closed Alpha ·{' '}
        <Link href="/guide" className="text-amber hover:text-amber/80">
          Player Guide
        </Link>
      </footer>
    </main>
  )
}
