"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { motion } from "framer-motion";
import {
  Boxes,
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  Layers,
  Zap,
} from "lucide-react";
import { useState } from "react";
import type { ModuleItem } from "@/lib/api";

interface ModulesProps {
  data: { total: number; modules: ModuleItem[] } | null;
  loading: boolean;
}

const priorityLabels: Record<number, string> = {
  0: "Config",
  10: "Database",
  20: "Cache",
  30: "Queue",
  40: "Auth",
  50: "Search",
  60: "Middleware",
  70: "Routes",
  80: "AI",
  90: "Payments",
  100: "Dashboard",
};

const moduleIcons: Record<string, React.ReactNode> = {
  logging: <Zap className="h-4 w-4" />,
  database: <Layers className="h-4 w-4" />,
  cache: <Clock className="h-4 w-4" />,
  ai: <Boxes className="h-4 w-4" />,
  agents: <Boxes className="h-4 w-4" />,
  auth: <CheckCircle2 className="h-4 w-4" />,
  security: <CheckCircle2 className="h-4 w-4" />,
  dashboard: <Boxes className="h-4 w-4" />,
};

export function ModulesPage({ data, loading }: ModulesProps) {
  const [search, setSearch] = useState("");

  if (loading || !data) {
    return (
      <div className="space-y-8 animate-pulse">
        <div className="h-10 w-64 bg-muted/20 rounded-xl border border-white/5" />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {[...Array(9)].map((_, i) => (
            <div key={i} className="h-40 rounded-2xl bg-muted/20 border border-white/5" />
          ))}
        </div>
      </div>
    );
  }

  const filtered = data.modules.filter(
    (m) =>
      m.name.toLowerCase().includes(search.toLowerCase()) ||
      m.description.toLowerCase().includes(search.toLowerCase())
  );

  const healthy = data.modules.filter((m) => m.state === "ready").length;
  const failed = data.modules.filter((m) => m.state === "failed").length;

  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
           <h2 className="text-3xl font-black tracking-tighter uppercase">Registry</h2>
           <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mt-1">Core Architecture Modules</p>
        </div>
        <div className="relative w-full md:w-80 group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
          <Input
            placeholder="Search Registry..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-11 h-12 bg-white/5 border-white/10 rounded-2xl focus:ring-primary/40 focus:border-primary/50 transition-all placeholder:text-muted-foreground/40 placeholder:uppercase placeholder:text-[10px] placeholder:tracking-widest"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <StatsTile label="Total Nodes" value={data.total} icon={<Boxes className="h-4 w-4 text-primary" />} />
        <StatsTile label="Healthy" value={healthy} icon={<CheckCircle2 className="h-4 w-4 text-emerald-400" />} color="text-emerald-400" />
        <StatsTile label="Critical" value={failed} icon={<XCircle className="h-4 w-4 text-red-400" />} color="text-red-400" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {filtered.map((mod, idx) => (
          <motion.div
            key={mod.name}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.03 }}
            whileHover={{ y: -4 }}
          >
            <Card className="glass border-white/5 hover:border-primary/40 transition-colors duration-300 relative overflow-hidden group">
              <CardHeader className="pb-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl bg-primary/10 p-2.5 group-hover:bg-primary/20 transition-colors">
                      {moduleIcons[mod.name] || <Boxes className="h-5 w-5 text-primary" />}
                    </div>
                    <div>
                      <CardTitle className="text-sm font-black tracking-tight uppercase">{mod.name}</CardTitle>
                      <CardDescription className="text-[10px] font-medium leading-relaxed opacity-60">
                        {mod.description}
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[9px] font-mono font-bold bg-white/5 border-white/10 px-1.5 py-0">
                      v{mod.version}
                    </Badge>
                    <Badge variant="secondary" className="text-[9px] font-bold px-1.5 py-0 bg-white/10">
                      P{mod.priority}
                    </Badge>
                  </div>
                  <StatusDot state={mod.state} />
                </div>
              </CardContent>
              <div className="absolute top-0 right-0 h-16 w-16 bg-primary/5 blur-3xl -z-10 group-hover:bg-primary/20 transition-colors" />
            </Card>
          </motion.div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-20 bg-white/5 rounded-3xl border border-dashed border-white/10">
          <Boxes className="h-10 w-10 mx-auto mb-3 opacity-20" />
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">No matches found in registry</p>
        </div>
      )}
    </div>
  );
}

function StatsTile({ label, value, icon, color = "text-foreground" }: { label: string; value: number; icon: React.ReactNode; color?: string }) {
  return (
    <Card className="glass border-white/5 overflow-hidden">
      <CardContent className="p-5 flex items-center gap-4">
        <div className="rounded-xl bg-white/5 p-3">
          {icon}
        </div>
        <div>
          <p className={cn("text-2xl font-black tabular-nums tracking-tighter", color)}>{value}</p>
          <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusDot({ state }: { state: string }) {
  const colors: Record<string, string> = {
    ready: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]",
    registered: "bg-amber-500",
    initializing: "bg-blue-500 animate-pulse",
    failed: "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]",
    shutting_down: "bg-amber-500 animate-pulse",
    shutdown: "bg-zinc-600",
  };
  return (
    <div className="flex items-center gap-2 px-2 py-0.5 rounded-full bg-white/5 border border-white/5">
      <div className={`h-1.5 w-1.5 rounded-full ${colors[state] || "bg-zinc-600"}`} />
      <span className="text-[9px] font-black uppercase tracking-tighter text-muted-foreground">{state}</span>
    </div>
  );
}
