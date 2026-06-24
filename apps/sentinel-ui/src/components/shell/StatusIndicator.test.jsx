/**
 * StatusIndicator now reflects real turn state from chatStore (it used to be a
 * hardcoded fake "Connected"). idle → Ready, in-flight → Streaming…, failed
 * turn → Connection error.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusIndicator } from './StatusIndicator'
import { useChatStore } from '../../stores/chatStore'

beforeEach(() => {
  useChatStore.setState({ isStreaming: false, streamError: false, rollResult: null })
})

describe('StatusIndicator', () => {
  it('shows Ready when idle', () => {
    render(<StatusIndicator />)
    expect(screen.getByText('Ready')).toBeInTheDocument()
  })

  it('shows Streaming… while a turn is in flight', () => {
    useChatStore.setState({ isStreaming: true })
    render(<StatusIndicator />)
    expect(screen.getByText('Streaming…')).toBeInTheDocument()
  })

  it('shows Connection error after a failed turn', () => {
    useChatStore.setState({ streamError: true })
    render(<StatusIndicator />)
    expect(screen.getByText('Connection error')).toBeInTheDocument()
  })

  it('shows "resolve to continue" while a rolled check awaits resolution', () => {
    useChatStore.setState({ rollResult: { stat: 'body', total: 77, margin: -3 } })
    render(<StatusIndicator />)
    expect(screen.getByText('Roll ready — resolve to continue')).toBeInTheDocument()
    // Not the misleading "Streaming…" — the DM isn't working yet.
    expect(screen.queryByText('Streaming…')).toBeNull()
  })

  it('streaming wins over a stale pending roll', () => {
    useChatStore.setState({ rollResult: { stat: 'body', total: 77 }, isStreaming: true })
    render(<StatusIndicator />)
    expect(screen.getByText('Streaming…')).toBeInTheDocument()
  })

  it('never shows the old hardcoded "Connected"', () => {
    render(<StatusIndicator />)
    expect(screen.queryByText('Connected')).toBeNull()
  })
})
