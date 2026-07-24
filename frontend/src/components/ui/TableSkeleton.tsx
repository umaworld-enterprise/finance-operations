interface TableSkeletonProps {
  rows?: number;
  cols?: number;
}

export function TableSkeleton({ rows = 5, cols = 6 }: TableSkeletonProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className="border-b border-border">
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-4 py-3">
              <div
                className="h-4 bg-muted rounded animate-pulse"
                style={{ width: c === 0 ? "80px" : c === cols - 1 ? "60px" : "100%" }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
