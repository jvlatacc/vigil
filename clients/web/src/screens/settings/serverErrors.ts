/** The backend's `detail` as human text: a plain string, a FastAPI 422 array,
 * or an object. Sections used to grow a private copy of this each; new ones
 * share it here instead. */
export function errText(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d as { msg?: string })?.msg || JSON.stringify(d))
      .join(', ')
  }
  if (detail && typeof detail === 'object') {
    return (detail as { msg?: string }).msg || JSON.stringify(detail)
  }
  return (e as { message?: string })?.message || fallback
}
