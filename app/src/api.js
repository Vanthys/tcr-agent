/**
 * api.js — Typed API client for the TCR Agent backend.
 *
 * All fetch calls go through this module so the base URL is
 * changed in one place for deployment.
 */

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

import { parse } from '@loaders.gl/core'
import { ArrowLoader } from '@loaders.gl/arrow'

// ── REST helpers ─────────────────────────────────────────────────────────────

async function get(path, params = {}, signal) {
    const url = new URL(BASE + path)
    Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
    const res = await fetch(url, signal ? { signal } : undefined)
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
    return res.json()
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
    health: () => get('/api/health'),
    umap: (params = {}, signal) => get('/api/umap', params, signal),
    umapArrow: async (params = {}, signal) => {
        const url = new URL(BASE + '/api/umap/arrow');
        Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
        const res = await fetch(url, signal ? { signal } : undefined);
        if (!res.ok) throw new Error(`GET /api/umap/arrow → ${res.status}`);
        const arrayBuffer = await res.arrayBuffer();
        return parse(arrayBuffer, ArrowLoader, { arrow: { shape: 'object-row-table' } });
    },
    streamUmap: (params = {}, signal, onChunk) => {
        const url = new URL(BASE + '/api/umap/stream')
        Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
        return fetch(url, signal ? { signal } : undefined).then(async (res) => {
            if (!res.ok) throw new Error(`GET /api/umap/stream → ${res.status}`)
            const reader = res.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() // keep incomplete last line

                const chunk = []
                for (const line of lines) {
                    if (line.trim()) chunk.push(JSON.parse(line))
                }
                if (chunk.length > 0) onChunk(chunk)
            }
            if (buffer.trim()) onChunk([JSON.parse(buffer)])
        })
    },
    tcr: (id) => get(`/api/tcr/${encodeURIComponent(id)}`),
    mutagenesis: (id) => get(`/api/mutagenesis/${encodeURIComponent(id)}`),
    epitopeDistribution: () => get('/api/epitope_distribution'),
    statsSummary: () => get('/api/stats_summary'),
    categorySummary: () => get('/api/category_summary'),
    synthesisExport: (data) => fetch(new URL(BASE + '/api/synthesis_export'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    }).then(res => {
        if (!res.ok) return res.json().then(e => Promise.reject(e))
        return res.json()
    }),
    nullDistribution: (epitope) => get(`/api/null_distribution/${encodeURIComponent(epitope)}`),
}

// ── SSE annotate stream ───────────────────────────────────────────────────────
/**
 * streamAnnotate(tcrId, onEvent, onDone, onError)
 *
 * Calls POST /api/annotate and processes the SSE stream.
 * onEvent(type, data) is called for every event.
 *   type === 'step'  → data is a parsed JSON object
 *   type === 'text'  → data is a raw text chunk from Claude
 *   type === 'done'  → stream finished
 *   type === 'error' → data is an error string
 *
 * Returns an AbortController so the caller can cancel.
 */
export function streamAnnotate(tcrId, question, provider, onEvent) {
    const controller = new AbortController()

        ; (async () => {
            let res
            try {
                res = await fetch(`${BASE}/api/annotate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tcr_id: tcrId, question, provider }),
                    signal: controller.signal,
                })
            } catch (err) {
                if (err.name !== 'AbortError') onEvent('error', String(err))
                return
            }

            if (!res.ok) {
                onEvent('error', `Server error ${res.status}`)
                return
            }

            const reader = res.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''
            let dataBuffer = []
            let eventType = 'message'

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() // keep incomplete last line

                for (let i = 0; i < lines.length; i++) {
                    let line = lines[i]
                    if (line.endsWith('\r')) line = line.slice(0, -1) // handle Windows CRLF

                    if (line === '') {
                        // Empty line means dispatch the accumulated event
                        if (dataBuffer.length > 0 || eventType === 'done') {
                            const payload = dataBuffer.join('\n')
                            if (eventType === 'step') {
                                try { onEvent('step', JSON.parse(payload)) } catch { /* skip */ }
                            } else if (eventType === 'text') {
                                try { onEvent('text', JSON.parse(payload)) } catch { onEvent('text', payload) }
                            } else if (eventType === 'done') {
                                onEvent('done', null)
                            } else if (eventType === 'error') {
                                onEvent('error', payload)
                            } else {
                                // Fallback (e.g. if eventType is "message")
                                onEvent('text', payload)
                            }
                            dataBuffer = []
                        }
                        eventType = 'message'
                    } else if (line.startsWith('event:')) {
                        eventType = line.slice(6).trim()
                    } else if (line.startsWith('data:')) {
                        const raw = line.slice(5)
                        dataBuffer.push(raw.startsWith(' ') ? raw.slice(1) : raw)
                    }
                }
            }
        })()

    return controller
}
