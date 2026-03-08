/**
 * DetailPanel.jsx — Animated right-side overlay panel.
 *
 * Shows either:
 * - TCR Detail view when a point is selected
 * - Lasso selection summary when TCRs are lasso-selected
 */
import { useMemo } from 'react'
import { Button } from 'antd'
import TcrDetail from './TcrDetail'
import SynthesisExport from './SynthesisExport'

export default function DetailPanel({
    open,
    displayPoint,
    lassoSelected,
    provider,
    onClose,
    onCloseLasso,
}) {
    const compositeSummary = useMemo(() => {
        if (!lassoSelected?.length) return null
        return {
            total: lassoSelected.length,
            categories: buildTopCounts(lassoSelected, p => p.a ?? p.antigen_category ?? 'unknown'),
            sources: buildTopCounts(lassoSelected, p => p.s ?? p.source ?? 'unknown'),
            epitopes: buildTopCounts(lassoSelected, p => p.e ?? p.known_epitope ?? null, 4, false),
        }
    }, [lassoSelected])

    return (
        <div
            className="detail-panel-overlay"
            style={{
                position: 'absolute',
                top: 0, right: 0,
                width: 400, height: '100%',
                background: 'var(--bg-surface)',
                borderLeft: '1px solid var(--border)',
                zIndex: 100,
                display: 'flex',
                flexDirection: 'column',
                transform: `translateX(${open ? '0' : '100%'})`,
            }}
        >
            {/* TCR Detail view */}
            {displayPoint && (
                <>
                    <PanelHeader title="TCR Detail" onClose={onClose} />
                    <div style={{ flex: 1, overflowY: 'auto' }}>
                        <TcrDetail
                            point={displayPoint}
                            provider={provider}
                            onClose={onClose}
                            lassoSelected={lassoSelected}
                        />
                    </div>
                </>
            )}

            {/* Lasso selection view */}
            {!displayPoint && lassoSelected.length > 0 && (
                <>
                    <PanelHeader title="Lasso Selection" onClose={onCloseLasso} />
                    <div style={{ padding: 16, flex: 1, overflowY: 'auto' }}>
                        <CompositeSummary summary={compositeSummary} />
                        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text-main)' }}>
                            {lassoSelected.length} TCRs Selected
                        </div>
                        <SynthesisExport tcrIds={lassoSelected.map(t => t.id ?? t.tcr_id)} />
                    </div>
                </>
            )}
        </div>
    )
}

function CompositeSummary({ summary }) {
    if (!summary) return null
    return (
        <div style={{
            padding: 16,
            marginBottom: 16,
            borderRadius: 14,
            border: '1px solid var(--border-strong)',
            background: 'color-mix(in srgb, var(--bg-overlay), transparent 10%)',
        }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: 6 }}>
                Composite Analysis
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 10 }}>
                Mapping {summary.total} neighbors for convergent epitopes & sources.
            </div>
            <SummaryRow title="Antigen categories" items={summary.categories} />
            <SummaryRow title="Sources" items={summary.sources} />
            <SummaryRow title="Notable epitopes" items={summary.epitopes} emptyHint="Mostly dark matter" />
        </div>
    )
}

function SummaryRow({ title, items, emptyHint = 'No signal yet' }) {
    return (
        <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-main)', marginBottom: 4 }}>{title}</div>
            {items.length === 0 ? (
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{emptyHint}</span>
            ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {items.map(item => (
                        <span key={item.label} style={{
                            padding: '4px 10px',
                            borderRadius: 999,
                            border: '1px solid var(--border)',
                            fontSize: 11,
                            color: 'var(--color-primary)',
                            background: 'rgba(16, 185, 129, 0.1)',
                        }}>
                            {item.label} · {item.count} ({item.pct}%)
                        </span>
                    ))}
                </div>
            )}
        </div>
    )
}

function buildTopCounts(items, accessor, limit = 3, allowEmpty = false) {
    const counts = new Map()
    for (const item of items) {
        const raw = accessor(item)
        if (!allowEmpty && !raw) continue
        const key = raw || 'unknown'
        counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, limit)
        .map(([label, count]) => ({
            label,
            count,
            pct: Math.round((count / items.length) * 100),
        }))
}

function PanelHeader({ title, onClose }) {
    return (
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
                {title}
            </span>
            <Button
                type="text"
                size="small"
                onClick={onClose}
                style={{ color: 'var(--text-dim)', fontSize: 18, lineHeight: 1, padding: '0 4px' }}
            >
                ×
            </Button>
        </div>
    )
}
