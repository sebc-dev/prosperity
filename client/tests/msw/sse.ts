import { HttpResponse } from 'msw'

// Helpers de streaming SSE pour MSW 2 (cf. plan §3). MSW intercepte `fetch` au niveau réseau ;
// `@microsoft/fetch-event-source` lit `response.body.getReader()` → on sert un vrai
// `ReadableStream` `text/event-stream`. Vérifié : la lecture est incrémentale sous jsdom.

const enc = new TextEncoder()

// Fabriques de lignes au format wire SSE (cf. `backend/.../sse/transports/http.py::_format`).
export const frame = (id: number, event: string, data: unknown) =>
  `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`
export const heartbeat = ': heartbeat\n\n'
export const resync = 'event: resync\ndata: {}\n\n'

function streamResponse(body: ReadableStream<Uint8Array>): Response {
  return new HttpResponse(body, {
    headers: { 'content-type': 'text/event-stream' },
  })
}

// MONO-SHOT : enqueue toutes les frames puis ferme (EOF). Pour les cas où la fermeture déclenche
// une reconnexion (resume, expiration silencieuse).
export function sseStream(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const f of frames) c.enqueue(enc.encode(f))
      c.close()
    },
  })
  return streamResponse(body)
}

// PROGRESSIF : flux ouvert dont on contrôle les `push`/`close` dans le temps. Pour prouver le
// parsing incrémental (cas 15) et pour parquer le client en état `open` sans EOF (la plupart des
// cas logiques). Un seul consommateur par `response` (le corps n'est lu qu'une fois).
export function sseChannel(): {
  response: Response
  push: (raw: string) => void
  close: () => void
} {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c
    },
  })
  return {
    response: streamResponse(body),
    push: (raw: string) => controller.enqueue(enc.encode(raw)),
    close: () => controller.close(),
  }
}
