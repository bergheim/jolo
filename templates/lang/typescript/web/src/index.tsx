import { Elysia, t } from 'elysia';
import { html } from '@elysiajs/html';
import { staticPlugin } from '@elysiajs/static';
import { Home } from './pages/home';

// Live reload: persist SSE clients across bun --hot reloads
const reloadClients = (globalThis as any).__reloadClients ??= new Set<ReadableStreamDefaultController>();
const enc = new TextEncoder();

// On hot reload, top-level code re-runs — notify all connected browsers
for (const c of reloadClients) {
  try { c.enqueue(enc.encode('data: reload\n\n')); } catch { reloadClients.delete(c); }
}

export const app = new Elysia()
    .use(html())
    .use(staticPlugin())
    .get('/', () => <Home />)
    .get('/health', () => ({ status: 'ok' }))
    .get('/api/hello', ({ query }) => ({
        message: `Hello, ${query.name || 'Stranger'}!`
    }), {
        query: t.Object({
            name: t.Optional(t.String())
        })
    })
    .get('/dev/reload', () => {
        let ctrl: ReadableStreamDefaultController;
        return new Response(
            new ReadableStream({
                start(controller) {
                    ctrl = controller;
                    reloadClients.add(controller);
                    controller.enqueue(enc.encode(': connected\n\n'));
                },
                cancel() {
                    reloadClients.delete(ctrl);
                }
            }),
            { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' } }
        );
    });

if (import.meta.main) {
    const port = process.env.PORT || 4000;
    app.listen({
        port: +port,
        hostname: '0.0.0.0'
    }, ({ hostname, port }) => {
        console.log(`🚀 Server running at http://${hostname}:${port}`);
    });
}
