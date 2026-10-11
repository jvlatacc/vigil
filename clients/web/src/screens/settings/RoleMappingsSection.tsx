import { useState } from 'react'
import { Icon } from '../../shared/icons'
import { ConfirmDialog, EmptyState, Field, NumberInput, Popup, Select, SettingsCard, TextInput } from '../../shared/ui'
import { useAuth } from '../../contexts/AuthContext'
import { errText } from './serverErrors'
import { emptyMappingPayload, useRoleMappings, type MappingPayload, type RoleGroupMapping } from './useRoleMappings'
import type { SectionProps } from './types'

// Every mapping route — reads included — is gated users.write server-side,
// so this section only renders for actors who can actually use it.
export default function RoleMappingsSection({ notify }: SectionProps) {
  const { hasPermission } = useAuth()
  const { mappings, roles, phase, error, reload, createMapping, updateMapping, deleteMapping } =
    useRoleMappings()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RoleGroupMapping | null>(null)
  const [form, setForm] = useState<MappingPayload>(emptyMappingPayload())
  const [dialogError, setDialogError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<RoleGroupMapping | null>(null)
  const [deleting, setDeleting] = useState(false)

  if (!hasPermission('users.write')) {
    return (
      <div className="settings-banner err">
        <Icon name="alert" size={14} /> You don’t have permission to manage role mappings.
      </div>
    )
  }
  if (phase === 'loading') {
    return <div className="text-sm text-tx-3 py-16 text-center">Loading role mappings…</div>
  }
  if (phase === 'error') {
    return (
      <div className="py-16 text-center flex flex-col items-center gap-2.5">
        <span className="text-sm text-tx-3">Couldn’t load role mappings: {error}</span>
        <button className="btn ghost" onClick={reload}>Retry</button>
      </div>
    )
  }

  const roleOptions = roles.map((r) => ({ value: r.role_id, label: r.name }))

  const openCreate = () => {
    if (roles.length === 0) {
      notify('err', 'Roles not loaded yet — try Refresh.')
      return
    }
    setEditing(null)
    setForm({ ...emptyMappingPayload(), role_id: roles[0].role_id })
    setDialogError('')
    setDialogOpen(true)
  }

  const openEdit = (m: RoleGroupMapping) => {
    setEditing(m)
    setForm({ role_id: m.role_id, idp_group: m.idp_group, priority: m.priority })
    setDialogError('')
    setDialogOpen(true)
  }

  const validate = (): string | null => {
    if (!form.idp_group.trim()) return 'Directory group is required'
    if (!form.role_id) return 'Role is required'
    if (!Number.isInteger(form.priority) || form.priority < 0) {
      return 'Priority must be a whole number of 0 or more'
    }
    return null
  }

  const handleSave = async () => {
    const v = validate()
    if (v) {
      setDialogError(v)
      return
    }
    setSaving(true)
    setDialogError('')
    const payload = { ...form, idp_group: form.idp_group.trim() }
    try {
      if (editing) {
        await updateMapping(editing.id, payload)
        notify('ok', `Updated the mapping for ${payload.idp_group}.`)
      } else {
        await createMapping(payload)
        notify('ok', `Mapped ${payload.idp_group} to a role.`)
      }
      setDialogOpen(false)
    } catch (e) {
      setDialogError(errText(e, 'Failed to save the mapping'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) return
    setDeleting(true)
    try {
      await deleteMapping(confirmDelete.id)
      notify('ok', `Deleted the mapping for ${confirmDelete.idp_group}.`)
      setConfirmDelete(null)
    } catch (e) {
      notify('err', errText(e, 'Failed to delete the mapping'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <SettingsCard
      title="Role mappings"
      desc="Directory groups from your identity provider, mapped onto Vigil roles. A group’s holders get its role’s permissions at their next sign-in; when someone holds several mapped groups, the highest-priority mapping wins."
      actions={
        <>
          <button className="btn ghost" onClick={reload}>
            <Icon name="refresh" /> Refresh
          </button>
          <button className="btn primary" onClick={openCreate}>
            <Icon name="plus" /> Add mapping
          </button>
        </>
      }
    >
      {mappings.length === 0 ? (
        <EmptyState
          icon="link"
          title="No role mappings yet."
          body="Without a mapping, federated sign-ins succeed but grant no permissions. Add one per directory group — for example vigil-analysts → Analyst."
        />
      ) : (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Directory group</th>
                <th>Role</th>
                <th>Priority</th>
                <th>Created</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <tr key={m.id}>
                  <td>{m.idp_group}</td>
                  <td>
                    <span className="chip">{m.role_name || m.role_id}</span>
                  </td>
                  <td className="muted">{m.priority}</td>
                  <td className="muted">
                    {m.created_at ? new Date(m.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="inline-flex gap-1.5">
                      <button className="btn ghost icon" title={`Edit ${m.idp_group}`} onClick={() => openEdit(m)}>
                        <Icon name="edit" size={15} />
                      </button>
                      <button
                        className="btn ghost icon"
                        title={`Delete ${m.idp_group}`}
                        onClick={() => setConfirmDelete(m)}
                      >
                        <Icon name="trash" size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Popup
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit mapping: ${editing.idp_group}` : 'Add role mapping'}
        width={460}
      >
        <div className="flex flex-col gap-3.5">
          {dialogError && (
            <div className="settings-banner err">
              <Icon name="alert" size={14} /> {dialogError}
            </div>
          )}
          <Field label="Directory group" hint="The group’s name in FreeIPA, e.g. vigil-analysts.">
            <TextInput
              value={form.idp_group}
              disabled={saving}
              onChange={(e) => setForm({ ...form, idp_group: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <Select
              value={form.role_id}
              options={roleOptions}
              placeholder={roles.length ? 'Select a role…' : 'Loading roles…'}
              onSelect={(v) => setForm({ ...form, role_id: v })}
            />
          </Field>
          <Field label="Priority" hint="Higher wins when someone holds several mapped groups.">
            <NumberInput
              value={form.priority}
              min={0}
              disabled={saving}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
            />
          </Field>
          <div className="flex justify-end gap-2.5 mt-1">
            <button className="btn ghost" onClick={() => setDialogOpen(false)} disabled={saving}>
              Cancel
            </button>
            <button className="btn primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : editing ? 'Update' : 'Create'}
            </button>
          </div>
        </div>
      </Popup>

      <ConfirmDialog
        open={!!confirmDelete}
        title="Delete mapping?"
        body={`Remove the mapping for ${confirmDelete?.idp_group ?? 'this group'}? Holders lose the role’s permissions at their next sign-in.`}
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={handleDelete}
        onClose={() => setConfirmDelete(null)}
      />
    </SettingsCard>
  )
}
