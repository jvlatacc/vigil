import { useCallback, useEffect, useState } from 'react'
import api, { roleMappingsApi } from '../../services/api'
import type { Phase } from './useSettings'

/** One directory-group → role row, as the mapping admin API serves it. */
export interface RoleGroupMapping {
  id: number
  role_id: string
  role_name: string
  idp_group: string
  priority: number
  created_at: string | null
}

export interface MappingPayload {
  role_id: string
  idp_group: string
  priority: number
}

const EMPTY_PAYLOAD: MappingPayload = { role_id: '', idp_group: '', priority: 100 }
export const emptyMappingPayload = () => ({ ...EMPTY_PAYLOAD })

export function useRoleMappings() {
  const [mappings, setMappings] = useState<RoleGroupMapping[]>([])
  const [roles, setRoles] = useState<{ role_id: string; name: string }[]>([])
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    setError(null)
    // The roles list feeds the editor's role picker; without it a mapping
    // cannot be created, so it loads as part of the section's one read pass.
    Promise.all([roleMappingsApi.getAll(), api.get('/users/roles/list')])
      .then(([mappingsRes, rolesRes]) => {
        if (cancelled) return
        const m = mappingsRes.data?.mappings
        const r = rolesRes.data?.roles
        if (!Array.isArray(m) || !Array.isArray(r)) throw new Error('Invalid mappings/roles data')
        setMappings(m)
        setRoles(r)
        setPhase('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.response?.data?.detail || e?.message || 'Failed to load role mappings')
        setPhase('error')
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const createMapping = useCallback(
    (payload: MappingPayload) => roleMappingsApi.create(payload).then(() => reload()),
    [reload],
  )
  const updateMapping = useCallback(
    (id: number, patch: Partial<MappingPayload>) =>
      roleMappingsApi.update(id, patch).then(() => reload()),
    [reload],
  )
  const deleteMapping = useCallback(
    (id: number) => roleMappingsApi.remove(id).then(() => reload()),
    [reload],
  )

  return { mappings, roles, phase, error, reload, createMapping, updateMapping, deleteMapping }
}
