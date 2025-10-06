import axios from 'axios';
import type { Service, UserJourney, SLI, SLO, Artifact, AnalysisJob } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Services
export const servicesApi = {
  getAll: () => apiClient.get<Service[]>('/services'),
  getById: (id: string) => apiClient.get<Service>(`/services/${id}`),
  create: (data: Partial<Service>) => apiClient.post<Service>('/services', data),
  update: (id: string, data: Partial<Service>) => apiClient.patch<Service>(`/services/${id}`, data),
  delete: (id: string) => apiClient.delete(`/services/${id}`),
};

// User Journeys
export const journeysApi = {
  getByServiceId: (serviceId: string) =>
    apiClient.get<UserJourney[]>(`/services/${serviceId}/journeys`),
  getById: (id: string) => apiClient.get<UserJourney>(`/journeys/${id}`),
};

// SLIs
export const slisApi = {
  getByJourneyId: (journeyId: string) =>
    apiClient.get<SLI[]>(`/journeys/${journeyId}/slis`),
  getById: (id: string) => apiClient.get<SLI>(`/slis/${id}`),
  approve: (id: string, approvedBy: string) =>
    apiClient.post(`/slis/${id}/approve`, { approved_by: approvedBy }),
};

// SLOs
export const slosApi = {
  getBySliId: (sliId: string) =>
    apiClient.get<SLO[]>(`/slis/${sliId}/slos`),
  getById: (id: string) => apiClient.get<SLO>(`/slos/${id}`),
  create: (data: Partial<SLO>) => apiClient.post<SLO>('/slos', data),
  update: (id: string, data: Partial<SLO>) =>
    apiClient.patch<SLO>(`/slos/${id}`, data),
  approve: (id: string) =>
    apiClient.post(`/slos/${id}/approve`),
};

// Artifacts
export const artifactsApi = {
  getBySloId: (sloId: string) =>
    apiClient.get<Artifact[]>(`/slos/${sloId}/artifacts`),
  getById: (id: string) => apiClient.get<Artifact>(`/artifacts/${id}`),
  validate: (id: string) =>
    apiClient.post(`/artifacts/${id}/validate`),
  approve: (id: string) =>
    apiClient.post(`/artifacts/${id}/approve`),
  deploy: (id: string) =>
    apiClient.post(`/artifacts/${id}/deploy`),
};

// Analysis
export const analysisApi = {
  trigger: (serviceId: string) =>
    apiClient.post<{ job_id: string }>('/analyze', { service_id: serviceId }),
  getStatus: (jobId: string) =>
    apiClient.get<AnalysisJob>(`/analyze/${jobId}`),
};

export default apiClient;
