import { Skeleton } from "@/components/ui/skeleton";

// This file only replaces the route-segment content area, not the whole layout.
// The sidebar and TopNav from layout.tsx stay mounted and visible during navigation.
export default function DashboardLoading() {
  return (
    <div className="flex-1 p-4 md:p-6 space-y-4">
      <Skeleton className="h-9 w-48" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-96 rounded-xl" />
    </div>
  );
}
