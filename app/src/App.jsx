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
import { useState, useEffect, useContext, useMemo } from 'react'
import { Layout, Select, AutoComplete, Badge, Tooltip, Spin, Button, Segmented, Input } from 'antd'
import { ThemeContext } from './main'
import {
  ApiOutlined,
  GithubOutlined,
  FilterOutlined,
  SunOutlined,
  MoonOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  DragOutlined,
} from '@ant-design/icons'
import { api } from './api'
import UmapCanvas from './components/UmapCanvas'
import TcrDetail from './components/TcrDetail'
import SidebarPanels from './components/SidebarPanels'
import SynthesisExport from './components/SynthesisExport'
import { parse } from '@loaders.gl/core'
import { ArrowLoader } from '@loaders.gl/arrow'

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
  const [isRevealing, setIsRevealing] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [lassoMode, setLassoMode] = useState(false)
  const [lassoSelected, setLassoSelected] = useState([])

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

  useEffect(() => {
    if (lassoSelected.length > 0) setPanelOpen(true)
  }, [lassoSelected])

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

  // Load UMAP data via high-performance Apache Arrow IPC binary
  useEffect(() => {
    let active = true
    setLoading(true)
    setPoints([])

    const controller = new AbortController()

    api.umapArrow({ limit: 100000 }, controller.signal).then(async (table) => {
      if (!active) return

      // The parsed table might have a .data array or just be the array directly depending on loaders.gl shape
      const data = Array.isArray(table) ? table : (table.data || table)

      // If it's still an arrow Table class, we can convert it to row objects (or deck.gl could take it directly natively, 
      // but our UmapCanvas does a manual filter/map loop which expects a JS array)
      const rows = typeof data.toArray === 'function' ? data.toArray() : Array.from(data)

      if (rows.length > 0) {
        setPoints(rows)
      }
      setLoading(false)
    }).catch(err => {
      console.error("UMAP Arrow failed:", err)
      if (active) setLoading(false)
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [])

  const handleSelect = (point) => {
    setSelected(point)
  }

  // ── Search logic
  const searchOptions = useMemo(() => {
    const formatOption = (m) => {
      const cid = m.id ?? m.tcr_id
      return {
        value: cid,
        label: (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
            <span>
              {m.h && <span style={{ background: '#e74c3c', color: '#fff', fontSize: 9, padding: '1px 4px', borderRadius: 3, marginRight: 6 }}>HERO</span>}
              <strong>{cid}</strong> <span style={{ color: 'var(--text-dim)', fontSize: 11, marginLeft: 4 }}>{m.c ?? m.CDR3b}</span>
            </span>
            <span style={{ color: 'var(--color-primary)' }}>{m.e ?? m.known_epitope ?? (m.p?.ep ? `pred: ${m.p.ep}` : 'dark matter')}</span>
          </div>
        ),
        point: m
      }
    }

    if (!searchText) {
      // Show hero TCRs as default suggestions when search is empty
      const heroes = points.filter(d => d.h).slice(0, 10)
      if (heroes.length === 0) return []
      return [
        {
          label: <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)' }}>SUGGESTED DEMO TCRS</span>,
          options: heroes.map(formatOption)
        }
      ]
    }

    if (searchText.length < 2) return []

    const q = searchText.toLowerCase()
    const isHeroSearch = q.includes('hero') || q.includes('heroes') || q.includes('demo')

    const matches = []
    for (let i = 0; i < points.length && matches.length < 20; i++) {
      const d = points[i]
      const cat = d.a ?? d.antigen_category ?? ''
      const ep = d.e ?? d.known_epitope ?? ''
      const cid = d.id ?? d.tcr_id ?? ''
      const cdr3 = d.c ?? d.CDR3b ?? ''

      if (isHeroSearch) {
        if (d.h) matches.push(d)
      } else if (
        cid.toLowerCase().includes(q) ||
        cdr3.toLowerCase().includes(q) ||
        ep.toLowerCase().includes(q) ||
        cat.toLowerCase().includes(q)
      ) {
        matches.push(d)
      }
    }

    matches.sort((a, b) => (b.h ? 1 : 0) - (a.h ? 1 : 0))

    return matches.map(formatOption)
  }, [searchText, points])

  const onSelectSearch = (val, option) => {
    handleSelect(option.point)
    setSearchText('')
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
            fontSize: 11, fontWeight: 800, color: '#0d0f17', // keep logo text dark for contrast on teal
          }}>TCR</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)', lineHeight: 1.2 }}>
              TCR Agent
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.2 }}>
              AI assisted TCR mapping
            </div>
          </div>
        </div>

        {/* Point count */}
        <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          {loading
            ? <><Spin size="small" style={{ marginRight: 8 }} /> Loading {points.length.toLocaleString()} TCRs...</>
            : <>{points.length.toLocaleString()} TCRs</>
          }
        </div>

        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
          <AutoComplete
            options={searchOptions}
            value={searchText}
            onChange={setSearchText}
            onSelect={onSelectSearch}
            width={500}
            popupMatchSelectWidth={500}
            defaultActiveFirstOption={false}
          >
            <Input
              size="small"
              placeholder="Search TCR ID, CDR3, epitope, or 'hero'..."
              prefix={<SearchOutlined style={{ color: 'var(--text-dim)' }} />}
              variant="filled"
              allowClear
            />
          </AutoComplete>
        </div>

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

        {/* Play Reveal button (Commented out per request)
        <Button
          type="primary"
          size="small"
          icon={<PlayCircleOutlined />}
          onClick={() => setIsRevealing(true)}
          disabled={isRevealing || loading || points.length === 0}
          style={{ background: 'linear-gradient(135deg, #F59E0B, #E11D48)', border: 'none' }}
        >
          Batch Reveal
        </Button>
        */}

        <Tooltip title="Lasso Selection">
          <Button
            type={lassoMode ? 'primary' : 'text'}
            size="small"
            icon={<DragOutlined />}
            onClick={() => {
              setLassoMode(!lassoMode)
              if (lassoMode) setLassoSelected([]) // Clear selection when turning off
            }}
            style={lassoMode ? { background: 'var(--color-primary)' } : { color: 'var(--text-dim)' }}
          />
        </Tooltip>

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
          {/* Loading Overlay */}
          {loading && points.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--bg-base)', opacity: 0.8, zIndex: 5,
              flexDirection: 'column', gap: 12,
            }}>
              <Spin size="large" />
              <span style={{ color: 'var(--text-dim)', fontSize: 13 }}>
                Loading Apache Arrow binary to GPU...
              </span>
            </div>
          )}
          <UmapCanvas
            points={points}
            selectedId={selected?.id ?? selected?.tcr_id}
            filters={filters}
            onSelect={handleSelect}
            isDark={isDark}
            isRevealing={isRevealing}
            onRevealComplete={() => setIsRevealing(false)}
            lassoMode={lassoMode}
            onLassoSelect={setLassoSelected}
            lassoSelected={lassoSelected}
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

            {!displayPoint && lassoSelected.length > 0 && (
              <>
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
                    Lasso Selection
                  </span>
                  <Button type="text" size="small"
                    onClick={() => { setLassoSelected([]); setPanelOpen(false) }}
                    style={{ color: 'var(--text-dim)', fontSize: 18, lineHeight: 1, padding: '0 4px' }}>
                    ×
                  </Button>
                </div>
                <div style={{ padding: 16, flex: 1, overflowY: 'auto' }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text-main)' }}>
                    {lassoSelected.length} TCRs Selected
                  </div>
                  <SynthesisExport tcrIds={lassoSelected.map(t => t.id ?? t.tcr_id)} />
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
