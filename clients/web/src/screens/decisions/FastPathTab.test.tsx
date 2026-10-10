/* The fast path's rows are ordinary approvals rows; what this slice must get
   right is the speculative lifecycle — what is still in force, what only
   pretends to be, and what a human can undo right now. */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  fastPathStatusChip,
  fastPathSimulated,
  secondsLeft,
  ExpiryCountdown,
} from './DecisionsScreen'
import type { FastPathAction } from './useDecisions'

function row(over: Partial<FastPathAction>): FastPathAction {
  return {
    action_id: 'act-fp-1',
    action_type: 'rate_limit',
    target: '203.0.113.7',
    status: 'speculative',
    reason: 'fast_path.review_threshold: severity=high, confidence=0.88 >= 0.85',
    simulated: false,
    ...over,
  }
}

describe('what a fast-path row says happened to it', () => {
  it('renders the three speculative statuses with distinct labels', () => {
    render(
      <>
        {fastPathStatusChip('speculative')}
        {fastPathStatusChip('rolled_back')}
        {fastPathStatusChip('escalated')}
      </>
    )
    expect(screen.getByText('Speculative')).toBeInTheDocument()
    expect(screen.getByText('Released')).toBeInTheDocument()
    expect(screen.getByText('Escalated')).toBeInTheDocument()
  })

  it('falls back to the raw status for a value the console does not know', () => {
    render(fastPathStatusChip('vanished'))
    expect(screen.getByText('vanished')).toBeInTheDocument()
  })
})

describe('the simulated badge', () => {
  // A restriction that touched nothing must never read as enforced: the badge
  // fails toward visible, not toward quiet.
  it('labels a row the adapter only simulated', () => {
    render(fastPathSimulated(true))
    expect(screen.getByText('simulated')).toBeInTheDocument()
  })

  it('hides the badge when the row was really enforced', () => {
    const { container } = render(fastPathSimulated(false))
    expect(container).toBeEmptyDOMElement()
  })

  it('labels a row whose enforcement flag never arrived', () => {
    render(fastPathSimulated(undefined))
    expect(screen.getByText('simulated')).toBeInTheDocument()
  })
})

describe('the expiry countdown', () => {
  it('computes the floor of the seconds remaining', () => {
    const now = Date.now()
    expect(secondsLeft(new Date(now + 90_500).toISOString(), now)).toBe(90)
    expect(secondsLeft(new Date(now - 5_000).toISOString(), now)).toBe(0)
    expect(secondsLeft(undefined, now)).toBeNull()
    expect(secondsLeft('not-a-date', now)).toBeNull()
  })

  it('runs a live clock for a row still in force', () => {
    const expires = new Date(Date.now() + 15 * 60 * 1000).toISOString()
    render(<ExpiryCountdown action={row({ expires_at: expires })} />)
    // The floor crosses the minute boundary between computing the expiry and
    // rendering, so the clock reads 14:59 or 15:00 -- both are the right clock.
    expect(screen.getByText(/^(14|15):\d{2}$/)).toBeInTheDocument()
  })

  it('clamps an elapsed expiry to zero rather than counting up', () => {
    const expires = new Date(Date.now() - 30_000).toISOString()
    render(<ExpiryCountdown action={row({ expires_at: expires })} />)
    expect(screen.getByText('0:00')).toBeInTheDocument()
  })

  it('shows no clock for a row that is no longer in force', () => {
    render(<ExpiryCountdown action={row({ status: 'rolled_back', expires_at: new Date().toISOString() })} />)
    expect(screen.getByText('\u2014')).toBeInTheDocument()
  })
})
