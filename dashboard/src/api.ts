import type { Bucket, GameRow, ProviderRow, Summary } from './types'

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  summary: () => fetchJson<Summary>('/api/summary'),
  providers: () => fetchJson<ProviderRow[]>('/api/providers'),
  games: (provider: string, aiOnly: boolean) => {
    const params = new URLSearchParams({ limit: '250' })
    if (provider) params.set('provider', provider)
    if (aiOnly) params.set('ai_only', 'true')
    return fetchJson<GameRow[]>(`/api/games?${params.toString()}`)
  },
  distribution: () => fetchJson<Bucket[]>('/api/confidence-distribution'),
}
