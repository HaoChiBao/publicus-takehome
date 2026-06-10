"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { ArrowUpDown, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import type { Award } from "@/lib/api";
import {
  awardDescription,
  awardExtraFields,
  awardLinks,
  hasAwardExtraInfo,
} from "@/lib/awardDetails";
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
      <p className="border-b px-4 py-2 text-xs text-muted-foreground">
        Click any row to see full award details, source links, and related programs.
      </p>
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
                  className={cn(
                    "cursor-pointer transition-colors",
                    open && "bg-muted/30"
                  )}
                  onClick={() => setExpanded(open ? null : a.id)}
                  aria-expanded={open}
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
                  <TableCell className="max-w-[220px] truncate text-muted-foreground">
                    {a.program_name_raw || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {a.department || "—"}
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
                    <TableCell colSpan={colCount} className="bg-muted/40 p-0">
                      <AwardDetailPanel award={a} />
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

function AwardDetailPanel({ award }: { award: Award }) {
  const fields = awardExtraFields(award).map((f) =>
    f.label === "Sector"
      ? { ...f, value: sectorLabel(f.value) }
      : f
  );
  const links = awardLinks(award);
  const description = awardDescription(award);
  const hasExtra = hasAwardExtraInfo(award);

  return (
    <div className="space-y-4 px-4 py-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Award details
        </p>
        <p className="mt-1 font-medium leading-snug">
          {award.program_name_raw || "Unknown program"}
        </p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {formatCurrencyFull(award.amount)}
          {award.fiscal_year ? ` · FY ${award.fiscal_year}` : ""}
          {award.province ? ` · ${award.province}` : ""}
        </p>
      </div>

      {fields.length > 0 && (
        <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
          {fields.map((f) => (
            <Detail key={f.label} label={f.label} value={f.value} />
          ))}
        </div>
      )}

      {description && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Description
          </p>
          <p className="mt-1 text-sm leading-relaxed">{description}</p>
        </div>
      )}

      {links.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Related links
          </p>
          <div className="flex flex-wrap gap-2">
            {links.map((link) =>
              link.external ? (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
                  onClick={(e) => e.stopPropagation()}
                >
                  {link.label}
                  <ExternalLink className="size-3.5 shrink-0 opacity-60" />
                </a>
              ) : (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
                  onClick={(e) => e.stopPropagation()}
                >
                  {link.label}
                </Link>
              )
            )}
          </div>
        </div>
      )}

      {!hasExtra && (
        <p className="text-sm text-muted-foreground">
          No additional details are recorded for this award beyond the summary
          shown in the table. Federal disclosure data typically includes
          program, amount, fiscal year, and location only.
        </p>
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
      <p className="mt-0.5 text-sm tabular-nums">{value || "—"}</p>
    </div>
  );
}
