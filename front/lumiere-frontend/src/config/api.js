const rawApiBaseUrl = String(import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').trim()

const withoutApiSuffix = rawApiBaseUrl.replace(/\/api\/?$/, '')
const withoutTrailingSlash = withoutApiSuffix.replace(/\/+$/, '')

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
export const API_ORIGIN = import.meta.env.VITE_API_BASE_URL
