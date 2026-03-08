/**
 * SidebarPanels.jsx — Left sidebar statistics panels.
 *
 * Three collapsible Ant Design Collapse panels:
 * 1. Data Gap — donut chart with per-category breakdown + dark matter %
 * 2. Top Epitopes — horizontal bar chart (clickable)
 * 3. Category Filter — interactive legend with click-to-toggle visibility
 */
import { useEffect, useState, useMemo } from 'react'
import { Collapse, Spin, Tooltip } from 'antd'
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

const CAT_LABELS = {
    viral: 'Viral',
    melanocyte: 'Melanocyte',
    cancer_associated: 'Cancer',
    autoimmune: 'Autoimmune',
    bacterial: 'Bacterial',
    neurodegeneration: 'Neurodegeneration',
    reactive_unclassified: 'Reactive',
    other: 'Other',
    unknown: 'Dark Matter',
}

// Ordered for display (dark matter last)
const CATEGORY_ORDER = [
    'viral', 'melanocyte', 'cancer_associated', 'autoimmune',
    'bacterial', 'neurodegeneration', 'reactive_unclassified', 'other', 'unknown',
]

// ── DataGap panel ─────────────────────────────────────────────────────────────
function DataGapPanel({ stats, categoryCounts }) {
    if (!stats) return null

    const total = stats.total_tcrs ?? 0

    // Build per-category donut segments from live point data
    const donutData = useMemo(() => {
        if (!categoryCounts || Object.keys(categoryCounts).length === 0) {
            // Fallback to simple dark/annotated split
            const dark = stats.dark_matter_pct ?? 78
            return [
                { name: 'Dark Matter', value: dark, color: CAT_COLORS.unknown },
                { name: 'Annotated', value: 100 - dark, color: 'var(--color-primary)' },
            ]
        }
        // Compute total for percentage
        const pointTotal = Object.values(categoryCounts).reduce((a, b) => a + b, 0)
        if (pointTotal === 0) return []

        return CATEGORY_ORDER
            .filter(cat => categoryCounts[cat] > 0)
            .map(cat => ({
                name: CAT_LABELS[cat] ?? cat,
                value: categoryCounts[cat],
                pct: ((categoryCounts[cat] / pointTotal) * 100).toFixed(1),
                color: CAT_COLORS[cat] ?? '#666',
            }))
    }, [categoryCounts, stats])

    const darkPct = categoryCounts?.unknown
        ? ((categoryCounts.unknown / Object.values(categoryCounts).reduce((a, b) => a + b, 0)) * 100)
        : (stats.dark_matter_pct ?? 78)

    return (
        <div>
            <div style={{ position: 'relative', height: 120, display: 'flex', justifyContent: 'center', marginBottom: 10 }}>
                <PieChart width={192} height={120}>
                    <Pie
                        data={donutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={38}
                        outerRadius={52}
                        startAngle={90}
                        endAngle={-270}
                        dataKey="value"
                        stroke="none"
                        paddingAngle={1}
                        animationDuration={1000}
                    >
                        {donutData.map((entry, index) => (
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
                        {Math.round(darkPct)}%
                    </span>
                    <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>
                        dark matter
                    </span>
                </div>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.8 }}>
                <Row label="Total TCRs" value={(total || Object.values(categoryCounts ?? {}).reduce((a, b) => a + b, 0)).toLocaleString()} />
                <Row label="Annotated" value={(stats.annotated_tcrs ?? 0).toLocaleString()} />
                <Row label="Dark matter" value={(stats.dark_matter_tcrs ?? (categoryCounts?.unknown ?? 0)).toLocaleString()} color="var(--cat-unknown)" />
                <Row label="Unique epitopes" value={(stats.unique_epitopes ?? 0).toLocaleString()} />
            </div>
        </div>
    )
}

// ── TopEpitopes panel ─────────────────────────────────────────────────────────
function TopEpitopesPanel({ items, onToggleCategory }) {
    if (!items?.length) return <EmptyMsg />
    const max = items[0].count
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {items.slice(0, 12).map((ep, i) => (
                <Tooltip key={i} title={`Click to solo ${ep.category}`} placement="right" mouseEnterDelay={0.5}>
                    <div
                        onClick={() => onToggleCategory?.(ep.category, true)}
                        style={{ cursor: 'pointer' }}
                    >
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
                </Tooltip>
            ))}
        </div>
    )
}

// ── Interactive Legend / Category Filter panel ────────────────────────────────
function CategoryFilterPanel({ categoryCounts, hiddenCategories, onToggleCategory, onResetCategories }) {
    const hidden = hiddenCategories ?? new Set()
    const hasFilters = hidden.size > 0

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Reset link */}
            {hasFilters && (
                <div
                    onClick={onResetCategories}
                    style={{
                        fontSize: 10, color: 'var(--color-primary)',
                        cursor: 'pointer', marginBottom: 4,
                        textAlign: 'right',
                    }}
                >
                    Show all
                </div>
            )}

            {CATEGORY_ORDER.map(key => {
                const isHidden = hidden.has(key)
                const count = categoryCounts?.[key] ?? 0
                return (
                    <div
                        key={key}
                        onClick={() => onToggleCategory?.(key, false)}
                        onContextMenu={(e) => { e.preventDefault(); onToggleCategory?.(key, true) }}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            padding: '3px 6px', borderRadius: 4,
                            cursor: 'pointer',
                            opacity: isHidden ? 0.3 : 1,
                            transition: 'opacity 0.15s, background 0.15s',
                            userSelect: 'none',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover, rgba(255,255,255,0.05))'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                        {/* Color dot with checkbox-like behavior */}
                        <div style={{
                            width: 10, height: 10, borderRadius: '50%',
                            background: isHidden ? 'transparent' : CAT_COLORS[key],
                            border: isHidden ? `2px solid ${CAT_COLORS[key]}` : 'none',
                            flexShrink: 0,
                            transition: 'all 0.15s',
                        }} />
                        <span style={{
                            fontSize: 11,
                            color: isHidden ? 'var(--text-dim)' : 'var(--text-main)',
                            flex: 1,
                            textDecoration: isHidden ? 'line-through' : 'none',
                        }}>
                            {CAT_LABELS[key]}
                        </span>
                        {count > 0 && (
                            <span style={{
                                fontSize: 9, color: 'var(--text-dim)',
                                fontFamily: 'JetBrains Mono, monospace',
                            }}>
                                {count.toLocaleString()}
                            </span>
                        )}
                    </div>
                )
            })}

            <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 4, opacity: 0.6 }}>
                Click to toggle. Right-click to solo.
            </div>
        </div>
    )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function SidebarPanels({ stats: propStats, categoryCounts, hiddenCategories, onToggleCategory, onResetCategories }) {
    const [epitopes, setEpitopes] = useState(null)
    const [loading, setLoading] = useState(false)

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
            children: <DataGapPanel stats={stats} categoryCounts={categoryCounts} />,
        },
        {
            key: '2',
            label: <PanelLabel>Top Epitopes</PanelLabel>,
            children: loading ? <Spin size="small" /> : <TopEpitopesPanel items={epitopes} onToggleCategory={onToggleCategory} />,
        },
        {
            key: '3',
            label: <PanelLabel>Category Filter</PanelLabel>,
            children: <CategoryFilterPanel
                categoryCounts={categoryCounts}
                hiddenCategories={hiddenCategories}
                onToggleCategory={onToggleCategory}
                onResetCategories={onResetCategories}
            />,
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
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>
            {children}
        </span>
    )
}

function Row({ label, value, color }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{label}</span>
            <span style={{ color: color ?? 'var(--text-main)', fontWeight: 500 }}>{value}</span>
        </div>
    )
}

function EmptyMsg() {
    return <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>No data available</span>
}
