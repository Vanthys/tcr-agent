/**
 * DetailPanel.jsx — Animated right-side overlay panel.
 *
 * Shows either:
 * - TCR Detail view when a point is selected
 * - Lasso selection summary when TCRs are lasso-selected
 */
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
                        <TcrDetail point={displayPoint} provider={provider} onClose={onClose} />
                    </div>
                </>
            )}

            {/* Lasso selection view */}
            {!displayPoint && lassoSelected.length > 0 && (
                <>
                    <PanelHeader title="Lasso Selection" onClose={onCloseLasso} />
                    <div style={{ padding: 16, flex: 1, overflowY: 'auto' }}>
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
