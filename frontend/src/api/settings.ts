import { apiClient } from './client';

export interface ChatSettings {
    llm_api_url: string;
    llm_api_key: string;
    llm_model: string;
    temperature: number;
}

export const settingsApi = {
    get: async () => {
        const response = await apiClient.get<ChatSettings>('/chat/settings');
        return response.data;
    },

    update: async (settings: ChatSettings) => {
        const response = await apiClient.put<ChatSettings>('/chat/settings', settings);
        return response.data;
    },
};
