/**
 * Tests for PanelRouter's tab set.
 *
 * The Quests and Map tabs were removed (no data model — Map rendered a
 * fabricated ASCII map, Quests was an unimplemented stub). Only tabs
 * backed by real session state remain: Codex and Inventory.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PanelRouter } from './PanelRouter'
import { useUIStore } from '../../stores/uiStore'

vi.mock('./CodexPanel', () => ({ CodexPanel: () => <div>codex-panel</div> }))
vi.mock('./InventoryPanel', () => ({ InventoryPanel: () => <div>inventory-panel</div> }))
vi.mock('./EntityCard', () => ({ EntityCard: () => null }))

beforeEach(() => {
  useUIStore.setState({ activeTab: 'codex', selectedEntity: null })
})

describe('PanelRouter tabs', () => {
  it('renders only the Codex and Inventory tabs', () => {
    render(<PanelRouter />)
    expect(screen.getByRole('button', { name: 'Codex' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Inv' })).toBeInTheDocument()
  })

  it('no longer offers the removed Quests or Map tabs', () => {
    render(<PanelRouter />)
    expect(screen.queryByRole('button', { name: 'Quests' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Map' })).toBeNull()
  })
})
