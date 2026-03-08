/**
 * AgentLog.jsx — The "wow" panel.
 *
 * Calls POST /api/annotate and renders the streaming SSE response
 * as a terminal-style log with per-step headers and Claude text
 * flowing in token by token.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { Button, Tag, Spin } from 'antd'
import {
    SearchOutlined,
    ThunderboltOutlined,
    ExperimentOutlined,
    RobotOutlined,
    CloseOutlined,
} from '@ant-design/icons'
import { streamAnnotate } from '../api'
import ReactMarkdown from 'react-markdown'

const STEP_META = {
    neighbors: { icon: <SearchOutlined />, label: 'Neighbor Search', color: '#4ecdc4' },
    predictions: { icon: <ThunderboltOutlined />, label: 'DecoderTCR Scoring', color: '#fd9644' },
    mutagenesis: { icon: <ExperimentOutlined />, label: 'Mutation Landscape', color: '#c44569' },
    synthesis: { icon: <RobotOutlined />, label: 'Claude Synthesis', color: '#a29bfe' },
}

const LEGACY_ACTION_META = {
    EXPLORE: { icon: <SearchOutlined />, color: '#4ecdc4' },
    COMPARE: { icon: <SearchOutlined />, color: '#fd9644' },
    SCORE: { icon: <ThunderboltOutlined />, color: '#e056fd' },
    ENGINEER: { icon: <ExperimentOutlined />, color: '#c44569' },
    SYNTHESIZE: { icon: <RobotOutlined />, color: '#a29bfe' },
}

export default function AgentLog({ tcrId, provider, onClose }) {
    const [lines, setLines] = useState([])       // {type, content}
    const [streaming, setStreaming] = useState(false)
    const [claudeText, setClaudeText] = useState('')
    const [done, setDone] = useState(false)
    const abortRef = useRef(null)
    const bottomRef = useRef(null)

    const appendLine = useCallback((line) => {
        setLines(prev => [...prev, line])
    }, [])

    useEffect(() => {
        if (!tcrId) return

        // Reset state
        setLines([])
        setClaudeText('')
        setDone(false)
        setStreaming(true)

        if (abortRef.current) abortRef.current.abort()

        abortRef.current = streamAnnotate(tcrId, null, provider, (type, data) => {
            if (type === 'step') {
                if (data.step === 'legacy_step') {
                    const baseMeta = LEGACY_ACTION_META[data.action] ?? { icon: <RobotOutlined />, color: '#a29bfe' }
                    const meta = { ...baseMeta, label: data.label }

                    appendLine({ type: 'step', step: data.step, meta, data })

                    if (data.detail) {
                        appendLine({ type: 'detail', content: `  → ${data.detail}` })
                    }

                    if (data.action === 'SYNTHESIZE' && !data.detail) {
                        // wait for text stream
                        appendLine({ type: 'claude-start' })
                    }
                    return
                }

                const meta = STEP_META[data.step] ?? {}

                // Always emit the step header
                appendLine({ type: 'step', step: data.step, meta, data })

                // Emit summary line if present
                if (data.summary) {
                    appendLine({ type: 'summary', content: data.summary })
                }

                // Emit neighbor details
                if (data.step === 'neighbors' && data.neighbors?.length) {
                    const annotated = data.neighbors.filter(n => n.known_epitope)
                    if (annotated.length) {
                        annotated.slice(0, 3).forEach(n => {
                            appendLine({
                                type: 'detail',
                                content: `  → ${n.tcr_id}  sim=${n.similarity}  epitope: ${n.known_epitope}`,
                            })
                        })
                    }
                }

                // Emit top predictions
                if (data.step === 'predictions' && data.top?.length) {
                    data.top.slice(0, 3).forEach(p => {
                        appendLine({
                            type: 'detail',
                            content: `  → ${p.epitope_name}  score=${p.interaction_score?.toFixed(4)}  [${p.epitope_category}]`,
                        })
                    })
                }

                // Mutagenesis variants
                if (data.step === 'mutagenesis' && data.available && data.top_variants?.length) {
                    data.top_variants.forEach(v => {
                        appendLine({
                            type: 'detail',
                            content: `  → variant ${v.mutations}  Δ${v.delta > 0 ? '+' : ''}${v.delta?.toFixed(4)}  (hypothesis)`,
                        })
                    })
                }

                if (data.step === 'synthesis') {
                    appendLine({ type: 'claude-start' })
                }

            } else if (type === 'text') {
                setClaudeText(prev => prev + data)

            } else if (type === 'done') {
                setStreaming(false)
                setDone(true)

            } else if (type === 'error') {
                appendLine({ type: 'error', content: data })
                setStreaming(false)
            }
        })

        return () => { abortRef.current?.abort() }
    }, [tcrId, appendLine])

    // Auto-scroll
    useEffect(() => {
        // High-frequency token streaming causes 'smooth' to stutter/jump if called continuously.
        bottomRef.current?.scrollIntoView({ behavior: 'auto' })
    }, [lines, claudeText])

    return (
        <div style={{
            display: 'flex', flexDirection: 'column', height: '100%',
            background: 'var(--bg-surface)', borderRadius: 10,
            border: '1px solid var(--border)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 12,
            overflow: 'hidden',
        }}>
            {/* Header bar */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 14px',
                borderBottom: '1px solid var(--border)',
                background: 'var(--bg-base)',
                flexShrink: 0,
            }}>
                <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: streaming ? '#4ecdc4' : done ? '#2ecc71' : '#555',
                    boxShadow: streaming ? '0 0 8px #4ecdc4' : 'none',
                    transition: 'all 0.3s',
                }} />
                <span style={{ color: 'var(--text-main)', flex: 1, fontSize: 11 }}>
                    TCR AGENT &nbsp;·&nbsp; {tcrId}
                </span>
                {streaming && <Spin size="small" />}
                {onClose && (
                    <Button type="text" size="small" icon={<CloseOutlined />}
                        onClick={onClose}
                        style={{ color: 'var(--text-dim)' }}
                    />
                )}
            </div>

            {/* Log body */}
            <div style={{
                flex: 1, overflowY: 'auto', padding: '12px 14px',
                display: 'flex', flexDirection: 'column', gap: 2,
            }}>
                {lines.map((line, i) => (
                    <LogLine key={i} line={line} />
                ))}

                {/* Claude streaming text */}
                {claudeText && (
                    <div className="log-line clause-markdown" style={{
                        color: 'var(--text-main)',
                        lineHeight: 1.7,
                        marginTop: 6,
                        fontFamily: "'Inter', sans-serif",
                        fontSize: 13,
                    }}>
                        <ReactMarkdown>
                            {claudeText + (streaming ? ' ▍' : '')}
                        </ReactMarkdown>
                    </div>
                )}

                <div ref={bottomRef} />
            </div>
        </div>
    )
}

