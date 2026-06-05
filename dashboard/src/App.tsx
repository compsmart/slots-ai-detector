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
import { api } from './api'
import type { Bucket, GameRow, ProviderRow, Summary } from './types'

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [providers, setProviders] = useState<ProviderRow[]>([])
  const [games, setGames] = useState<GameRow[]>([])
  const [distribution, setDistribution] = useState<Bucket[]>([])
  const [providerFilter, setProviderFilter] = useState('')
  const [aiOnly, setAiOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadStatic() {
      try {
        setLoading(true)
        const [s, p, d] = await Promise.all([
          api.summary(),
          api.providers(),
          api.distribution(),
        ])
        if (cancelled) return
        setSummary(s)
        setProviders(p)
        setDistribution(d)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadStatic()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadGames() {
      try {
        const rows = await api.games(providerFilter, aiOnly)
        if (!cancelled) setGames(rows)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    loadGames()
    return () => {
      cancelled = true
    }
  }, [providerFilter, aiOnly])

  const topProviders = useMemo(() => providers.slice(0, 12), [providers])

  if (loading) {
    return <div className="status">Loading dashboard...</div>
  }

  if (error) {
    return <div className="status error">Error: {error}</div>
  }

  return (
    <div className="shell">
      <header className="hero">
        <h1>Slot AI Asset Analyzer</h1>
        <p>
          Tracks AI-image detector results across slot providers, ordered from newest
          releases backward.
        </p>
      </header>

      <section className="metrics-grid">
        <div className="metric-card">
          <span>Total Games</span>
          <strong>{summary?.total_games ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Detected Covers</span>
          <strong>{summary?.detected_games ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>Likely AI Covers</span>
          <strong>{summary?.ai_count ?? 0}</strong>
        </div>
        <div className="metric-card">
          <span>AI Share</span>
          <strong>{percent(summary?.ai_share ?? 0)}</strong>
        </div>
        <div className="metric-card">
          <span>Average Confidence</span>
          <strong>{percent(summary?.avg_confidence ?? 0)}</strong>
        </div>
        <div className="metric-card">
          <span>Providers</span>
          <strong>{summary?.provider_count ?? 0}</strong>
        </div>
      </section>

      <section className="chart-grid">
        <article className="panel">
          <h2>Provider AI Usage</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={topProviders} margin={{ top: 8, right: 24, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis
                dataKey="provider_slug"
                stroke="#f3dfb3"
                angle={-45}
                textAnchor="end"
                interval={0}
                height={90}
              />
              <YAxis stroke="#f3dfb3" />
              <Tooltip />
              <Bar dataKey="ai_games" fill="#fb7185" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>

        <article className="panel">
          <h2>Confidence Distribution</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={distribution} margin={{ top: 8, right: 12, left: 0, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="bucket" stroke="#f3dfb3" />
              <YAxis stroke="#f3dfb3" />
              <Tooltip />
              <Bar dataKey="count" fill="#38bdf8" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>
      </section>

      <section className="panel">
        <h2>Games</h2>
        <div className="filters">
          <label>
            Provider
            <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)}>
              <option value="">All providers</option>
              {providers.map((p) => (
                <option key={p.provider_slug} value={p.provider_slug}>
                  {p.provider_name}
                </option>
              ))}
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={aiOnly}
              onChange={(e) => setAiOnly(e.target.checked)}
            />
            AI-labeled only
          </label>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cover</th>
                <th>Game</th>
                <th>Provider</th>
                <th>Top Label</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr key={g.id}>
                  <td>
                    {g.library_image || g.cover_url ? (
                      <img src={g.library_image ?? g.cover_url} alt={g.title} className="cover" />
                    ) : (
                      <span className="muted">N/A</span>
                    )}
                  </td>
                  <td>{g.title}</td>
                  <td>{g.provider_name}</td>
                  <td>{g.top_label ?? 'pending'}</td>
                  <td>{g.top_score !== null ? percent(g.top_score) : 'pending'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
