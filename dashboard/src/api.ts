import type { GameResult, ImageResult, Outcome, ProviderResult, ResultsSummary } from './types'

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function appendCommon(params: URLSearchParams, search: string, status: StatusFilter) {
  if (search.trim()) params.set('search', search.trim())
  if (status !== 'all') params.set('ai_status', status)
}

export type StatusFilter = 'all' | 'ai' | 'not_ai' | 'pending'

export const api = {
  summary: () => fetchJson<ResultsSummary>('/api/results/summary'),
  providers: (search: string, status: StatusFilter) => {
    const params = new URLSearchParams()
    appendCommon(params, search, status)
    return fetchJson<ProviderResult[]>(`/api/results/providers?${params.toString()}`)
  },
  games: (provider: string, search: string, status: StatusFilter) => {
    const params = new URLSearchParams()
    appendCommon(params, search, status)
    if (provider) params.set('provider', provider)
    return fetchJson<GameResult[]>(`/api/results/games?${params.toString()}`)
  },
  images: (provider: string, gameId: number | null, search: string, status: StatusFilter) => {
    const params = new URLSearchParams()
    appendCommon(params, search, status)
    if (provider) params.set('provider', provider)
    if (gameId !== null) params.set('game_id', String(gameId))
    return fetchJson<ImageResult[]>(`/api/results/images?${params.toString()}`)
  },
}

export function isAiOutcome(status: Outcome): boolean {
  return status === 'ai_detected'
}
