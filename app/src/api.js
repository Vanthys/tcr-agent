/**
 * api.js — Typed API client for the TCR Agent backend.
 *
 * All fetch calls go through this module so the base URL is
 * changed in one place for deployment.
 */

const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:3001'

import { fetchEventSource } from '@microsoft/fetch-event-source'
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
    ingestedPoints: () => get('/api/umap/ingested'),
    clearIngested: () => fetch(new URL(BASE + '/api/umap/ingested'), { method: 'DELETE' }).then(r => r.json()),
    tcr: (id) => get(`/api/tcr/${encodeURIComponent(id)}`),
    mutagenesis: (id, params = {}) => get(`/api/mutagenesis/${encodeURIComponent(id)}`, params),
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
    getChatCacheStatus: (tcrId, provider = 'claude') =>
        get(`/api/annotate/cache/${encodeURIComponent(tcrId)}`, { provider }),
    listAllChats: () => get('/api/annotate/caches'),
    clearChatCache: (tcrId, provider = 'claude') =>
        fetch(`${BASE}/api/annotate/cache/${encodeURIComponent(tcrId)}?provider=${encodeURIComponent(provider)}`, { method: 'DELETE' }).then(r => r.json()),

    dispatchSuggestion: (tcrId, provider, suggestion, callbacks) => {
        const { onMessage, onError, onClose } = callbacks
        const controller = new AbortController()

        fetchEventSource(`${BASE}/api/annotate/suggestion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tcr_id: tcrId, provider, suggestion }),
            signal: controller.signal,
            onmessage(msg) {
                if (msg.event === 'done') {
                    onClose?.()
                    return
                }
                if (msg.event === 'error') {
                    onError?.(new Error(msg.data))
                    return
                }
                if (msg.event === 'step' || msg.event === 'text' || msg.event === 'raw_result' || msg.event === 'analyzing') {
                    onMessage?.(msg.event, msg.data)
                }
            },
            onerror(err) {
                onError?.(err)
                throw err // prevent retry
            },
            onclose() {
                onClose?.()
            }
        })
        return controller
    },
    getWorkerTask: (taskId) => get(`/api/worker/status/${encodeURIComponent(taskId)}`),
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
export function streamAnnotate(tcrId, question, provider, onEvent, forceRefresh = false) {
    const controller = new AbortController()

        ; (async () => {
            let res
            try {
                res = await fetch(`${BASE}/api/annotate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tcr_id: tcrId, question, provider, force_refresh: forceRefresh }),
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
                            } else if (eventType === 'cached') {
                                try { onEvent('cached', JSON.parse(payload)) } catch { /* skip */ }
                            } else if (eventType === 'done') {
                                onEvent('done', null)
                            } else if (eventType === 'error') {
                                onEvent('error', payload)
                            } else {
                                // Fallback
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
