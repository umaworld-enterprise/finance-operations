"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Inbox } from "lucide-react";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  className?: string;
  hideOnMobile?: boolean;
  hideOnTablet?: boolean;
  mobileCardLabel?: string;
  mobileCardPriority?: number;
}

export interface MobileCardConfig<T> {
  title: (row: T) => React.ReactNode;
  subtitle?: (row: T) => React.ReactNode;
  status?: (row: T) => React.ReactNode;
  href?: (row: T) => string;
  fields: { label: string; value: (row: T) => React.ReactNode; priority?: number }[];
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: React.ReactNode;
  mobileCard?: MobileCardConfig<T>;
  desktopOnlyColumns?: number;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  loading = false,
  emptyTitle = "No data",
  emptyDescription,
  emptyAction,
  mobileCard,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={col.key} className={col.className}>
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableSkeleton rows={5} cols={columns.length} />
          </TableBody>
        </Table>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card className="p-0">
        <EmptyState
          icon={Inbox}
          title={emptyTitle}
          description={emptyDescription}
          action={emptyAction}
        />
      </Card>
    );
  }

  const cellClass = (col: Column<T>) =>
    cn(
      col.hideOnMobile && "hidden md:table-cell",
      col.hideOnTablet && "hidden lg:table-cell",
      col.className
    );

  if (mobileCard) {
    const sortedFields = [...mobileCard.fields].sort(
      (a, b) => (a.priority ?? 99) - (b.priority ?? 99)
    );
    const topFields = sortedFields.slice(0, 4);

    return (
      <>
        {/* Mobile: stacked cards */}
        <div className="md:hidden space-y-3">
          {data.map((row) => {
            const content = (
              <Card className={cn("p-4", mobileCard.href && "hover:border-foreground/30 transition-colors cursor-pointer")}>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm text-foreground truncate">
                      {mobileCard.title(row)}
                    </div>
                    {mobileCard.subtitle && (
                      <div className="text-xs text-muted-foreground mt-0.5 truncate">
                        {mobileCard.subtitle(row)}
                      </div>
                    )}
                  </div>
                  {mobileCard.status && (
                    <div className="shrink-0">{mobileCard.status(row)}</div>
                  )}
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                  {topFields.map((f) => (
                    <div key={f.label}>
                      <dt className="text-muted-foreground">{f.label}</dt>
                      <dd className="font-medium text-foreground mt-0.5">
                        {f.value(row)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            );

            if (mobileCard.href) {
              return (
                <Link key={rowKey(row)} href={mobileCard.href(row)}>
                  {content}
                </Link>
              );
            }
            return <div key={rowKey(row)}>{content}</div>;
          })}
        </div>

        {/* Desktop: table */}
        <Card className="overflow-hidden hidden md:block">
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((col) => (
                  <TableHead key={col.key} className={cellClass(col)}>
                    {col.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <TableRow key={rowKey(row)}>
                  {columns.map((col) => (
                    <TableCell key={col.key} className={cellClass(col)}>
                      {col.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </>
    );
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => (
              <TableHead key={col.key} className={cellClass(col)}>
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((col) => (
                <TableCell key={col.key} className={cellClass(col)}>
                  {col.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
