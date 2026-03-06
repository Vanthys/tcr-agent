import { useState, useEffect } from 'react'
import { Skeleton } from 'antd'
import {
    ComposedChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    ReferenceLine,
    ResponsiveContainer
} from 'recharts'
import { api } from '../api'

export default function NullDistribution({ epitope, score, isDark }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        if (!epitope) return
        setLoading(true)
        api.nullDistribution(epitope)
            .then(res => {
                if (!res.scores || res.scores.length === 0) {
                    setData(null)
                    return
                }

                // Create histogram buckets
                const scores = res.scores

                // Need some padding so the reference line isn't cut off if it's the max
                let min = Math.min(...scores, score)
                let max = Math.max(...scores, score)
                const range = max - min || 1
                min -= range * 0.05
                max += range * 0.05

                const BUCKETS = 40
                const step = (max - min) / BUCKETS
                const buckets = Array(BUCKETS).fill(0).map((_, i) => ({
                    x: min + i * step + step / 2,
                    xMin: min + i * step,
                    xMax: min + (i + 1) * step,
                    count: 0
                }))

                for (const s of scores) {
                    let idx = Math.floor((s - min) / step)
                    if (idx >= BUCKETS) idx = BUCKETS - 1
                    if (idx < 0) idx = 0
                    buckets[idx].count++
                }

                // Calculate empirical p-value for the true score
                const n_exceeding = scores.filter(s => s >= score).length
                const p_value = n_exceeding / scores.length

                setData({
                    histogram: buckets,
                    percentiles: res.percentiles,
                    n_scrambles: res.n_scrambles,
                    p_value
                })
            })
            .catch((e) => {
                console.error("Failed to load null distribution", e)
                setData(null)
            })
            .finally(() => setLoading(false))
    }, [epitope, score])

    if (loading) return <div style={{ marginTop: 12 }}><Skeleton active paragraph={{ rows: 3 }} /></div>
    if (!data) return null

    return (
        <div style={{
            marginTop: 12,
            background: 'var(--bg-base)',
            border: '1px solid var(--border)',
            padding: '10px 12px',
            borderRadius: 8
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-main)' }}>
                    Null Distribution (10K Scrambles)
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: "'JetBrains Mono', monospace" }}>
                    p = {data.p_value.toFixed(4)}
                </span>
            </div>

            <div style={{ height: 100, width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={data.histogram} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                        <XAxis
                            dataKey="x"
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            tick={{ fontSize: 9, fill: 'var(--text-dim)' }}
                            tickFormatter={v => v.toFixed(2)}
                            tickCount={5}
                            axisLine={{ stroke: 'var(--border)' }}
                            tickLine={false}
                        />
                        <YAxis
                            tick={{ fontSize: 9, fill: 'var(--text-dim)' }}
                            tickCount={3}
                            axisLine={false}
                            tickLine={false}
                        />
                        <Tooltip
                            contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--border)', fontSize: 11, borderRadius: 6, backdropFilter: 'blur(8px)' }}
                            labelFormatter={v => `Score: ${v.toFixed(3)}`}
                            formatter={(val) => [val, 'TCRs']}
                            cursor={{ fill: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' }}
                        />
                        <Bar
                            dataKey="count"
                            fill="var(--color-primary)"
                            opacity={0.4}
                            isAnimationActive={false}
                        />
                        <ReferenceLine
                            x={score}
                            stroke="#ef4444"
                            strokeWidth={2}
                            strokeDasharray="3 3"
                            label={{ position: 'top', value: 'This TCR', fill: '#ef4444', fontSize: 9, fontWeight: 600 }}
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    )
}
