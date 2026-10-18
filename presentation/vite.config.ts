import type { UserConfig } from 'vite'

// The Laya daemon sends no CORS headers, so the dev server proxies it.
const daemon = process.env.LGH_DAEMON_URL ?? 'http://127.0.0.1:8765'

export default {
  server: {
    proxy: {
      '/laya': {
        target: daemon,
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/laya/, ''),
      },
    },
  },
} satisfies UserConfig
