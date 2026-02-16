import { Layout } from '../components/layout';

export const Home = () => (
  <Layout>
    <div class="max-w-2xl mx-auto space-y-8 text-center">
      <header class="space-y-4">
        <h1 class="text-5xl font-extrabold tracking-tight text-slate-900 sm:text-6xl">
          BETH Stack Scaffold
        </h1>
        <p class="text-lg text-slate-600">
          Bun + Elysia + Tailwind + HTMX
        </p>
      </header>

      <section class="p-8 bg-white border border-slate-200 rounded-2xl shadow-sm space-y-6">
        <div class="space-y-2">
          <h2 class="text-xl font-semibold">HTMX Demo</h2>
          <p class="text-slate-500">Click the button below to fetch a message from the API.</p>
        </div>

        <div class="flex flex-col items-center gap-4">
          <button
            hx-get="/api/hello?name=Developer"
            hx-target="#result"
            hx-swap="innerHTML"
            class="px-6 py-3 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-sm cursor-pointer"
          >
            Say Hello
          </button>

          <div id="result" class="min-h-[3rem] p-4 bg-slate-50 rounded-lg w-full font-mono text-indigo-600 flex items-center justify-center border border-slate-100 italic">
            Waiting for greeting...
          </div>
        </div>
      </section>

      <footer class="pt-8 text-sm text-slate-400">
        Edit <code>src/pages/home.tsx</code> to start building.
      </footer>
    </div>
  </Layout>
);
