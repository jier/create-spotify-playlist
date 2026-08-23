import { defineConfig } from "vite";

/**
 * Minimal Vite config: no framework plugins, just a dev server + a static
 * build for this pure TypeScript/HTML/CSS app.
 *
 * The proxy avoids CORS entirely rather than adding CORSMiddleware to the
 * FastAPI backend (src/app.py already locks that down to loopback-only via
 * LoopbackOnlyMiddleware, not worth widening for a frontend dev-server
 * concern). fetchTrace() in traceEvent.ts calls a same-origin relative path
 * (`/runs/{run_id}`); this proxy forwards that straight to uvicorn.
 */
export default defineConfig({
  server: {
    proxy: {
      "/runs": "http://127.0.0.1:8000",
      "/me": "http://127.0.0.1:8000",
    },
  },
});
