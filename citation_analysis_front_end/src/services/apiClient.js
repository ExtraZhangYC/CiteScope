import { clearUser, getStoredUser, getToken } from './auth'

const attachUserHeaders = (headers) => {
  const user = getStoredUser()
  const token = getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (!user) {
    return
  }
  headers.set('X-User-Id', user.id)
  headers.set('X-User-Name', user.username)
  headers.set('X-User-Info', JSON.stringify({ id: user.id, username: user.username }))
}

export const apiFetch = async (url, options = {}) => {
  const headers = new Headers(options.headers || {})
  attachUserHeaders(headers)
  const response = await fetch(url, { ...options, headers })

  if (response.status === 401 || response.status === 403) {
    clearUser()
    window.dispatchEvent(new Event('userLogout'))
  }

  return response
}
