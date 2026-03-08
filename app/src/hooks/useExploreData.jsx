/**
 * useExploreData — Data fetching, search, and backend concerns for the Explore page.
 *
 * Separates all async / computation logic from the UI layout so that
 * ExplorePage.jsx can remain a thin orchestrator.
 */
import { useState, useEffect, useMemo } from 'react'
import { message } from 'antd'
import { api } from '../api'

export function useExploreData() {
    const [points, setPoints] = useState([])
    const [loading, setLoading] = useState(true)
    const [backendOk, setBackendOk] = useState(null)
    const [stats, setStats] = useState(null)
    const [searchText, setSearchText] = useState('')
    const [workerLoading, setWorkerLoading] = useState(false)
    const [ingestedPoints, setIngestedPoints] = useState([])

    // ── Health check ────────────────────────────────────────────────────────────
    useEffect(() => {
        api.health()
            .then(() => setBackendOk(true))
            .catch(() => setBackendOk(false))
    }, [])

    // ── Fetch summary stats ──────────────────────────────────────────────────────
    useEffect(() => {
        if (backendOk) {
            api.statsSummary().then(setStats).catch(() => { })
        }
    }, [backendOk, points])

    // ── Load UMAP data via Apache Arrow IPC binary ──────────────────────────────
    useEffect(() => {
        let active = true
        setLoading(true)
        setPoints([])

        const controller = new AbortController()

        api.umapArrow({ limit: 100000 }, controller.signal).then(async (table) => {
            if (!active) return
            const data = Array.isArray(table) ? table : (table.data || table)
            const rows = typeof data.toArray === 'function' ? data.toArray() : Array.from(data)
            if (rows.length > 0) setPoints(rows)
            setLoading(false)
        }).catch(err => {
            console.error('UMAP Arrow failed:', err)
            if (active) setLoading(false)
        })

        return () => {
            active = false
            controller.abort()
        }
    }, [])

    // ── Poll for ephemeral ingested points (pipeline may still be running) ──────
    useEffect(() => {
        if (!backendOk) return
        const fetch = () =>
            api.ingestedPoints()
                .then(pts => setIngestedPoints(pts ?? []))
                .catch(() => {})
        fetch()
        const id = setInterval(fetch, 3000)
        return () => clearInterval(id)
    }, [backendOk])

    // ── Search / autocomplete options ────────────────────────────────────────────
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
                        <span style={{ color: 'var(--color-primary)' }}>
                            {m.e ?? m.known_epitope ?? (m.p?.ep ? `pred: ${m.p.ep}` : 'dark matter')}
                        </span>
                    </div>
                ),
                point: m,
            }
        }

        if (!searchText) {
            const heroes = points.filter(d => d.h).slice(0, 10)
            if (heroes.length === 0) return []
            return [{
                label: <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)' }}>SUGGESTED DEMO TCRS</span>,
                options: heroes.map(formatOption),
            }]
        }

        if (searchText.length < 2) return []

        const q = searchText.toLowerCase()
        const isHeroSearch = q.includes('hero') || q.includes('heroes') || q.includes('demo')

        const matches = []
        for (let i = 0; i < points.length && matches.length < 20; i++) {
            const d = points[i]
            if (isHeroSearch) {
                if (d.h) matches.push(d)
            } else {
                const cid = d.id ?? d.tcr_id ?? ''
                const cdr3 = d.c ?? d.CDR3b ?? ''
                const ep = d.e ?? d.known_epitope ?? ''
                const cat = d.a ?? d.antigen_category ?? ''
                if (
                    cid.toLowerCase().includes(q) ||
                    cdr3.toLowerCase().includes(q) ||
                    ep.toLowerCase().includes(q) ||
                    cat.toLowerCase().includes(q)
                ) matches.push(d)
            }
        }

        matches.sort((a, b) => (b.h ? 1 : 0) - (a.h ? 1 : 0))
        return matches.map(formatOption)
    }, [searchText, points])

    // ── Trigger UMAP recompute ───────────────────────────────────────────────────
    const triggerUmapRecompute = async () => {
        try {
            setWorkerLoading(true)
            await api.triggerUmapRecompute()
            message.success('UMAP recomputation queued! View backend logs for progress.')
        } catch (e) {
            console.error(e)
            message.error('Failed to start worker')
        } finally {
            setTimeout(() => setWorkerLoading(false), 2000)
        }
    }

    const clearIngestedPoints = () => {
        api.clearIngested().catch(() => {})
        setIngestedPoints([])
    }

    return {
        points,
        loading,
        backendOk,
        stats,
        searchText,
        setSearchText,
        searchOptions,
        triggerUmapRecompute,
        workerLoading,
        ingestedPoints,
        clearIngestedPoints,
    }
}
