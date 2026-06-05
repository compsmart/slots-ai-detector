export type Summary = {
  total_games: number
  detected_games: number
  ai_count: number
  ai_share: number
  avg_confidence: number
  provider_count: number
}

export type ProviderRow = {
  provider_slug: string
  provider_name: string
  total_games: number
  ai_games: number
  ai_share: number
  avg_confidence: number
}

export type GameRow = {
  id: number
  title: string
  provider_slug: string
  provider_name: string
  cover_url: string
  library_image: string | null
  top_label: string | null
  top_score: number | null
}

export type Bucket = {
  bucket: string
  count: number
}
