/**
 * UmapCanvas.jsx — 89K-point canvas scatter plot.
 *
 * Performance fixes:
 * - requestAnimationFrame throttling: rapid events collapse into 1 draw/frame
 * - Native wheel listener with { passive: false } to allow preventDefault
 * - devicePixelRatio support for crisp rendering on retina displays
 * - Off-screen point culling (skip dots outside viewport bounds)
 */
import { useRef, useEffect, useLayoutEffect, useCallback, useState } from 'react'

const CAT_COLORS_DARK = {
    viral: '#4ecdc4',
    melanocyte: '#ff6b6b',
    cancer_associated: '#c44569',
    autoimmune: '#574b90',
    bacterial: '#f8a5c2',
    neurodegeneration: '#f78fb3',
    reactive_unclassified: '#fd9644',
    other: '#778ca3',
    unknown: '#3a3e4a',
}

const CAT_COLORS_LIGHT = {
    viral: '#2c7a7b',
    melanocyte: '#c53030',
    cancer_associated: '#9b2c2c',
    autoimmune: '#44337a',
    bacterial: '#b83280',
    neurodegeneration: '#d53f8c',
    reactive_unclassified: '#c05621',
    other: '#4a5568',
    unknown: '#a0aec0',
}

const SOURCE_LABELS = {
    T: 'TCRAFT', V: 'VDJdb', P: 'PDAC', A: 'AD CSF', M: 'McPAS',
    TCRAFT: 'TCRAFT', VDJdb: 'VDJdb', PDAC: 'PDAC', AD_CSF: 'AD CSF', McPAS: 'McPAS',
}

function getColor(p, isDark) {
    const colors = isDark ? CAT_COLORS_DARK : CAT_COLORS_LIGHT
    return colors[p.a ?? p.antigen_category ?? 'unknown'] ?? colors.unknown
}

