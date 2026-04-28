"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Cpu, Bot, Brain, MessageSquare, Zap, DollarSign, ArrowRight } from "lucide-react";

// AI module page with provider info, model configs, and capabilities
interface AIProps {
  config: {
    default_model: string;
    max_tokens: number;
    temperature: number;
    cache_responses: boolean;
    track_costs: boolean;
  } | null;
  loading: boolean;
}

export function AIPage({ config, loading }: AIProps) {
  const aiConfig = config || {
    default_model: "gpt-4o",
    max_tokens: 4096,
    temperature: 0.7,
    cache_responses: true,
    track_costs: true,
  };

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const providers = [
    {
      name: "OpenAI",
      models: ["GPT-4o", "GPT-4o Mini", "GPT-4 Turbo", "GPT-3.5 Turbo", "o1", "o3-mini"],
      features: ["Chat", "Streaming", "Embeddings", "Vision", "Functions", "JSON Mode"],
      status: "active",
      color: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
    },
    {
      name: "Anthropic",
      models: ["Claude 4 Sonnet", "Claude 4 Opus", "Claude 3.5 Haiku"],
      features: ["Chat", "Streaming", "Vision", "Functions", "JSON Mode", "Extended Thinking"],
      status: "active",
      color: "bg-orange-500/10 text-orange-600 border-orange-500/20",
    },
    {
      name: "Google",
      models: ["Gemini 2.5 Pro", "Gemini 2.5 Flash", "Gemini 2.0"],
      features: ["Chat", "Streaming", "Vision", "Functions", "JSON Mode"],
      status: "active",
      color: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    },
    {
      name: "Mistral",
      models: ["Mistral Large", "Mistral Medium", "Mistral Small", "Codestral"],
      features: ["Chat", "Streaming", "Functions", "JSON Mode"],
      status: "active",
      color: "bg-violet-500/10 text-violet-600 border-violet-500/20",
    },
  ];

  const capabilities = [
    {
      title: "Universal AI Client",
      description:
        "Provider-agnostic API that works identically across all supported LLM providers. Switch providers with a single config change without modifying your code.",
      icon: <Cpu className="h-5 w-5 text-emerald-500" />,
    },
    {
      title: "AI Agents",
      description:
        "Build autonomous agents with tools, memory (short-term + long-term), RAG pipelines, guardrails (PII detection, content filtering), and multi-agent orchestration.",
      icon: <Bot className="h-5 w-5 text-blue-500" />,
    },
    {
      title: "Streaming Support",
      description:
        "Real-time token streaming via Server-Sent Events (SSE) and WebSocket connections. Get instant responses as the model generates tokens.",
      icon: <MessageSquare className="h-5 w-5 text-violet-500" />,
    },
    {
      title: "Cost Tracking",
      description:
        "Automatic token usage tracking and cost estimation for every request. Monitor spending across providers and models in the dashboard.",
      icon: <DollarSign className="h-5 w-5 text-amber-500" />,
    },
    {
      title: "Smart Caching",
      description:
        "Cache AI responses to reduce costs and latency. Semantic caching understands context similarity, not just exact matches.",
      icon: <Zap className="h-5 w-5 text-pink-500" />,
    },
    {
      title: "Structured Output",
      description:
        "Generate responses that conform to your Pydantic models. Define schemas and get type-safe, validated outputs from any LLM provider.",
      icon: <Brain className="h-5 w-5 text-cyan-500" />,
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      {/* Config Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Default Model</p>
            <p className="text-lg font-bold font-mono">{aiConfig.default_model}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Max Tokens</p>
            <p className="text-lg font-bold">{aiConfig.max_tokens.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Temperature</p>
            <p className="text-lg font-bold">{aiConfig.temperature}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Response Cache</p>
            <p className="text-lg font-bold text-emerald-500">
              {aiConfig.cache_responses ? "Enabled" : "Disabled"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Providers */}
      <div>
        <h2 className="text-sm font-medium mb-3">Supported Providers</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {providers.map((provider) => (
            <Card key={provider.name} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{provider.name}</CardTitle>
                  <Badge className={`text-[10px] border ${provider.color}`}>
                    {provider.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                    Models
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {provider.models.map((model) => (
                      <Badge key={model} variant="outline" className="text-[10px] font-mono">
                        {model}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                    Features
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {provider.features.map((f) => (
                      <Badge key={f} variant="secondary" className="text-[10px]">
                        {f}
                      </Badge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Capabilities */}
      <div>
        <h2 className="text-sm font-medium mb-3">AI Capabilities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {capabilities.map((cap) => (
            <Card key={cap.title} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-muted p-2 shrink-0">{cap.icon}</div>
                  <div>
                    <p className="text-sm font-medium">{cap.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {cap.description}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Quick Start */}
      <Card className="border-2 border-dashed">
        <CardContent className="p-6">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="h-4 w-4" />
            <h3 className="text-sm font-medium">Framework Developer Assistants</h3>
          </div>
          <div className="bg-muted rounded-lg p-4 font-mono text-xs leading-relaxed overflow-x-auto">
            <pre className="text-muted-foreground">
              {`from vorte import Vorte

app = Vorte(auto_load=True)

@app.post("/api/v1/chat")
async def chat(message: str):
    # Use the AI client directly — provider-agnostic
    result = await app.ai.chat(
        messages=[{"role": "user", "content": message}],
        model="gpt-4o",
        temperature=0.7,
    )
    return {"response": result.content}`}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
