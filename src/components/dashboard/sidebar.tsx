"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Boxes,
  Route,
  HeartPulse,
  Settings,
  Activity,
  Zap,
  Cpu,
  BookOpen,
  Terminal,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

export type DashboardPage = "overview" | "modules" | "routes" | "health" | "config" | "metrics" | "ai" | "docs" | "logs";

interface SidebarProps {
  currentPage: DashboardPage;
  onNavigate: (page: DashboardPage) => void;
  moduleCount: number;
  healthyCount: number;
}

const navItems: { id: DashboardPage; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "modules", label: "Modules", icon: Boxes },
  { id: "routes", label: "Routes", icon: Route },
  { id: "health", label: "Health", icon: HeartPulse },
  { id: "config", label: "Config", icon: Settings },
  { id: "metrics", label: "Metrics", icon: Activity },
  { id: "ai", label: "AI Engine", icon: Cpu },
  { id: "docs", label: "API Docs", icon: BookOpen },
  { id: "logs", label: "Terminal", icon: Terminal },
];

export function DashboardSidebar({ currentPage, onNavigate, moduleCount, healthyCount }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col border-r glass transition-all duration-500 ease-in-out relative z-40 shadow-2xl",
        collapsed ? "w-20" : "w-72"
      )}
    >
      {/* Brand Header */}
      <div className="flex items-center gap-4 px-6 h-16 border-b border-white/5 shrink-0">
        <motion.div 
          whileHover={{ rotate: 180 }}
          className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary text-primary-foreground font-black text-lg shadow-[0_0_15px_rgba(var(--primary),0.5)]"
        >
          V
        </motion.div>
        {!collapsed && (
          <motion.div 
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col"
          >
            <span className="font-black text-sm tracking-tighter uppercase">Vorte Framework</span>
            <span className="text-label">Control Center</span>
          </motion.div>
        )}
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-6 px-3">
        <nav className="flex flex-col gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            return (
              <Button
                key={item.id}
                variant="ghost"
                className={cn(
                  "relative group justify-start gap-4 h-11 px-4 text-label transition-all duration-200",
                  isActive ? "text-primary bg-primary/5" : "text-muted-foreground hover:text-foreground hover:bg-white/5",
                  collapsed && "justify-center px-0"
                )}
                onClick={() => onNavigate(item.id)}
              >
                {isActive && (
                  <motion.div 
                    layoutId="sidebar-active"
                    className="absolute left-0 w-1 h-6 bg-primary rounded-r-full"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
                <Icon className={cn("h-4 w-4 shrink-0 transition-transform group-hover:scale-110", isActive && "text-primary")} />
                {!collapsed && (
                   <motion.span 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                   >
                    {item.label}
                   </motion.span>
                )}
                {isActive && !collapsed && (
                  <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(var(--primary),0.8)]" />
                )}
              </Button>
            );
          })}
        </nav>
      </ScrollArea>

      <Separator className="bg-white/5" />

      {/* Footer Stats */}
      <div className="p-4 bg-black/20 shrink-0">
        {!collapsed && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 p-3 rounded-xl bg-white/5 border border-white/5 space-y-3"
          >
            <div className="flex items-center justify-between">
               <div className="flex items-center gap-2">
                 <Zap className="h-3 w-3 text-emerald-400" />
                 <span className="text-label">Modules</span>
               </div>
               <span className="text-[10px] font-mono font-black">{healthyCount}/{moduleCount}</span>
            </div>
            <div className="h-1 rounded-full bg-white/5 overflow-hidden">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: `${(healthyCount/moduleCount)*100}%` }}
                className="h-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"
              />
            </div>
          </motion.div>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="w-full h-10 hover:bg-white/10 text-muted-foreground transition-all"
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
    </aside>
  );
}
