import { describe, expect, it, vi } from 'vitest'
import { StrictMode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { useTwinGraph } from './useTwinGraph'
import { DEMO_TWIN_PAYLOAD as DEMO } from './fixtures'

const api = vi.hoisted(() => ({ getTwinGraph: vi.fn() }))
vi.mock('../../services/api', () => ({ twinApi: api }))

// The app mounts under <React.StrictMode> (src/main.tsx), which simulates an
// unmount/remount on first render. The hook's stale-response guard must
// re-arm on the second mount, or every response is discarded and the screen
// is stuck in Loading forever — invisible to tests that mock this hook.
describe('useTwinGraph under StrictMode', () => {
  it('reaches ready after the StrictMode double-mount', async () => {
    api.getTwinGraph.mockResolvedValue({ data: DEMO })
    const { result } = renderHook(() => useTwinGraph(), { wrapper: StrictMode })
    await waitFor(() => expect(result.current.phase).toBe('ready'), { timeout: 3000 })
    expect(result.current.payload?.devices).toHaveLength(DEMO.devices.length)
    expect(result.current.error).toBeNull()
  })
})
