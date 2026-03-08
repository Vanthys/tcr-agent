/**
 * TcrDetail.jsx — Right-side detail panel for a selected TCR.
 *
 * Shows CDR3, V/J genes, source, epitope, prediction bars,
 * neighbor list, and triggers the agent log.
 */
import { useState, useEffect } from 'react'
import { Button, Divider, Progress, Tag, Skeleton, Tooltip } from 'antd'
import { RobotOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'
import AgentLog from './AgentLog'
import MutationHeatmap from './MutationHeatmap'
import SynthesisExport from './SynthesisExport'
import NullDistribution from './NullDistribution'
import PdbViewer from './PdbViewer'

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

const SOURCE_LABELS = {
    TCRAFT: 'Vitiligo (TCRAFT)', PDAC: 'Pancreatic Cancer', AD_CSF: "Alzheimer's CSF",
    VDJdb: 'VDJdb (reference)', VDJdb_beta_only: 'VDJdb β-only', McPAS: 'McPAS',
    T: 'TCRAFT', V: 'VDJdb', P: 'PDAC', A: 'AD CSF', M: 'McPAS',
}

export default function TcrDetail({ point, provider, onClose }) {
    const [detail, setDetail] = useState(null)
    const [mutagenesis, setMutagenesis] = useState(null)
    const [loadingDetail, setLoadingDetail] = useState(false)
    const [loadingMutagenesis, setLoadingMutagenesis] = useState(false)
    const [showAgent, setShowAgent] = useState(false)
    const [agentKey, setAgentKey] = useState(0)

    const tcrId = point?.id ?? point?.tcr_id

    useEffect(() => {
        if (!tcrId) return
        setDetail(null)
        setMutagenesis(null)
        setShowAgent(false)

        // Fetch TCR detail
        setLoadingDetail(true)
        api.tcr(tcrId)
            .then(setDetail)
            .catch(() => { })
            .finally(() => setLoadingDetail(false))

        // Fetch mutagenesis (404 is fine)
        setLoadingMutagenesis(true)
        api.mutagenesis(tcrId)
            .then(setMutagenesis)
            .catch(() => setMutagenesis(null))
            .finally(() => setLoadingMutagenesis(false))

        // Auto-show AgentLog if a cached session exists
        api.getChatCacheStatus(tcrId, provider)
            .then(({ cached }) => { if (cached) setShowAgent(true) })
            .catch(() => { })
    }, [tcrId, provider])

    if (!point) return null

    const cdr3 = point.c ?? point.CDR3b ?? detail?.CDR3b ?? '—'
    const src = SOURCE_LABELS[point.s ?? point.source ?? detail?.source] ?? point.source ?? '—'
    const epitope = point.e ?? point.known_epitope ?? detail?.known_epitope
    const cat = point.a ?? point.antigen_category ?? detail?.antigen_category ?? 'unknown'

    const predictions = detail?.predictions ?? []
    const neighbors = detail?.nearest_neighbors ?? []

    // Normalise prediction scores for bar widths
    const scores = predictions.map(p => p.interaction_score ?? 0)
    const maxScore = Math.max(Math.abs(Math.min(...scores, 0)), Math.max(...scores, 0.01))

    return (
        <div style={{
            height: '100%', overflowY: 'auto',
            padding: '16px 14px',
            display: 'flex', flexDirection: 'column', gap: 12,
        }}>
            {/* ── ID + CDR3 header ── */}
            <div>
                <div style={{
                    fontSize: 11, color: 'var(--text-dim)',
                    fontFamily: 'JetBrains Mono, monospace', marginBottom: 4,
                }}>{tcrId}</div>
                <div style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 16, fontWeight: 600,
                    color: 'var(--color-primary)', letterSpacing: '0.05em',
                    wordBreak: 'break-all',
                }}>{cdr3}</div>
            </div>

            {/* ── Tags ── */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <Tag color="default" style={{ margin: 0 }}>{src}</Tag>
                <Tag color={cat === 'unknown' ? 'default' : undefined}
                    style={{
                        margin: 0,
                        background: `color-mix(in srgb, ${CAT_COLORS[cat]}, transparent 80%)`,
                        borderColor: `color-mix(in srgb, ${CAT_COLORS[cat]}, transparent 60%)`,
                        color: CAT_COLORS[cat]
                    }}>
                    {cat}
                </Tag>
                {epitope
                    ? <Tag color="error" style={{ margin: 0 }}>{epitope}</Tag>
                    : <Tag style={{ margin: 0, color: 'var(--text-dim)', borderColor: 'var(--border)' }}>dark matter</Tag>
                }
            </div>

            {/* ── V/J genes ── */}
            {(detail?.TRBV ?? detail?.TRAV) && (
                <div style={{ fontSize: 11, color: 'var(--text-dim)', opacity: 0.8, fontFamily: 'JetBrains Mono, monospace' }}>
                    {detail.TRBV && <span>TRBV: {detail.TRBV}</span>}
                    {detail.TRAV && <span style={{ marginLeft: 12 }}>TRAV: {detail.TRAV}</span>}
                </div>
            )}

            <Divider style={{ margin: '4px 0', borderColor: 'var(--border)' }} />

            {/* ── Annotate button ── */}
            {showAgent ? (
                <div style={{ height: 340 }}>
                    <AgentLog
                        key={agentKey}
                        tcrId={tcrId}
                        provider={provider}
                        onClose={() => setShowAgent(false)}
                    />
                </div>
            ) : (
                <Button
                    type="primary"
                    icon={<RobotOutlined />}
                    onClick={() => { setShowAgent(true); setAgentKey(k => k + 1) }}
                    className="glow-active"
                    block
                    style={{ background: 'linear-gradient(135deg, var(--color-primary), var(--color-accent))', border: 'none' }}
                >
                    Analyse with Agent
                </Button>
            )}

            <Divider style={{ margin: '4px 0', borderColor: 'rgba(255,255,255,0.08)' }} />

            {/* ── Predictions ── */}
            <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{
                        fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase',
                        fontWeight: 700, color: 'var(--text-dim)', marginBottom: 6,
                    }}>
                        DecoderTCR Predictions
                    </div>
                </div>
                <div style={{
                    fontSize: 10, color: 'var(--color-primary)', marginBottom: 12,
                    padding: '6px 8px', background: 'rgba(78, 205, 196, 0.1)',
                    border: '1px solid rgba(78, 205, 196, 0.2)', borderRadius: 6
                }}>
                    <strong>Viral Bias Note:</strong> Viral epitopes tend to score higher absolute values due to training data imbalance. Rely on the empirical Null Distribution (p-values) for true significance.
                </div>
                {loadingDetail && <Skeleton active paragraph={{ rows: 3 }} />}
                {!loadingDetail && predictions.length === 0 && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>No predictions available</span>
                )}
                {predictions.slice(0, 8).map((p, i) => {
                    const sc = p.interaction_score ?? 0
                    const pct = (Math.abs(sc) / maxScore) * 100
                    return (
                        <div key={i} style={{ marginBottom: 6 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
                                <span style={{ color: 'var(--text-main)', opacity: 0.8 }}>{p.epitope_name}</span>
                                <span style={{
                                    fontFamily: 'JetBrains Mono, monospace',
                                    color: sc > 0 ? 'var(--color-primary)' : 'var(--color-accent)', fontSize: 10,
                                }}>{sc.toFixed(4)}</span>
                            </div>
                            <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%', width: `${pct}%`,
                                    background: sc > 0 ? 'var(--color-primary)' : 'var(--color-accent)',
                                    borderRadius: 2, transition: 'width 0.4s ease',
                                }} />
                            </div>
                            {i === 0 && <NullDistribution epitope={p.epitope_name} score={sc} isDark={true} />}
                        </div>
                    )
                })}
            </div>

            <Divider style={{ margin: '4px 0', borderColor: 'var(--border)' }} />

            {/* ── Mutation heatmap ── */}
            <div>
                <SectionLabel>Mutation Landscape</SectionLabel>
                <MutationHeatmap data={mutagenesis} loading={loadingMutagenesis} />
            </div>

            {detail?.has_boltz2 && (
                <>
                    <Divider style={{ margin: '4px 0', borderColor: 'var(--border)' }} />
                    <div>
                        <SectionLabel>3D Structure (Boltz-2)</SectionLabel>
                        <PdbViewer tcrId={tcrId} />
                    </div>
                </>
            )}

            <Divider style={{ margin: '4px 0', borderColor: 'var(--border)' }} />

            {/* ── Neighbors ── */}
            <div>
                <SectionLabel>ESM-2 Nearest Neighbors</SectionLabel>
                {loadingDetail && <Skeleton active paragraph={{ rows: 3 }} />}
                {neighbors.slice(0, 6).map((n, i) => (
                    <div key={i} style={{
                        padding: '6px 0',
                        borderBottom: '1px solid var(--border)',
                        fontSize: 11,
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                            <span style={{ color: 'var(--text-dim)', fontFamily: 'JetBrains Mono, monospace', fontSize: 10 }}>
                                {n.tcr_id}
                            </span>
                            <span style={{ color: 'var(--color-primary)', fontSize: 10 }}>sim {n.similarity?.toFixed(3)}</span>
                        </div>
                        {n.cdr3b && (
                            <div style={{ color: 'var(--color-primary)', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{n.cdr3b}</div>
                        )}
                        {n.known_epitope && (
                            <Tag color="error" style={{ margin: '2px 0 0', fontSize: 10 }}>{n.known_epitope}</Tag>
                        )}
                    </div>
                ))}
                {neighbors.length === 0 && !loadingDetail && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Backend required for neighbor search</span>
                )}
            </div>

            <Divider style={{ margin: '4px 0', borderColor: 'var(--border)' }} />

            {/* ── Synthesis export ── */}
            <SynthesisExport tcrId={tcrId} epitope={epitope || predictions[0]?.epitope_name} />
        </div>
    )
}

function SectionLabel({ children }) {
    return (
        <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--text-dim)',
            marginBottom: 8,
        }}>{children}</div>
    )
}
