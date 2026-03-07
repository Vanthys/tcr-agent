import React, { useMemo, useState, useCallback, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { ScatterplotLayer, PolygonLayer } from '@deck.gl/layers';
import { OrthographicView, LinearInterpolator } from '@deck.gl/core';
import { easeCubicInOut } from 'd3-ease';

const CAT_COLORS_DARK = {
    viral: [78, 205, 196],
    melanocyte: [255, 107, 107],
    cancer_associated: [196, 69, 105],
    autoimmune: [87, 75, 144],
    bacterial: [248, 165, 194],
    neurodegeneration: [247, 143, 179],
    reactive_unclassified: [253, 150, 68],
    other: [119, 140, 163],
    unknown: [58, 62, 74],
}

const CAT_COLORS_LIGHT = {
    viral: [44, 122, 123],
    melanocyte: [197, 48, 48],
    cancer_associated: [155, 44, 44],
    autoimmune: [68, 51, 122],
    bacterial: [184, 50, 128],
    neurodegeneration: [213, 63, 140],
    reactive_unclassified: [192, 86, 33],
    other: [74, 85, 104],
    unknown: [160, 174, 192],
}

const SOURCE_LABELS = {
    T: 'TCRAFT', V: 'VDJdb', P: 'PDAC', A: 'AD CSF', M: 'McPAS',
    TCRAFT: 'TCRAFT', VDJdb: 'VDJdb', PDAC: 'PDAC', AD_CSF: 'AD CSF', McPAS: 'McPAS',
}

function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? [
        parseInt(result[1], 16),
        parseInt(result[2], 16),
        parseInt(result[3], 16)
    ] : [100, 100, 100];
}

function getColor(p, isDark) {
    const colors = isDark ? CAT_COLORS_DARK : CAT_COLORS_LIGHT
    return colors[p.a ?? p.antigen_category ?? 'unknown'] ?? colors.unknown
}

