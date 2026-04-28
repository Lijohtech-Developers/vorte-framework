"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Maximize2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DocsPage() {
  const [loading, setLoading] = useState(true);

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex items-center justify-between p-4 border-b shrink-0 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">API Documentation</h2>
          <p className="text-sm text-muted-foreground">
            Interactive Swagger UI for your framework endpoints
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href="/docs" target="_blank" rel="noreferrer">
              <ExternalLink className="h-4 w-4 mr-2" />
              Open in new tab
            </a>
          </Button>
        </div>
      </div>
      
      <div className="flex-1 relative w-full h-full bg-white dark:bg-zinc-950">
        {loading && (
          <div className="absolute inset-0 flex flex-col gap-4 p-8">
            <Skeleton className="h-10 w-1/3" />
            <Skeleton className="h-[400px] w-full" />
            <Skeleton className="h-[200px] w-full" />
          </div>
        )}
        <iframe
          src="/docs"
          className="w-full h-full border-0 absolute inset-0"
          title="API Documentation"
          onLoad={() => setLoading(false)}
        />
      </div>
    </div>
  );
}
