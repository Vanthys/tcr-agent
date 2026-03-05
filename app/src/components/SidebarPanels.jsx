/**
 * SidebarPanels.jsx — Left sidebar statistics panels.
 *
 * Four collapsible Ant Design Collapse panels:
 * 1. Data Gap — donut chart + dark matter %
 * 2. Top Epitopes — horizontal bar chart
 * 3. DecoderTCR Summary — per-category mean scores
 * 4. Color Legend — antigen category colors
 */
import { useEffect, useState } from 'react'
import { Collapse, Spin } from 'antd'
import { PieChart, Pie, Cell } from 'recharts'
import { api } from '../api'

const CAT_COLORS = {
    viral: 'var(--cat-viral)',
    melanocyte: 'var(--cat-melanocyte)',
    cancer_associated: 'var(--cat-cancer)',
    autoimmune: 'var(--cat-autoimmune)',
    bacterial: 'var(--cat-bacterial)',
    neurodegeneration: 'var(--cat-neurodegeneration)',
    reactive_unclassified: 'var(--cat-reactive)',
    other: 'var(--cat-other)',
    unknown: 'var(--cat-unknown)',
}

const LEGEND_ITEMS = [
    { key: 'viral', label: 'Viral' },
    { key: 'melanocyte', label: 'Melanocyte' },
    { key: 'cancer_associated', label: 'Cancer' },
    { key: 'autoimmune', label: 'Autoimmune' },
    { key: 'bacterial', label: 'Bacterial' },
    { key: 'neurodegeneration', label: 'Neurodegeneration' },
    { key: 'reactive_unclassified', label: 'Reactive' },
    { key: 'other', label: 'Other' },
    { key: 'unknown', label: 'Unknown / Dark Matter' },
]

// ── DataGap panel ─────────────────────────────────────────────────────────────
function DataGapPanel({ stats }) {
    if (!stats) return null

    const dark = stats.dark_matter_pct ?? 78
    const ann = 100 - dark

    const data = [
        { name: 'Dark Matter', value: dark, color: 'var(--cat-unknown)' },
        { name: 'Annotated', value: ann, color: 'var(--color-primary)' },
    ]

    return (
        <div>
            <div style={{ position: 'relative', height: 120, display: 'flex', justifyContent: 'center', marginBottom: 10 }}>
                <PieChart width={192} height={120}>
                    <Pie
                        data={data}
                        cx="50%"
                        cy="50%"
                        innerRadius={38}
                        outerRadius={52}
                        startAngle={90}
                        endAngle={-270}
                        dataKey="value"
                        stroke="none"
                        paddingAngle={3}
                        animationDuration={1000}
                    >
                        {data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                    </Pie>
                </PieChart>
                <div style={{
                    position: 'absolute', inset: 0,
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    pointerEvents: 'none',
                }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-main)', fontFamily: 'JetBrains Mono, monospace' }}>
                        {Math.round(dark)}%
                    </span>
                    <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>
                        dark matter
                    </span>
                </div>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.8 }}>
                <Row label="Total TCRs" value={(stats.total_tcrs ?? 88962).toLocaleString()} />
                <Row label="Annotated" value={(stats.annotated_tcrs ?? 19606).toLocaleString()} />
                <Row label="Dark matter" value={(stats.dark_matter_tcrs ?? 69356).toLocaleString()} color="var(--cat-unknown)" />
                <Row label="Unique epitopes" value={(stats.unique_epitopes ?? 727).toLocaleString()} />
            </div>
        </div>
    )
}

// ── TopEpitopes panel ─────────────────────────────────────────────────────────
function TopEpitopesPanel({ items }) {
    if (!items?.length) return <EmptyMsg />
    const max = items[0].count
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {items.slice(0, 12).map((ep, i) => (
                <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
                        <span style={{ color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }}>
                            {ep.epitope}
                        </span>
                        <span style={{ color: CAT_COLORS[ep.category] ?? '#aaa', flexShrink: 0 }}>{ep.count}</span>
                    </div>
                    <div style={{ height: 3, background: 'var(--border)', borderRadius: 2 }}>
                        <div style={{
                            height: '100%', width: `${(ep.count / max) * 100}%`,
                            background: CAT_COLORS[ep.category] ?? '#aaa',
                            borderRadius: 2, transition: 'width 0.4s',
                        }} />
                    </div>
                </div>
            ))}
        </div>
    )
}

// ── Legend panel ──────────────────────────────────────────────────────────────
function LegendPanel() {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {LEGEND_ITEMS.map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: CAT_COLORS[key], flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
                </div>
            ))}
        </div>
    )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function SidebarPanels({ stats: propStats }) {
    const [epitopes, setEpitopes] = useState(null)
    const [loading, setLoading] = useState(false)

    // Use passed stats or minimal fallback
    const stats = propStats ?? null

    useEffect(() => {
        setLoading(true)
        api.epitopeDistribution()
            .then(setEpitopes)
            .catch(() => { })
            .finally(() => setLoading(false))
    }, [])

    const items = [
        {
            key: '1',
            label: <PanelLabel>Data Gap</PanelLabel>,
            children: <DataGapPanel stats={stats} />,
        },
        {
            key: '2',
            label: <PanelLabel>Top Epitopes</PanelLabel>,
            children: loading ? <Spin size="small" /> : <TopEpitopesPanel items={epitopes} />,
        },
        {
            key: '3',
            label: <PanelLabel>Color Legend</PanelLabel>,
            children: <LegendPanel />,
        },
    ]

    return (
        <Collapse
            defaultActiveKey={['1', '3']}
            items={items}
            ghost
            style={{ background: 'transparent' }}
        />
    )
}

function PanelLabel({ children }) {
    return (
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.55)' }}>
            {children}
        </span>
    )
}

function Row({ label, value, color }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{label}</span>
            <span style={{ color: color ?? 'rgba(255,255,255,0.8)', fontWeight: 500 }}>{value}</span>
        </div>
    )
}

function EmptyMsg() {
    return <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)' }}>No data available</span>
}