export default function UmapCanvas({ points, selectedId, filters, onSelect, isDark = true }) {
    const containerRef = useRef(null)
    const canvasRef = useRef(null)
    const screenPos = useRef([])
    const transform = useRef({ scale: 1, tx: 0, ty: 0 })
    const dragging = useRef(null)
    const boundsRef = useRef({ minX: 0, maxX: 1, minY: 0, maxY: 1 })
    const rafRef = useRef(null)       // pending animation frame id
    const [tooltip, setTooltip] = useState(null)

    // ── Compute data bounds when points arrive ────────────────────────────────
    useEffect(() => {
        if (!points?.length) return
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
        for (const p of points) {
            const px = p.x ?? p.umap_x, py = p.y ?? p.umap_y
            if (px < minX) minX = px; if (px > maxX) maxX = px
            if (py < minY) minY = py; if (py > maxY) maxY = py
        }
        boundsRef.current = { minX, maxX, minY, maxY }
        transform.current = { scale: 1, tx: 0, ty: 0 }
    }, [points])

    // ── Size canvas (also handles devicePixelRatio) ───────────────────────────
    const sizeCanvas = useCallback(() => {
        const container = containerRef.current
        const canvas = canvasRef.current
        if (!container || !canvas) return
        const { width, height } = container.getBoundingClientRect()
        if (width <= 0 || height <= 0) return
        const dpr = window.devicePixelRatio || 1
        canvas.width = width * dpr
        canvas.height = height * dpr
        // CSS size stays the same — canvas just has more pixels on HiDPI
        canvas.style.width = width + 'px'
        canvas.style.height = height + 'px'
    }, [])

    useLayoutEffect(() => { sizeCanvas() }, [sizeCanvas])

    // ── Core draw function ────────────────────────────────────────────────────
    const drawNow = useCallback(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        // Ensure sized
        if (canvas.width === 0 || canvas.height === 0) sizeCanvas()
        const W = canvas.width, H = canvas.height
        if (W === 0 || H === 0 || !points?.length) return

        const dpr = window.devicePixelRatio || 1
        const ctx = canvas.getContext('2d')
        const { minX, maxX, minY, maxY } = boundsRef.current
        const { scale, tx, ty } = transform.current

        ctx.clearRect(0, 0, W, H)
        ctx.fillStyle = isDark ? '#0a0c12' : '#f0f2f5'
        ctx.fillRect(0, 0, W, H)

        // Scale context for HiDPI
        ctx.save()
        ctx.scale(dpr, dpr)

        const cssW = W / dpr
        const cssH = H / dpr
        const pad = 32
        const dataW = cssW - pad * 2
        const dataH = cssH - pad * 2
        const rangeX = maxX - minX || 1
        const rangeY = maxY - minY || 1
        const DOT = 2.2

        const filterSource = filters?.source
        const filterCat = filters?.category

        const positions = []

        for (let i = 0; i < points.length; i++) {
            const p = points[i]
            const src = p.s ?? p.source
            const cat = p.a ?? p.antigen_category ?? 'unknown'

            if (filterSource !== '' && filterSource != null && src !== filterSource) continue
            if (filterCat !== '' && filterCat != null && cat !== filterCat) continue

            const px = p.x ?? p.umap_x
            const py = p.y ?? p.umap_y
            if (px == null || py == null || isNaN(px) || isNaN(py)) continue

            const base_x = pad + ((px - minX) / rangeX) * dataW
            const base_y = pad + ((py - minY) / rangeY) * dataH
            const fx = base_x * scale + tx
            const fy = base_y * scale + ty

            // Cull well off-screen
            if (fx < -16 || fx > cssW + 16 || fy < -16 || fy > cssH + 16) continue

            const isSelected = (p.id ?? p.tcr_id) === selectedId
            const color = getColor(p, isDark) // Added isDark prop

            if (isSelected) {
                ctx.beginPath()
                ctx.arc(fx, fy, DOT + 4, 0, Math.PI * 2)
                ctx.fillStyle = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)' // Theme-based glow
                ctx.fill()
                ctx.beginPath()
                ctx.arc(fx, fy, DOT + 2, 0, Math.PI * 2)
                ctx.strokeStyle = isDark ? '#fff' : '#000' // Theme-based stroke
                ctx.lineWidth = 1.5
                ctx.stroke()
            }

            ctx.beginPath()
            ctx.arc(fx, fy, isSelected ? DOT + 1 : DOT, 0, Math.PI * 2)
            ctx.fillStyle = isSelected ? (isDark ? '#fff' : '#000') : color
            ctx.globalAlpha = isSelected ? 1 : 0.72
            ctx.fill()
            ctx.globalAlpha = 1

            positions.push({ x: fx, y: fy, idx: i })
        }

        ctx.restore()
        screenPos.current = positions
    }, [points, selectedId, filters, sizeCanvas, isDark])

    // ── Schedule draw (collapses rapid events into one frame) ─────────────────
    const scheduleDraw = useCallback(() => {
        if (rafRef.current) return                           // already queued
        rafRef.current = requestAnimationFrame(() => {
            rafRef.current = null
            drawNow()
        })
    }, [drawNow])

    useEffect(() => { scheduleDraw() }, [scheduleDraw])

    // ── ResizeObserver ────────────────────────────────────────────────────────
    useEffect(() => {
        const container = containerRef.current
        if (!container) return
        const ro = new ResizeObserver(() => { sizeCanvas(); scheduleDraw() })
        ro.observe(container)
        return () => ro.disconnect()
    }, [sizeCanvas, scheduleDraw])

    // ── Native wheel listener (passive: false so preventDefault works) ────────
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return
        const onWheel = (e) => {
            e.preventDefault()
            const rect = canvas.getBoundingClientRect()
            const mx = e.clientX - rect.left
            const my = e.clientY - rect.top
            const factor = e.deltaY < 0 ? 1.12 : 0.9
            const t = transform.current
            t.tx = mx + (t.tx - mx) * factor
            t.ty = my + (t.ty - my) * factor
            t.scale *= factor
            scheduleDraw()
        }
        canvas.addEventListener('wheel', onWheel, { passive: false })
        return () => canvas.removeEventListener('wheel', onWheel)
    }, [scheduleDraw])

    // ── Hit test ─────────────────────────────────────────────────────────────
    const hitTest = useCallback((ex, ey) => {
        let best = null, bestDist = 14
        for (const { x, y, idx } of screenPos.current) {
            const d = Math.hypot(ex - x, ey - y)
            if (d < bestDist) { bestDist = d; best = idx }
        }
        return best
    }, [])

    // ── Mouse events (pan + click) — use React handlers (not wheel) ───────────
    const onMouseMove = useCallback((e) => {
        if (!canvasRef.current) return
        const rect = canvasRef.current.getBoundingClientRect()
        const ex = e.clientX - rect.left
        const ey = e.clientY - rect.top

        if (dragging.current) {
            transform.current.tx += e.movementX
            transform.current.ty += e.movementY
            scheduleDraw()
            return
        }

        const idx = hitTest(ex, ey)
        if (idx != null) {
            setTooltip({ x: ex, y: ey, point: points[idx] })
            canvasRef.current.style.cursor = 'pointer'
        } else {
            setTooltip(null)
            canvasRef.current.style.cursor = 'grab'
        }
    }, [points, hitTest, scheduleDraw])

    const onMouseDown = useCallback((e) => {
        dragging.current = { x: e.clientX, y: e.clientY }
        if (canvasRef.current) canvasRef.current.style.cursor = 'grabbing'
    }, [])

    const onMouseUp = useCallback((e) => {
        const wasDrag = dragging.current &&
            (Math.abs(e.clientX - dragging.current.x) > 4 ||
                Math.abs(e.clientY - dragging.current.y) > 4)
        dragging.current = null
        if (canvasRef.current) canvasRef.current.style.cursor = 'grab'
        if (!wasDrag) {
            const rect = canvasRef.current.getBoundingClientRect()
            const idx = hitTest(e.clientX - rect.left, e.clientY - rect.top)
            if (idx != null && onSelect) onSelect(points[idx])
        }
    }, [points, hitTest, onSelect])

    return (
        <div
            ref={containerRef}
            style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}
        >
            <canvas
                ref={canvasRef}
                style={{ display: 'block', cursor: 'grab' }}
                onMouseMove={onMouseMove}
                onMouseDown={onMouseDown}
                onMouseUp={onMouseUp}
            // onWheel intentionally omitted — handled natively above
            />
            {tooltip && <CanvasTooltip {...tooltip} isDark={isDark} />}
            {points?.length > 0 && (
                <div style={{
                    position: 'absolute', bottom: 10, right: 12,
                    fontSize: 10, color: 'rgba(255,255,255,0.2)',
                    fontFamily: "'JetBrains Mono', monospace",
                    pointerEvents: 'none',
                }}>
                    {points.length.toLocaleString()} TCRs
                </div>
            )}
        </div>
    )
}

