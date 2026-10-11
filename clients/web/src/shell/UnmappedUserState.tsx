import { useAuth } from '../contexts/AuthContext'
import { useColorScheme } from '../contexts/ColorSchemeContext'
import { Icon } from '../shared/icons'
import { VigilMark } from '../shared/VigilLogo'

/**
 * True when the signed-in account's permission map exists and grants nothing
 * — the deny-by-default session a federated sign-in lands in when no
 * directory group maps to a role (and the shape of a role stripped to
 * nothing). A user object with NO map at all is shape drift, not a provably
 * unmapped session: the console renders and its per-screen gates surface it
 * rather than the UI asserting a reason it cannot see.
 */
export const hasNoPermissions = (
  user: { permissions?: Record<string, boolean> } | null | undefined,
): boolean =>
  !!user &&
  user.permissions !== undefined &&
  !Object.values(user.permissions).some((v) => v === true)

export default function UnmappedUserState() {
  const { user, logout } = useAuth()
  const { scheme } = useColorScheme()
  return (
    <div
      className={`soc-console soc-loader ${scheme === 'light' ? 'vg-light' : 'vg-dark'}`}
      data-theme={scheme}
    >
      <div className="soc-loader-inner soc-unmapped" role="status">
        <VigilMark className="soc-loader-mark soc-unmapped-mark" />
        <h1 className="soc-unreachable-title">No role mapped</h1>
        <p className="soc-unreachable-body">
          You’re signed in as {user?.username || 'a user'}, but your account has no
          permissions. A federated sign-in lands here when none of your directory groups
          maps to a Vigil role — ask an administrator to add the mapping under
          Settings → System → Roles, then sign in again.
        </p>
        <button type="button" className="btn primary" onClick={() => logout()}>
          <Icon name="logout" />
          Sign out
        </button>
      </div>
    </div>
  )
}
