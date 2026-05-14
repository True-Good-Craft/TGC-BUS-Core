// SPDX-License-Identifier: AGPL-3.0-or-later
import { apiGet, apiPatch, apiPost, rawFetch } from './api.js';

async function parseBody(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function buildError(response, body) {
  const detail = body && typeof body === 'object' ? body.detail || body.error || body.message : body;
  const nested = detail && typeof detail === 'object' ? detail.error || detail.message : null;
  const message = nested || (typeof detail === 'string' ? detail : null) || response.statusText || 'Request failed';
  const error = new Error(message);
  error.status = response.status;
  error.payload = body;
  if (detail && typeof detail === 'object') Object.assign(error, detail);
  else if (typeof detail === 'string') error.error = detail;
  return error;
}

async function authRequest(path, method = 'GET', payload) {
  const init = {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
  };
  if (payload !== undefined) init.body = JSON.stringify(payload ?? {});
  const response = await rawFetch(path, init);
  const body = await parseBody(response);
  if (response.ok) return body;
  throw buildError(response, body);
}

export function getAuthState() {
  return authRequest('/auth/state');
}

export function setupOwner(payload) {
  return authRequest('/auth/setup-owner', 'POST', payload);
}

export function login(payload) {
  return authRequest('/auth/login', 'POST', payload);
}

export function recoverAccount(payload) {
  return authRequest('/auth/recover', 'POST', payload);
}

export function regenerateRecoveryCodes(payload = {}) {
  return authRequest('/auth/recovery-codes/regenerate', 'POST', payload);
}

export function logout() {
  return authRequest('/auth/logout', 'POST', {});
}

export function getMe() {
  return authRequest('/auth/me');
}

export function listUsers() {
  return apiGet('/app/users');
}

export function createUser(payload) {
  return apiPost('/app/users', payload);
}

export function updateUser(userId, payload) {
  return apiPatch(`/app/users/${encodeURIComponent(userId)}`, payload);
}

export function disableUser(userId) {
  return apiPost(`/app/users/${encodeURIComponent(userId)}/disable`, {});
}

export function enableUser(userId) {
  return apiPost(`/app/users/${encodeURIComponent(userId)}/enable`, {});
}

export function resetPassword(userId, payload) {
  return apiPost(`/app/users/${encodeURIComponent(userId)}/reset-password`, payload);
}

export function listRoles() {
  return apiGet('/app/roles');
}

export function setUserRoles(userId, roles) {
  return apiPatch(`/app/users/${encodeURIComponent(userId)}/roles`, { roles });
}

export function listSessions() {
  return apiGet('/app/sessions');
}

export function revokeSession(sessionId) {
  return apiPost(`/app/sessions/${encodeURIComponent(sessionId)}/revoke`, {});
}

export function listAudit() {
  return apiGet('/app/audit');
}