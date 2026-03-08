/**
 * PastChatsPage.jsx — Browse all cached agent analysis sessions.
 */
import { useState, useEffect, useCallback } from 'react'
import { Layout, Button, Popconfirm, Spin, Empty, Tag, Tooltip, Modal, Input } from 'antd'
import {
    RobotOutlined, DeleteOutlined, SearchOutlined,
    ClockCircleOutlined, HistoryOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, streamAnnotate } from '../api'
import AgentLog from '../components/AgentLog'

const { Header, Content } = Layout

const PROVIDER_COLORS = { claude: '#a29bfe', gemini: '#4ecdc4' }
const PROVIDER_LABELS = { claude: 'Claude', gemini: 'Gemini' }

function formatDate(iso) {
    try {
        return new Intl.DateTimeFormat('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        }).format(new Date(iso))
    } catch { return iso }
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
}

export default function PastChatsPage() {
    const navigate = useNavigate()
    const [chats, setChats] = useState([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [selected, setSelected] = useState(null) // { tcrId, provider }
    const [clearing, setClearing] = useState(null) // tcrId+provider being cleared

    const loadChats = useCallback(() => {
        setLoading(true)
        api.listAllChats()
            .then(setChats)
            .catch(() => setChats([]))
            .finally(() => setLoading(false))
    }, [])

    useEffect(() => { loadChats() }, [loadChats])

    const clearOne = async (tcrId, provider) => {
        setClearing(`${tcrId}-${provider}`)
        try { await api.clearChatCache(tcrId, provider) } catch { /* ignore */ }
        setClearing(null)
        loadChats()
        if (selected?.tcrId === tcrId && selected?.provider === provider) {
            setSelected(null)
        }
    }

    const filtered = chats.filter(c =>
        c.tcr_id.toLowerCase().includes(search.toLowerCase()) ||
        c.provider.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <Layout style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-base)' }}>
            {/* Top nav */}
            <Header style={{
                background: 'var(--bg-surface)',
                borderBottom: '1px solid var(--border)',
                padding: '0 20px',
                height: 52,
                display: 'flex', alignItems: 'center', gap: 16,
                flexShrink: 0,
            }}>
                {/* Logo */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                        width: 28, height: 28, borderRadius: 8,
                        background: 'linear-gradient(135deg, #4ecdc4, #a29bfe)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 800, color: '#0d0f17',
                    }}>TCR</div>
                    <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)', lineHeight: 1.2 }}>
                            TCR Agent
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.2 }}>
                            Past Agent Analyses
                        </div>
                    </div>
                </div>

                {/* Page title */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '4px 10px',
                    background: 'rgba(162, 155, 254, 0.1)',
                    border: '1px solid rgba(162, 155, 254, 0.2)',
                    borderRadius: 20,
                    fontSize: 11, fontWeight: 600, color: '#a29bfe',
                    letterSpacing: '0.04em',
                }}>
                    <HistoryOutlined /> Past Chats
                </div>

                <div style={{ flex: 1 }} />

                <Input
                    placeholder="Search TCR ID or provider…"
                    prefix={<SearchOutlined style={{ color: 'var(--text-dim)' }} />}
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    allowClear
                    size="small"
                    variant="filled"
                    style={{ width: 280 }}
                />

                <Button
                    type="text" size="small" icon={<ReloadOutlined />}
                    onClick={loadChats} loading={loading}
                    style={{ color: 'var(--text-dim)' }}
                />

                <Button
                    size="small"
                    onClick={() => navigate('/')}
                    style={{ color: 'var(--text-dim)', borderColor: 'var(--border)' }}
                >
                    ← Back to Explorer
                </Button>
            </Header>

            {/* Body */}
            <Content style={{
                flex: 1, overflow: 'hidden',
                display: 'flex', gap: 0,
            }}>
                {/* Sidebar list */}
                <div style={{
                    width: 320, flexShrink: 0,
                    borderRight: '1px solid var(--border)',
                    overflowY: 'auto',
                    background: 'var(--bg-surface)',
                }}>
                    {loading && (
                        <div style={{ padding: 32, textAlign: 'center' }}>
                            <Spin />
                        </div>
                    )}
                    {!loading && filtered.length === 0 && (
                        <div style={{ padding: 32 }}>
                            <Empty
                                description={
                                    <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>
                                        No cached analyses yet.<br />
                                        Run an agent analysis on any TCR to see it here.
                                    </span>
                                }
                            />
                        </div>
                    )}
                    {filtered.map(chat => {
                        const key = `${chat.tcr_id}-${chat.provider}`
                        const isActive = selected?.tcrId === chat.tcr_id && selected?.provider === chat.provider
                        const isLoadingClear = clearing === key
                        return (
                            <div
                                key={key}
                                onClick={() => setSelected({ tcrId: chat.tcr_id, provider: chat.provider })}
                                style={{
                                    padding: '12px 14px',
                                    borderBottom: '1px solid var(--border)',
                                    cursor: 'pointer',
                                    background: isActive
                                        ? 'rgba(78, 205, 196, 0.08)'
                                        : 'transparent',
                                    borderLeft: isActive
                                        ? '2px solid var(--color-primary)'
                                        : '2px solid transparent',
                                    transition: 'all 0.15s ease',
                                    display: 'flex', flexDirection: 'column', gap: 6,
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                                    <span style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: 12, fontWeight: 600,
                                        color: isActive ? 'var(--color-primary)' : 'var(--text-main)',
                                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                    }}>
                                        {chat.tcr_id}
                                    </span>

                                    <Popconfirm
                                        title="Delete this cached analysis?"
                                        onConfirm={e => { e?.stopPropagation(); clearOne(chat.tcr_id, chat.provider) }}
                                        onCancel={e => e?.stopPropagation()}
                                        okText="Delete"
                                        cancelText="Cancel"
                                        okButtonProps={{ danger: true }}
                                        placement="right"
                                    >
                                        <Button
                                            type="text" size="small"
                                            icon={<DeleteOutlined />}
                                            loading={isLoadingClear}
                                            onClick={e => e.stopPropagation()}
                                            style={{ color: 'var(--text-dim)', flexShrink: 0 }}
                                        />
                                    </Popconfirm>
                                </div>

                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <Tag style={{
                                        margin: 0, fontSize: 10,
                                        color: PROVIDER_COLORS[chat.provider],
                                        background: `${PROVIDER_COLORS[chat.provider]}18`,
                                        borderColor: `${PROVIDER_COLORS[chat.provider]}40`,
                                    }}>
                                        <RobotOutlined style={{ marginRight: 3 }} />
                                        {PROVIDER_LABELS[chat.provider] ?? chat.provider}
                                    </Tag>
                                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                                        {formatSize(chat.payload_size)}
                                    </span>
                                </div>

                                <div style={{
                                    fontSize: 10, color: 'var(--text-dim)',
                                    display: 'flex', alignItems: 'center', gap: 4,
                                }}>
                                    <ClockCircleOutlined />
                                    {formatDate(chat.cached_at)}
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* Detail panel */}
                <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                    {!selected ? (
                        <div style={{
                            flex: 1, display: 'flex', flexDirection: 'column',
                            alignItems: 'center', justifyContent: 'center', gap: 16,
                            color: 'var(--text-dim)',
                        }}>
                            <HistoryOutlined style={{ fontSize: 48, opacity: 0.3 }} />
                            <div style={{ fontSize: 13, opacity: 0.6 }}>
                                Select a cached analysis from the list
                            </div>
                        </div>
                    ) : (
                        <div style={{ flex: 1, overflow: 'hidden', padding: '16px 20px' }}>
                            <div style={{ marginBottom: 12, fontSize: 11, color: 'var(--text-dim)', fontFamily: "'JetBrains Mono', monospace" }}>
                                <RobotOutlined style={{ marginRight: 6 }} />
                                {selected.tcrId} · {PROVIDER_LABELS[selected.provider] ?? selected.provider}
                            </div>
                            <div style={{ height: 'calc(100% - 36px)' }}>
                                <AgentLog
                                    key={`${selected.tcrId}-${selected.provider}`}
                                    tcrId={selected.tcrId}
                                    provider={selected.provider}
                                />
                            </div>
                        </div>
                    )}
                </div>
            </Content>
        </Layout>
    )
}
