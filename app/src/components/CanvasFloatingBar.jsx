/**
 * CanvasFloatingBar.jsx — Floating control pill at the bottom of the UMAP canvas.
 *
 * Contains the lasso toggle, dimension slider, and a hint text.
 */
import { Button, Tooltip, Slider } from 'antd'
import { DragOutlined } from '@ant-design/icons'

export default function CanvasFloatingBar({
    visible,
    lassoMode,
    onLassoToggle,
    sliderVal,
    onSliderChange,
    onDimsChange,
    panelOpen,
}) {
    if (!visible) return null

    return (
        <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            background: 'var(--bg-overlay)', backdropFilter: 'blur(12px)',
            border: '1px solid var(--border-strong)',
            borderRadius: 100, padding: '8px 24px',
            display: 'flex', alignItems: 'center', gap: 20,
            boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
            zIndex: 10,
        }}>
            {/* Lasso toggle */}
            <Tooltip title="Lasso Selection">
                <Button
                    shape="circle"
                    type={lassoMode ? 'primary' : 'text'}
                    icon={<DragOutlined />}
                    onClick={onLassoToggle}
                    style={lassoMode
                        ? { background: 'var(--color-primary)', border: 'none' }
                        : { color: 'var(--text-dim)', border: 'none' }
                    }
                />
            </Tooltip>

            <div style={{ width: 1, height: 20, background: 'var(--border)' }} />

            {/* Dimension slider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Dims
                </span>
                <Slider
                    min={1}
                    max={4}
                    value={sliderVal}
                    onChange={onSliderChange}
                    onChangeComplete={onDimsChange}
                    tooltip={{ formatter: v => `Dims ${v}-${v + 1}` }}
                    style={{ width: 100, margin: 0 }}
                />
            </div>

            {/* Hint text — only when panel is closed */}
            {!panelOpen && (
                <>
                    <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                    <div style={{ fontSize: 12, color: 'var(--text-dim)', pointerEvents: 'none', whiteSpace: 'nowrap' }}>
                        {lassoMode ? 'Draw to select' : 'Click to select · Scroll to zoom'}
                    </div>
                </>
            )}
        </div>
    )
}
