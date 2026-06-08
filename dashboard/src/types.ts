export type Outcome = 'ai_detected' | 'not_ai' | 'pending'

export type ResultsSummary = {
  total_games: number
  provider_count: number
  asset_count: number
  detected_assets: number
  detected_games: number
  ai_games: number
  ai_share: number
  asset_coverage: number
}

export type ProviderResult = {
  provider_slug: string
  provider_name: string
  total_games: number
  detected_games: number
  ai_games: number
  ai_share: number
  asset_count: number
  detected_assets: number
  max_confidence: number | null
  status: Outcome
}

export type GameResult = {
  id: number
  title: string
  provider_slug: string
  provider_name: string
  asset_count: number
  detected_assets: number
  ai_images: number
  max_confidence: number | null
  status: Outcome
}

export type ImageResult = {
  id: number
  game_id: number
  title: string
  provider_slug: string
  provider_name: string
  asset_kind: string
  source_host: string | null
  image_url: string | null
  top_label: string | null
  top_score: number | null
  status: Outcome
}
