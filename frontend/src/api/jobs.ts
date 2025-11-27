import apiClient from './client';

export interface Job {
  id: string;
  status: 'pending' | 'processing' | 'paused' | 'completed' | 'failed' | 'cancelled';
  source_file_name: string;
  source_file_size_bytes: number;
  source_format: string | null;
  output_format: string | null;
  source_language: string;
  target_language: string;
  total_units: number;
  completed_units: number;
  progress_percent: number;
  current_phase: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
}

export interface CreateJobParams {
  file: File;
  sourceLanguage?: string;
  targetLanguage?: string;
  outputFormat?: 'docx' | 'pdf';
}

export interface GlossaryTerm {
  source_term: string;
  target_term: string;
  confidence: string;
  occurrence_count: number;
}

export interface GlossaryConflict {
  source_term: string;
  translations: string[];
  resolved: boolean;
  resolved_translation: string | null;
}

export interface JobGlossary {
  terms: GlossaryTerm[];
  conflicts: GlossaryConflict[];
}

export const jobsApi = {
  async list(page = 1, perPage = 20): Promise<JobListResponse> {
    const response = await apiClient.get<JobListResponse>('/jobs', {
      params: { page, per_page: perPage },
    });
    return response.data;
  },

  async get(id: string): Promise<Job> {
    const response = await apiClient.get<Job>(`/jobs/${id}`);
    return response.data;
  },

  async create(params: CreateJobParams): Promise<Job> {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('source_language', params.sourceLanguage || 'ko');
    formData.append('target_language', params.targetLanguage || 'en');
    formData.append('output_format', params.outputFormat || 'docx');

    const response = await apiClient.post<Job>('/jobs', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async pause(id: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${id}/pause`);
    return response.data;
  },

  async resume(id: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${id}/resume`);
    return response.data;
  },

  async cancel(id: string): Promise<void> {
    await apiClient.delete(`/jobs/${id}`);
  },

  getDownloadUrl(id: string): string {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    const token = localStorage.getItem('access_token');
    return `${baseUrl}/jobs/${id}/download?token=${token}`;
  },

  async getGlossary(id: string): Promise<JobGlossary> {
    const response = await apiClient.get<JobGlossary>(`/jobs/${id}/glossary`);
    return response.data;
  },

  async resolveConflict(id: string, sourceTerm: string, chosenTranslation: string): Promise<void> {
    await apiClient.post(`/jobs/${id}/glossary/resolve`, {
      source_term: sourceTerm,
      chosen_translation: chosenTranslation,
    });
  },
};

