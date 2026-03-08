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

const CAT_OPTIONS = [
    { value: '', label: 'All categories' },
    { value: 'viral', label: 'Viral' },
    { value: 'melanocyte', label: 'Melanocyte' },
    { value: 'cancer_associated', label: 'Cancer' },
    { value: 'autoimmune', label: 'Autoimmune' },
    { value: 'unknown', label: 'Dark matter only' },
]

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

            {/* Point count */}
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                {loading
                    ? <><Spin size="small" style={{ marginRight: 8 }} />Loading {pointCount.toLocaleString()} TCRs...</>
                    : <>{pointCount.toLocaleString()} TCRs</>
                }
            </div>

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
            <Button
                type="primary"
                size="small"
                onClick={() => navigate('/ingest')}
                style={{ background: 'var(--color-primary)', fontWeight: 600 }}
            >
                + Add TCRs
            </Button>

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
            <Select
                value={filters.category}
                onChange={v => onFiltersChange(f => ({ ...f, category: v }))}
                options={CAT_OPTIONS}
                size="small"
                style={{ width: 160 }}
                variant="filled"
                popupMatchSelectWidth={false}
            />

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

            {/* Backend status */}
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
        </Header>
    )
}