function CanvasTooltip({ x, y, point, isDark }) {
    if (!point) return null
    const id = point.id ?? point.tcr_id ?? '—'
    const cdr3 = point.c ?? point.CDR3b ?? '—'
    const src = SOURCE_LABELS[point.s ?? point.source] ?? point.source ?? '—'
    const epitope = point.e ?? point.known_epitope

    return (
        <div style={{
            position: 'absolute',
            left: x + 14, top: y - 10,
            background: 'var(--bg-overlay)',
            border: '1px solid var(--border-strong)',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: 12, lineHeight: 1.65,
            pointerEvents: 'none',
            backdropFilter: 'blur(10px)',
            zIndex: 100,
            maxWidth: 240,
            boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
        }}>
            <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: 11 }}>{id}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--color-primary)', fontSize: 11 }}>{cdr3}</div>
            <div style={{ color: 'var(--text-dim)', marginTop: 2, fontSize: 11 }}>{src}</div>
            {epitope
                ? <div style={{ color: 'var(--color-accent)', marginTop: 2, fontSize: 11 }}>{epitope}</div>
                : <div style={{ color: 'var(--text-dim)', opacity: 0.6, marginTop: 2, fontSize: 10, fontStyle: 'italic' }}>dark matter</div>
            }
        </div>
    )
}
