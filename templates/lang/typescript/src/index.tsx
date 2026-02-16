import { Elysia, t } from 'elysia';
import { html } from '@elysiajs/html';
import { staticPlugin } from '@elysiajs/static';
import { Home } from './pages/home';

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
