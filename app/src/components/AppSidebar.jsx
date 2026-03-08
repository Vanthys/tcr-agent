/**
 * AppSidebar.jsx — Left statistics sidebar for the Explore page.
 *
 * Contains the SidebarPanels statistics and the AI provider selector at the bottom.
 */
import { Layout, Select } from 'antd'
import SidebarPanels from './SidebarPanels'

const { Sider } = Layout

export default function AppSidebar({ stats, provider, onProviderChange, categoryCounts, hiddenCategories, onToggleCategory, onResetCategories, ingestedPoints = [], onClearIngested }) {
    return (
        <Sider
            width={220}
            style={{
                background: 'var(--bg-surface)',
                borderRight: '1px solid var(--border)',
                overflow: 'hidden',
                flexShrink: 0,
                display: 'flex',
                flexDirection: 'column',
            }}
            breakpoint="lg"
            collapsedWidth={0}
        >
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
                <SidebarPanels
                    stats={stats}
                    categoryCounts={categoryCounts}
                    hiddenCategories={hiddenCategories}
                    onToggleCategory={onToggleCategory}
                    onResetCategories={onResetCategories}
                />
            </div>

            {/* Recent upload indicator */}
            {ingestedPoints.length > 0 && (
                <div style={{
                    padding: '10px 14px',
                    borderTop: '1px solid var(--border)',
                    background: 'var(--bg-surface)',
                    flexShrink: 0,
                }}>
                    <div style={{
                        fontSize: 10, color: 'var(--text-dim)', marginBottom: 6,
                        fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <span>Recent Upload</span>
                        <span
                            onClick={onClearIngested}
                            style={{ cursor: 'pointer', color: 'var(--color-primary)', fontSize: 9, textTransform: 'none', fontWeight: 400 }}
                        >clear</span>
                    </div>
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
                    }}>
                        <span style={{
                            width: 10, height: 10, borderRadius: '50%',
                            background: '#FFB900', border: '2px solid #fff',
                            display: 'inline-block', flexShrink: 0,
                            boxShadow: '0 0 4px rgba(255,185,0,0.6)',
                        }} />
                        <span style={{ color: 'var(--text-main)' }}>
                            <strong>{ingestedPoints.length}</strong> TCRs
                        </span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4, lineHeight: 1.3 }}>
                        Shown as gold dots on Canvas
                    </div>
                </div>
            )}

            {/* AI Provider selector */}
            <div style={{
                padding: '12px 14px',
                borderTop: '1px solid var(--border)',
                background: 'var(--bg-surface)',
                flexShrink: 0,
            }}>
                <div style={{
                    fontSize: 10, color: 'var(--text-dim)', marginBottom: 6,
                    fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em',
                }}>
                    Agent Model
                </div>
                <Select
                    value={provider}
                    onChange={onProviderChange}
                    options={[
                        { label: 'Claude 3.5 Sonnet', value: 'claude' },
                        { label: 'Gemini 2.5 Flash', value: 'gemini' },
                    ]}
                    size="small"
                    style={{ width: '100%' }}
                    variant="filled"
                    popupMatchSelectWidth={false}
                />
            </div>
        </Sider>
    )
}
