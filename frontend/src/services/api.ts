import axios from 'axios';
import type { Service, UserJourney, SLI, SLO, Artifact, AnalysisJob } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Type-safe response handler
const handleResponse = <T>(response: { data: T }) => response.data;

// Services API
export const servicesApi = {
  getAll: async (): Promise<Service[]> => {
    const response = await apiClient.get<Service[]>('/services');
    return handleResponse(response);
  },
  getById: async (id: string): Promise<Service> => {
    const response = await apiClient.get<Service>(`/services/${id}`);
    return handleResponse(response);
  },
  create: async (data: {
    name: string;
    environment: 'development' | 'staging' | 'production';
    owner_team: string;
    telemetry_endpoints: Record<string, string>;
  }): Promise<Service> => {
    const response = await apiClient.post<Service>('/services', data);
    return handleResponse(response);
  },
  update: async (id: string, data: Partial<Service>): Promise<Service> => {
    const response = await apiClient.patch<Service>(`/services/${id}`, data);
    return handleResponse(response);
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/services/${id}`);
  },
};

// User Journeys API
export const journeysApi = {
  getByServiceId: async (serviceId: string): Promise<UserJourney[]> => {
    const response = await apiClient.get<UserJourney[]>(`/services/${serviceId}/journeys`);
    return handleResponse(response);
  },
  getById: async (id: string): Promise<UserJourney> => {
    const response = await apiClient.get<UserJourney>(`/journeys/${id}`);
    return handleResponse(response);
  },
};

// SLIs API
export const slisApi = {
  getByJourneyId: async (journeyId: string): Promise<SLI[]> => {
    const response = await apiClient.get<SLI[]>(`/journeys/${journeyId}/slis`);
    return handleResponse(response);
  },
  getById: async (id: string): Promise<SLI> => {
    const response = await apiClient.get<SLI>(`/slis/${id}`);
    return handleResponse(response);
  },
  approve: async (id: string, approvedBy: string): Promise<SLI> => {
    const response = await apiClient.post<SLI>(`/slis/${id}/approve`, { approved_by: approvedBy });
    return handleResponse(response);
  },
  getAll: async (): Promise<SLI[]> => {
    const response = await apiClient.get<SLI[]>('/slis');
    return handleResponse(response);
  },
};

// SLOs API
export const slosApi = {
  getBySliId: async (sliId: string): Promise<SLO[]> => {
    const response = await apiClient.get<SLO[]>(`/slis/${sliId}/slos`);
    return handleResponse(response);
  },
  getById: async (id: string): Promise<SLO> => {
    const response = await apiClient.get<SLO>(`/slos/${id}`);
    return handleResponse(response);
  },
  create: async (data: {
    sli_id: string;
    threshold_value: number;
    comparison_operator: 'lt' | 'lte' | 'gt' | 'gte' | 'eq';
    time_window: string;
    target_percentage: number;
    severity: 'critical' | 'high' | 'medium' | 'low';
  }): Promise<SLO> => {
    const response = await apiClient.post<SLO>('/slos', data);
    return handleResponse(response);
  },
  update: async (id: string, data: Partial<SLO>): Promise<SLO> => {
    const response = await apiClient.patch<SLO>(`/slos/${id}`, data);
    return handleResponse(response);
  },
  approve: async (id: string): Promise<SLO> => {
    const response = await apiClient.post<SLO>(`/slos/${id}/approve`);
    return handleResponse(response);
  },
  getAll: async (): Promise<SLO[]> => {
    const response = await apiClient.get<SLO[]>('/slos');
    return handleResponse(response);
  },
};

// Artifacts API
export const artifactsApi = {
  getBySloId: async (sloId: string): Promise<Artifact[]> => {
    const response = await apiClient.get<Artifact[]>(`/slos/${sloId}/artifacts`);
    return handleResponse(response);
  },
  getById: async (id: string): Promise<Artifact> => {
    const response = await apiClient.get<Artifact>(`/artifacts/${id}`);
    return handleResponse(response);
  },
  validate: async (id: string): Promise<Artifact> => {
    const response = await apiClient.post<Artifact>(`/artifacts/${id}/validate`);
    return handleResponse(response);
  },
  approve: async (id: string): Promise<Artifact> => {
    const response = await apiClient.post<Artifact>(`/artifacts/${id}/approve`);
    return handleResponse(response);
  },
  deploy: async (id: string): Promise<Artifact> => {
    const response = await apiClient.post<Artifact>(`/artifacts/${id}/deploy`);
    return handleResponse(response);
  },
};

// Analysis API
export const analysisApi = {
  trigger: async (serviceId: string): Promise<{ job_id: string }> => {
    const response = await apiClient.post<{ job_id: string }>('/analyze', { service_id: serviceId });
    return handleResponse(response);
  },
  getStatus: async (jobId: string): Promise<AnalysisJob> => {
    const response = await apiClient.get<AnalysisJob>(`/analyze/${jobId}`);
    return handleResponse(response);
  },
  getAll: async (): Promise<AnalysisJob[]> => {
    const response = await apiClient.get<AnalysisJob[]>('/analyze');
    return handleResponse(response);
  },
};

export default apiClient;
