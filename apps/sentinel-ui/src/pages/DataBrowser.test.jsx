/**
 * Tests for the /data training-data browser.
 *
 * Mocks fetch (apiClient uses it) to serve a session list + detail, and
 * asserts the list renders, a session opens to show its turns, and the
 * per-session export links point at the backend export endpoint.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DataBrowser from './DataBrowser'
import { API_BASE } from '../api/client'

const SID = 'abc-123'

function fakeFetch() {
  return vi.fn((url) => {
    if (url === `${API_BASE}/sessions`) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              sessionId: SID,
              worldName: 'Hallowrun',
              persona: 'Oracle',
              character: 'Bob',
              turnCount: 2,
              startedAt: '',
            },
          ]),
      })
    }
    if (url === `${API_BASE}/sessions/${SID}`) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            sessionId: SID,
            worldName: 'Hallowrun',
            persona: 'Oracle',
            character: 'Bob',
            startedAt: '',
            turns: [
              { id: 1, turn_number: 0, player_action: 'look', narrative: 'You see a road.' },
            ],
          }),
      })
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', fakeFetch())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DataBrowser', () => {
  it('lists recorded sessions', async () => {
    render(<DataBrowser />)
    expect(await screen.findByText('Hallowrun')).toBeInTheDocument()
    expect(screen.getByText(/2 turns/)).toBeInTheDocument()
  })

  it('opens a session and exposes export links to the backend endpoint', async () => {
    render(<DataBrowser />)
    fireEvent.click(await screen.findByText('Hallowrun'))
    expect(await screen.findByText(/You see a road\./)).toBeInTheDocument()

    const schema = screen.getByRole('link', { name: /Schema \.jsonl/ })
    expect(schema).toHaveAttribute(
      'href',
      `${API_BASE}/sessions/${SID}/export?format=schema`,
    )
    const chatlog = screen.getByRole('link', { name: /Chatlog \.md/ })
    expect(chatlog).toHaveAttribute(
      'href',
      `${API_BASE}/sessions/${SID}/export?format=chatlog`,
    )
  })
})
