// 轻量 fetch 封装（FastAPI 后端，经 Vite /api 代理）
async function request(path, options = {}) {
  const res = await fetch(path, options)
  let data = null
  try {
    data = await res.json()
  } catch {
    /* 非 JSON */
  }
  if (!res.ok) {
    const msg = data && data.detail ? data.detail : `HTTP ${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const apiGet = (path) => request(path)

export const apiPost = (path, body) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

export const apiUpload = (path, file) => {
  const fd = new FormData()
  fd.append('file', file)
  return request(path, { method: 'POST', body: fd })
}
