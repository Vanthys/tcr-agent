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
import { useState, useEffect, useContext, useMemo, useCallback } from 'react'
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
    ingestedPoints, clearIngestedPoints,
  } = useExploreData()

  // ── UI state ─────────────────────────────────────────────────────────────
  const [selected, setSelected] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [displayPoint, setDisplayPoint] = useState(null)
  const [filters, setFilters] = useState({ source: '', category: '' })
  const [hiddenCategories, setHiddenCategories] = useState(new Set())
  const [provider, setProvider] = useState('claude')
  const [lassoMode, setLassoMode] = useState(false)
  const [lassoSelected, setLassoSelected] = useState([])
  const [xDim, setXDim] = useState(1)
  const [yDim, setYDim] = useState(2)
  const [sliderVal, setSliderVal] = useState(1)

  // Compute per-category counts from loaded points
  const categoryCounts = useMemo(() => {
    const counts = {}
    if (!points) return counts
    for (const p of points) {
      const cat = p.a ?? p.antigen_category ?? 'unknown'
      counts[cat] = (counts[cat] || 0) + 1
    }
    return counts
  }, [points])

  const handleToggleCategory = useCallback((key, solo) => {
    setHiddenCategories(prev => {
      const ALL_CATS = ['viral', 'melanocyte', 'cancer_associated', 'autoimmune', 'bacterial', 'neurodegeneration', 'reactive_unclassified', 'other', 'unknown']
      const next = new Set(prev)
      if (solo) {
        // Solo mode: show only this category (hide all others)
        const allHiddenExceptThis = ALL_CATS.filter(c => c !== key)
        // If already in solo mode for this key, reset to show all
        if (prev.size === allHiddenExceptThis.length && allHiddenExceptThis.every(c => prev.has(c))) {
          return new Set()
        }
        return new Set(allHiddenExceptThis)
      }
      // Toggle mode
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
    // Clear any single-category dropdown filter since legend now controls it
    setFilters(f => ({ ...f, category: '' }))
  }, [])

  // Open/close detail panel when selection changes
  const lassoCount = lassoSelected.length

  useEffect(() => {
    if (selected) {
      setDisplayPoint(selected)
      setPanelOpen(true)
      return
    }
    setDisplayPoint(null)
    setPanelOpen(lassoCount > 0)
  }, [selected, lassoCount])

  const onSearchSelect = (_, option) => {
    setSelected(option.point)
    setSearchText('')
  }

  const handleLassoToggle = () => {
    setLassoMode(prev => !prev)
    if (lassoMode) setLassoSelected([])
  }

  const handleLassoResult = useCallback((pointsFromLasso = []) => {
    const additions = Array.isArray(pointsFromLasso) ? pointsFromLasso : []
    if (additions.length === 0) {
      setLassoSelected([])
      return
    }

    const uniqueMap = new Map()
    for (const entry of additions) {
      if (!entry) continue
      const identifier = entry.id ?? entry.tcr_id
      if (!identifier || uniqueMap.has(identifier)) continue
      uniqueMap.set(identifier, entry)
    }

    setLassoSelected(Array.from(uniqueMap.values()))
  }, [])

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
        <AppSidebar
          stats={stats}
          provider={provider}
          onProviderChange={setProvider}
          categoryCounts={categoryCounts}
          hiddenCategories={hiddenCategories}
          onToggleCategory={handleToggleCategory}
          onResetCategories={() => setHiddenCategories(new Set())}
          ingestedPoints={ingestedPoints}
          onClearIngested={clearIngestedPoints}
        />

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
            ingestedPoints={ingestedPoints}
            xDim={xDim}
            yDim={yDim}
            selectedId={selected?.id ?? selected?.tcr_id}
            filters={filters}
            hiddenCategories={hiddenCategories}
            onSelect={setSelected}
            isDark={isDark}
            lassoMode={lassoMode}
            onLassoSelect={handleLassoResult}
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
