"use client";

import Link from "next/link";
import { formatCurrency, formatDate, requestDisplayNumber } from "@/lib/utils";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { DepositRequest } from "@/types";
import { ClipboardList, ArrowUpRight } from "lucide-react";

interface RequestsTableProps {
  requests: DepositRequest[];
  basePath?: string;
  emptyMessage?: string;
}

export function RequestsTable({
  requests,
  basePath = "/merchandiser",
  emptyMessage = "Requests you submit will appear here.",
}: RequestsTableProps) {
  if (requests.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="No requests found"
        description={emptyMessage}
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Request #</TableHead>
            <TableHead>Supplier</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead className="hidden md:table-cell">Vertical</TableHead>
            <TableHead className="text-right">Deposit</TableHead>
            <TableHead className="hidden md:table-cell">Est. Shipment</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="hidden lg:table-cell">Submitted</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.map((req) => (
            <TableRow key={req.id}>
              <TableCell>
                <span className="font-mono text-xs text-foreground font-semibold">
                  {requestDisplayNumber(req)}
                </span>
              </TableCell>
              <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
              <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
              <TableCell className="hidden md:table-cell text-muted-foreground text-xs">
                {req.vertical.name}
              </TableCell>
              <TableCell className="text-right font-semibold text-foreground">
                {formatCurrency(req.deposit_amount, req.currency)}
              </TableCell>
              <TableCell className="hidden md:table-cell text-muted-foreground">
                {formatDate(req.estimated_shipment_date)}
              </TableCell>
              <TableCell>
                <StatusBadge status={req.current_status} />
              </TableCell>
              <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">
                {formatDate(req.created_at)}
              </TableCell>
              <TableCell>
                <Button size="sm" variant="ghost" asChild>
                  <Link href={`${basePath}/${req.id}`} aria-label={`View request ${requestDisplayNumber(req)}`}>
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
