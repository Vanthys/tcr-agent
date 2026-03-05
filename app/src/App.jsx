/**
 * App.jsx — Main layout shell.
 *
 * Layout:
 *   ┌────────┬───────────────────────────────┬──────────────┐
 *   │ Sider  │       UMAP Canvas             │  TCR Detail  │
 *   │ 220px  │       (fills remaining)       │  320px       │
 *   │ stats  │                               │  (if selected)│
 *   └────────┴───────────────────────────────┴──────────────┘
 *
 * Filters live in the top bar over the canvas.
 */
import { useState, useEffect, useContext } from 'react'
import { Layout, Select, Badge, Tooltip, Spin, Button, Segmented } from 'antd'
import { ThemeContext } from './main'
import {
  ApiOutlined,
  GithubOutlined,
  FilterOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons'
import { api } from './api'
import UmapCanvas from './components/UmapCanvas'
import TcrDetail from './components/TcrDetail'
import SidebarPanels from './components/SidebarPanels'

const { Header, Sider, Content } = Layout

const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'TCRAFT', label: 'TCRAFT (vitiligo)' },
  { value: 'PDAC', label: 'PDAC (tumor)' },
  { value: 'AD_CSF', label: "AD CSF (Alzheimer's)" },
  { value: 'VDJdb', label: 'VDJdb' },
  { value: 'McPAS', label: 'McPAS' },
]

const CAT_OPTIONS = [
  { value: '', label: 'All categories' },
  { value: 'viral', label: 'Viral' },
  { value: 'melanocyte', label: 'Melanocyte' },
  { value: 'cancer_associated', label: 'Cancer' },
  { value: 'autoimmune', label: 'Autoimmune' },
  { value: 'unknown', label: 'Dark matter only' },
]

