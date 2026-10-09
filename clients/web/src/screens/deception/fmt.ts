/** Display formatting for the deception surfaces — pure functions, shared by
 *  the screen and its tests. */

export const fmtClock = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString(undefined, { hour12: false }) : '—'

/** Time left on a lease, refreshed each second by the hook's ticker. */
export const fmtCountdown = (expiresAt: string | null, now: number): string => {
  if (!expiresAt) return '—'
  const remaining = new Date(expiresAt).getTime() - now
  if (remaining <= 0) return 'expired'
  const totalSeconds = Math.floor(remaining / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    return `${hours}h ${minutes % 60}m left`
  }
  return minutes > 0 ? `${minutes}m ${seconds}s left` : `${seconds}s left`
}
