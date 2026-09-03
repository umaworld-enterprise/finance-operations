"use client";

import Link from "next/link";
import { amountPayable, formatCurrency, formatDate, requestDisplayNumber } from "@/lib/utils";
import { latestPaymentDate } from "@/lib/exportExcel";
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
            <TableHead className="hidden sm:table-cell">Invoice #</TableHead>
            <TableHead>Supplier</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead className="hidden md:table-cell">Vertical</TableHead>
            <TableHead className="hidden sm:table-cell text-right">Amount Payable</TableHead>
            <TableHead className="text-right">Deposit</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="hidden md:table-cell">Payment Date</TableHead>
            <TableHead className="hidden lg:table-cell">Submitted</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.map((req) => (
            <TableRow key={req.id}>
              <TableCell>
                <Link
                  href={`${basePath}/${req.id}`}
                  className="font-mono text-xs text-foreground font-semibold hover:underline underline-offset-2"
                >
                  {requestDisplayNumber(req)}
                </Link>
              </TableCell>
              <TableCell className="hidden sm:table-cell font-mono text-xs text-muted-foreground">
                {req.sunshine_invoice_number || "—"}
              </TableCell>
              <TableCell className="text-foreground font-medium">{req.supplier.name}</TableCell>
              <TableCell className="text-muted-foreground">{req.customer.name}</TableCell>
              <TableCell className="hidden md:table-cell text-muted-foreground text-xs">
                {req.vertical?.name ?? "—"}
              </TableCell>
              <TableCell className="hidden sm:table-cell text-right font-semibold text-foreground">
                {formatCurrency(amountPayable(req), req.currency)}
              </TableCell>
              <TableCell className="text-right font-semibold text-foreground">
                {formatCurrency(req.deposit_amount, req.currency)}
              </TableCell>
              <TableCell>
                <StatusBadge status={req.current_status} />
              </TableCell>
              {/* Payment date beside every paid amount (2 Sep 2026). */}
              <TableCell className="hidden md:table-cell text-muted-foreground text-xs whitespace-nowrap">
                {latestPaymentDate(req) ? formatDate(latestPaymentDate(req)) : "—"}
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
