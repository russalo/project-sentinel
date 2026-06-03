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
  useChatStore.setState({ isStreaming: false, streamError: false })
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

  it('never shows the old hardcoded "Connected"', () => {
    render(<StatusIndicator />)
    expect(screen.queryByText('Connected')).toBeNull()
  })
})
