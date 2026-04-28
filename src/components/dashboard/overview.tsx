"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  Boxes,
  Clock,
  Gauge,
  Route,
  Server,
  Zap,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { DashboardOverview } from "@/lib/api";
import { getOverview } from "@/lib/api";

import { motion } from "framer-motion";

interface HeaderProps {
  onRefresh: () => void;
  loading: boolean;
}

export function DashboardHeader({ onRefresh, loading }: HeaderProps) {
  return (
    <header className="flex items-center justify-between h-16 px-6 lg:px-10 border-b glass shrink-0 sticky top-0 z-30">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-violet-400 bg-clip-text text-transparent">
          Vorte Console
        </h1>
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-label text-emerald-500">Live</span>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Badge variant="outline" className="hidden sm:flex text-[10px] px-2 py-0.5 font-mono glass">
          v1.0.0
        </Badge>
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={onRefresh} 
          disabled={loading}
          className="hover:bg-primary/10 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">Sync</span>
        </Button>
      </div>
    </header>
  );
}

function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  trendUp,
  index,
}: {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ReactNode;
  trend?: string;
  trendUp?: boolean;
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      whileHover={{ y: -4, scale: 1.02 }}
      className="group"
    >
      <Card className="relative overflow-hidden glass border-white/5 hover:border-primary/50 transition-colors duration-300">
        <CardContent className="p-5">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-label">{title}</p>
              <p className="text-3xl font-black tracking-tighter tabular">{value}</p>
              {description && <p className="text-[10px] font-medium text-muted-foreground">{description}</p>}
            </div>
            <div className="rounded-xl bg-primary/10 p-2.5 group-hover:bg-primary/20 transition-colors">
              {icon}
            </div>
          </div>
          {trend && (
            <div className="flex items-center gap-1.5 mt-4">
              <div className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${trendUp ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"}`}>
                {trendUp ? (
                  <ArrowUpRight className="h-2.5 w-2.5" />
                ) : (
                  <ArrowDownRight className="h-2.5 w-2.5" />
                )}
                {trend}
              </div>
            </div>
          )}
        </CardContent>
        <div className="absolute bottom-0 left-0 h-1 w-full bg-gradient-to-r from-transparent via-primary/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      </Card>
    </motion.div>
  );
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

interface OverviewProps {
  data: DashboardOverview | null;
  loading: boolean;
}

export function OverviewPage({ data, loading }: OverviewProps) {
  if (loading || !data) {
    return (
      <div className="space-y-8 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-5">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-32 rounded-2xl bg-muted/20 border border-white/5" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
           <div className="lg:col-span-1 h-80 rounded-2xl bg-muted/20 border border-white/5" />
           <div className="lg:col-span-2 h-80 rounded-2xl bg-muted/20 border border-white/5" />
        </div>
      </div>
    );
  }

  const { framework, app, modules, routes, metrics, system } = data;
  const errorRate = metrics.total > 0 ? ((metrics.errors / metrics.total) * 100).toFixed(1) : "0";
  const avgLatency = Object.values(metrics.by_path).length > 0
    ? Math.round(
        Object.values(metrics.by_path).reduce((a, b) => a + b.total_ms, 0) /
          Object.values(metrics.by_path).reduce((a, b) => a + b.count, 0)
      )
    : 0;

  return (
    <div className="space-y-8 pb-10">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-5">
        <StatCard
          index={0}
          title="Uptime"
          value={formatUptime(app.uptime_seconds)}
          description={`Env: ${app.env}`}
          icon={<Clock className="h-5 w-5 text-emerald-400" />}
          trend="Online"
          trendUp={true}
        />
        <StatCard
          index={1}
          title="Modules"
          value={modules.total}
          description={`${modules.healthy} healthy`}
          icon={<Boxes className="h-5 w-5 text-blue-400" />}
        />
        <StatCard
          index={2}
          title="Routes"
          value={routes.total}
          description="Active API"
          icon={<Route className="h-5 w-5 text-violet-400" />}
        />
        <StatCard
          index={3}
          title="Requests"
          value={metrics.total.toLocaleString()}
          description={`${metrics.errors} errors`}
          icon={<Activity className="h-5 w-5 text-orange-400" />}
          trend={`${errorRate}% error`}
          trendUp={parseFloat(errorRate) < 5}
        />
        <StatCard
          index={4}
          title="Latency"
          value={`${avgLatency}ms`}
          description="Average"
          icon={<Gauge className="h-5 w-5 text-cyan-400" />}
        />
        <StatCard
          index={5}
          title="Memory"
          value={`${system.memory_mb.toFixed(0)}MB`}
          description={`Process ID ${system.pid}`}
          icon={<Server className="h-5 w-5 text-pink-400" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Framework Info */}
        <Card className="lg:col-span-1 glass border-white/5 overflow-hidden relative">
          <div className="absolute top-0 right-0 p-3 opacity-10">
            <Zap className="h-20 w-20 text-primary" />
          </div>
          <CardHeader className="pb-4">
            <CardTitle className="text-label text-glow">Framework Engine</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <InfoRow label="Core Version" value={framework.version} />
            <InfoRow label="Runtime" value={framework.python} />
            <InfoRow label="OS Platform" value={framework.platform} />
            <div className="pt-4 border-t border-white/5 space-y-4">
              <InfoRow label="Project" value={app.name} />
              <InfoRow label="Root Prefix" value={app.api_prefix} />
              <InfoRow label="Dev Mode" value={app.debug ? "Active" : "Production"} />
            </div>
          </CardContent>
        </Card>

        {/* Recent Requests */}
        <Card className="lg:col-span-2 glass border-white/5">
          <CardHeader className="pb-4 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-label text-glow">Traffic Monitor</CardTitle>
              <CardDescription className="text-[9px] mt-1 uppercase tracking-tighter opacity-70">Real-time stream of incoming requests</CardDescription>
            </div>
            <Activity className="h-4 w-4 text-primary animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 no-scrollbar max-h-[300px] overflow-y-auto">
              {metrics.last_requests.map((req, i) => (
                <motion.div 
                  key={i} 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02 }}
                  className="flex items-center gap-4 py-2.5 px-4 rounded-xl hover:bg-white/5 transition-all group"
                >
                  <MethodBadge method={req.method} />
                  <code className="text-[11px] font-mono flex-1 truncate text-muted-foreground group-hover:text-foreground transition-colors">{req.path}</code>
                  <StatusBadge status={req.status} />
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[10px] font-mono tabular-nums w-14 text-right text-muted-foreground">
                      {req.latency_ms}ms
                    </span>
                    <span className="text-[10px] font-mono tabular-nums w-14 text-right text-primary/60">
                      {req.time}
                    </span>
                  </div>
                </motion.div>
              ))}
              {metrics.last_requests.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
                  <Activity className="h-8 w-8 opacity-20" />
                  <p className="text-label">Waiting for traffic...</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Top Endpoints */}
      <Card className="glass border-white/5">
        <CardHeader className="pb-4">
          <CardTitle className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Global Heatmap</CardTitle>
          <CardDescription className="text-[10px] mt-1 uppercase tracking-tighter">Highest traffic endpoints by volume</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
            {Object.entries(metrics.by_path)
              .sort((a, b) => b[1].count - a[1].count)
              .slice(0, 8)
              .map(([path, stats], idx) => {
                const maxCount = Math.max(
                  ...Object.values(metrics.by_path).map((s) => s.count)
                );
                const pct = (stats.count / maxCount) * 100;
                const avgMs = Math.round(stats.total_ms / stats.count);
                return (
                  <motion.div 
                    key={path} 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.2 + idx * 0.05 }}
                    className="space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 max-w-[70%]">
                        <span className="text-[10px] font-bold text-muted-foreground/40 tabular-nums">0{idx + 1}</span>
                        <code className="font-mono text-[11px] truncate">{path}</code>
                      </div>
                      <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-tighter">
                        <span className="text-primary">{stats.count} hits</span>
                        <span className="text-muted-foreground">{avgMs}ms</span>
                        {stats.errors > 0 && (
                          <span className="text-red-500 flex items-center gap-0.5">
                            <AlertTriangle className="h-3 w-3" />
                            {stats.errors}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                        className="h-full rounded-full bg-gradient-to-r from-primary/40 to-primary shadow-[0_0_10px_rgba(var(--primary),0.3)]"
                      />
                    </div>
                  </motion.div>
                );
              })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium font-mono">{value}</span>
    </div>
  );
}

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    GET: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    POST: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
    PUT: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    PATCH: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
    DELETE: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
  };
  return (
    <span
      className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${colors[method] || "bg-muted text-muted-foreground"}`}
    >
      {method || "WS"}
    </span>
  );
}

function StatusBadge({ status }: { status: number }) {
  const color =
    status >= 200 && status < 300
      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      : status >= 300 && status < 400
      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
      : status >= 400 && status < 500
      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
      : "bg-red-500/10 text-red-600 dark:text-red-400";
  return (
    <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${color}`}>
      {status}
    </span>
  );
}

export { MethodBadge, StatusBadge, formatUptime };