export default function App() {
  const { isDark, toggle } = useContext(ThemeContext)
  const [points, setPoints] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [backendOk, setBackendOk] = useState(null)
  const [filters, setFilters] = useState({ source: '', category: '' })
  const [provider, setProvider] = useState('claude')
  const [stats, setStats] = useState(null)

  // UI state for animated detail panel
  const [panelOpen, setPanelOpen] = useState(false)
  const [displayPoint, setDisplayPoint] = useState(null)

  useEffect(() => {
    if (selected) {
      setDisplayPoint(selected)
      setPanelOpen(true)
    } else {
      setPanelOpen(false)
    }
  }, [selected])

  // Fetch summary stats
  useEffect(() => {
    if (backendOk) {
      api.statsSummary().then(setStats).catch(() => { })
    }
  }, [backendOk, points])

  // Health check
  useEffect(() => {
    api.health()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false))
  }, [])

  // Load UMAP data — try backend first, fall back to local JSON
  useEffect(() => {
    setLoading(true)

    // Abort after 8s so we don't hang on an unresponsive backend
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8000)

    api.umap({ limit: 100000 }, controller.signal)
      .then(data => { setPoints(data); setLoading(false) })
      .catch(() => {
        // Fallback: static umap_data.json in app/public/
        return fetch('/umap_data.json')
          .then(r => { if (!r.ok) throw new Error('no static file'); return r.json() })
          .then(data => setPoints(data))
          .catch(() => {
            // Both failed — just show empty canvas with backend-offline hint
            setPoints([])
          })
          .finally(() => setLoading(false))
      })
      .finally(() => clearTimeout(timeout))
  }, [])

  const handleSelect = (point) => {
    setSelected(point)
  }

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <Header style={{
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
        padding: '0 20px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        gap: 20,
        flexShrink: 0,
        zIndex: 10,
      }}>
        {/* Logo / title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'linear-gradient(135deg, #4ecdc4, #a29bfe)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 800, color: '#0d0f17', // keep logo text dark for contrast on teal
          }}>T</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)', lineHeight: 1.2 }}>
              TCR Agent
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.2 }}>
              Dark Matter Explorer
            </div>
          </div>
        </div>

        {/* Point count */}
        <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          {loading
            ? <Spin size="small" />
            : <>{points.length.toLocaleString()} TCRs</>
          }
        </div>

        <div style={{ flex: 1 }} />

        {/* Filters */}
        <FilterOutlined style={{ color: 'var(--text-dim)', fontSize: 13 }} />
        <Select
          value={filters.source}
          onChange={v => setFilters(f => ({ ...f, source: v }))}
          options={SOURCE_OPTIONS}
          size="small"
          style={{ width: 160 }}
          variant="filled"
          popupMatchSelectWidth={false}
        />
        <Select
          value={filters.category}
          onChange={v => setFilters(f => ({ ...f, category: v }))}
          options={CAT_OPTIONS}
          size="small"
          style={{ width: 160 }}
          variant="filled"
          popupMatchSelectWidth={false}
        />

        <Button
          type="text"
          size="small"
          icon={isDark ? <SunOutlined /> : <MoonOutlined />}
          onClick={toggle}
          style={{
            color: 'var(--text-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        />

        {/* Backend status */}
        <Tooltip title={backendOk == null ? 'Checking backend…' : backendOk ? 'Backend connected' : 'Backend offline — running in static mode'}>
          <Badge
            status={backendOk == null ? 'processing' : backendOk ? 'success' : 'warning'}
            text={
              <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 8 }}>
                <ApiOutlined /> {backendOk ? 'live' : backendOk === false ? 'static' : '…'}
              </span>
            }
          />
        </Tooltip>
      </Header>

      <Layout style={{ flex: 1, overflow: 'hidden' }}>
        {/* ── Left sider ──────────────────────────────────────────────────── */}
        <Sider
          width={220}
          style={{
            background: 'var(--bg-surface)',
            borderRight: '1px solid var(--border)',
            overflow: 'hidden',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
          breakpoint="lg"
          collapsedWidth={0}
        >
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            <SidebarPanels stats={stats} />
          </div>

          {/* AI Provider selector at bottom */}
          <div style={{
            padding: '12px 14px',
            borderTop: '1px solid var(--border)',
            background: 'var(--bg-surface)',
          }}>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Agent Model
            </div>
            <Select
              value={provider}
              onChange={setProvider}
              options={[
                { label: 'Claude 3.5 Sonnet', value: 'claude' },
                { label: 'Gemini 2.5 Flash', value: 'gemini' },
              ]}
              size="small"
              style={{ width: '100%' }}
              variant="filled"
              popupMatchSelectWidth={false}
            />
          </div>
        </Sider>

        {/* ── Canvas area ─────────────────────────────────────────────────── */}
        <Content style={{ position: 'relative', overflow: 'hidden', flex: 1 }}>
          {loading && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--bg-base)', opacity: 0.8, zIndex: 5,
              flexDirection: 'column', gap: 12,
            }}>
              <Spin size="large" />
              <span style={{ color: 'var(--text-dim)', fontSize: 13 }}>
                Loading {(88962).toLocaleString()} TCRs…
              </span>
            </div>
          )}
          <UmapCanvas
            points={points}
            selectedId={selected?.id ?? selected?.tcr_id}
            filters={filters}
            onSelect={handleSelect}
            isDark={isDark}
          />

          {/* ── Right detail panel (Floating / Animated) ────────────────────── */}
          <div
            className="detail-panel-overlay"
            style={{
              position: 'absolute',
              top: 0, right: 0,
              width: 340, height: '100%',
              background: 'var(--bg-surface)',
              borderLeft: '1px solid var(--border)',
              zIndex: 100,
              display: 'flex',
              flexDirection: 'column',
              transform: `translateX(${panelOpen ? '0' : '100%'})`,
            }}
          >
            {displayPoint && (
              <>
                {/* Panel header */}
                <div style={{
                  padding: '10px 14px',
                  borderBottom: '1px solid var(--border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  background: 'var(--bg-base)',
                  flexShrink: 0,
                }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    TCR Detail
                  </span>
                  <Button type="text" size="small"
                    onClick={() => setSelected(null)}
                    style={{ color: 'var(--text-dim)', fontSize: 18, lineHeight: 1, padding: '0 4px' }}>
                    ×
                  </Button>
                </div>

                <div style={{ flex: 1, overflowY: 'auto' }}>
                  <TcrDetail point={displayPoint} provider={provider} onClose={() => setSelected(null)} />
                </div>
              </>
            )}
          </div>

          {/* Click-to-select hint */}
          {!loading && !selected && !panelOpen && points.length > 0 && (
            <div style={{
              position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
              background: 'rgba(13,15,23,0.85)', backdropFilter: 'blur(8px)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 20, padding: '6px 16px',
              fontSize: 12, color: 'rgba(255,255,255,0.45)',
              pointerEvents: 'none',
            }}>
              Click any point to select a TCR · Scroll to zoom · Drag to pan
            </div>
          )}
        </Content>

        {/* Detail panel logic moved into Content area as an overlay */}
      </Layout>
    </Layout>
  )
}
