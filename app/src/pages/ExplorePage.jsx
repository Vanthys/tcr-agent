/**
 * ExplorePage.jsx — Thin orchestrator for the main explore view.
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────────────┐
 *   │                   ExploreTopNav (header)                   │
 *   ├─────────┬──────────────────────────────────────────────────┤
 *   │         │              UmapCanvas                          │
 *   │App      │                                                  │
 *   │Sidebar  │         DetailPanel (overlay, right)             │
 *   │         │                                                  │
 *   │         │      CanvasFloatingBar (overlay, bottom)         │
 *   └─────────┴──────────────────────────────────────────────────┘
 */
import { useState, useEffect, useContext } from 'react'
import { Layout, Spin } from 'antd'
import { ThemeContext } from '../main'
import { useExploreData } from '../hooks/useExploreData.jsx'
import ExploreTopNav from '../components/ExploreTopNav'
import AppSidebar from '../components/AppSidebar'
import CanvasFloatingBar from '../components/CanvasFloatingBar'
import DetailPanel from '../components/DetailPanel'
import UmapCanvas from '../components/UmapCanvas'

const { Content } = Layout

export default function ExplorePage() {
  const { isDark, toggle } = useContext(ThemeContext)

  // ── Data & search ────────────────────────────────────────────────────────
  const {
    points, loading, backendOk, stats,
    searchText, setSearchText, searchOptions,
    triggerUmapRecompute, workerLoading,
  } = useExploreData()

  // ── UI state ─────────────────────────────────────────────────────────────
  const [selected, setSelected] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [displayPoint, setDisplayPoint] = useState(null)
  const [filters, setFilters] = useState({ source: '', category: '' })
  const [provider, setProvider] = useState('claude')
  const [lassoMode, setLassoMode] = useState(false)
  const [lassoSelected, setLassoSelected] = useState([])
  const [xDim, setXDim] = useState(1)
  const [yDim, setYDim] = useState(2)
  const [sliderVal, setSliderVal] = useState(1)

  // Open/close detail panel when selection changes
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

  const onSearchSelect = (_, option) => {
    setSelected(option.point)
    setSearchText('')
  }

  const handleLassoToggle = () => {
    setLassoMode(prev => !prev)
    if (lassoMode) setLassoSelected([])
  }

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <ExploreTopNav
        loading={loading}
        pointCount={points.length}
        backendOk={backendOk}
        workerLoading={workerLoading}
        isDark={isDark}
        onToggleTheme={toggle}
        filters={filters}
        onFiltersChange={setFilters}
        searchOptions={searchOptions}
        searchText={searchText}
        onSearchChange={setSearchText}
        onSearchSelect={onSearchSelect}
        onRecompute={triggerUmapRecompute}
      />

      <Layout style={{ flex: 1, overflow: 'hidden' }}>
        <AppSidebar stats={stats} provider={provider} onProviderChange={setProvider} />

        <Content style={{ position: 'relative', overflow: 'hidden', flex: 1 }}>
          {/* Loading overlay */}
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
            xDim={xDim}
            yDim={yDim}
            selectedId={selected?.id ?? selected?.tcr_id}
            filters={filters}
            onSelect={setSelected}
            isDark={isDark}
            lassoMode={lassoMode}
            onLassoSelect={setLassoSelected}
            lassoSelected={lassoSelected}
          />

          <DetailPanel
            open={panelOpen}
            displayPoint={displayPoint}
            lassoSelected={lassoSelected}
            provider={provider}
            onClose={() => setSelected(null)}
            onCloseLasso={() => { setLassoSelected([]); setPanelOpen(false) }}
          />

          <CanvasFloatingBar
            visible={!loading && points.length > 0}
            lassoMode={lassoMode}
            onLassoToggle={handleLassoToggle}
            sliderVal={sliderVal}
            onSliderChange={setSliderVal}
            onDimsChange={v => { setXDim(v); setYDim(v + 1) }}
            panelOpen={panelOpen}
          />
        </Content>
      </Layout>
    </Layout>
  )
}
