import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, type StatusFilter } from './api'
import type { GameResult, ImageResult, Outcome, ProviderResult, ResultsSummary } from './types'

type Tab = 'providers' | 'games' | 'images'

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function confidence(value: number | null): string {
  return value === null ? 'pending' : percent(value)
}

function statusLabel(status: Outcome): string {
  if (status === 'ai_detected') return 'AI detected'
  if (status === 'not_ai') return 'No AI detected'
  return 'Pending'
}

function StatusBadge({ status }: { status: Outcome }) {
  return <span className={`badge ${status}`}>{statusLabel(status)}</span>
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty">{message}</div>
}

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('providers')
  const [summary, setSummary] = useState<ResultsSummary | null>(null)
  const [providers, setProviders] = useState<ProviderResult[]>([])
  const [allProviders, setAllProviders] = useState<ProviderResult[]>([])
  const [games, setGames] = useState<GameResult[]>([])
  const [images, setImages] = useState<ImageResult[]>([])

  const [providerSearch, setProviderSearch] = useState('')
  const [gameSearch, setGameSearch] = useState('')
  const [imageSearch, setImageSearch] = useState('')
  const [providerStatus, setProviderStatus] = useState<StatusFilter>('all')
  const [gameStatus, setGameStatus] = useState<StatusFilter>('all')
  const [imageStatus, setImageStatus] = useState<StatusFilter>('all')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const rows = await api.summary()
        const providerRows = await api.providers('', 'all')
        if (!cancelled) {
          setSummary(rows)
          setAllProviders(providerRows)
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadProviders() {
      try {
        setLoading(true)
        const rows = await api.providers(providerSearch, providerStatus)
        if (!cancelled) setProviders(rows)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadProviders()
    return () => {
      cancelled = true
    }
  }, [providerSearch, providerStatus])

  useEffect(() => {
    let cancelled = false
    async function loadGames() {
      try {
        const rows = await api.games(selectedProvider, gameSearch, gameStatus)
        if (!cancelled) setGames(rows)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    loadGames()
    return () => {
      cancelled = true
    }
  }, [selectedProvider, gameSearch, gameStatus])

  useEffect(() => {
    let cancelled = false
    async function loadImages() {
      try {
        const rows = await api.images(selectedProvider, selectedGameId, imageSearch, imageStatus)
        if (!cancelled) setImages(rows)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    loadImages()
    return () => {
      cancelled = true
    }
  }, [selectedProvider, selectedGameId, imageSearch, imageStatus])

  const chartProviders = useMemo(
    () => providers.filter((p) => p.detected_games > 0).slice(0, 12),
    [providers],
  )
  const providerOptions = useMemo(() => allProviders.slice().sort((a, b) => a.provider_name.localeCompare(b.provider_name)), [allProviders])
  const gameOptions = useMemo(() => games.slice().sort((a, b) => a.title.localeCompare(b.title)), [games])
  const selectedProviderName = providerOptions.find((p) => p.provider_slug === selectedProvider)?.provider_name
  const selectedGameTitle = gameOptions.find((g) => g.id === selectedGameId)?.title

  function openProvider(provider: ProviderResult) {
    setSelectedProvider(provider.provider_slug)
    setSelectedGameId(null)
    setActiveTab('games')
  }

  function openGame(game: GameResult) {
    setSelectedProvider(game.provider_slug)
    setSelectedGameId(game.id)
    setActiveTab('images')
  }

  if (error) {
    return <div className="status error">Error: {error}</div>
  }

  return (
    <div className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Asset-only AI detection</p>
          <h1>Slot AI Results Explorer</h1>
          <p>
            Browse providers, games, and captured in-game images. Sprite sheets and cover photos
            are excluded from the AI usage metrics.
          </p>
        </div>
        <div className="rule-card">
          <span>AI rule</span>
          <strong>{'artificial >= 80%'}</strong>
        </div>
      </header>

      <section className="metrics-grid">
        <Metric label="Providers" value={summary?.provider_count ?? 0} />
        <Metric label="Games" value={summary?.total_games ?? 0} />
        <Metric label="Detected Games" value={summary?.detected_games ?? 0} />
        <Metric label="AI Games" value={summary?.ai_games ?? 0} tone="hot" />
        <Metric label="AI Share" value={percent(summary?.ai_share ?? 0)} tone="hot" />
        <Metric label="Asset Coverage" value={percent(summary?.asset_coverage ?? 0)} />
      </section>

      <section className="chart-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Provider AI Share</h2>
            <span>Detected games denominator</span>
          </div>
          {chartProviders.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartProviders} margin={{ top: 8, right: 24, left: 0, bottom: 70 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis
                  dataKey="provider_slug"
                  stroke="#f3dfb3"
                  angle={-45}
                  textAnchor="end"
                  interval={0}
                  height={100}
                />
                <YAxis stroke="#f3dfb3" tickFormatter={(value) => percent(Number(value))} />
                <Tooltip formatter={(value) => percent(Number(value))} />
                <Bar dataKey="ai_share" fill="#fb7185" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState message="No detected in-game assets yet. Run detect-assets after capture." />
          )}
        </article>

        <article className="panel focus-panel">
          <div className="panel-head">
            <h2>Current Filter</h2>
            <span>Click rows to drill down</span>
          </div>
          <dl className="filter-summary">
            <div>
              <dt>Provider</dt>
              <dd>{selectedProviderName ?? 'All providers'}</dd>
            </div>
            <div>
              <dt>Game</dt>
              <dd>{selectedGameTitle ?? 'All games'}</dd>
            </div>
            <div>
              <dt>Image rows</dt>
              <dd>{images.length}</dd>
            </div>
          </dl>
          <button
            className="ghost-button"
            onClick={() => {
              setSelectedProvider('')
              setSelectedGameId(null)
            }}
          >
            Clear drilldown
          </button>
        </article>
      </section>

      <nav className="tabs" aria-label="Result sections">
        <TabButton active={activeTab === 'providers'} onClick={() => setActiveTab('providers')}>
          Providers
        </TabButton>
        <TabButton active={activeTab === 'games'} onClick={() => setActiveTab('games')}>
          Games
        </TabButton>
        <TabButton active={activeTab === 'images'} onClick={() => setActiveTab('images')}>
          Images
        </TabButton>
      </nav>

      {loading && activeTab === 'providers' ? <div className="status-inline">Loading providers...</div> : null}
      {activeTab === 'providers' ? (
        <ProvidersTab
          providers={providers}
          search={providerSearch}
          status={providerStatus}
          setSearch={setProviderSearch}
          setStatus={setProviderStatus}
          onOpen={openProvider}
        />
      ) : null}
      {activeTab === 'games' ? (
        <GamesTab
          games={games}
          providers={providerOptions}
          provider={selectedProvider}
          search={gameSearch}
          status={gameStatus}
          setProvider={(value) => {
            setSelectedProvider(value)
            setSelectedGameId(null)
          }}
          setSearch={setGameSearch}
          setStatus={setGameStatus}
          onOpen={openGame}
        />
      ) : null}
      {activeTab === 'images' ? (
        <ImagesTab
          images={images}
          providers={providerOptions}
          games={gameOptions}
          provider={selectedProvider}
          gameId={selectedGameId}
          search={imageSearch}
          status={imageStatus}
          setProvider={(value) => {
            setSelectedProvider(value)
            setSelectedGameId(null)
          }}
          setGameId={setSelectedGameId}
          setSearch={setImageSearch}
          setStatus={setImageStatus}
        />
      ) : null}
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: 'hot' }) {
  return (
    <div className={`metric-card ${tone ?? ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function TabButton({ active, children, onClick }: { active: boolean; children: string; onClick: () => void }) {
  return (
    <button className={active ? 'active' : ''} onClick={onClick}>
      {children}
    </button>
  )
}

function StatusSelect({ value, onChange }: { value: StatusFilter; onChange: (value: StatusFilter) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value as StatusFilter)}>
      <option value="all">All outcomes</option>
      <option value="ai">AI detected</option>
      <option value="not_ai">No AI detected</option>
      <option value="pending">Pending</option>
    </select>
  )
}

function ProvidersTab({
  providers,
  search,
  status,
  setSearch,
  setStatus,
  onOpen,
}: {
  providers: ProviderResult[]
  search: string
  status: StatusFilter
  setSearch: (value: string) => void
  setStatus: (value: StatusFilter) => void
  onOpen: (provider: ProviderResult) => void
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Providers</h2>
        <span>{providers.length} rows</span>
      </div>
      <div className="filters">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search providers..." />
        <StatusSelect value={status} onChange={setStatus} />
      </div>
      {providers.length ? (
        <div className="cards-list provider-list">
          {providers.map((provider) => (
            <button key={provider.provider_slug} className="result-card" onClick={() => onOpen(provider)}>
              <div className="result-main">
                <h3>{provider.provider_name}</h3>
                <span>{provider.provider_slug}</span>
              </div>
              <StatusBadge status={provider.status} />
              <Stat label="Games" value={provider.total_games} />
              <Stat label="Detected" value={provider.detected_games} />
              <Stat label="AI Games" value={provider.ai_games} />
              <Stat label="AI Share" value={percent(provider.ai_share)} />
              <Stat label="Confidence" value={confidence(provider.max_confidence)} />
            </button>
          ))}
        </div>
      ) : (
        <EmptyState message="No providers match the current filters." />
      )}
    </section>
  )
}

function GamesTab({
  games,
  providers,
  provider,
  search,
  status,
  setProvider,
  setSearch,
  setStatus,
  onOpen,
}: {
  games: GameResult[]
  providers: ProviderResult[]
  provider: string
  search: string
  status: StatusFilter
  setProvider: (value: string) => void
  setSearch: (value: string) => void
  setStatus: (value: StatusFilter) => void
  onOpen: (game: GameResult) => void
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Games</h2>
        <span>{games.length} rows</span>
      </div>
      <div className="filters">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="">All providers</option>
          {providers.map((row) => (
            <option key={row.provider_slug} value={row.provider_slug}>
              {row.provider_name}
            </option>
          ))}
        </select>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search games..." />
        <StatusSelect value={status} onChange={setStatus} />
      </div>
      {games.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Game</th>
                <th>Provider</th>
                <th>Outcome</th>
                <th>Assets</th>
                <th>Detected Assets</th>
                <th>AI Images</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {games.map((game) => (
                <tr key={game.id} onClick={() => onOpen(game)}>
                  <td>{game.title}</td>
                  <td>{game.provider_name}</td>
                  <td>
                    <StatusBadge status={game.status} />
                  </td>
                  <td>{game.asset_count}</td>
                  <td>{game.detected_assets}</td>
                  <td>{game.ai_images}</td>
                  <td>{confidence(game.max_confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message="No games match the current filters." />
      )}
    </section>
  )
}

function ImagesTab({
  images,
  providers,
  games,
  provider,
  gameId,
  search,
  status,
  setProvider,
  setGameId,
  setSearch,
  setStatus,
}: {
  images: ImageResult[]
  providers: ProviderResult[]
  games: GameResult[]
  provider: string
  gameId: number | null
  search: string
  status: StatusFilter
  setProvider: (value: string) => void
  setGameId: (value: number | null) => void
  setSearch: (value: string) => void
  setStatus: (value: StatusFilter) => void
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Images</h2>
        <span>{images.length} rows</span>
      </div>
      <div className="filters">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="">All providers</option>
          {providers.map((row) => (
            <option key={row.provider_slug} value={row.provider_slug}>
              {row.provider_name}
            </option>
          ))}
        </select>
        <select value={gameId ?? ''} onChange={(e) => setGameId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">All games</option>
          {games.map((game) => (
            <option key={game.id} value={game.id}>
              {game.title}
            </option>
          ))}
        </select>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search images..." />
        <StatusSelect value={status} onChange={setStatus} />
      </div>
      {images.length ? (
        <div className="image-grid">
          {images.map((image) => (
            <article key={image.id} className="image-card">
              {image.image_url ? (
                <img src={image.image_url} alt={`${image.title} asset ${image.id}`} />
              ) : (
                <div className="missing-image">No preview</div>
              )}
              <div className="image-meta">
                <StatusBadge status={image.status} />
                <h3>{image.title}</h3>
                <p>{image.provider_name}</p>
                <dl>
                  <div>
                    <dt>Confidence</dt>
                    <dd>{confidence(image.top_score)}</dd>
                  </div>
                  <div>
                    <dt>Outcome</dt>
                    <dd>{image.top_label ?? 'pending'}</dd>
                  </div>
                  <div>
                    <dt>Kind</dt>
                    <dd>{image.asset_kind}</dd>
                  </div>
                </dl>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState message="No in-game images match the current filters. Covers and sprite sheets are intentionally excluded." />
      )}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="mini-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
