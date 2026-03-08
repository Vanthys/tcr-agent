/**
 * api.js — Typed API client for the TCR Agent backend.
 *
 * All fetch calls go through this module so the base URL is
 * changed in one place for deployment.
 */

const RAW_API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:3001/api'
const API_BASE = RAW_API_BASE.replace(/\/$/, '')
const FALLBACK_ORIGIN = typeof window !== 'undefined' && window.location?.origin
    ? window.location.origin
    : 'http://localhost:5173'

import { fetchEventSource } from '@microsoft/fetch-event-source'
import { parse } from '@loaders.gl/core'
import { ArrowLoader } from '@loaders.gl/arrow'

function resolveUrl(path) {
    const normalized = path.startsWith('/') ? path : `/${path}`
    const full = `${API_BASE}${normalized}`
    if (/^https?:\/\//i.test(full)) return new URL(full)
    return new URL(full, FALLBACK_ORIGIN)
}

// ── REST helpers ─────────────────────────────────────────────────────────────

async function get(path, params = {}, signal) {
    const url = resolveUrl(path)
    Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
    const res = await fetch(url, signal ? { signal } : undefined)
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
    return res.json()
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
    health: () => get('/health'),
    umap: (params = {}, signal) => get('/umap', params, signal),
    umapArrow: async (params = {}, signal) => {
        const url = resolveUrl('/umap/arrow')
        Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
        const res = await fetch(url, signal ? { signal } : undefined)
        if (!res.ok) throw new Error(`GET /api/umap/arrow → ${res.status}`);
        const arrayBuffer = await res.arrayBuffer();
        return parse(arrayBuffer, ArrowLoader, { arrow: { shape: 'object-row-table' } });
    },
    streamUmap: (params = {}, signal, onChunk) => {
        const url = resolveUrl('/umap/stream')
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
    ingestedPoints: () => get('/umap/ingested'),
    clearIngested: () => fetch(new URL('/umap/ingested'), { method: 'DELETE' }).then(r => r.json()),
    tcr: (id) => get(`/tcr/${encodeURIComponent(id)}`),
    mutagenesis: (id, params = {}) => get(`/mutagenesis/${encodeURIComponent(id)}`, params),
    epitopeDistribution: () => get('/epitope_distribution'),
    statsSummary: () => get('/stats_summary'),
    categorySummary: () => get('/category_summary'),
    synthesisExport: (data) => fetch(resolveUrl('/synthesis_export'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    }).then(res => {
        if (!res.ok) return res.json().then(e => Promise.reject(e))
        return res.json()
    }),
    nullDistribution: (epitope) => get(`/null_distribution/${encodeURIComponent(epitope)}`),
    listAllChats: (limit = 50) => get('/chat', { limit }),
    startChat: ({ tcrId, provider = 'claude', question } = {}) =>
        fetch(resolveUrl('/chat'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tcr_id: tcrId, provider, question }),
        }).then(res => {
            if (!res.ok) return res.json().then(e => Promise.reject(e))
            return res.json()
        }),
    getChat: (messageId) => get(`/chat/${encodeURIComponent(messageId)}`),
    deleteChat: (messageId) =>
        fetch(resolveUrl(`/chat/${encodeURIComponent(messageId)}`), { method: 'DELETE' }).then(r => r.json()),
    streamChat: (messageId, { onEvent, onError, onClose } = {}) => {
        const controller = new AbortController()
        fetchEventSource(resolveUrl(`/chat/${encodeURIComponent(messageId)}/stream`).toString(), {
            signal: controller.signal,
            onmessage(msg) {
                onEvent?.(msg.event, msg.data)
            },
            onerror(err) {
                onError?.(err)
                throw err
            },
            onclose() {
                onClose?.()
            }
        })
        return controller
    },

    dispatchSuggestion: (tcrId, provider, suggestion, callbacks) => {
        const { onMessage, onError, onClose } = callbacks
        const controller = new AbortController()

        fetchEventSource(resolveUrl('/chat/suggestion').toString(), {
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
    triggerUmapRecompute: () =>
        fetch(resolveUrl('/worker/umap/compute'), { method: 'POST' }).then(res => {
            if (!res.ok) throw new Error(`POST /worker/umap/compute → ${res.status}`)
            return res.json().catch(() => ({}))
        }),
    getWorkerTask: (taskId) => get(`/worker/status/${encodeURIComponent(taskId)}`),
}
