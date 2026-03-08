/**
 * AgentLog.jsx — The "wow" panel.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { Button, Spin, Modal, Collapse, Tooltip } from 'antd'
import {
    SearchOutlined,
    ThunderboltOutlined,
    ExperimentOutlined,
    RobotOutlined,
    CloseOutlined,
    ExpandAltOutlined,
    CheckCircleOutlined,
} from '@ant-design/icons'
import { api } from '../api'
import ReactMarkdown from 'react-markdown'
import { PlayCircleOutlined, LoadingOutlined, WarningOutlined } from '@ant-design/icons'

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

export default function AgentLog({ tcrId, provider, onClose, messageId: presetMessageId }) {
    const [lines, setLines] = useState([])
    const [streaming, setStreaming] = useState(false)
    const [claudeText, setClaudeText] = useState('')
    const [done, setDone] = useState(false)
    const [isExpanded, setIsExpanded] = useState(false)
    const [messageId, setMessageId] = useState(null)
    const [activeJobs, setActiveJobs] = useState([])
    const [followups, setFollowups] = useState([])
    const abortRef = useRef(null)
    const reconnectTimerRef = useRef(null)
    const logBodyRef = useRef(null)
    const modalBodyRef = useRef(null)
    const seenStepsRef = useRef(new Set())
    const stageLogRef = useRef(new Map())
    const jobLabelsRef = useRef(new Map())
    const statusRef = useRef('idle')

    const appendLine = useCallback((line) => {
        setLines(prev => [...prev, line])
    }, [])

    const handleStageEvent = useCallback((stage) => {
        if (!stage?.name) return
        const stepKey = stage.name
        if (!seenStepsRef.current.has(stepKey)) {
            seenStepsRef.current.add(stepKey)
            if (stepKey === 'synthesis') {
                const label = stage.label || (provider === 'gemini' ? 'Gemini Synthesis' : 'Claude Synthesis')
                appendLine({ type: 'step', step: 'synthesis', meta: { ...STEP_META.synthesis, label } })
                appendLine({ type: 'claude-start' })
            } else {
                const meta = STEP_META[stepKey] ?? { label: stepKey, icon: <RobotOutlined />, color: 'var(--text-dim)' }
                appendLine({ type: 'step', step: stepKey, meta })
            }
        }

        const stageState = stageLogRef.current.get(stepKey) ?? { detailLogged: false, finalLogged: false }
        if (stage.detail && !stageState.detailLogged) {
            appendLine({ type: 'detail', content: `▸ ${stage.detail}` })
            stageState.detailLogged = true
        }

        const isFinal = stage.status === 'done' || stage.status === 'error'
        if (!isFinal || stageState.finalLogged) {
            stageLogRef.current.set(stepKey, stageState)
            return
        }

        if (stage.summary) appendLine({ type: 'summary', content: stage.summary })

        const payload = stage?.payload ?? {}

        if (Array.isArray(payload.neighbors) && payload.neighbors.length > 0) {
            payload.neighbors
                .slice(0, 3)
                .forEach(n => {
                    const sim = typeof n?.similarity === 'number' ? n.similarity.toFixed(3) : '?'
                    const pieces = [
                        n?.tcr_id ? `ID ${n.tcr_id}` : null,
                        `sim=${sim}`,
                        n?.known_epitope ? `epitope:${n.known_epitope}` : null,
                    ].filter(Boolean)
                    appendLine({ type: 'detail', content: `▸ ${pieces.join(' · ')}` })
                })
        }

        if (Array.isArray(payload.predictions) && payload.predictions.length > 0) {
            payload.predictions
                .slice(0, 3)
                .forEach(p => {
                    const score = typeof p?.interaction_score === 'number'
                        ? p.interaction_score.toFixed(3)
                        : 'N/A'
                    const label = p?.epitope_name ?? 'Prediction'
                    appendLine({ type: 'detail', content: `▸ ${label} score=${score}` })
                })
        }

        if (Array.isArray(payload.top_variants) && payload.top_variants.length > 0) {
            payload.top_variants
                .slice(0, 3)
                .forEach(v => {
                    const muts = v?.mutations ?? 'variant'
                    const delta = typeof v?.delta === 'number' ? `Δ${v.delta.toFixed(3)}` : ''
                    const score = typeof v?.predicted_score === 'number' ? `score ${v.predicted_score.toFixed(3)}` : ''
                    const note = v?.note ? `(${v.note})` : ''
                    const pieces = [muts, score, delta, note].filter(Boolean).join(' ')
                    appendLine({ type: 'detail', content: `▸ ${pieces}` })
                })
        }

        stageState.finalLogged = true
        stageLogRef.current.set(stepKey, stageState)
    }, [appendLine, provider])

    const handleStreamEvent = useCallback((event, raw) => {
        if (!raw) return
        try {
            const payload = JSON.parse(raw)
            if (event === 'stage') {
                handleStageEvent(payload)
            } else if (event === 'chunk') {
                setClaudeText(prev => prev + (payload.text ?? ''))
            } else if (event === 'status') {
                statusRef.current = payload.status
                if (payload.status === 'done') {
                    setStreaming(false)
                    setDone(true)
                } else if (payload.status === 'failed') {
                    setStreaming(false)
                    appendLine({ type: 'error', content: payload.error || 'Agent run failed' })
                } else {
                    setStreaming(true)
                }
            } else if (event === 'followup') {
                setFollowups(prev => [...prev, payload])
            }
        } catch {
            // ignore
        }
    }, [appendLine, handleStageEvent])

    const handleJobStart = useCallback((jobId, label) => {
        jobLabelsRef.current.set(jobId, label)
        setActiveJobs(js => [...js, { id: jobId, label, state: 'running' }])
    }, [])

    const handleJobDone = useCallback((jobId, label, result) => {
        setActiveJobs(js => js.map(j => j.id === jobId ? { ...j, state: 'done', result } : j))
        jobLabelsRef.current.delete(jobId)
        if (typeof result === 'string' && result.trim()) {
            appendLine({ type: 'job-result', label, content: result.trim() })
        }
    }, [appendLine])

    const handleJobError = useCallback((jobId, label, error) => {
        setActiveJobs(js => js.map(j => j.id === jobId ? { ...j, state: 'error', error } : j))
        jobLabelsRef.current.delete(jobId)
        if (error) appendLine({ type: 'error', content: `${label}: ${error}` })
    }, [appendLine])

    const startStream = useCallback((msgId) => {
        if (!msgId) return
        statusRef.current = 'running'
        setStreaming(true)
        if (abortRef.current) abortRef.current.abort()
        abortRef.current = api.streamChat(msgId, {
            onEvent: (event, data) => handleStreamEvent(event, data),
            onError: () => {},
            onClose: () => {
                if (statusRef.current === 'running') {
                    reconnectTimerRef.current = setTimeout(() => startStream(msgId), 1200)
                } else {
                    setStreaming(false)
                }
            }
        })
    }, [handleStreamEvent])

    useEffect(() => {
        if (!tcrId && !presetMessageId) return

        let cancelled = false
        const intro = presetMessageId ? 'Loading saved agent session...' : 'Initializing agent session...'
        setLines([{ type: 'detail', content: intro }])
        setClaudeText('')
        setDone(false)
        setStreaming(true)
        setMessageId(null)
        setFollowups([])
        seenStepsRef.current = new Set()
        stageLogRef.current = new Map()
        jobLabelsRef.current = new Map()
        statusRef.current = 'running'

        if (abortRef.current) abortRef.current.abort()
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current)
            reconnectTimerRef.current = null
        }

        const boot = async () => {
            if (presetMessageId) {
                setMessageId(presetMessageId)
                startStream(presetMessageId)
                return
            }
            try {
                const res = await api.startChat({ tcrId, provider })
                if (cancelled) return
                setMessageId(res.message_id)
                startStream(res.message_id)
            } catch (err) {
                if (cancelled) return
                setStreaming(false)
                appendLine({ type: 'error', content: err?.detail || err?.message || String(err) })
            }
        }
        boot()

        return () => {
            cancelled = true
            abortRef.current?.abort()
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current)
                reconnectTimerRef.current = null
            }
        }
    }, [tcrId, provider, presetMessageId, appendLine, startStream])
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
                <span style={{ color: 'var(--text-main)', flex: 1, fontSize: 11, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span>AGENT LOG · {tcrId}</span>
                    {messageId && (
                        <Tooltip title={`Session ${messageId}`}>
                            <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>#{messageId.slice(0, 8)}</span>
                        </Tooltip>
                    )}
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
                            <SuggestionButtons
                                suggestionsText={suggestionsText}
                                streaming={streaming}
                                tcrId={tcrId}
                                provider={provider}
                                onJobStart={handleJobStart}
                                onJobDone={handleJobDone}
                                onJobError={handleJobError}
                            />
                        )}

                        {/* Historical followups */}
                        {followups.map((f, i) => (
                            <JobCard key={`fu-${i}`} job={{
                                id: `fu-${i}`,
                                label: f.suggestion?.label || 'Job run',
                                state: 'done',
                                result: f.analysis
                            }} compact />
                        ))}

                        {/* Inline active job result cards */}
                        {activeJobs.map((job) => (
                            <JobCard key={job.id} job={job} compact />
                        ))}
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
                styles={{
                    body: {
                        padding: 0,
                        height: '65vh',
                        display: 'flex',
                        flexDirection: 'column',
                        background: 'var(--bg-surface)'
                    }
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
                                <SuggestionButtons
                                    suggestionsText={suggestionsText}
                                    streaming={streaming}
                                    tcrId={tcrId}
                                    provider={provider}
                                    onJobStart={handleJobStart}
                                    onJobDone={handleJobDone}
                                    onJobError={handleJobError}
                                />
                            )}

                            {/* Historical followups */}
                            {followups.map((f, i) => (
                                <JobCard key={`fu-modal-${i}`} job={{
                                    id: `fu-modal-${i}`,
                                    label: f.suggestion?.label || 'Job run',
                                    state: 'done',
                                    result: f.analysis
                                }} />
                            ))}

                            {/* Inline active job result cards */}
                            {activeJobs.map((job) => (
                                <JobCard key={job.id} job={job} />
                            ))}
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

    if (line.type === 'job-result') {
        return (
            <div style={{
                marginTop: 10,
                padding: '10px 12px',
                border: '1px solid rgba(162,155,254,0.2)',
                borderRadius: 8,
                background: 'rgba(162,155,254,0.06)',
            }}>
                <div style={{
                    fontSize: 10,
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                    color: 'var(--color-primary)',
                    marginBottom: 6,
                }}>
                    Follow-up · {line.label}
                </div>
                <div style={{ fontFamily: "'Inter', sans-serif", color: 'var(--text-main)', fontSize: 12, lineHeight: 1.6 }}>
                    <ReactMarkdown components={MARKDOWN_COMPONENTS}>
                        {line.content}
                    </ReactMarkdown>
                </div>
            </div>
        )
    }

    return null
}

