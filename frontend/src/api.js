import axios from 'axios';

export const api = axios.create({baseURL: import.meta.env.VITE_API_BASE_URL || '', timeout: 30000});
const auth = (session, signal) => ({headers: {Authorization: `Bearer ${session.session_token}`}, signal});

export async function uploadDocument(file, documentType, signal) {
  const form = new FormData();
  form.append('image', file);
  form.append('document_type', documentType);
  form.append('consent', 'true');
  // Let the browser set the multipart boundary.
  return (await api.post('/api/v1/kyc/verify-document', form, {signal})).data;
}
export async function startChallenge(session, signal) {
  return (await api.post('/api/v1/kyc/liveness/start', {document_id: session.document_id}, auth(session, signal))).data;
}
export async function checkFrame(session, challengeId, sequence, image, signal) {
  return (await api.post('/api/v1/kyc/liveness-check', {
    document_id: session.document_id, challenge_id: challengeId, sequence, image_base64: image,
  }, auth(session, signal))).data;
}
export async function verifyFace(session, challengeId, selfie, signal) {
  return (await api.post('/api/v1/kyc/verify-face', {
    document_id: session.document_id, challenge_id: challengeId, selfie_base64: selfie,
  }, auth(session, signal))).data;
}
export async function deleteSession(session) {
  if (session) await api.delete(`/api/v1/kyc/sessions/${session.document_id}`, auth(session));
}
export function errorMessage(error) {
  const detail = error?.response?.data?.error;
  if (detail) return `${detail.message}${detail.request_id ? ` (Reference: ${detail.request_id})` : ''}`;
  if (error?.code === 'ECONNABORTED') return 'The request timed out. Please retry.';
  if (error?.isAxiosError && !error.response) return 'Cannot reach the API. Check that the backend is running.';
  return error?.message || 'Something went wrong. Please retry.';
}

