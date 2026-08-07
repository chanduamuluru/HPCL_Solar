const DEFAULT_BASE = import.meta.env.VITE_API_BASE || ''

function resolveBase() {
  const params = new URLSearchParams(window.location.search)
  const fromQuery = params.get('api')
  const fromStore = localStorage.getItem('HPCL_Solar_api_base')
  if (fromQuery) {
    const b = fromQuery.replace(/\/$/, '')
    localStorage.setItem('HPCL_Solar_api_base', b)
    return b
  }
  if (fromStore) return fromStore.replace(/\/$/, '')
  return DEFAULT_BASE.replace(/\/$/, '')
}

export const API_BASE = resolveBase()

export async function fetchJson(path) {
  const full = path.startsWith('http') ? path : `${API_BASE}${path}`
  const res = await fetch(full)
  if (!res.ok) throw new Error(`${full} → ${res.status}`)
  return res.json()
}
