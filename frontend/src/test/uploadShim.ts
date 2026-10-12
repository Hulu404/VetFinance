// jsdom's XMLHttpRequest cannot pass a multipart body through MSW, so tests replace the upload transport:
// the same fields go out as JSON through fetch. The mock handler understands both (mocks/transactionHandlers.ts).
import { errorFromParts } from '../api/errors'
import type { UploadHandle } from '../api/client'

function readText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

export function fakeUpload<T>(path: string, form: FormData): UploadHandle<T> {
  const promise = (async () => {
    const file = form.get('file')
    if (!file || typeof file === 'string') throw new Error('no file')
    const body = JSON.stringify({ name: file.name, text: await readText(file), account_id: form.get('account_id') })
    const response = await fetch(new URL(path, 'http://localhost'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer test-token' },
      body,
    })
    const json: unknown = await response.json()
    if (!response.ok) throw errorFromParts(response.status, json, response.statusText)
    return json as T
  })()
  return { promise, abort: () => undefined }
}
