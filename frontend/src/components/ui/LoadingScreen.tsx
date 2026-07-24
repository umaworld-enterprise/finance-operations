import Image from "next/image";
import { Loader2 } from "lucide-react";

interface LoadingScreenProps {
  message?: string;
}

export function LoadingScreen({ message = "Loading…" }: LoadingScreenProps) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="bg-white border border-border p-4 rounded-2xl shadow-sm">
          <Image
            src="/logo.png"
            alt="Sunshine"
            width={56}
            height={56}
            className="h-14 w-14 object-contain"
          />
        </div>

        <div className="text-center mt-2">
          <p className="text-foreground font-semibold text-lg tracking-wide">
            Finance Operations
          </p>
          <p className="text-muted-foreground text-xs mt-0.5">
            Sunshine Finance &amp; Operations
          </p>
        </div>

        <div className="flex items-center gap-2 mt-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <p className="text-sm">{message}</p>
        </div>
      </div>
    </div>
  );
}
