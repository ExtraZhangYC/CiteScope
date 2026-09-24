const USER_KEY = 'user'
const TOKEN_KEY = 'token'
const LOGGED_IN_KEY = 'isLoggedIn'
const AUTH_BASE_URL = '/api'

const generateUserId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `u_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export const getStoredUser = () => {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) {
    return null
  }
  try {
    const parsed = JSON.parse(raw)
    if (parsed && parsed.id && (parsed.username || parsed.nickname)) {
      return {
        ...parsed,
        username: parsed.username || parsed.nickname
      }
    }
  } catch (error) {
    console.warn('解析用户信息失败:', error)
  }
  return null
}

export const getToken = () => localStorage.getItem(TOKEN_KEY)

export const setAuthData = ({ token, user }) => {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  }
  if (user) {
    const normalizedUser = {
      ...user,
      id: user.id || user.user_id || generateUserId(),
      username: user.username || user.nickname || ''
    }
    localStorage.setItem(USER_KEY, JSON.stringify(normalizedUser))
    localStorage.setItem('username', normalizedUser.username)
  }
  localStorage.setItem(LOGGED_IN_KEY, 'true')
}

export const registerUser = async ({ nickname, password, email, scholarId }) => {
  const response = await fetch(`${AUTH_BASE_URL}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nickname: nickname.trim(),
      password: password.trim(),
      email: email?.trim() || '',
      scholar_id: scholarId?.trim() || ''
    })
  })
  const result = await response.json()
  return { ok: response.ok, result }
}

export const loginUser = async ({ nickname, password }) => {
  const response = await fetch(`${AUTH_BASE_URL}/users/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      nickname: nickname.trim(),
      password: password.trim()
    })
  })
  const result = await response.json()
  return { ok: response.ok, result }
}

export const clearUser = () => {
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(LOGGED_IN_KEY)
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem('username')
}

export const isAuthenticated = () => {
  const loggedIn = localStorage.getItem(LOGGED_IN_KEY) === 'true'
  const user = getStoredUser()
  const token = getToken()
  if (!loggedIn || !user) {
    if (loggedIn && !user) {
      clearUser()
    }
    return false
  }
  return !!token
}
