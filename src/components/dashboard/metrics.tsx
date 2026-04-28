"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MethodBadge, StatusBadge } from "./overview";
import { Activity, BarChart3, TrendingUp, AlertTriangle } from "lucide-react";
import type { Metrics } from "@/lib/api";
import { getMetrics } from "@/lib/api";

interface MetricsProps {
  data: Metrics | null;
  loading: boolean;
}

export function MetricsPage({ data, loading }: MetricsProps) {
  if (loading || !data) {
    return (
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-[100px] rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-[300px] rounded-xl" />
      </div>
    );
  }

  const errorRate = data.total > 0 ? ((data.errors / data.total) * 100).toFixed(2) : "0";
  const topPaths = Object.entries(data.by_path)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 8);

  const methodColors: Record<string, string> = {
    GET: "bg-emerald-500",
    POST: "bg-blue-500",
    PUT: "bg-amber-500",
    DELETE: "bg-red-500",
    PATCH: "bg-orange-500",
  };

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <Activity className="h-4 w-4 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.total.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Total Requests</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-red-500/10 p-2">
                <AlertTriangle className="h-4 w-4 text-red-500" />
              </div>
              <div>
                <p className="text-2xl font-bold text-red-500">{data.errors}</p>
                <p className="text-sm text-muted-foreground">Errors ({errorRate}%)</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <BarChart3 className="h-4 w-4 text-violet-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{Object.keys(data.by_path).length}</p>
                <p className="text-sm text-muted-foreground">Active Endpoints</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{Object.keys(data.by_method).length}</p>
                <p className="text-sm text-muted-foreground">HTTP Methods</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Method Distribution */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Request Methods</CardTitle>
            <CardDescription>Distribution of HTTP methods</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(data.by_method)
                .sort((a, b) => b[1] - a[1])
                .map(([method, count]) => {
                  const max = Math.max(...Object.values(data.by_method));
                  const pct = (count / max) * 100;
                  return (
                    <div key={method} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <MethodBadge method={method} />
                          <span className="text-sm">{count.toLocaleString()} requests</span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {((count / data.total) * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full ${methodColors[method] || "bg-primary"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          </CardContent>
        </Card>

        {/* Error Endpoints */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Endpoints with Errors</CardTitle>
            <CardDescription>Endpoints that returned error responses</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(data.by_path)
                .filter(([, stats]) => stats.errors > 0)
                .sort((a, b) => b[1].errors - a[1].errors)
                .map(([path, stats]) => {
                  const errorRate = ((stats.errors / stats.count) * 100).toFixed(1);
                  return (
                    <div key={path} className="flex items-center gap-3 p-3 rounded-lg border">
                      <code className="text-xs font-mono flex-1 truncate">{path}</code>
                      <Badge variant="destructive" className="text-[10px] shrink-0">
                        {stats.errors} errors
                      </Badge>
                      <span className="text-xs text-red-500 tabular-nums w-14 text-right">
                        {errorRate}%
                      </span>
                    </div>
                  );
                })}
              {Object.values(data.by_path).every((s) => s.errors === 0) && (
                <p className="text-sm text-muted-foreground text-center py-6">
                  No errors recorded
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Endpoint Performance */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Endpoint Performance</CardTitle>
          <CardDescription>Average response time and request count per endpoint</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {topPaths.map(([path, stats]) => {
              const avgMs = Math.round(stats.total_ms / stats.count);
              const isError = stats.errors > 0;
              const barColor =
                avgMs < 50
                  ? "bg-emerald-500"
                  : avgMs < 150
                  ? "bg-amber-500"
                  : "bg-red-500";
              const maxAvg = Math.max(
                ...topPaths.map(([, s]) => Math.round(s.total_ms / s.count))
              );
              const pct = (avgMs / maxAvg) * 100;
              return (
                <div key={path} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <code className="text-xs font-mono truncate">{path}</code>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 text-xs text-muted-foreground">
                      <span>{stats.count} req</span>
                      <span className={`font-mono ${avgMs > 150 ? "text-red-500" : ""}`}>
                        {avgMs}ms avg
                      </span>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full ${barColor} transition-all duration-500`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Request Log */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Request Log</CardTitle>
          <CardDescription>Most recent API requests (last 50)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            <div className="grid grid-cols-[60px_1fr_60px_80px_70px] gap-2 px-3 py-2 text-xs font-medium text-muted-foreground border-b">
              <span>Method</span>
              <span>Path</span>
              <span className="text-center">Status</span>
              <span className="text-right">Latency</span>
              <span className="text-right">Time</span>
            </div>
            {data.last_requests.map((req, i) => (
              <div
                key={i}
                className="grid grid-cols-[60px_1fr_60px_80px_70px] gap-2 px-3 py-2 rounded-lg hover:bg-muted/50 transition-colors items-center"
              >
                <MethodBadge method={req.method} />
                <code className="text-xs font-mono truncate">{req.path}</code>
                <StatusBadge status={req.status} />
                <span className="text-xs text-muted-foreground tabular-nums text-right">
                  {req.latency_ms}ms
                </span>
                <span className="text-xs text-muted-foreground tabular-nums text-right">
                  {req.time}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
