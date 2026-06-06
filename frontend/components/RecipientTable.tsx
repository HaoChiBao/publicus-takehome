"use client";

import { Fragment, useState } from "react";
import { ArrowUpDown, ChevronDown, ChevronRight } from "lucide-react";
import type { Award } from "@/lib/api";
import { formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type SortKey = "amount" | "fiscal_year";

function fmtDate(d?: string | null) {
  if (!d) return "—";
  return d;
}

export default function RecipientTable({
  awards,
  showRecipient = false,
  pageSize = 25,
}: {
  awards: Award[];
  showRecipient?: boolean;
  pageSize?: number;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("amount");
  const [asc, setAsc] = useState(false);
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);

  const sorted = [...awards].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "amount") cmp = (a.amount || 0) - (b.amount || 0);
    else cmp = (a.fiscal_year || "").localeCompare(b.fiscal_year || "");
    return asc ? cmp : -cmp;
  });

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const rows = sorted.slice(page * pageSize, page * pageSize + pageSize);
  const colCount = (showRecipient ? 7 : 6) + 1;

  function toggleSort(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(false);
    }
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-8" />
            {showRecipient && <TableHead>Recipient</TableHead>}
            <TableHead>Program</TableHead>
            <TableHead>Department</TableHead>
            <TableHead className="text-right">
              <button
                onClick={() => toggleSort("amount")}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                Amount <ArrowUpDown className="size-3" />
              </button>
            </TableHead>
            <TableHead>
              <button
                onClick={() => toggleSort("fiscal_year")}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                Fiscal Year <ArrowUpDown className="size-3" />
              </button>
            </TableHead>
            <TableHead>Province</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((a) => {
            const open = expanded === a.id;
            return (
              <Fragment key={a.id}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => setExpanded(open ? null : a.id)}
                >
                  <TableCell className="text-muted-foreground">
                    {open ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronRight className="size-4" />
                    )}
                  </TableCell>
                  {showRecipient && (
                    <TableCell className="font-medium">
                      {a.recipient_name || a.recipient_name_raw}
                    </TableCell>
                  )}
                  <TableCell className="text-muted-foreground">
                    {a.program_name_raw}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {a.department}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {formatCurrencyFull(a.amount)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {a.fiscal_year || "—"}
                  </TableCell>
                  <TableCell>{a.province || "—"}</TableCell>
                </TableRow>
                {open && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={colCount} className="bg-muted/40">
                      <div className="grid grid-cols-2 gap-x-8 gap-y-3 px-2 py-1 text-sm sm:grid-cols-4">
                        <Detail label="Agreement type" value={a.agreement_type} />
                        <Detail
                          label="Sector"
                          value={a.sector_normalized ? sectorLabel(a.sector_normalized) : undefined}
                        />
                        <Detail label="NAICS" value={a.naics_code} />
                        <Detail label="Source" value={a.source} />
                        <Detail label="Start date" value={fmtDate(a.start_date)} />
                        <Detail label="End date" value={fmtDate(a.end_date)} />
                        <Detail label="City" value={a.city} />
                        {a.description && (
                          <div className="col-span-2 sm:col-span-4">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                              Description
                            </p>
                            <p className="mt-0.5 leading-relaxed">
                              {a.description}
                            </p>
                          </div>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
          {rows.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell
                colSpan={colCount}
                className="py-10 text-center text-muted-foreground"
              >
                No awards found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {pages > 1 && (
        <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
          <span className="text-muted-foreground">
            Page {page + 1} of {pages} · {sorted.length} awards
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages - 1}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className={cn(!value && "opacity-60")}>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 tabular-nums">{value || "—"}</p>
    </div>
  );
}
