import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '../api/settings';


export const useChatSettings = () => {
    const queryClient = useQueryClient();

    const { data: settings, isLoading, error } = useQuery({
        queryKey: ['chatSettings'],
        queryFn: settingsApi.get,
        staleTime: 1000 * 60 * 5, // 5 minutes
        enabled: !!localStorage.getItem('access_token'), // Only fetch if authenticated
        retry: false,
    });

    const updateMutation = useMutation({
        mutationFn: settingsApi.update,
        onSuccess: (newSettings) => {
            queryClient.setQueryData(['chatSettings'], newSettings);
        },
    });

    return {
        settings,
        isLoading,
        error,
        updateSettings: updateMutation.mutateAsync,
        isUpdating: updateMutation.isPending,
    };
};
