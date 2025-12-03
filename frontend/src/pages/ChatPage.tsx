import { useState, useRef, useEffect } from "react";
import {
    Send,
    Settings,
    X,
    Bot,
    User,
    Loader2,
    AlertCircle,
    Trash2,
    Plus,
    MessageSquare,
    Pencil,
    Check,
    RotateCcw,
    ChevronLeft,
    Menu,
} from "lucide-react";
import { apiClient } from "../api/client";
import Layout from "../components/layout/Layout";

const generateId = () => Math.random().toString(36).substr(2, 9);

interface Message {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
}

interface Room {
    id: string;
    name: string;
    messages: Message[];
    systemPrompt: string;
    createdAt: number;
}

interface ChatSettings {
    llm_api_url: string;
    llm_api_key: string;
    llm_model: string;
    temperature: number;
}

export default function ChatPage() {
    // Chat rooms state
    const [rooms, setRooms] = useState<Room[]>([
        {
            id: "default",
            name: "New Chat",
            messages: [],
            systemPrompt: "",
            createdAt: Date.now(),
        },
    ]);
    const [activeRoomId, setActiveRoomId] = useState("default");
    const [showSidebar, setShowSidebar] = useState(true);

    // UI state
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showSettings, setShowSettings] = useState(false);
    const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
    const [editingContent, setEditingContent] = useState("");
    const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
    const [editingRoomName, setEditingRoomName] = useState("");

    // Config state
    const [config, setConfig] = useState<ChatSettings>({
        llm_api_url: "",
        llm_api_key: "",
        llm_model: "gpt-3.5-turbo",
        temperature: 0.7,
    });

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    const activeRoom = rooms.find((r) => r.id === activeRoomId) || rooms[0];

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [activeRoom?.messages]);

    // Fetch settings on mount
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const response = await apiClient.get<ChatSettings>("/chat/settings");
                setConfig(response.data);
            } catch (err) {
                console.error("Failed to fetch chat settings", err);
            }
        };
        fetchSettings();
    }, []);

    const saveSettings = async () => {
        try {
            await apiClient.put("/chat/settings", config);
            setShowSettings(false);
        } catch (err) {
            setError("Failed to save settings");
        }
    };

    // Room management
    const createRoom = () => {
        const newRoom: Room = {
            id: generateId(),
            name: "New Chat",
            messages: [],
            systemPrompt: "",
            createdAt: Date.now(),
        };
        setRooms((prev) => [newRoom, ...prev]);
        setActiveRoomId(newRoom.id);
    };

    const deleteRoom = (roomId: string) => {
        if (rooms.length === 1) {
            setRooms([
                {
                    id: generateId(),
                    name: "New Chat",
                    messages: [],
                    systemPrompt: "",
                    createdAt: Date.now(),
                },
            ]);
        } else {
            setRooms((prev) => prev.filter((r) => r.id !== roomId));
            if (activeRoomId === roomId) {
                setActiveRoomId(rooms.find((r) => r.id !== roomId)?.id || "default");
            }
        }
    };

    const updateRoom = (roomId: string, updates: Partial<Room>) => {
        setRooms((prev) =>
            prev.map((r) => (r.id === roomId ? { ...r, ...updates } : r)),
        );
    };

    const updateMessages = (newMessages: Message[]) => {
        updateRoom(activeRoomId, { messages: newMessages });
    };

    // Message editing
    const startEditMessage = (msg: Message) => {
        setEditingMessageId(msg.id);
        setEditingContent(msg.content);
    };

    const cancelEditMessage = () => {
        setEditingMessageId(null);
        setEditingContent("");
    };

    const saveEditMessage = (msgId: string) => {
        const msgIndex = activeRoom.messages.findIndex((m) => m.id === msgId);
        if (msgIndex === -1) return;

        // Keep messages up to and including the edited one, remove everything after
        const newMessages = activeRoom.messages
            .slice(0, msgIndex + 1)
            .map((m) =>
                m.id === msgId ? { ...m, content: editingContent } : m,
            );
        updateMessages(newMessages);
        cancelEditMessage();
    };

    const regenerateFrom = async (msgId: string) => {
        const msgIndex = activeRoom.messages.findIndex((m) => m.id === msgId);
        if (msgIndex === -1) return;

        // Keep messages up to but not including the assistant message to regenerate
        const newMessages = activeRoom.messages.slice(0, msgIndex);
        updateMessages(newMessages);

        // Regenerate
        await sendMessageWithHistory(newMessages);
    };

    const sendMessageWithHistory = async (history: Message[]) => {
        setError(null);
        setIsLoading(true);

        try {
            const messagesPayload = [];
            if (activeRoom.systemPrompt.trim()) {
                messagesPayload.push({
                    role: "system",
                    content: activeRoom.systemPrompt.trim(),
                });
            }
            history.forEach((m) =>
                messagesPayload.push({ role: m.role, content: m.content }),
            );

            const token = localStorage.getItem('access_token');
            const response = await fetch(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'}/chat/completions`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        model: config.llm_model,
                        messages: messagesPayload,
                        temperature: config.temperature,
                        stream: true,
                    }),
                },
            );

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }

            const assistantMsg: Message = {
                id: generateId(),
                role: "assistant",
                content: "",
            };

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let content = "";

            if (!reader) throw new Error("No response body");

            updateRoom(activeRoomId, {
                messages: [...history, assistantMsg],
            });

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk
                    .split("\n")
                    .filter((line) => line.startsWith("data: "));

                for (const line of lines) {
                    const data = line.slice(6);
                    if (data === "[DONE]") continue;
                    try {
                        const parsed = JSON.parse(data);
                        const delta = parsed.choices?.[0]?.delta;
                        if (delta?.content) {
                            content += delta.content;
                            updateRoom(activeRoomId, {
                                messages: [
                                    ...history,
                                    { ...assistantMsg, content },
                                ],
                            });
                        }
                    } catch { }
                }
            }

            // Auto-name room if first message
            if (history.length === 1 && activeRoom.name === "New Chat") {
                const preview =
                    history[0].content.slice(0, 30) +
                    (history[0].content.length > 30 ? "..." : "");
                updateRoom(activeRoomId, { name: preview });
            }
        } catch (err: any) {
            setError(err.message);
        } finally {
            setIsLoading(false);
            inputRef.current?.focus();
        }
    };

    const sendMessage = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            id: generateId(),
            role: "user",
            content: input.trim(),
        };
        const newHistory = [...activeRoom.messages, userMessage];
        updateMessages(newHistory);
        setInput("");

        await sendMessageWithHistory(newHistory);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <Layout>
            <div className="h-[calc(100vh-8rem)] flex bg-gray-900 text-gray-100 rounded-xl overflow-hidden shadow-2xl border border-gray-700">
                {/* Sidebar */}
                <aside
                    className={`${showSidebar ? "w-64" : "w-0"} transition-all duration-200 border-r border-gray-700 bg-gray-800 flex flex-col overflow-hidden`}
                >
                    <div className="p-3 border-b border-gray-700">
                        <button
                            onClick={createRoom}
                            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition text-sm font-medium"
                        >
                            <Plus className="w-4 h-4" /> New Chat
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {rooms.map((room) => (
                            <div
                                key={room.id}
                                className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition ${room.id === activeRoomId
                                        ? "bg-gray-700"
                                        : "hover:bg-gray-700/50"
                                    }`}
                                onClick={() => setActiveRoomId(room.id)}
                            >
                                <MessageSquare className="w-4 h-4 text-gray-400 flex-shrink-0" />

                                {editingRoomId === room.id ? (
                                    <input
                                        type="text"
                                        value={editingRoomName}
                                        onChange={(e) =>
                                            setEditingRoomName(e.target.value)
                                        }
                                        onBlur={() => {
                                            updateRoom(room.id, {
                                                name: editingRoomName || "Untitled",
                                            });
                                            setEditingRoomId(null);
                                        }}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                updateRoom(room.id, {
                                                    name:
                                                        editingRoomName ||
                                                        "Untitled",
                                                });
                                                setEditingRoomId(null);
                                            }
                                        }}
                                        className="flex-1 bg-gray-600 px-2 py-0.5 rounded text-sm"
                                        autoFocus
                                        onClick={(e) => e.stopPropagation()}
                                    />
                                ) : (
                                    <span className="flex-1 text-sm truncate">
                                        {room.name}
                                    </span>
                                )}

                                <div className="hidden group-hover:flex items-center gap-1">
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setEditingRoomId(room.id);
                                            setEditingRoomName(room.name);
                                        }}
                                        className="p-1 hover:bg-gray-600 rounded"
                                    >
                                        <Pencil className="w-3 h-3 text-gray-400" />
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            deleteRoom(room.id);
                                        }}
                                        className="p-1 hover:bg-gray-600 rounded"
                                    >
                                        <Trash2 className="w-3 h-3 text-gray-400" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="p-3 border-t border-gray-700">
                        <button
                            onClick={() => setShowSettings(true)}
                            className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-700 rounded-lg transition text-sm text-gray-400"
                        >
                            <Settings className="w-4 h-4" /> Settings
                        </button>
                    </div>
                </aside>

                {/* Main Chat Area */}
                <main className="flex-1 flex flex-col overflow-hidden">
                    {/* Header */}
                    <header className="flex items-center gap-3 px-4 py-3 border-b border-gray-700 bg-gray-800">
                        <button
                            onClick={() => setShowSidebar(!showSidebar)}
                            className="p-2 hover:bg-gray-700 rounded-lg transition"
                        >
                            {showSidebar ? (
                                <ChevronLeft className="w-5 h-5" />
                            ) : (
                                <Menu className="w-5 h-5" />
                            )}
                        </button>
                        <div className="flex-1">
                            <h1 className="font-medium truncate">
                                {activeRoom.name}
                            </h1>
                            <p className="text-xs text-gray-500">{config.llm_model}</p>
                        </div>
                    </header>

                    {/* System Prompt Bar */}
                    <div className="px-4 py-2 bg-gray-800/50 border-b border-gray-700">
                        <details className="group">
                            <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-300 flex items-center gap-1">
                                <span>System Prompt</span>
                                {activeRoom.systemPrompt && (
                                    <span className="text-green-400">●</span>
                                )}
                            </summary>
                            <textarea
                                value={activeRoom.systemPrompt}
                                onChange={(e) =>
                                    updateRoom(activeRoomId, {
                                        systemPrompt: e.target.value,
                                    })
                                }
                                placeholder="Enter system instructions (e.g., 'You are a helpful coding assistant...')"
                                className="mt-2 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-blue-500"
                                rows={3}
                            />
                        </details>
                    </div>

                    {/* Messages */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {activeRoom.messages.length === 0 && (
                            <div className="h-full flex items-center justify-center">
                                <div className="text-center text-gray-500">
                                    <Bot className="w-12 h-12 mx-auto mb-3 opacity-50" />
                                    <p className="text-lg">Start a conversation</p>
                                    <p className="text-sm mt-1">
                                        Configure system prompt above if needed
                                    </p>
                                </div>
                            </div>
                        )}

                        {activeRoom.messages.map((msg, i) => (
                            <div
                                key={msg.id}
                                className={`group flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                            >
                                {msg.role === "assistant" && (
                                    <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                                        <Bot className="w-5 h-5" />
                                    </div>
                                )}

                                <div
                                    className={`max-w-2xl ${msg.role === "user" ? "order-first" : ""}`}
                                >
                                    {editingMessageId === msg.id ? (
                                        <div className="space-y-2">
                                            <textarea
                                                value={editingContent}
                                                onChange={(e) =>
                                                    setEditingContent(
                                                        e.target.value,
                                                    )
                                                }
                                                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-blue-500"
                                                rows={4}
                                                autoFocus
                                            />
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() =>
                                                        saveEditMessage(msg.id)
                                                    }
                                                    className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm flex items-center gap-1"
                                                >
                                                    <Check className="w-3 h-3" />{" "}
                                                    Save
                                                </button>
                                                <button
                                                    onClick={cancelEditMessage}
                                                    className="px-3 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div
                                            className={`px-4 py-3 rounded-2xl ${msg.role === "user"
                                                    ? "bg-blue-600 text-white rounded-br-md"
                                                    : "bg-gray-700 text-gray-100 rounded-bl-md"
                                                }`}
                                        >
                                            <p className="whitespace-pre-wrap text-sm leading-relaxed">
                                                {msg.content ||
                                                    (isLoading &&
                                                        i ===
                                                        activeRoom.messages.length -
                                                        1
                                                        ? "..."
                                                        : "")}
                                            </p>
                                        </div>
                                    )}

                                    {/* Message actions */}
                                    {editingMessageId !== msg.id && (
                                        <div className="hidden group-hover:flex items-center gap-1 mt-1 justify-end">
                                            {msg.role === "user" && (
                                                <button
                                                    onClick={() =>
                                                        startEditMessage(msg)
                                                    }
                                                    className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-gray-200"
                                                    title="Edit"
                                                >
                                                    <Pencil className="w-3 h-3" />
                                                </button>
                                            )}
                                            {msg.role === "assistant" && (
                                                <button
                                                    onClick={() =>
                                                        regenerateFrom(msg.id)
                                                    }
                                                    className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-gray-200"
                                                    title="Regenerate"
                                                >
                                                    <RotateCcw className="w-3 h-3" />
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {msg.role === "user" && (
                                    <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center flex-shrink-0">
                                        <User className="w-5 h-5" />
                                    </div>
                                )}
                            </div>
                        ))}

                        {isLoading &&
                            activeRoom.messages[activeRoom.messages.length - 1]
                                ?.role !== "assistant" && (
                                <div className="flex gap-3">
                                    <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                                        <Bot className="w-5 h-5" />
                                    </div>
                                    <div className="bg-gray-700 px-4 py-3 rounded-2xl rounded-bl-md">
                                        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                                    </div>
                                </div>
                            )}

                        <div ref={messagesEndRef} />
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="mx-4 mb-2 p-3 bg-red-900/50 border border-red-700 rounded-lg flex items-center gap-2 text-red-200">
                            <AlertCircle className="w-5 h-5 flex-shrink-0" />
                            <p className="text-sm flex-1">{error}</p>
                            <button
                                onClick={() => setError(null)}
                                className="p-1 hover:bg-red-800 rounded"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                    )}

                    {/* Input */}
                    <div className="p-4 border-t border-gray-700 bg-gray-800">
                        <div className="flex gap-2 items-end max-w-4xl mx-auto">
                            <textarea
                                ref={inputRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Type your message..."
                                rows={1}
                                className="flex-1 bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-blue-500 max-h-32"
                            />
                            <button
                                onClick={sendMessage}
                                disabled={!input.trim() || isLoading}
                                className="p-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-xl transition"
                            >
                                {isLoading ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Send className="w-5 h-5" />
                                )}
                            </button>
                        </div>
                    </div>
                </main>

                {/* Settings Modal */}
                {showSettings && (
                    <div
                        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                        onClick={() => setShowSettings(false)}
                    >
                        <div
                            className="bg-gray-800 rounded-xl w-full max-w-md p-6 m-4"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex justify-between items-center mb-4">
                                <h2 className="text-lg font-semibold">Settings</h2>
                                <button
                                    onClick={() => setShowSettings(false)}
                                    className="p-1 hover:bg-gray-700 rounded"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">
                                        API URL
                                    </label>
                                    <input
                                        type="text"
                                        value={config.llm_api_url}
                                        onChange={(e) =>
                                            setConfig((c) => ({
                                                ...c,
                                                llm_api_url: e.target.value,
                                            }))
                                        }
                                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">
                                        API Key
                                    </label>
                                    <input
                                        type="password"
                                        value={config.llm_api_key}
                                        onChange={(e) =>
                                            setConfig((c) => ({
                                                ...c,
                                                llm_api_key: e.target.value,
                                            }))
                                        }
                                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">
                                        Model
                                    </label>
                                    <input
                                        type="text"
                                        value={config.llm_model}
                                        onChange={(e) =>
                                            setConfig((c) => ({
                                                ...c,
                                                llm_model: e.target.value,
                                            }))
                                        }
                                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">
                                        Temperature: {config.temperature}
                                    </label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="2"
                                        step="0.1"
                                        value={config.temperature}
                                        onChange={(e) =>
                                            setConfig((c) => ({
                                                ...c,
                                                temperature: parseFloat(
                                                    e.target.value,
                                                ),
                                            }))
                                        }
                                        className="w-full accent-blue-500"
                                    />
                                </div>
                            </div>

                            <button
                                onClick={saveSettings}
                                className="w-full mt-6 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition"
                            >
                                Save & Close
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </Layout>
    );
}
