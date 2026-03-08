/**
 * ExploreTopNav.jsx — Top header bar for the Explore page.
 *
 * Responsibilities: logo, TCR count, search bar, filters, theme toggle,
 * backend status indicator, and UMAP recompute trigger.
 */
import { Layout, Select, AutoComplete, Badge, Tooltip, Spin, Button, Input, Popconfirm } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
    ApiOutlined,
    FilterOutlined,
    SunOutlined,
    MoonOutlined,
    SearchOutlined,
    SyncOutlined,
    HistoryOutlined,
} from '@ant-design/icons'

const { Header } = Layout

const SOURCE_OPTIONS = [
    { value: '', label: 'All sources' },
    { value: 'TCRAFT', label: 'TCRAFT (vitiligo)' },
    { value: 'PDAC', label: 'PDAC (tumor)' },
    { value: 'AD_CSF', label: "AD CSF (Alzheimer's)" },
    { value: 'VDJdb', label: 'VDJdb' },
    { value: 'McPAS', label: 'McPAS' },
]

// Category filter removed — now handled by interactive sidebar legend

export default function ExploreTopNav({
    loading,
    pointCount,
    backendOk,
    workerLoading,
    isDark,
    onToggleTheme,
    filters,
    onFiltersChange,
    searchOptions,
    searchText,
    onSearchChange,
    onSearchSelect,
    onRecompute,
}) {
    const navigate = useNavigate()

    return (
        <Header style={{
            background: 'var(--bg-surface)',
            borderBottom: '1px solid var(--border)',
            padding: '0 20px',
            height: 52,
            display: 'flex',
            alignItems: 'center',
            gap: 20,
            flexShrink: 0,
            zIndex: 10,
            overflowX: 'auto',
        }}>
            {/* Logo / title */}
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
                        AI assisted TCR mapping
                    </div>
                </div>
            </div>

            {/* Point count 
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                {loading
                    ? <><Spin size="small" style={{ marginRight: 8 }} />Loading {pointCount.toLocaleString()} TCRs...</>
                    : <>{pointCount.toLocaleString()} TCRs</>
                }
            </div>
            */}

            {/* Search bar */}
            <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
                <AutoComplete
                    options={searchOptions}
                    value={searchText}
                    onChange={onSearchChange}
                    onSelect={onSearchSelect}
                    popupMatchSelectWidth={500}
                    defaultActiveFirstOption={false}
                >
                    <Input
                        size="small"
                        placeholder="Search TCR ID, CDR3, epitope, or 'hero'..."
                        prefix={<SearchOutlined style={{ color: 'var(--text-dim)' }} />}
                        variant="filled"
                        allowClear
                        style={{ width: 500 }}
                    />
                </AutoComplete>
            </div>

            {/* Ingest navigation */}
            <Tooltip title="Add new TCR Data" placement="bottom">

                <Button
                    type="primary"
                    size="small"
                    onClick={() => navigate('/ingest')}
                    style={{ background: 'var(--color-primary)', fontWeight: 600 }}
                >
                    +
                </Button>
            </Tooltip>

            {/* Past chats navigation */}
            <Tooltip title="View past chats with agent" placement="bottom">

                <Button
                    size="small"
                    icon={<HistoryOutlined />}
                    onClick={() => navigate('/chats')}
                    style={{ color: 'var(--text-dim)', borderColor: 'var(--border)' }}
                >
                </Button>
            </Tooltip>

            {/* Filters */}
            <FilterOutlined style={{ color: 'var(--text-dim)', fontSize: 13 }} />
            <Select
                value={filters.source}
                onChange={v => onFiltersChange(f => ({ ...f, source: v }))}
                options={SOURCE_OPTIONS}
                size="small"
                style={{ width: 160 }}
                variant="filled"
                popupMatchSelectWidth={false}
            />
            {/* Category filter now in sidebar legend */}

            {/* Theme toggle */}
            <Button
                type="text"
                size="small"
                icon={isDark ? <SunOutlined /> : <MoonOutlined />}
                onClick={onToggleTheme}
                style={{ color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            />

            {/* UMAP recompute */}
            <Popconfirm
                title="Trigger Full UMAP Recompute?"
                description="This is a heavy asynchronous operation that may take several minutes. Are you sure?"
                onConfirm={onRecompute}
                okText="Yes, start job"
                cancelText="Cancel"
                placement="bottomRight"
            >
                <Tooltip title="Trigger Full UMAP Recompute (Async)">
                    <Button
                        type="text"
                        size="small"
                        icon={<SyncOutlined spin={workerLoading} />}
                        style={{ color: 'var(--text-dim)' }}
                    />
                </Tooltip>
            </Popconfirm>

            {/* Backend status 
            <Tooltip title={backendOk == null ? 'Checking backend…' : backendOk ? 'Backend connected' : 'Backend offline — running in static mode'}>
                <Badge
                    status={backendOk == null ? 'processing' : backendOk ? 'success' : 'warning'}
                    text={
                        <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 8 }}>
                            <ApiOutlined /> {backendOk ? 'live' : backendOk === false ? 'static' : '…'}
                        </span>
                    }
                />
            </Tooltip>
            */}
        </Header>
    )
}
