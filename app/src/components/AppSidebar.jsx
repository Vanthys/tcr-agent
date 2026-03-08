/**
 * AppSidebar.jsx — Left statistics sidebar for the Explore page.
 *
 * Contains the SidebarPanels statistics and the AI provider selector at the bottom.
 */
import { Layout, Select } from 'antd'
import SidebarPanels from './SidebarPanels'

const { Sider } = Layout

export default function AppSidebar({ stats, provider, onProviderChange }) {
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
                <SidebarPanels stats={stats} />
            </div>

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
