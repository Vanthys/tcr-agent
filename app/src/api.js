/**
 * api.js — Typed API client for the TCR Agent backend.
 *
 * All fetch calls go through this module so the base URL is
 * changed in one place for deployment.
 */

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

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
    tcr: (id) => get(`/api/tcr/${encodeURIComponent(id)}`),
    mutagenesis: (id) => get(`/api/mutagenesis/${encodeURIComponent(id)}`),
    epitopeDistribution: () => get('/api/epitope_distribution'),
    statsSummary: () => get('/api/stats_summary'),
    categorySummary: () => get('/api/category_summary'),
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
            let lastEvent = 'message'

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() // keep incomplete last line

                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        lastEvent = line.slice(6).trim()
                    } else if (line.startsWith('data:')) {
                        const raw = line.slice(5).trim()
                        if (lastEvent === 'step') {
                            try { onEvent('step', JSON.parse(raw)) } catch { /* skip */ }
                        } else if (lastEvent === 'done') {
                            onEvent('done', null)
                        } else if (lastEvent === 'error') {
                            onEvent('error', raw)
                        } else {
                            // plain text delta from Claude
                            onEvent('text', raw)
                        }
                        lastEvent = 'message' // reset after data line
                    }
                }
            }
        })()

    return controller
}