export default function UmapCanvas({ points, selectedId, filters, onSelect, isDark = true, isRevealing, onRevealComplete, lassoMode, onLassoSelect, lassoSelected = [], xDim = 1, yDim = 2 }) {
    const [viewState, setViewState] = useState({
        target: [0, 0, 0],
        zoom: 4,
        minZoom: 1,
        maxZoom: 20
    });

    const [hoverInfo, setHoverInfo] = useState(null);
    const [lassoPolygon, setLassoPolygon] = useState([]);
    const containerRef = useRef(null);
    const revealCount = isRevealing ? 0 : points?.length; // Simplified for now

    const lassoSet = useMemo(() => {
        return new Set(lassoSelected ? lassoSelected.map(ld => ld.id ?? ld.tcr_id) : [])
    }, [lassoSelected])

    const filterSource = filters?.source
    const filterCat = filters?.category

    // Deck.gl data transformation
    const scatterData = useMemo(() => {
        if (!points) return [];
        return points.filter(p => {
            const src = p.s ?? p.source
            const cat = p.a ?? p.antigen_category ?? 'unknown'
            if (filterSource && src !== filterSource) return false
            if (filterCat && cat !== filterCat) return false
            return p.d1 != null || p.x != null || p.umap_x != null;
        }).map(p => {
            const pid = p.id ?? p.tcr_id;
            return {
                ...p,
                position: [(p[`d${xDim}`] ?? p.x ?? p.umap_x ?? 0), (p[`d${yDim}`] ?? p.y ?? p.umap_y ?? 0)],
                color: getColor(p, isDark),
                isSelected: pid === selectedId,
                isLassoed: lassoSet.has(pid)
            };
        });
    }, [points, isDark, lassoSet, selectedId, filterSource, filterCat, xDim, yDim]);

    // Initial ViewState Auto-fit
    React.useEffect(() => {
        if (points?.length > 0 && containerRef.current && viewState.zoom === 4 && viewState.target[0] === 0) {
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
            for (const p of scatterData) {
                if (p.position[0] < minX) minX = p.position[0];
                if (p.position[0] > maxX) maxX = p.position[0];
                if (p.position[1] < minY) minY = p.position[1];
                if (p.position[1] > maxY) maxY = p.position[1];
            }
            if (minX !== Infinity) {
                const { width, height } = containerRef.current.getBoundingClientRect();
                const scaleX = width / ((maxX - minX) || 1);
                const scaleY = height / ((maxY - minY) || 1);
                const zoom = Math.log2(Math.min(scaleX, scaleY)) - 0.5; // less margin
                setViewState(prev => ({
                    ...prev,
                    target: [(minX + maxX) / 2, (minY + maxY) / 2, 0],
                    zoom: isNaN(zoom) ? 4 : zoom
                }));
            }
        }
    }, [points?.length, viewState.zoom, viewState.target, scatterData]);

    // Zoom to selected point when it changes or dimensions change
    React.useEffect(() => {
        if (selectedId && scatterData) {
            const point = scatterData.find(p => (p.id ?? p.tcr_id) === selectedId);
            if (point && point.position) {
                setViewState(prev => ({
                    ...prev,
                    target: [point.position[0], point.position[1], 0],
                    zoom: 12, // zoom in close
                    transitionDuration: 1000,
                    transitionEasing: easeCubicInOut,
                    transitionInterpolator: new LinearInterpolator(['target', 'zoom'])
                }));
            }
        }
    }, [selectedId, xDim, yDim]);

    const layers = [
        new ScatterplotLayer({
            id: 'scatterplot-layer',
            data: scatterData,
            pickable: true,
            opacity: 0.8,
            stroked: true,
            filled: true,
            radiusUnits: 'pixels', // Force radii to evaluate in screen pixels, not UMAP coordinate units
            lineWidthUnits: 'pixels', // Force strokes to evaluate in screen pixels
            radiusMinPixels: 0.5,
            radiusMaxPixels: 15,
            getPosition: d => d.position,
            getFillColor: d => d.color,
            getLineColor: d => d.isSelected ? (isDark ? [255, 255, 255] : [0, 0, 0]) : d.color,
            getRadius: d => d.isSelected ? 6 : 2, // Now strictly 2px and 6px wide on screen
            getLineWidth: d => d.isSelected || d.isLassoed ? 1.5 : 0,
            updateTriggers: {
                getFillColor: [isDark],
                getLineColor: [selectedId, isDark],
                getRadius: [selectedId],
                getLineWidth: [selectedId, lassoSet]
            },
            onHover: info => setHoverInfo(info),
            onClick: info => {
                if (info.object && onSelect) {
                    onSelect(info.object);
                }
            }
        }),
        lassoMode && lassoPolygon.length > 0 && new PolygonLayer({
            id: 'lasso-layer',
            data: [{ polygon: lassoPolygon }],
            pickable: false,
            stroked: true,
            filled: true,
            lineWidthUnits: 'pixels', // Force lasso lines to be 2 screen pixels, not 2 UMAP units!
            getPolygon: d => d.polygon,
            getFillColor: [16, 185, 129, 50],
            getLineColor: [16, 185, 129, 255],
            getLineWidth: 2,
        })
    ].filter(Boolean);

    // Coordinate projection trick to manual poly point checking
    // Wait, let's keep it simple.

    // Using simple point-in-polygon ray casting inside data bounds:
    const onLassoEnd = useCallback((poly) => {
        if (!poly || poly.length < 3) return;

        const selected = [];
        for (const pt of scatterData) {
            const pos = pt.position;
            let inside = false;
            for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
                const xi = poly[i][0], yi = poly[i][1];
                const xj = poly[j][0], yj = poly[j][1];
                if ((yi > pos[1]) !== (yj > pos[1]) && pos[0] < (xj - xi) * (pos[1] - yi) / (yj - yi) + xi) {
                    inside = !inside;
                }
            }
            if (inside) selected.push(pt);
        }
        if (onLassoSelect) onLassoSelect(selected);
    }, [scatterData, onLassoSelect]);

    // Handle dragging lasso
    const onDragStart = (info, event) => {
        if (lassoMode) {
            setLassoPolygon([info.coordinate]);
        }
    };
    const onDrag = (info, event) => {
        if (lassoMode && lassoPolygon.length > 0) {
            setLassoPolygon(prev => [...prev, info.coordinate]);
        }
    };
    const onDragEnd = (info, event) => {
        if (lassoMode) {
            onLassoEnd(lassoPolygon);
            setLassoPolygon([]);
        }
    };

    return (
        <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
            <DeckGL
                views={new OrthographicView({ id: 'ortho' })}
                viewState={viewState}
                onViewStateChange={e => {
                    const next = e.viewState;
                    if (e.interactionState.isDragging || e.interactionState.isPanning || e.interactionState.isZooming) {
                        next.transitionDuration = 0;
                    }
                    setViewState(next);
                }}
                controller={{ dragPan: !lassoMode }}
                layers={layers}
                getCursor={({ isDragging, isHovering }) =>
                    lassoMode ? 'crosshair' :
                        isDragging ? 'grabbing' :
                            isHovering ? 'pointer' : 'grab'
                }
                onDragStart={onDragStart}
                onDrag={onDrag}
                onDragEnd={onDragEnd}
                style={{ backgroundColor: isDark ? '#0a0c12' : '#f0f2f5' }}
            >
            </DeckGL>

            {/* Tooltip implementation */}
            {hoverInfo && hoverInfo.object && (
                <CanvasTooltip
                    x={hoverInfo.x}
                    y={hoverInfo.y}
                    point={hoverInfo.object}
                    isDark={isDark}
                />
            )}

            {points?.length > 0 && (
                <div style={{
                    position: 'absolute', bottom: 10, right: 12,
                    fontSize: 10, color: 'rgba(255,255,255,0.4)',
                    fontFamily: "'JetBrains Mono', monospace",
                    pointerEvents: 'none',
                    borderRadius: 4,
                }}>
                    {points.length.toLocaleString()} TCRs
                </div>
            )}
        </div>
    );
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
