"use client";

import { useState, useEffect, useRef } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Terminal, RefreshCw, Filter, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getLogs, type LogEntry } from "@/lib/api";

const REFRESH_INTERVAL = 3000;

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    if (isPaused) return;
    try {
      const data = await getLogs();
      setLogs(data.logs || []);
    } catch (err) {
      console.error("Failed to fetch logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isPaused]);

  useEffect(() => {
    if (!isPaused) {
      logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, isPaused]);

  const getBadgeColor = (level: string) => {
    switch (level.toUpperCase()) {
      case "INFO": return "bg-blue-500/10 text-blue-500 hover:bg-blue-500/20";
      case "WARN":
      case "WARNING": return "bg-amber-500/10 text-amber-500 hover:bg-amber-500/20";
      case "ERROR":
      case "CRITICAL": return "bg-red-500/10 text-red-500 hover:bg-red-500/20";
      case "DEBUG": return "bg-zinc-500/10 text-zinc-500 hover:bg-zinc-500/20";
      default: return "bg-zinc-500/10 text-zinc-500 hover:bg-zinc-500/20";
    }
  };

  const getMethodColor = (method?: string) => {
    switch (method?.toUpperCase()) {
      case "GET": return "text-blue-400";
      case "POST": return "text-emerald-400";
      case "PUT": return "text-amber-400";
      case "DELETE": return "text-red-400";
      default: return "text-zinc-400";
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b bg-background shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Live Logs</h2>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={isPaused ? "secondary" : "outline"}
            size="sm"
            onClick={() => setIsPaused(!isPaused)}
            className="text-xs"
          >
            {isPaused ? "Resume" : "Pause"}
          </Button>
          <Button variant="outline" size="sm" onClick={fetchLogs} disabled={isPaused}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div className="flex-1 bg-zinc-950 p-4 font-mono text-xs overflow-y-auto w-full">
        {loading && logs.length === 0 ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-4 w-3/4 bg-zinc-800" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="text-zinc-500 text-center mt-10">No logs available</div>
        ) : (
          <div className="space-y-1">
            {logs.map((log, i) => (
              <div key={i} className="flex gap-3 hover:bg-zinc-900/50 p-1 rounded transition-colors group text-zinc-300">
                <span className="text-zinc-500 shrink-0 select-none">
                  {new Date(log.timestamp).toLocaleTimeString([], { hour12: false, fractionalSecondDigits: 3 })}
                </span>
                <span className="shrink-0 w-20">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${getBadgeColor(log.level)}`}>
                    {log.level}
                  </span>
                </span>
                <span className="text-zinc-500 shrink-0 w-24 truncate" title={log.logger}>
                  [{log.logger}]
                </span>
                
                <div className="flex flex-wrap gap-x-3 gap-y-1 items-start flex-1 break-all">
                  <span className="text-zinc-100">{log.message}</span>
                  
                  {log.method && log.path && (
                    <span className="inline-flex gap-1.5 items-center bg-zinc-900 px-1.5 rounded text-[10px]">
                      <span className={getMethodColor(log.method)}>{log.method}</span>
                      <span>{log.path}</span>
                      {log.status_code && (
                        <span className={log.status_code >= 400 ? "text-red-400" : "text-emerald-400"}>
                          {log.status_code}
                        </span>
                      )}
                      {log.latency_ms && <span className="text-zinc-500">{log.latency_ms}ms</span>}
                    </span>
                  )}

                  {Object.entries(log).map(([k, v]) => {
                    if (["level", "timestamp", "message", "logger", "method", "path", "status_code", "latency_ms"].includes(k)) return null;
                    return (
                      <span key={k} className="text-zinc-500 text-[10px]">
                        <span className="text-zinc-400">{k}=</span>
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}
