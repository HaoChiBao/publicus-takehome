"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Download, Pencil, TrendingUp, X } from "lucide-react";
import {
  api,
  type DeadlineAlert,
  type PeerCompany,
  type Program,
  type SectorSummary,
  type TrendingProgram,
} from "@/lib/api";
import { formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import AlertsBanner from "@/components/AlertsBanner";
import CompanyProfileForm, {
  profileToFormValues,
  type ProfileFormValues,
} from "@/components/CompanyProfileForm";
import ProgramCard from "@/components/ProgramCard";
import PeerMatchCard from "@/components/PeerMatchCard";
import SectorIntelCard from "@/components/SectorIntelCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface DashboardData {
  profile: {
    name?: string;
    sector?: string;
    province?: string;
    size_band?: string;
    naics_code?: string;
    activities?: string[];
  };
  matches: Program[];
  sector_summary: SectorSummary;
  trending: TrendingProgram[];
  alerts: DeadlineAlert[];
  peers: PeerCompany[];
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formValues, setFormValues] = useState<ProfileFormValues | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function loadDashboard(session: string) {
    return api
      .dashboard(session)
      .then(setData)
      .catch(() => setError("Could not load your dashboard. Is the API running?"));
  }

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    if (!session) {
      router.push("/");
      return;
    }
    loadDashboard(session);
  }, [router]);

  function startEditing() {
    if (!data) return;
    setFormValues(profileToFormValues(data.profile));
    setSaveError(null);
    setEditing(true);
  }

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    const session = localStorage.getItem("publicus_session");
    if (!session || !formValues) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.createProfile({
        session_id: session,
        name: formValues.name || undefined,
        sector: formValues.sector,
        province: formValues.province,
        size_band: formValues.sizeBand,
        activities: formValues.activities,
        naics_code: formValues.naicsCode || undefined,
      });
      setEditing(false);
      await loadDashboard(session);
    } catch {
      setSaveError("Could not save your profile. Is the API running?");
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    const session = localStorage.getItem("publicus_session");
    if (!session) return;
    setExporting(true);
    try {
      await api.exportDashboard(session);
    } finally {
      setExporting(false);
    }
  }

  if (error)
    return (
      <p className="text-center text-sm font-medium text-destructive">{error}</p>
    );

  if (!data)
    return (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
        <div className="space-y-6 lg:col-span-3">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {data.profile.name ? `${data.profile.name} · ` : ""}Grants Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">
            {sectorLabel(data.profile.sector)} · {data.profile.province} ·{" "}
            {data.profile.size_band} employees
            {data.profile.naics_code && ` · NAICS ${data.profile.naics_code}`}
            {data.profile.activities?.length
              ? ` · ${data.profile.activities.join(", ")}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={startEditing}>
            <Pencil className="size-4" />
            Edit profile
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
            <Download className="size-4" />
            {exporting ? "Exporting…" : "Export report"}
          </Button>
        </div>
      </div>

      {editing && formValues && (
        <Card className="mb-6">
          <CardHeader className="flex flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle>Edit company profile</CardTitle>
              <CardDescription>
                Updating your profile will refresh your grant matches.
              </CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditing(false)}
              aria-label="Close"
            >
              <X className="size-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <CompanyProfileForm
              values={formValues}
              onChange={setFormValues}
              onSubmit={handleSaveProfile}
              loading={saving}
              error={saveError}
              submitLabel="Save changes"
            />
          </CardContent>
        </Card>
      )}

      {data.alerts.length > 0 && (
        <div className="mb-6">
          <AlertsBanner alerts={data.alerts} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="lg:col-span-2">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Grants You Match
            </h2>
            <Link
              href="/grants"
              className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              Browse all grants →
            </Link>
          </div>
          <div className="space-y-3">
            {data.matches.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No matching programs found for this profile.
              </p>
            )}
            {data.matches.map((p) => (
              <ProgramCard key={p.id} program={p} compact />
            ))}
          </div>
        </section>

        <div className="space-y-6 lg:col-span-3">
          <SectorIntelCard summary={data.sector_summary} />

          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Companies Like You
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {data.peers.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No similar companies found in this segment yet.
                </p>
              )}
              {data.peers.map((peer) => (
                <PeerMatchCard key={peer.id} peer={peer} />
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              On Your Radar
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {data.trending.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No fast-growing programs detected for this segment.
                </p>
              )}
              {data.trending.map((t) => (
                <Link key={t.program_id} href={`/program/${t.program_id}`}>
                  <Card className="h-full transition-colors hover:border-foreground">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-semibold leading-tight">
                          {t.name}
                        </h3>
                        <Badge className="shrink-0 gap-1">
                          <TrendingUp className="size-3" />
                          {t.yoy_change_pct}%
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        {formatCurrencyFull(t.previous_total)} →{" "}
                        {formatCurrencyFull(t.latest_total)} in{" "}
                        {t.latest_fiscal_year}
                      </p>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

