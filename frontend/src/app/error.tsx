"use client";

import Image from "next/image";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-4 text-center">
      <div className="bg-white border border-border p-3 rounded-xl mb-6 shadow-sm">
        <Image
          src="/logo.png"
          alt="Sunshine"
          width={32}
          height={32}
          className="h-8 w-8 object-contain"
        />
      </div>
      <div className="bg-muted rounded-full p-4 mb-4">
        <AlertCircle className="h-8 w-8 text-foreground" />
      </div>
      <h2 className="text-lg font-semibold text-foreground">Something went wrong</h2>
      <p className="text-sm text-muted-foreground mt-1 max-w-sm">
        An unexpected error occurred while loading this page. You can try again.
      </p>
      {error.digest && (
        <p className="text-xs text-muted-foreground mt-2 font-mono">
          Error ID: {error.digest}
        </p>
      )}
      <Button onClick={reset} className="mt-4">
        Try again
      </Button>
    </div>
  );
}
