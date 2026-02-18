import * as Html from '@kitajs/html';

export const Layout = ({ children }: Html.PropsWithChildren) => (
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>{{PROJECT_NAME}}</title>
      <link rel="stylesheet" href="/public/styles.css" />
      <script src="/public/htmx.min.js"></script>
    </head>
    <body class="bg-slate-50 text-slate-900 min-h-screen">
      <main class="container mx-auto px-4 py-8">
        {children}
      </main>
    </body>
  </html>
);
