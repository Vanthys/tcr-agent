/**
 * AgentLog.jsx — The "wow" panel.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { Button, Spin, Modal, Collapse } from 'antd'
import {
    SearchOutlined,
    ThunderboltOutlined,
    ExperimentOutlined,
    RobotOutlined,
    CloseOutlined,
    ExpandAltOutlined,
} from '@ant-design/icons'
import { streamAnnotate } from '../api'
import ReactMarkdown from 'react-markdown'

const STEP_META = {
    neighbors: { icon: <SearchOutlined />, label: 'Neighbor Search', color: '#4ecdc4' },
    predictions: { icon: <ThunderboltOutlined />, label: 'DecoderTCR Scoring', color: '#fd9644' },
    mutagenesis: { icon: <ExperimentOutlined />, label: 'Mutation Landscape', color: '#c44569' },
    synthesis: { icon: <RobotOutlined />, label: 'AI Synthesis', color: '#a29bfe' },
}

const LEGACY_ACTION_META = {
    EXPLORE: { icon: <SearchOutlined />, color: '#4ecdc4' },
    COMPARE: { icon: <SearchOutlined />, color: '#fd9644' },
    SCORE: { icon: <ThunderboltOutlined />, color: '#e056fd' },
    ENGINEER: { icon: <ExperimentOutlined />, color: '#c44569' },
    SYNTHESIZE: { icon: <RobotOutlined />, color: '#a29bfe' },
}

const MARKDOWN_COMPONENTS = {
    h1: ({ node, ...props }) => <h1 style={{ fontSize: 13, margin: '12px 0 4px', color: 'var(--text-main)', fontWeight: 700 }} {...props} />,
    h2: ({ node, ...props }) => <h2 style={{ fontSize: 12, margin: '12px 0 4px', color: 'var(--text-main)', fontWeight: 700 }} {...props} />,
    h3: ({ node, ...props }) => <h3 style={{ fontSize: 11, margin: '8px 0 2px', color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }} {...props} />,
    p: ({ node, ...props }) => <p style={{ margin: '0 0 8px 0', whiteSpace: 'pre-wrap' }} {...props} />,
    ul: ({ node, ...props }) => <ul style={{ margin: '0 0 8px 0', paddingLeft: 18 }} {...props} />,
    ol: ({ node, ...props }) => <ol style={{ margin: '0 0 8px 0', paddingLeft: 18 }} {...props} />,
    li: ({ node, ...props }) => <li style={{ margin: '2px 0' }} {...props} />,
    strong: ({ node, ...props }) => <strong style={{ color: 'var(--text-main)', fontWeight: 700 }} {...props} />,
}

const MODAL_MARKDOWN_COMPONENTS = {
    ...MARKDOWN_COMPONENTS,
    h1: ({ node, ...props }) => <h1 style={{ fontSize: 16, margin: '16px 0 6px', color: 'var(--text-main)', fontWeight: 700 }} {...props} />,
    h2: ({ node, ...props }) => <h2 style={{ fontSize: 15, margin: '16px 0 6px', color: 'var(--text-main)', fontWeight: 700 }} {...props} />,
    h3: ({ node, ...props }) => <h3 style={{ fontSize: 13, margin: '12px 0 4px', color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }} {...props} />,
    p: ({ node, ...props }) => <p style={{ margin: '0 0 12px 0', whiteSpace: 'pre-wrap' }} {...props} />,
    ul: ({ node, ...props }) => <ul style={{ margin: '0 0 12px 0', paddingLeft: 22 }} {...props} />,
    ol: ({ node, ...props }) => <ol style={{ margin: '0 0 12px 0', paddingLeft: 22 }} {...props} />,
    li: ({ node, ...props }) => <li style={{ margin: '4px 0' }} {...props} />,
}

export default function AgentLog({ tcrId, provider, onClose }) {
    const [lines, setLines] = useState([])
    const [streaming, setStreaming] = useState(false)
    const [claudeText, setClaudeText] = useState('')
    const [done, setDone] = useState(false)
    const [isExpanded, setIsExpanded] = useState(false)
    const abortRef = useRef(null)
    const logBodyRef = useRef(null)
    const modalBodyRef = useRef(null)
    const seenStepsRef = useRef(new Set()) // Track headers already shown

    const appendLine = useCallback((line) => {
        setLines(prev => [...prev, line])
    }, [])

    useEffect(() => {
        if (!tcrId) return

        // Reset state
        setLines([{ type: 'detail', content: 'Initializing agent session...' }])
        setClaudeText('')
        setDone(false)
        setStreaming(true)
        seenStepsRef.current = new Set()

        if (abortRef.current) abortRef.current.abort()

        abortRef.current = streamAnnotate(tcrId, null, provider, (type, data) => {
            if (type === 'step') {
                // Determine if we need a new header
                let stepKey = data.step
                if (data.step === 'legacy_step') stepKey = `legacy_${data.action}`

                if (!seenStepsRef.current.has(stepKey)) {
                    seenStepsRef.current.add(stepKey)

                    if (data.step === 'synthesis') {
                        const label = data.provider === 'gemini' ? 'Gemini Synthesis' : 'Claude Synthesis'
                        appendLine({ type: 'step', step: 'synthesis', meta: { ...STEP_META.synthesis, label } })
                        appendLine({ type: 'claude-start' })
                    } else if (data.step === 'legacy_step') {
                        const baseMeta = LEGACY_ACTION_META[data.action] ?? { icon: <RobotOutlined />, color: '#a29bfe' }
                        appendLine({ type: 'step', step: data.step, meta: { ...baseMeta, label: data.label } })
                    } else {
                        const meta = STEP_META[data.step] ?? { label: data.step, icon: <RobotOutlined />, color: 'var(--text-dim)' }
                        appendLine({ type: 'step', step: data.step, meta })
                    }
                }

                // Append content details (don't repeat action/label headers)
                if (data.detail) {
                    appendLine({ type: 'detail', content: `  → ${data.detail}` })
                }
                if (data.summary) {
                    appendLine({ type: 'summary', content: data.summary })
                }

                // Tool Results (Unified for legacy and live)
                if (data.neighbors?.length) {
                    data.neighbors.filter(n => n.known_epitope).slice(0, 3).forEach(n => {
                        appendLine({
                            type: 'detail',
                            content: `  → ${n.tcr_id} sim=${Number(n.similarity).toFixed(4)} epitope: ${n.known_epitope}`,
                        })
                    })
                }
                if (data.top?.length) {
                    data.top.slice(0, 3).forEach(p => {
                        appendLine({
                            type: 'detail',
                            content: `  → ${p.epitope_name} score=${p.interaction_score?.toFixed(4)}`,
                        })
                    })
                }
                if (data.top_variants?.length) {
                    data.top_variants.slice(0, 3).forEach(v => {
                        appendLine({
                            type: 'detail',
                            content: `  → variant ${v.mutations} Δ${v.delta?.toFixed(4)}`,
                        })
                    })
                }

            } else if (type === 'text') {
                setClaudeText(prev => prev + data)

            } else if (type === 'done') {
                setStreaming(false)
                setDone(true)

            } else if (type === 'error') {
                appendLine({ type: 'error', content: String(data) })
                setStreaming(false)
            }
        })

        return () => { abortRef.current?.abort() }
    }, [tcrId, provider, appendLine])

    // Auto-scroll logic for both normal view and modal view
    useEffect(() => {
        const el = logBodyRef.current
        if (el) el.scrollTop = el.scrollHeight

        const modalEl = modalBodyRef.current
        if (modalEl) modalEl.scrollTop = modalEl.scrollHeight
    }, [lines, claudeText, isExpanded])

    // Parse Claude's XML structure dynamically during the stream
    const reasoningMatch = claudeText.match(/<reasoning>([\s\S]*?)(?:<\/reasoning>|$)/i);
    const reportMatch = claudeText.match(/<report>([\s\S]*?)(?:<\/report>|$)/i);
    const suggestionsMatch = claudeText.match(/<suggestions>([\s\S]*?)(?:<\/suggestions>|$)/i);

    const isUsingXML = /<(reasoning|report|suggestions)>/.test(claudeText);
    const reasoningText = reasoningMatch ? reasoningMatch[1].trim() : '';
    const reportText = reportMatch ? reportMatch[1].trim() : (isUsingXML ? '' : claudeText);
    const suggestionsText = suggestionsMatch ? suggestionsMatch[1].trim() : '';

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
                padding: '10px 14px',
                borderBottom: '1px solid var(--border)',
                background: 'var(--bg-base)',
                display: 'flex', alignItems: 'center', gap: 8,
                flexShrink: 0,
            }}>
                <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: streaming ? '#4ecdc4' : done ? '#2ecc71' : '#555',
                    boxShadow: streaming ? '0 0 8px #4ecdc4' : 'none',
                }} />
                <span style={{ color: 'var(--text-main)', flex: 1, fontSize: 11 }}>
                    AGENT LOG &nbsp;·&nbsp; {tcrId}
                </span>
                {streaming && <Spin size="small" />}

                <Button type="text" size="small" icon={<ExpandAltOutlined />}
                    onClick={() => setIsExpanded(true)}
                    style={{ color: 'var(--text-dim)' }}
                    title="Open in full modal"
                />

                {onClose && (
                    <Button type="text" size="small" icon={<CloseOutlined />}
                        onClick={onClose}
                        style={{ color: 'var(--text-dim)' }}
                    />
                )}
            </div>

            {/* Log body */}
            <div
                ref={logBodyRef}
                style={{
                    flex: 1, overflowY: 'auto', padding: '12px 14px',
                    display: 'flex', flexDirection: 'column', gap: 2,
                }}
            >
                {lines.map((line, i) => (
                    <LogLine key={i} line={line} />
                ))}

                {(claudeText || isUsingXML) && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
                        {reasoningText && (
                            <Collapse
                                ghost
                                size="small"
                                items={[{
                                    key: '1',
                                    label: <span style={{ color: 'var(--text-dim)', fontStyle: 'italic', fontSize: 11 }}>
                                        Agent Reasoning... {streaming && !reportText ? <Spin size="small" style={{ marginLeft: 8 }} /> : ''}
                                    </span>,
                                    children: <div style={{ color: 'var(--text-dim)', fontSize: 11, whiteSpace: 'pre-wrap', fontFamily: "'Inter', sans-serif" }}>{reasoningText}</div>
                                }]}
                            />
                        )}

                        {reportText && (
                            <div style={{
                                color: 'var(--text-main)',
                                lineHeight: 1.7,
                                fontFamily: "'Inter', sans-serif",
                                fontSize: 13,
                            }}>
                                <ReactMarkdown components={MARKDOWN_COMPONENTS}>
                                    {reportText + (streaming && !suggestionsText ? ' ▍' : '')}
                                </ReactMarkdown>
                            </div>
                        )}

                        {suggestionsText && (
                            <div style={{
                                marginTop: 8,
                                padding: '10px 14px',
                                background: 'rgba(78, 205, 196, 0.05)',
                                border: '1px solid rgba(78, 205, 196, 0.2)',
                                borderRadius: 8,
                            }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-primary)', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 4 }}>
                                    Suggested Action Items {streaming ? <Spin size="small" style={{ marginLeft: 8 }} /> : ''}
                                </div>
                                <div style={{
                                    color: 'var(--text-main)',
                                    lineHeight: 1.6,
                                    fontFamily: "'Inter', sans-serif",
                                    fontSize: 12,
                                }}>
                                    <ReactMarkdown components={MARKDOWN_COMPONENTS}>
                                        {suggestionsText + (streaming ? ' ▍' : '')}
                                    </ReactMarkdown>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Breakout Modal View */}
            <Modal
                title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <RobotOutlined style={{ color: 'var(--color-primary)' }} />
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14 }}>
                            AGENT SYNTHESIS REPORT · {tcrId}
                        </span>
                        {streaming && <Spin size="small" style={{ marginLeft: 8 }} />}
                    </div>
                }
                open={isExpanded}
                onCancel={() => setIsExpanded(false)}
                footer={null}
                width={800}
                centered
                bodyStyle={{
                    padding: 0,
                    height: '65vh',
                    display: 'flex',
                    flexDirection: 'column',
                    background: 'var(--bg-surface)'
                }}
            >
                <div
                    ref={modalBodyRef}
                    style={{
                        flex: 1, overflowY: 'auto', padding: '24px 32px',
                        display: 'flex', flexDirection: 'column', gap: 4,
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 13,
                    }}
                >
                    {lines.map((line, i) => (
                        <LogLine key={`modal-${i}`} line={line} />
                    ))}

                    {(claudeText || isUsingXML) && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 12 }}>
                            {reasoningText && (
                                <Collapse
                                    ghost
                                    size="small"
                                    items={[{
                                        key: '1',
                                        label: <span style={{ color: 'var(--text-dim)', fontStyle: 'italic', fontSize: 13 }}>
                                            Agent Reasoning... {streaming && !reportText ? <Spin size="small" style={{ marginLeft: 8 }} /> : ''}
                                        </span>,
                                        children: <div style={{ color: 'var(--text-dim)', fontSize: 13, whiteSpace: 'pre-wrap', fontFamily: "'Inter', sans-serif" }}>{reasoningText}</div>
                                    }]}
                                />
                            )}

                            {reportText && (
                                <div style={{
                                    color: 'var(--text-main)',
                                    lineHeight: 1.7,
                                    fontFamily: "'Inter', sans-serif",
                                    fontSize: 15,
                                }}>
                                    <ReactMarkdown components={MODAL_MARKDOWN_COMPONENTS}>
                                        {reportText + (streaming && !suggestionsText ? ' ▍' : '')}
                                    </ReactMarkdown>
                                </div>
                            )}

                            {suggestionsText && (
                                <div style={{
                                    marginTop: 12,
                                    padding: '14px 18px',
                                    background: 'rgba(78, 205, 196, 0.05)',
                                    border: '1px solid rgba(78, 205, 196, 0.2)',
                                    borderRadius: 10,
                                }}>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-primary)', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 8 }}>
                                        Suggested Action Items {streaming ? <Spin size="small" style={{ marginLeft: 8 }} /> : ''}
                                    </div>
                                    <div style={{
                                        color: 'var(--text-main)',
                                        lineHeight: 1.6,
                                        fontFamily: "'Inter', sans-serif",
                                        fontSize: 14,
                                    }}>
                                        <ReactMarkdown components={MODAL_MARKDOWN_COMPONENTS}>
                                            {suggestionsText + (streaming ? ' ▍' : '')}
                                        </ReactMarkdown>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </Modal>
        </div>
    )
}

function LogLine({ line }) {
    if (line.type === 'step') {
        const { meta } = line
        return (
            <div style={{
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
            <div style={{
                borderTop: '1px solid rgba(162,155,254,0.1)',
                marginTop: 8, marginBottom: 6,
            }} />
        )
    }

    if (line.type === 'summary' || line.type === 'detail') {
        return (
            <div style={{
                color: 'var(--text-dim)',
                lineHeight: 1.5,
                opacity: line.type === 'detail' ? 0.7 : 1,
                whiteSpace: 'pre-wrap'
            }}>
                {line.content}
            </div>
        )
    }

    if (line.type === 'error') {
        return (
            <div style={{ color: '#ff6b6b', lineHeight: 1.5 }}>
                ⚠ {line.content}
            </div>
        )
    }

    return null
}
