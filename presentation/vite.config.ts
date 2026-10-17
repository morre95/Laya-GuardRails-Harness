// The live slide talks to the local Laya daemon. The daemon sends no CORS headers,
// so the dev server proxies /laya/* to it instead.
const DAEMON_URL = process.env.LGH_DAEMON_URL ?? 'http://127.0.0.1:8765'

export default {
  server: {
    proxy: {
      '/laya': {
        target: DAEMON_URL,
        rewrite: path => path.replace(/^\/laya/, ''),
      },
    },
    // The question set is imported from src/lgh/laya/questions_v0_1.yaml.
    fs: { allow: ['..'] },
  },
}
