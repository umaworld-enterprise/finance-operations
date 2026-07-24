"use client";

import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center bg-background">
          <div className="bg-muted rounded-full p-4 mb-4">
            <AlertCircle className="h-8 w-8 text-foreground" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">
            Application error
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm">
            A critical error occurred. Please try reloading the page.
          </p>
          <Button onClick={reset} className="mt-4">
            Reload
          </Button>
        </div>
      </body>
    </html>
  );
}
