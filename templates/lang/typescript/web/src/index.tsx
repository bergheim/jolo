import { html } from "@elysiajs/html";
import { staticPlugin } from "@elysiajs/static";
import { Elysia, t } from "elysia";
import { Home } from "./pages/home.js";

// Live reload: persist SSE clients across bun --hot reloads
const g = globalThis as Record<string, unknown>;
if (!g.__reloadClients)
	g.__reloadClients = new Set<ReadableStreamDefaultController>();
const reloadClients = g.__reloadClients as Set<ReadableStreamDefaultController>;
const enc = new TextEncoder();

// On hot reload, top-level code re-runs — notify all connected browsers
for (const c of reloadClients) {
	try {
		c.enqueue(enc.encode("data: reload\n\n"));
	} catch {
		reloadClients.delete(c);
	}
}

export const app = new Elysia()
	.use(html())
	.use(staticPlugin())
	.get("/", () => <Home />)
	.get("/health", () => ({ status: "ok" }))
	.get(
		"/api/hello",
		({ query }) => ({
			message: `Hello, ${query.name || "Stranger"}!`,
		}),
		{
			query: t.Object({
				name: t.Optional(t.String()),
			}),
		},
	)
	.get("/dev/reload", () => {
		let ctrl: ReadableStreamDefaultController;
		return new Response(
			new ReadableStream({
				start(controller) {
					ctrl = controller;
					reloadClients.add(controller);
					controller.enqueue(enc.encode(": connected\n\n"));
				},
				cancel() {
					reloadClients.delete(ctrl);
				},
			}),
			{
				headers: {
					"Content-Type": "text/event-stream",
					"Cache-Control": "no-cache",
				},
			},
		);
	});

if (import.meta.main) {
	const port = process.env.PORT || 4000;
	app.listen(
		{
			port: +port,
			hostname: "0.0.0.0",
			reusePort: false,
		},
		({ hostname, port }) => {
			console.log(`🚀 Server running at http://${hostname}:${port}`);
		},
	);
}
