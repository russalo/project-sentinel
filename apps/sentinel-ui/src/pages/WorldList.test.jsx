/**
 * Tests for the "my worlds" picker (ADR 0002 Slice 5).
 *
 * Mocks fetch (apiClient) to serve GET /api/worlds, and asserts the list
 * renders with resume links to /w/<worldId> and that the empty state offers a
 * create CTA.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import WorldList from './WorldList'
import { API_BASE } from '../api/client'

const WID = '9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f'

function worldsFetch(worlds) {
  return vi.fn((url) => {
    if (url === `${API_BASE}/worlds`) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(worlds) })
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('WorldList', () => {
  it('lists worlds with a resume link to /w/<worldId>', async () => {
    vi.stubGlobal(
      'fetch',
      worldsFetch([
        {
          worldId: WID,
          worldName: 'Saltmarsh',
          persona: 'Oracle',
          character: 'Russalo',
          turnCount: 3,
          startedAt: '',
        },
      ]),
    )
    render(<WorldList />)
    const link = await screen.findByRole('link', { name: /Saltmarsh/ })
    expect(link).toHaveAttribute('href', `/w/${WID}`)
    expect(screen.getByText(/3 turns/)).toBeInTheDocument()
    expect(screen.getByText(/Russalo · Oracle/)).toBeInTheDocument()
  })

  it('shows a create CTA when there are no worlds', async () => {
    vi.stubGlobal('fetch', worldsFetch([]))
    render(<WorldList />)
    const cta = await screen.findByRole('link', { name: /Begin a new world/ })
    expect(cta).toHaveAttribute('href', '/create')
    expect(screen.getByText(/No worlds yet/)).toBeInTheDocument()
  })
})