const SUGGESTION_COLORS = {
    expand_neighbors: { bg: 'rgba(78,205,196,0.08)', border: 'rgba(78,205,196,0.3)', accent: '#4ecdc4' },
    compute_mutagenesis: { bg: 'rgba(196,69,105,0.08)', border: 'rgba(196,69,105,0.3)', accent: '#c44569' },
}

function SuggestionButtons({ suggestionsText, streaming, tcrId, provider, onJobStart, onJobDone, onJobError, onJobFullComplete }) {
    const [jobStates, setJobStates] = useState({}) // { idx: 'idle'|'running'|'done'|'error' }
    const pollerRefs = useRef({})

    // Try to parse as JSON; fall back to plain text
    let suggestions = null
    try {
        const trimmed = suggestionsText.trim()
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed) && parsed.length > 0) suggestions = parsed
    } catch { /* fall through */ }

    // Fallback: still-streaming (show placeholder) or truly unstructured markdown
    if (!suggestions) {
        return (
            <div style={{
                marginTop: 8, padding: '10px 14px',
                background: 'rgba(78,205,196,0.05)',
                border: '1px solid rgba(78,205,196,0.2)', borderRadius: 8,
                display: 'flex', alignItems: 'center', gap: 8,
            }}>
                {streaming
                    ? <><Spin size="small" /><span style={{ fontSize: 11, color: 'var(--text-dim)', fontStyle: 'italic' }}>Drafting suggested next steps…</span></>
                    : <div style={{ color: 'var(--text-dim)', fontSize: 12, whiteSpace: 'pre-wrap', fontFamily: "'Inter', sans-serif" }}>{suggestionsText}</div>
                }
            </div>
        )
    }

    const startJob = async (suggestion, idx) => {
        setJobStates(s => ({ ...s, [idx]: 'running' }))
        const jobId = `${Date.now()}-${idx}-${suggestion.type}`
        onJobStart?.(jobId, suggestion.label)

        let resultText = ''

        try {
            api.dispatchSuggestion(tcrId, provider, suggestion, {
                onMessage: (event, data) => {
                    // Update job label if it's a step
                    if (event === 'step') {
                        try {
                            const parsed = JSON.parse(data)
                            // We don't overwrite the main row label, but we could
                        } catch { }
                    } else if (event === 'raw_result') {
                        // We could show the raw result, but we'll wait for the LLM analysis
                    } else if (event === 'text') {
                        try {
                            const chunk = JSON.parse(data)
                            resultText += chunk
                            setJobStates(s => ({ ...s, [idx]: 'done' }))
                            onJobDone?.(jobId, suggestion.label, resultText)
                        } catch { }
                    }
                },
                onError: (err) => {
                    setJobStates(s => ({ ...s, [idx]: 'error' }))
                    onJobError?.(jobId, suggestion.label, err.message || String(err))
                },
                onClose: () => {
                    setJobStates(s => ({ ...s, [idx]: 'done' }))
                    onJobDone?.(jobId, suggestion.label, resultText)
                    onJobFullComplete?.()
                }
            })
        } catch (e) {
            setJobStates(s => ({ ...s, [idx]: 'error' }))
            onJobError?.(jobId, suggestion.label, String(e))
        }
    }

    return (
        <div style={{
            marginTop: 8, padding: '10px 14px',
            background: 'rgba(78,205,196,0.04)',
            border: '1px solid rgba(78,205,196,0.15)', borderRadius: 8,
        }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-primary)', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 8 }}>
                Suggested Next Steps
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {suggestions.map((s, idx) => {
                    const state = jobStates[idx] ?? 'idle'
                    const colors = SUGGESTION_COLORS[s.type] ?? SUGGESTION_COLORS.expand_neighbors
                    return (
                        <div key={idx} style={{
                            display: 'flex', alignItems: 'flex-start', gap: 10,
                            padding: '8px 10px',
                            background: colors.bg,
                            border: `1px solid ${colors.border}`,
                            borderRadius: 6,
                        }}>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-main)', marginBottom: 2 }}>
                                    {s.label}
                                </div>
                                {s.reason && (
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.5, fontFamily: "'Inter', sans-serif" }}>
                                        {s.reason}
                                    </div>
                                )}
                            </div>
                            <Tooltip title={
                                state === 'done' ? 'Done — result added below' :
                                    state === 'error' ? 'Job failed' :
                                        state === 'running' ? 'Running…' : 'Run this analysis'
                            }>
                                <Button
                                    type="text" size="small"
                                    icon={
                                        state === 'running' ? <LoadingOutlined style={{ color: colors.accent }} /> :
                                            state === 'done' ? <CheckCircleOutlined style={{ color: '#2ecc71' }} /> :
                                                state === 'error' ? <WarningOutlined style={{ color: '#ff6b6b' }} /> :
                                                    <PlayCircleOutlined style={{ color: colors.accent }} />
                                    }
                                    disabled={state !== 'idle'}
                                    onClick={() => startJob(s, idx)}
                                    style={{ flexShrink: 0 }}
                                />
                            </Tooltip>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function JobCard({ job, compact }) {
    const isRunning = job.state === 'running'
    const isError = job.state === 'error'

    return (
        <div style={{
            marginTop: 8,
            padding: compact ? '8px 10px' : '12px 16px',
            background: isError ? 'rgba(255,107,107,0.06)' : isRunning ? 'rgba(162,155,254,0.06)' : 'rgba(46,204,113,0.06)',
            border: `1px solid ${isError ? 'rgba(255,107,107,0.25)' : isRunning ? 'rgba(162,155,254,0.25)' : 'rgba(46,204,113,0.25)'}`,
            borderRadius: 8,
        }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: (isRunning || isError) ? 0 : 8 }}>
                {isRunning && <LoadingOutlined style={{ color: '#a29bfe', fontSize: 12 }} />}
                {!isRunning && !isError && <CheckCircleOutlined style={{ color: '#2ecc71', fontSize: 12 }} />}
                {isError && <WarningOutlined style={{ color: '#ff6b6b', fontSize: 12 }} />}
                <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    color: isError ? '#ff6b6b' : isRunning ? '#a29bfe' : '#2ecc71',
                }}>
                    {isRunning ? `Running: ${job.label}` : isError ? `Failed: ${job.label}` : job.label}
                </span>
            </div>

            {/* Animated progress bar while running */}
            {isRunning && (
                <div style={{ marginTop: 6, height: 2, background: 'rgba(162,155,254,0.15)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{
                        height: '100%', width: '40%',
                        background: 'linear-gradient(90deg, transparent, #a29bfe, transparent)',
                        animation: 'slide-bar 1.5s ease-in-out infinite',
                    }} />
                </div>
            )}

            {/* Result text — markdown */}
            {job.state === 'done' && job.result && (
                <div style={{
                    marginTop: 8,
                    color: 'var(--text-main)',
                    fontFamily: "'Inter', sans-serif",
                    fontSize: compact ? 13 : 15,
                    lineHeight: 1.7,
                }}>
                    <ReactMarkdown components={compact ? MARKDOWN_COMPONENTS : MODAL_MARKDOWN_COMPONENTS}>
                        {job.result}
                    </ReactMarkdown>
                </div>
            )}

            {/* Error message */}
            {isError && job.error && (
                <div style={{ marginTop: 6, fontSize: 10, color: '#ff6b6b', fontFamily: "'Inter', sans-serif" }}>
                    {job.error}
                </div>
            )}
        </div>
    )
}


