/**
 * Tests for WorldMetrics — the day counter + tension meter that lives at
 * the bottom of the world-state dashboard. Tension is the 0-10 int the
 * backend emits (engine/prompts/dm.py § TENSION & ENCOUNTER PRESSURE);
 * the meter renders it as a coloured progressbar plus a categorical
 * label that mirrors the prompt's bands (Calm / Off-balance / Overdue /
 * Critical).
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WorldMetrics } from './WorldMetrics'

describe('WorldMetrics — tension meter', () => {
  it('renders Calm at 0', () => {
    render(<WorldMetrics day={1} tension={0} />)
    expect(screen.getByText(/Calm/)).toBeInTheDocument()
    expect(screen.getByText(/0\/10/)).toBeInTheDocument()
    const bar = screen.getByRole('progressbar', { name: /tension/i })
    expect(bar).toHaveAttribute('aria-valuenow', '0')
  })

  it('renders Off-balance at 4-6', () => {
    render(<WorldMetrics day={3} tension={5} />)
    expect(screen.getByText(/Off-balance/)).toBeInTheDocument()
    expect(screen.getByText(/5\/10/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '5')
  })

  it('renders Overdue at 7-8 — the encounter-overdue band', () => {
    render(<WorldMetrics day={5} tension={7} />)
    expect(screen.getByText(/Overdue/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '7')
  })

  it('renders Critical at 9-10 — the encounter-must band', () => {
    render(<WorldMetrics day={8} tension={10} />)
    expect(screen.getByText(/Critical/)).toBeInTheDocument()
    expect(screen.getByText(/10\/10/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '10')
  })

  it('clamps an out-of-range tension into [0, 10]', () => {
    render(<WorldMetrics day={1} tension={42} />)
    // 42 → 10 (clamped). Critical band.
    expect(screen.getByText(/Critical/)).toBeInTheDocument()
    expect(screen.getByText(/10\/10/)).toBeInTheDocument()
  })

  it('falls back to 0 when tension is null/undefined', () => {
    render(<WorldMetrics day={1} tension={undefined} />)
    expect(screen.getByText(/Calm/)).toBeInTheDocument()
    expect(screen.getByText(/0\/10/)).toBeInTheDocument()
  })

  it('exposes day on the dashboard', () => {
    render(<WorldMetrics day={42} tension={3} />)
    expect(screen.getByText(/Day/)).toBeInTheDocument()
    expect(screen.getByText(/42 of 365/)).toBeInTheDocument()
  })
})
