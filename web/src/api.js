const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const endpoints = {
  healthFull: '/health/full',
  advancedSearch: '/search-identity-advanced',
  osintJobs: '/api/v1/osint/jobs',
  documentJobs: '/api/v1/jobs/document-validation',
  faceJobs: '/api/v1/jobs/face-search',
  videoFaceJobs: '/api/v1/jobs/video-face-search',
  adminIdentities: '/admin/identities',
  newsTopClusters: '/api/v1/news/clusters/top',
  newsSearch: '/api/v1/news/search',
  newsTopics: '/api/v1/news/topics',
  newsClusters: '/api/v1/news/clusters',
  newsSync: '/api/v1/news/sync-status/latest',
  drishtiOverview: '/api/v1/drishti/overview',
  drishtiRefresh: '/api/v1/drishti/refresh',
  drishtiSearch: '/api/v1/drishti/search',
  drishtiContent: '/api/v1/drishti/content/generate'
};

export function apiUrl(path) {
  if (!path) return API_BASE;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${API_BASE}${path}`;
}

export function mediaUrl(path) {
  if (!path) return '';
  const raw = String(path).trim();
  if (!raw || raw === '-') return '';
  if (raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('data:')) return raw;
  const normalized = raw.split('\\').join('/');
  if (normalized.startsWith('/media/')) return apiUrl(normalized);
  if (normalized.includes('frontend/matched_employee_photos/')) {
    return apiUrl(`/media/matched-photos/${normalized.split('frontend/matched_employee_photos/')[1]}`);
  }
  if (normalized.startsWith('/matched_employee_photos/')) {
    return apiUrl(`/media/matched-photos/${normalized.slice('/matched_employee_photos/'.length)}`);
  }
  if (normalized.startsWith('matched_employee_photos/')) {
    return apiUrl(`/media/matched-photos/${normalized.slice('matched_employee_photos/'.length)}`);
  }
  if (normalized.includes('backend/uploads/')) {
    return apiUrl(`/media/backend-uploads/${normalized.split('backend/uploads/')[1]}`);
  }
  if (normalized.includes('/uploads/')) {
    return apiUrl(`/media/uploads/${normalized.split('/uploads/').pop()}`);
  }
  if (normalized.startsWith('uploads/')) {
    return apiUrl(`/media/uploads/${normalized.slice('uploads/'.length)}`);
  }
  return normalized;
}

async function parseResponse(response) {
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { status: 'error', message: text || response.statusText };
  }
  if (!response.ok) {
    const message = payload.message || payload.detail || response.statusText;
    throw new Error(message);
  }
  return payload;
}

export async function getJson(path, params = {}) {
  const url = new URL(apiUrl(path));
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });
  const response = await fetch(url);
  return parseResponse(response);
}

export async function postForm(path, formData) {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    body: formData
  });
  return parseResponse(response);
}

export async function postJson(path, body) {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  return parseResponse(response);
}
