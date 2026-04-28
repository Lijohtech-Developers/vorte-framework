"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HeartPulse,
  Activity,
  Shield,
  Database,
  Cpu,
  Zap,
} from "lucide-react";
import type { ModuleItem } from "@/lib/api";

interface HealthProps {
  data: { status: string; modules: Record<string, { module: string; status: string }> } | null;
  loading: boolean;
  modules: ModuleItem[] | null;
}

const moduleIcons: Record<string, React.ReactNode> = {
  logging: <Zap className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
  cache: <Activity className="h-4 w-4" />,
  auth: <Shield className="h-4 w-4" />,
  ai: <Cpu className="h-4 w-4" />,
  security: <Shield className="h-4 w-4" />,
};

export function HealthPage({ data, loading, modules }: HealthProps) {
  if (loading || !data) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-32 rounded-xl" />
        <Skeleton className="h-[400px] rounded-xl" />
      </div>
    );
  }

  const moduleData = modules || [];
  const healthyCount = Object.values(data.modules).filter((m) => m.status === "healthy").length;
  const totalCount = Object.values(data.modules).length;
  const healthPct = totalCount > 0 ? (healthyCount / totalCount) * 100 : 0;

  const overallColor = data.status === "healthy" ? "text-emerald-500" : "text-amber-500";
  const OverallIcon = data.status === "healthy" ? CheckCircle2 : AlertTriangle;

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      {/* Overall Status */}
      <Card className="border-2">
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <div className={`rounded-full p-3 ${data.status === "healthy" ? "bg-emerald-500/10" : "bg-amber-500/10"}`}>
              <OverallIcon className={`h-8 w-8 ${overallColor}`} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold capitalize">{data.status}</h2>
                <Badge variant={data.status === "healthy" ? "default" : "secondary"}>
                  {healthyCount}/{totalCount}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                All system components are operating normally
              </p>
              <div className="mt-3 max-w-md">
                <Progress value={healthPct} className="h-2" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Module Health Grid */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Module Health Status</CardTitle>
          <CardDescription>Detailed health check for each registered module</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {moduleData.map((mod) => {
              const health = data.modules[mod.name];
              const status = health?.status || "unknown";
              return (
                <div
                  key={mod.name}
                  className="flex items-center gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className={`rounded-lg p-1.5 ${status === "healthy" ? "bg-emerald-500/10" : status === "unhealthy" ? "bg-red-500/10" : "bg-amber-500/10"}`}>
                    {moduleIcons[mod.name] || <HeartPulse className="h-4 w-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{mod.name}</p>
                    <p className="text-[11px] text-muted-foreground capitalize">{status}</p>
                  </div>
                  {status === "healthy" ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  ) : status === "unhealthy" ? (
                    <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Endpoints */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Health Endpoints</CardTitle>
          <CardDescription>External health check endpoints for monitoring</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[
              { path: "/health", desc: "Full system health check", method: "GET" },
              { path: "/ready", desc: "Kubernetes readiness probe", method: "GET" },
              { path: "/live", desc: "Kubernetes liveness probe", method: "GET" },
            ].map((ep) => (
              <div key={ep.path} className="flex items-center gap-3 p-3 rounded-lg border">
                <code className="text-xs font-mono bg-muted px-2 py-1 rounded">{ep.method}</code>
                <code className="text-sm font-mono flex-1">{ep.path}</code>
                <span className="text-xs text-muted-foreground">{ep.desc}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