function LogLine({ line }) {
    if (line.type === 'step') {
        const { meta } = line
        return (
            <div className="log-line" style={{
                display: 'flex', alignItems: 'center', gap: 8,
                marginTop: 10, marginBottom: 4,
                color: meta.color ?? 'var(--text-main)',
                fontWeight: 600, fontSize: 11, letterSpacing: '0.05em',
            }}>
                <span style={{ fontSize: 14 }}>{meta.icon}</span>
                <span style={{ textTransform: 'uppercase' }}>{meta.label}</span>
                <span style={{
                    flex: 1, height: 1,
                    background: `linear-gradient(to right, ${meta.color}44, transparent)`,
                    marginLeft: 4,
                }} />
            </div>
        )
    }

    if (line.type === 'claude-start') {
        return (
            <div className="log-line" style={{
                borderTop: '1px solid rgba(162,155,254,0.2)',
                marginTop: 8, marginBottom: 6,
            }} />
        )
    }

    if (line.type === 'summary') {
        return (
            <div className="log-line" style={{ color: 'var(--text-dim)', lineHeight: 1.5 }}>
                {line.content}
            </div>
        )
    }

    if (line.type === 'detail') {
        return (
            <div className="log-line" style={{ color: 'var(--text-dim)', opacity: 0.8, lineHeight: 1.5 }}>
                {line.content}
            </div>
        )
    }

    if (line.type === 'error') {
        return (
            <div className="log-line" style={{ color: '#ff6b6b', lineHeight: 1.5 }}>
                ⚠ {line.content}
            </div>
        )
    }

    return null
}
