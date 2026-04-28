"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Settings,
  Database,
  Shield,
  Cpu,
  HardDrive,
  Mail,
  Globe,
  LayoutDashboard,
} from "lucide-react";
import type { DashboardConfig } from "@/lib/api";
import { getConfig } from "@/lib/api";

interface ConfigProps {
  data: DashboardConfig | null;
  loading: boolean;
}

export function ConfigPage({ data, loading }: ConfigProps) {
  if (loading || !data) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      {/* App Settings */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Settings className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">Application Settings</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <ConfigItem label="App Name" value={data.app_name} />
          <ConfigItem label="Environment" value={data.app_env} badge />
          <ConfigItem label="Debug Mode" value={data.app_debug ? "Enabled" : "Disabled"} toggle={data.app_debug} />
          <ConfigItem label="App URL" value={data.app_url} mono />
          <ConfigItem label="API Prefix" value={data.api_prefix} mono />
          <ConfigItem label="Default Version" value={data.default_version} mono />
          <ConfigItem label="Timezone" value={data.timezone} />
          <ConfigItem label="CORS Origins" value={data.cors_origins.join(", ")} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Database */}
        <ConfigCard
          icon={<Database className="h-4 w-4 text-blue-500" />}
          title="Database"
          items={[
            { label: "Pool Size", value: String(data.database.pool_size) },
            { label: "Query Echo", value: data.database.echo ? "Enabled" : "Disabled" },
          ]}
        />

        {/* Auth */}
        <ConfigCard
          icon={<Shield className="h-4 w-4 text-emerald-500" />}
          title="Authentication"
          items={[
            { label: "Strategy", value: data.auth.strategy.toUpperCase(), badge: true },
            { label: "MFA", value: data.auth.mfa ? "Enabled" : "Disabled" },
            { label: "Refresh Tokens", value: data.auth.refresh_tokens ? "Enabled" : "Disabled" },
          ]}
        />

        {/* AI */}
        <ConfigCard
          icon={<Cpu className="h-4 w-4 text-violet-500" />}
          title="AI / LLM"
          items={[
            { label: "Default Model", value: data.ai.default_model, mono: true },
            { label: "Max Tokens", value: String(data.ai.max_tokens) },
            { label: "Temperature", value: String(data.ai.temperature) },
          ]}
        />

        {/* Cache */}
        <ConfigCard
          icon={<HardDrive className="h-4 w-4 text-amber-500" />}
          title="Cache"
          items={[
            { label: "Driver", value: data.cache.driver, badge: true },
            { label: "Default TTL", value: `${data.cache.default_ttl}s` },
          ]}
        />

        {/* Queue */}
        <ConfigCard
          icon={<LayoutDashboard className="h-4 w-4 text-cyan-500" />}
          title="Queue"
          items={[
            { label: "Driver", value: data.queue.driver, badge: true },
            { label: "Concurrency", value: String(data.queue.concurrency) },
          ]}
        />

        {/* Security */}
        <ConfigCard
          icon={<Shield className="h-4 w-4 text-red-500" />}
          title="Security"
          items={[
            { label: "Helmet", value: data.security.helmet ? "Enabled" : "Disabled" },
            { label: "CSRF", value: data.security.csrf ? "Enabled" : "Disabled" },
            { label: "Rate Limit", value: data.security.rate_limit ? "Enabled" : "Disabled" },
          ]}
        />

        {/* Storage */}
        <ConfigCard
          icon={<HardDrive className="h-4 w-4 text-pink-500" />}
          title="Storage"
          items={[
            { label: "Driver", value: data.storage.driver, badge: true },
          ]}
        />

        {/* Dashboard */}
        <ConfigCard
          icon={<LayoutDashboard className="h-4 w-4 text-indigo-500" />}
          title="Dashboard"
          items={[
            { label: "Enabled", value: data.dashboard.enabled ? "Enabled" : "Disabled" },
            { label: "Path", value: data.dashboard.path, mono: true },
          ]}
        />
      </div>
    </div>
  );
}

function ConfigCard({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: { label: string; value: string; badge?: boolean; mono?: boolean }[];
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.label} className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{item.label}</span>
              {item.badge ? (
                <Badge variant="outline" className="text-xs">{item.value}</Badge>
              ) : (
                <span className={`text-sm font-medium ${item.mono ? "font-mono text-xs" : ""}`}>{item.value}</span>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ConfigItem({
  label,
  value,
  badge,
  mono,
  toggle,
}: {
  label: string;
  value: string;
  badge?: boolean;
  mono?: boolean;
  toggle?: boolean;
}) {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg border">
      <span className="text-sm text-muted-foreground">{label}</span>
      {toggle !== undefined ? (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{value}</span>
          <Switch checked={toggle} disabled />
        </div>
      ) : badge ? (
        <Badge variant="outline">{value}</Badge>
      ) : (
        <span className={`text-sm font-medium ${mono ? "font-mono text-xs" : ""}`}>{value}</span>
      )}
    </div>
  );
}
