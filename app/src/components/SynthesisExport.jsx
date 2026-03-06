import { useState } from 'react'
import { Button, Checkbox, Select, Table, Modal, Alert, Space } from 'antd'
import { DownloadOutlined, MedicineBoxOutlined } from '@ant-design/icons'
import { api } from '../api'

export default function SynthesisExport({ tcrId, tcrIds, epitope }) {
    const [loading, setLoading] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)
    const [open, setOpen] = useState(false)

    const [includeVariants, setIncludeVariants] = useState(true)
    const [maxVariants, setMaxVariants] = useState(5)
    const [includeControls, setIncludeControls] = useState(true)

    const handleExport = async () => {
        setLoading(true)
        setError(null)
        setResult(null)
        try {
            const data = await api.synthesisExport({
                tcr_id: tcrId || '',
                tcr_ids: tcrIds || [],
                epitope: epitope || 'TRP2_SVYDFFVWL',
                include_variants: includeVariants,
                max_variants: maxVariants,
                include_controls: includeControls,
            })
            setResult(data)
            setOpen(true)
        } catch (err) {
            setError(err.detail || err.message || String(err))
        } finally {
            setLoading(false)
        }
    }

    const downloadCSV = () => {
        if (!result) return
        const constructs = result.constructs
        function csvEscape(val) {
            const s = String(val == null ? '' : val)
            if (s.includes(',') || s.includes('"') || s.includes('\n')) {
                return '"' + s.replace(/"/g, '""') + '"'
            }
            return s
        }
        let csv = 'Name,V_alpha,V_beta,CDR3_alpha,CDR3_beta,J_alpha,J_beta,Mutation,Delta_Score,Type\n'
        for (const c of constructs) {
            const type = !c.mutation ? 'WT' : (c.variant_type === 'control_decrease' ? 'CTRL-' : 'MUT+')
            csv += [
                c.name, c.V_alpha, c.V_beta, c.CDR3_alpha, c.CDR3_beta, c.J_alpha, c.J_beta,
                c.mutation || '', c.delta_score?.toFixed(4) || '0.0000', type
            ].map(csvEscape).join(',') + '\n'
        }
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `tcraft_synthesis_${tcrId || 'bulk'}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    const columns = [
        {
            title: 'Type',
            dataIndex: 'variant_type',
            render: (type, record) => !record.mutation ? 'WT' : (type === 'control_decrease' ? 'CTRL-' : 'MUT+'),
        },
        { title: 'Name', dataIndex: 'name' },
        { title: 'CDR3β', dataIndex: 'CDR3_beta' },
        { title: 'Mut', dataIndex: 'mutation' },
        { title: 'Δ Score', dataIndex: 'delta_score', render: (val) => val ? val.toFixed(4) : '—' },
    ];

    return (
        <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 8 }}>
                TCRAFT Synthesis Export
            </div>

            <div style={{ marginBottom: 12, fontSize: 11, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Checkbox checked={includeVariants} onChange={e => setIncludeVariants(e.target.checked)}>
                    Include mutagenesis variants
                </Checkbox>
                {includeVariants && (
                    <div style={{ paddingLeft: 24, display: 'flex', alignItems: 'center', gap: 8 }}>
                        Top count:
                        <Select size="small" value={maxVariants} onChange={setMaxVariants} options={[{ value: 3 }, { value: 5 }, { value: 10 }]} style={{ width: 60 }} />
                    </div>
                )}
                <Checkbox checked={includeControls} onChange={e => setIncludeControls(e.target.checked)}>
                    <span style={{ color: 'var(--color-accent)' }}>+ 2 negative controls (binding-decrease)</span>
                </Checkbox>
            </div>

            <Button
                type="primary"
                icon={<MedicineBoxOutlined />}
                onClick={handleExport}
                loading={loading}
                block
                style={{ background: 'var(--cat-bacterial)', border: 'none' }}
            >
                Generate TCRAFT Order
            </Button>

            {error && <Alert type="error" message={error} style={{ marginTop: 8 }} />}

            <Modal
                title={`Synthesis Plan: ${tcrId || (tcrIds?.length + ' TCRs')}`}
                open={open}
                onCancel={() => setOpen(false)}
                width={700}
                footer={[
                    <Button key="download" type="primary" icon={<DownloadOutlined />} onClick={downloadCSV}>
                        Download CSV
                    </Button>,
                    <Button key="close" onClick={() => setOpen(false)}>
                        Close
                    </Button>
                ]}
            >
                {result && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                        {result.warnings?.length > 0 && (
                            <Alert type="warning" message={result.warnings.join(', ')} />
                        )}
                        <p style={{ margin: 0 }}>
                            {result.n_wt} WT + {result.n_variants} variants = <strong>{result.n_constructs} oligos</strong>
                        </p>
                        <Table
                            dataSource={result.constructs}
                            columns={columns}
                            size="small"
                            pagination={false}
                            rowKey="name"
                            scroll={{ y: 240 }}
                        />
                        <div style={{ marginTop: 16 }}>
                            <div style={{ fontSize: 16, fontWeight: 'bold', color: 'var(--cat-bacterial)' }}>
                                ${result.cost_estimate?.total_usd?.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                                {result.cost_estimate?.n_oligos} oligos × ${result.cost_estimate?.cost_per_oligo_usd}/ea • TCRAFT pooled
                            </div>
                        </div>
                    </Space>
                )}
            </Modal>
        </div>
    )
}
