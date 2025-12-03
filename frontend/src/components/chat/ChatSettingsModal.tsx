import { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle } from 'lucide-react';
import { useChatSettings } from '../../hooks/useChatSettings';
import Button from '../ui/Button';
import Input from '../ui/Input';

interface ChatSettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function ChatSettingsModal({ isOpen, onClose }: ChatSettingsModalProps) {
    const { settings, updateSettings, isUpdating, isLoading, error } = useChatSettings();
    const [localSettings, setLocalSettings] = useState({
        llm_api_url: '',
        llm_api_key: '',
        llm_model: 'gpt-3.5-turbo',
        temperature: 0.7,
    });

    useEffect(() => {
        if (settings) {
            setLocalSettings(settings);
        }
    }, [settings]);

    if (!isOpen) return null;

    const handleSave = async () => {
        try {
            await updateSettings(localSettings);
            onClose();
        } catch (err) {
            console.error('Failed to save settings', err);
        }
    };

    return (
        <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-in fade-in duration-200"
            onClick={onClose}
        >
            <div
                className="bg-background rounded-xl w-full max-w-md p-6 m-4 border border-border shadow-xl animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-lg font-semibold text-foreground">Chat Settings</h2>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-background-tertiary rounded-lg transition-colors text-foreground-muted hover:text-foreground"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {isLoading ? (
                    <div className="flex justify-center py-8">
                        <Loader2 className="w-8 h-8 animate-spin text-accent" />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {error && (
                            <div className="flex items-center gap-2 p-3 bg-danger/10 border border-danger/20 rounded-lg text-danger text-sm">
                                <AlertCircle className="w-4 h-4 shrink-0" />
                                Failed to load settings
                            </div>
                        )}

                        <Input
                            id="api-url"
                            label="API URL"
                            value={localSettings.llm_api_url}
                            onChange={(e) =>
                                setLocalSettings((s) => ({ ...s, llm_api_url: e.target.value }))
                            }
                            placeholder="http://localhost:8000/api/v1"
                        />

                        <Input
                            id="api-key"
                            type="password"
                            label="API Key"
                            value={localSettings.llm_api_key}
                            onChange={(e) =>
                                setLocalSettings((s) => ({ ...s, llm_api_key: e.target.value }))
                            }
                            placeholder="sk-..."
                        />

                        <Input
                            id="model"
                            label="Model"
                            value={localSettings.llm_model}
                            onChange={(e) =>
                                setLocalSettings((s) => ({ ...s, llm_model: e.target.value }))
                            }
                            placeholder="gpt-3.5-turbo"
                        />

                        <div>
                            <label className="block text-sm font-medium text-foreground mb-2">
                                Temperature: {localSettings.temperature}
                            </label>
                            <input
                                type="range"
                                min="0"
                                max="2"
                                step="0.1"
                                value={localSettings.temperature}
                                onChange={(e) =>
                                    setLocalSettings((s) => ({
                                        ...s,
                                        temperature: parseFloat(e.target.value),
                                    }))
                                }
                                className="w-full accent-accent h-2 bg-background-tertiary rounded-lg appearance-none cursor-pointer"
                            />
                            <div className="flex justify-between text-xs text-foreground-subtle mt-1">
                                <span>Precise</span>
                                <span>Creative</span>
                            </div>
                        </div>

                        <div className="pt-4">
                            <Button
                                onClick={handleSave}
                                isLoading={isUpdating}
                                className="w-full"
                            >
                                Save Changes
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
