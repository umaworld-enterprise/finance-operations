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
  /** When set, the whole card becomes a button — e.g. tiles that switch the
   * page's table to their tab (19 Aug 2026). Ignored when href is given. */
  onClick?: () => void;
}

export function StatCard({ label, value, icon: Icon, subtext, trend, href, onClick }: StatCardProps) {
  const interactive = Boolean(href || onClick);
  const card = (
    <Card
      className={cn(
        "relative overflow-hidden border-l-4 border-l-primary",
        interactive && "hover:shadow-md hover:border-foreground/30 transition-all cursor-pointer h-full"
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

  if (href) {
    return (
      <Link href={href} aria-label={`${label} — view details`} className="block h-full">
        {card}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={`${label} — view listing`}
        className="block h-full w-full text-left"
      >
        {card}
      </button>
    );
  }
  return card;
}
