import Link from "next/link";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  subtext?: string;
  trend?: { value: number; label: string };
  /** When set, the whole card becomes a link (in-page anchors work too). */
  href?: string;
}

export function StatCard({ label, value, icon: Icon, subtext, trend, href }: StatCardProps) {
  const card = (
    <Card
      className={cn(
        "relative overflow-hidden border-l-4 border-l-primary",
        href && "hover:shadow-md hover:border-foreground/30 transition-all cursor-pointer h-full"
      )}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-muted-foreground tracking-wide">
              {label}
            </p>
            <p
              className={cn(
                "font-bold text-foreground mt-1 leading-tight break-words",
                typeof value === "string" && value.length > 8 ? "text-lg" : "text-2xl"
              )}
            >
              {value}
            </p>
            {subtext && <p className="text-xs text-muted-foreground mt-1.5">{subtext}</p>}
            {trend && (
              <p className="text-xs mt-1.5 font-medium text-muted-foreground">
                {trend.value >= 0 ? "↑" : "↓"} {Math.abs(trend.value)}% {trend.label}
              </p>
            )}
          </div>
          <div className="p-2.5 rounded-xl shrink-0 bg-muted">
            <Icon className="h-5 w-5 text-foreground" />
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (!href) return card;
  return (
    <Link href={href} aria-label={`${label} — view details`} className="block h-full">
      {card}
    </Link>
  );
}
