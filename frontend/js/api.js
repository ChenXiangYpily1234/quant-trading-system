export async function request(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options,
    body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.message || payload.detail || '请求失败');
  return payload;
}
