import { useState, useRef, useEffect } from "react";
import {
    Send,
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
import Layout from "../components/layout/Layout";
import { useChatSettings } from "../hooks/useChatSettings";
import { API_URL } from "../api/client";

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

export default function ChatPage() {
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

    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
    const [editingContent, setEditingContent] = useState("");
    const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
    const [editingRoomName, setEditingRoomName] = useState("");

    const { settings } = useChatSettings();

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    const activeRoom = rooms.find((r) => r.id === activeRoomId) || rooms[0];

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [activeRoom?.messages]);

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
                `${API_URL}/chat/completions`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        model: settings?.llm_model || "gpt-3.5-turbo",
                        messages: messagesPayload,
                        temperature: settings?.temperature ?? 0.7,
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
                    } catch {
                        // Ignore parse errors for partial chunks
                    }
                }
            }

            // Auto-name room if first message
            if (history.length === 1 && activeRoom.name === "New Chat") {
                const preview =
                    history[0].content.slice(0, 30) +
                    (history[0].content.length > 30 ? "..." : "");
                updateRoom(activeRoomId, { name: preview });
            }
        } catch (err: unknown) {
            if (err instanceof Error) {
                setError(err.message);
            } else {
                setError("An unknown error occurred");
            }
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
            <div className="mb-4">
                <h1 className="text-2xl font-display font-bold text-foreground mb-2">
                    AI Assistant
                </h1>
                <p className="text-foreground-muted">
                    Chat with your documents and get instant translations
                </p>
            </div>

            <div className="h-[calc(100vh-12rem)] flex bg-background-secondary rounded-xl overflow-hidden shadow-sm border border-border">
                {/* Sidebar */}
                <aside
                    className={`${showSidebar ? "w-64" : "w-0"} transition-all duration-200 border-r border-border bg-background-secondary flex flex-col overflow-hidden`}
                >
                    <div className="p-3 border-b border-border">
                        <button
                            onClick={createRoom}
                            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg transition text-sm font-medium"
                        >
                            <Plus className="w-4 h-4" /> New Chat
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-2 space-y-1">
                        {rooms.map((room) => (
                            <div
                                key={room.id}
                                className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition ${room.id === activeRoomId
                                    ? "bg-background-tertiary text-foreground"
                                    : "text-foreground-muted hover:bg-background-tertiary/50 hover:text-foreground"
                                    }`}
                                onClick={() => setActiveRoomId(room.id)}
                            >
                                <MessageSquare className="w-4 h-4 flex-shrink-0" />

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
                                        className="flex-1 bg-background border border-border px-2 py-0.5 rounded text-sm text-foreground focus:outline-none focus:border-accent"
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
                                        className="p-1 hover:bg-background-tertiary rounded text-foreground-muted hover:text-foreground"
                                    >
                                        <Pencil className="w-3 h-3" />
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            deleteRoom(room.id);
                                        }}
                                        className="p-1 hover:bg-background-tertiary rounded text-foreground-muted hover:text-danger"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </aside>

                {/* Main Chat Area */}
                <main className="flex-1 flex flex-col overflow-hidden bg-background">
                    {/* Header */}
                    <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-background-secondary">
                        <button
                            onClick={() => setShowSidebar(!showSidebar)}
                            className="p-2 hover:bg-background-tertiary rounded-lg transition text-foreground-muted hover:text-foreground"
                        >
                            {showSidebar ? (
                                <ChevronLeft className="w-5 h-5" />
                            ) : (
                                <Menu className="w-5 h-5" />
                            )}
                        </button>
                        <div className="flex-1">
                            <h1 className="font-medium truncate text-foreground">
                                {activeRoom.name}
                            </h1>
                            <p className="text-xs text-foreground-subtle">{settings?.llm_model || "Loading..."}</p>
                        </div>
                    </header>

                    {/* System Prompt Bar */}
                    <div className="px-4 py-2 bg-background-secondary/50 border-b border-border">
                        <details className="group">
                            <summary className="cursor-pointer text-xs text-foreground-muted hover:text-foreground flex items-center gap-1">
                                <span>System Prompt</span>
                                {activeRoom.systemPrompt && (
                                    <span className="text-success">●</span>
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
                                className="mt-2 w-full bg-background border border-border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-accent text-foreground placeholder:text-foreground-subtle"
                                rows={3}
                            />
                        </details>
                    </div>

                    {/* Messages */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {activeRoom.messages.length === 0 && (
                            <div className="h-full flex items-center justify-center">
                                <div className="text-center text-foreground-muted">
                                    <Bot className="w-12 h-12 mx-auto mb-3 opacity-50" />
                                    <p className="text-lg font-medium text-foreground">Start a conversation</p>
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
                                    <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center flex-shrink-0 text-white">
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
                                                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-accent text-foreground"
                                                rows={4}
                                                autoFocus
                                            />
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() =>
                                                        saveEditMessage(msg.id)
                                                    }
                                                    className="px-3 py-1 bg-accent hover:bg-accent-hover text-white rounded text-sm flex items-center gap-1"
                                                >
                                                    <Check className="w-3 h-3" />{" "}
                                                    Save
                                                </button>
                                                <button
                                                    onClick={cancelEditMessage}
                                                    className="px-3 py-1 bg-background-tertiary hover:bg-background-tertiary/80 text-foreground rounded text-sm"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div
                                            className={`px-4 py-3 rounded-2xl ${msg.role === "user"
                                                ? "bg-accent text-white rounded-br-md"
                                                : "bg-background-tertiary text-foreground rounded-bl-md"
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
                                                    className="p-1 hover:bg-background-tertiary rounded text-foreground-muted hover:text-foreground"
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
                                                    className="p-1 hover:bg-background-tertiary rounded text-foreground-muted hover:text-foreground"
                                                    title="Regenerate"
                                                >
                                                    <RotateCcw className="w-3 h-3" />
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {msg.role === "user" && (
                                    <div className="w-8 h-8 rounded-full bg-background-tertiary flex items-center justify-center flex-shrink-0 text-foreground">
                                        <User className="w-5 h-5" />
                                    </div>
                                )}
                            </div>
                        ))}

                        {isLoading &&
                            activeRoom.messages[activeRoom.messages.length - 1]
                                ?.role !== "assistant" && (
                                <div className="flex gap-3">
                                    <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white">
                                        <Bot className="w-5 h-5" />
                                    </div>
                                    <div className="bg-background-tertiary px-4 py-3 rounded-2xl rounded-bl-md">
                                        <Loader2 className="w-5 h-5 animate-spin text-foreground-muted" />
                                    </div>
                                </div>
                            )}

                        <div ref={messagesEndRef} />
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="mx-4 mb-2 p-3 bg-danger/10 border border-danger/20 rounded-lg flex items-center gap-2 text-danger">
                            <AlertCircle className="w-5 h-5 flex-shrink-0" />
                            <p className="text-sm flex-1">{error}</p>
                            <button
                                onClick={() => setError(null)}
                                className="p-1 hover:bg-danger/20 rounded"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                    )}

                    {/* Input */}
                    <div className="p-4 border-t border-border bg-background-secondary">
                        <div className="flex gap-2 items-end max-w-4xl mx-auto">
                            <textarea
                                ref={inputRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Type your message..."
                                rows={1}
                                className="flex-1 bg-background border border-border rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-accent text-foreground placeholder:text-foreground-subtle max-h-32"
                            />
                            <button
                                onClick={sendMessage}
                                disabled={!input.trim() || isLoading}
                                className="p-3 bg-accent hover:bg-accent-hover disabled:bg-background-tertiary disabled:text-foreground-muted disabled:cursor-not-allowed rounded-xl transition text-white"
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
            </div>
        </Layout>
    );
}
