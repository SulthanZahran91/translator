import { useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';
import type { JobLog } from '../../api/jobs';
import Card from './Card';
import { Terminal, Info, AlertTriangle, AlertCircle } from 'lucide-react';

interface LogPanelProps {
    logs: JobLog[];
    className?: string;
    isLoading?: boolean;
}

export default function LogPanel({ logs, className, isLoading }: LogPanelProps) {
    const scrollRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom when new logs arrive
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    const getIcon = (level: string) => {
        switch (level.toUpperCase()) {
            case 'ERROR':
                return <AlertCircle className="w-4 h-4 text-danger" />;
            case 'WARNING':
                return <AlertTriangle className="w-4 h-4 text-warning" />;
            default:
                return <Info className="w-4 h-4 text-accent" />;
        }
    };

    const getColor = (level: string) => {
        switch (level.toUpperCase()) {
            case 'ERROR':
                return 'text-danger';
            case 'WARNING':
                return 'text-warning';
            default:
                return 'text-foreground-muted';
        }
    };

    return (
        <Card className={cn('flex flex-col h-[400px]', className)}>
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-background-secondary rounded-t-xl">
                <Terminal className="w-4 h-4 text-foreground-subtle" />
                <h3 className="font-medium text-foreground text-sm">Execution Logs</h3>
                {isLoading && (
                    <span className="ml-auto text-xs text-foreground-muted animate-pulse">
                        Syncing...
                    </span>
                )}
            </div>

            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-2 bg-background-tertiary rounded-b-xl"
            >
                {logs.length === 0 ? (
                    <div className="text-center text-foreground-muted py-8">
                        No logs available yet
                    </div>
                ) : (
                    logs.map((log) => (
                        <div key={log.id} className="flex gap-3 hover:bg-background-secondary/50 p-1 rounded transition-colors">
                            <div className="shrink-0 pt-0.5 opacity-70">
                                {getIcon(log.level)}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5">
                                    <span className="text-foreground-subtle opacity-60">
                                        {new Date(log.created_at).toLocaleTimeString()}
                                    </span>
                                    {log.phase && (
                                        <span className="px-1.5 py-0.5 rounded-full bg-background-secondary text-foreground-muted text-[10px] border border-border">
                                            {log.phase}
                                        </span>
                                    )}
                                </div>
                                <p className={cn('break-words leading-relaxed', getColor(log.level))}>
                                    {log.message}
                                </p>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </Card>
    );
}
