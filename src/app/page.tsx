"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardSidebar, type DashboardPage } from "@/components/dashboard/sidebar";
import { DashboardHeader, OverviewPage } from "@/components/dashboard/overview";
import { ModulesPage } from "@/components/dashboard/modules";
import { RoutesPage } from "@/components/dashboard/routes";
import { HealthPage } from "@/components/dashboard/health";
import { ConfigPage } from "@/components/dashboard/config";
import { MetricsPage } from "@/components/dashboard/metrics";
import { AIPage } from "@/components/dashboard/ai";
import { DocsPage } from "@/components/dashboard/docs";
import { LogsPage } from "@/components/dashboard/logs";
import { ScrollArea } from "@/components/ui/scroll-area";
import type {
  DashboardOverview,
  DashboardConfig,
} from "@/lib/api";
import {
  getOverview,
  getConfig,
} from "@/lib/api";

const REFRESH_INTERVAL = 5000;

const pageVariants = {
  initial: { opacity: 0, y: 10, scale: 0.99 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -10, scale: 0.99 },
};

export default function DashboardPage() {
  const [currentPage, setCurrentPage] = useState<DashboardPage>("overview");
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [data, setData] = useState<{
    overview: DashboardOverview | null;
    config: DashboardConfig | null;
  }>({
    overview: null,
    config: null,
  });

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setIsRefreshing(true);
    try {
      const [overview, config] = await Promise.all([
        getOverview(),
        getConfig(),
      ]);
      setData({ overview, config });
    } catch (err) {
      console.error("Dashboard sync error:", err);
    } finally {
      setIsInitialLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(true), REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  const stats = useMemo(() => ({
    total: data.overview?.modules.total || 0,
    healthy: data.overview?.modules.healthy || 0,
  }), [data.overview]);

  if (isInitialLoading && !data.overview) {
    return (
      <div className="flex items-center justify-center h-screen w-screen bg-background">
        <div className="relative">
          <div className="h-24 w-24 rounded-full border-t-2 border-primary animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center font-bold text-xl text-primary animate-pulse">
            V
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background font-sans selection:bg-primary/20">
      <DashboardSidebar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        moduleCount={stats.total}
        healthyCount={stats.healthy}
      />

      <div className="flex flex-col flex-1 min-w-0 relative">
        <DashboardHeader 
          onRefresh={() => fetchData(true)} 
          loading={isRefreshing} 
        />

        {isRefreshing && (
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-primary/20 z-50">
            <motion.div 
              className="h-full bg-primary"
              initial={{ width: "0%" }}
              animate={{ width: "100%" }}
              transition={{ duration: 2, repeat: Infinity }}
            />
          </div>
        )}

        <ScrollArea className="flex-1">
          <main className="p-6 pb-20 lg:p-10 max-w-7xl mx-auto w-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentPage}
                variants={pageVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="w-full"
              >
                {currentPage === "overview" && (
                  <OverviewPage data={data.overview} loading={false} />
                )}
                {currentPage === "modules" && (
                  <ModulesPage
                    data={data.overview ? {
                      total: data.overview.modules.total,
                      modules: data.overview.modules.items,
                    } : null}
                    loading={false}
                  />
                )}
                {currentPage === "routes" && (
                  <RoutesPage data={data.overview?.routes || null} loading={false} />
                )}
                {currentPage === "health" && (
                  <HealthPage
                    data={data.overview ? {
                      status: "healthy",
                      modules: Object.fromEntries(
                        data.overview.modules.items.map((m) => [
                          m.name,
                          { module: m.name, status: m.state === "ready" ? "healthy" : m.state },
                        ])
                      ),
                    } : null}
                    loading={false}
                    modules={data.overview?.modules.items || null}
                  />
                )}
                {currentPage === "config" && <ConfigPage data={data.config} loading={false} />}
                {currentPage === "metrics" && (
                  <MetricsPage data={data.overview?.metrics || null} loading={false} />
                )}
                {currentPage === "ai" && <AIPage config={data.config ? {
                  default_model: data.config.ai.default_model,
                  max_tokens: data.config.ai.max_tokens,
                  temperature: data.config.ai.temperature,
                  cache_responses: true,
                  track_costs: true,
                } : null} loading={false} />}
                {currentPage === "docs" && <DocsPage />}
                {currentPage === "logs" && <LogsPage />}
              </motion.div>
            </AnimatePresence>
          </main>
        </ScrollArea>
      </div>
    </div>
  );
}
