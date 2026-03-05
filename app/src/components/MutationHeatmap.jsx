/**
 * MutationHeatmap.jsx — 20 × L CDR3 mutation sensitivity grid.
 *
 * Red = score delta > 0 (mutation increases predicted binding)
 * Blue = score delta < 0
 * White = neutral
 */
import { useRef, useEffect, useState } from 'react'
import { Empty, Spin, Tooltip } from 'antd'

const AA_ORDER = [
    'A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'K', 'L',
    'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'Y',
]
const CELL = { w: 22, h: 18 }
const AXIS_LEFT = 30
const AXIS_TOP = 20

function deltaToColor(delta, maxAbs) {
    const t = Math.max(-1, Math.min(1, delta / (maxAbs || 1)))
    if (t > 0) {
        // white → red
        const r = 255, g = Math.round(255 * (1 - t)), b = Math.round(255 * (1 - t))
        return `rgb(${r},${g},${b})`
    } else {
        // white → blue
        const r = Math.round(255 * (1 + t)), g = Math.round(255 * (1 + t)), b = 255
        return `rgb(${r},${g},${b})`
    }
}

export default function MutationHeatmap({ data, loading }) {
    const canvasRef = useRef(null)
    const [hovered, setHovered] = useState(null)

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas || !data?.landscape?.length) return

        const cdr3 = data.cdr3b ?? ''
        const L = cdr3.length || Math.max(...data.landscape.map(e => e.position)) + 1
        const W = AXIS_LEFT + L * CELL.w + 20
        const H = AXIS_TOP + AA_ORDER.length * CELL.h + 20

        canvas.width = W
        canvas.height = H

        const ctx = canvas.getContext('2d')
        ctx.clearRect(0, 0, W, H)
        ctx.fillStyle = '#0d0f17'
        ctx.fillRect(0, 0, W, H)

        // Find max absolute delta for color scale
        const maxAbs = Math.max(...data.landscape.map(e => Math.abs(e.delta)), 0.01)

        // Build lookup: (position, mut_aa) → delta
        const lookup = new Map()
        for (const entry of data.landscape) {
            lookup.set(`${entry.position}:${entry.mut_aa}`, entry.delta)
        }

        // Draw cells
        for (let col = 0; col < L; col++) {
            for (let row = 0; row < AA_ORDER.length; row++) {
                const aa = AA_ORDER[row]
                const wt = cdr3[col]
                const x = AXIS_LEFT + col * CELL.w
                const y = AXIS_TOP + row * CELL.h

                if (aa === wt) {
                    // Wild-type diagonal — show as dark outlined cell
                    ctx.fillStyle = 'rgba(255,255,255,0.06)'
                    ctx.fillRect(x, y, CELL.w - 1, CELL.h - 1)
                    ctx.strokeStyle = 'rgba(255,255,255,0.2)'
                    ctx.lineWidth = 1
                    ctx.strokeRect(x + 0.5, y + 0.5, CELL.w - 2, CELL.h - 2)
                    ctx.fillStyle = 'rgba(255,255,255,0.3)'
                    ctx.font = '7px Inter'
                    ctx.textAlign = 'center'
                    ctx.fillText('WT', x + CELL.w / 2, y + CELL.h / 2 + 3)
                } else {
                    const delta = lookup.get(`${col}:${aa}`) ?? 0
                    ctx.fillStyle = deltaToColor(delta, maxAbs)
                    ctx.fillRect(x, y, CELL.w - 1, CELL.h - 1)
                }
            }
        }

        // Amino acid labels (left axis)
        ctx.fillStyle = 'rgba(255,255,255,0.45)'
        ctx.font = '9px JetBrains Mono'
        ctx.textAlign = 'right'
        for (let row = 0; row < AA_ORDER.length; row++) {
            ctx.fillText(
                AA_ORDER[row],
                AXIS_LEFT - 4,
                AXIS_TOP + row * CELL.h + CELL.h / 2 + 3,
            )
        }

        // Position labels (top axis) — show wt amino acid
        ctx.textAlign = 'center'
        for (let col = 0; col < L; col++) {
            ctx.fillStyle = 'rgba(255,255,255,0.5)'
            ctx.fillText(
                cdr3[col] ?? col,
                AXIS_LEFT + col * CELL.w + CELL.w / 2,
                AXIS_TOP - 6,
            )
        }
    }, [data])

    if (loading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
                <Spin />
            </div>
        )
    }

    if (!data) {
        return (
            <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                    <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>
                        No mutation landscape available<br />for this TCR yet
                    </span>
                }
                style={{ padding: '16px 0' }}
            />
        )
    }

    return (
        <div>
            {/* Epitope label */}
            {data.epitope && (
                <div style={{
                    fontSize: 11, color: 'rgba(255,255,255,0.45)',
                    marginBottom: 8, fontFamily: 'JetBrains Mono, monospace',
                }}>
                    Target: <span style={{ color: '#fd9644' }}>{data.epitope}</span>
                    &nbsp;·&nbsp; WT score: {data.wild_type_score?.toFixed(4)}
                </div>
            )}

            {/* Color scale legend */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>
                <div style={{ width: 60, height: 8, background: 'linear-gradient(to right, #4466ff, white, #ff4444)', borderRadius: 2 }} />
                <span>↓ binding</span>
                <span style={{ marginLeft: 'auto' }}>↑ binding</span>
            </div>

            <div style={{ overflowX: 'auto' }}>
                <canvas ref={canvasRef} style={{ display: 'block' }} />
            </div>

            <p style={{ fontSize: 10, color: 'rgba(255,255,255,0.25)', marginTop: 8, fontStyle: 'italic' }}>
                Predicted score sensitivity — computational hypotheses, not validated binding measurements.
            </p>
        </div>
    )
}
