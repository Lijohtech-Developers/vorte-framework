"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { motion } from "framer-motion";
import { MethodBadge } from "./overview";
import { Route, Search, Globe } from "lucide-react";
import { useState } from "react";
import type { RouteItem } from "@/lib/api";

interface RoutesProps {
  data: { total: number; routes: RouteItem[] } | null;
  loading: boolean;
}

export function RoutesPage({ data, loading }: RoutesProps) {
  const [search, setSearch] = useState("");

  if (loading || !data) {
    return (
      <div className="space-y-8 animate-pulse">
        <div className="h-10 w-64 bg-muted/20 rounded-xl border border-white/5" />
        <div className="h-[500px] rounded-3xl bg-muted/20 border border-white/5" />
      </div>
    );
  }

  const filtered = data.routes.filter(
    (r) =>
      r.path.toLowerCase().includes(search.toLowerCase()) ||
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.methods.some((m) => m.toLowerCase().includes(search.toLowerCase()))
  );

  const methodCounts: Record<string, number> = {};
  data.routes.forEach((r) => r.methods.forEach((m) => { methodCounts[m] = (methodCounts[m] || 0) + 1; }));

  return (
    <div className="space-y-8 pb-10">
      {/* Header & Stats */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
           <h2 className="text-3xl font-black tracking-tighter uppercase">Endpoints</h2>
           <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mt-1">API Surface Map</p>
        </div>
        <div className="relative w-full md:w-80 group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
          <Input
            placeholder="Search Endpoints..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-11 h-12 bg-white/5 border-white/10 rounded-2xl focus:ring-primary/40 focus:border-primary/50 transition-all placeholder:text-muted-foreground/40 placeholder:uppercase placeholder:text-[10px] placeholder:tracking-widest"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="glass border-white/5">
          <CardContent className="p-4">
            <p className="text-2xl font-black tracking-tighter text-primary">{data.total}</p>
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Total Routes</p>
          </CardContent>
        </Card>
        {["GET", "POST", "PUT", "DELETE"].map((m) => (
          <Card key={m} className="glass border-white/5">
            <CardContent className="p-4">
              <p className="text-2xl font-black tracking-tighter">{methodCounts[m] || 0}</p>
              <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">{m} Total</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Routes Map */}
      <Card className="glass border-white/5 overflow-hidden">
        <CardHeader className="pb-4 border-b border-white/5 bg-white/5">
          <div className="flex items-center gap-3">
             <div className="p-2 rounded-lg bg-primary/10">
               <Globe className="h-4 w-4 text-primary" />
             </div>
             <div>
               <CardTitle className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Routing Registry</CardTitle>
               <CardDescription className="text-[10px] mt-0.5 uppercase tracking-tighter">Live API surface exploration</CardDescription>
             </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto no-scrollbar">
            <div className="min-w-[800px]">
              {/* Table Header */}
              <div className="grid grid-cols-[1fr_160px_240px] gap-6 px-6 py-4 text-[10px] font-black text-muted-foreground uppercase tracking-widest bg-white/[0.02] border-b border-white/5">
                <span>Resource Path</span>
                <span className="text-center">Protocol / Method</span>
                <span>Endpoint Descriptor</span>
              </div>

              <div className="divide-y divide-white/5">
                {filtered.map((route, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -5 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.01 }}
                    className="grid grid-cols-[1fr_160px_240px] gap-6 px-6 py-4 hover:bg-white/5 transition-all group items-center"
                  >
                    <div className="flex items-center gap-3">
                       <div className="w-1.5 h-1.5 rounded-full bg-primary/20 group-hover:bg-primary transition-colors" />
                       <code className="text-[11px] font-mono text-muted-foreground group-hover:text-foreground transition-colors font-medium">{route.path}</code>
                    </div>
                    <div className="flex items-center gap-1.5 justify-center flex-wrap">
                      {route.methods.length > 0
                        ? route.methods.map((m) => <MethodBadge key={m} method={m} />)
                        : <Badge variant="outline" className="text-[9px] font-black bg-violet-500/10 text-violet-400 border-violet-500/20">WEBSOCKET</Badge>}
                    </div>
                    <span className="text-[10px] font-bold text-muted-foreground/60 uppercase tracking-widest truncate">{route.name}</span>
                  </motion.div>
                ))}
              </div>

              {filtered.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
                  <Route className="h-10 w-10 opacity-10" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">No matching endpoints located</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
