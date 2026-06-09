"use client";

import { Check } from "lucide-react";
import {
  ACTIVITIES,
  COMMON_NAICS,
  PROVINCES,
  SECTORS,
  SIZE_BANDS,
} from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export interface ProfileFormValues {
  name: string;
  sector: string;
  province: string;
  sizeBand: string;
  activities: string[];
  naicsCode: string;
}

interface CompanyProfileFormProps {
  values: ProfileFormValues;
  onChange: (values: ProfileFormValues) => void;
  onSubmit: (e: React.FormEvent) => void;
  loading?: boolean;
  error?: string | null;
  submitLabel: string;
}

export function profileToFormValues(profile: {
  name?: string;
  sector?: string;
  province?: string;
  size_band?: string;
  activities?: string[];
  naics_code?: string;
}): ProfileFormValues {
  return {
    name: profile.name || "",
    sector: profile.sector || "IT_SOFTWARE",
    province: profile.province || "ON",
    sizeBand: profile.size_band || "11-50",
    activities: profile.activities?.length ? profile.activities : ["R&D"],
    naicsCode: profile.naics_code || "541510",
  };
}

export default function CompanyProfileForm({
  values,
  onChange,
  onSubmit,
  loading,
  error,
  submitLabel,
}: CompanyProfileFormProps) {
  function setField<K extends keyof ProfileFormValues>(
    key: K,
    value: ProfileFormValues[K]
  ) {
    onChange({ ...values, [key]: value });
  }

  function toggleActivity(a: string) {
    setField(
      "activities",
      values.activities.includes(a)
        ? values.activities.filter((x) => x !== a)
        : [...values.activities, a]
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="name">
          Company name{" "}
          <span className="text-muted-foreground">(optional)</span>
        </Label>
        <Input
          id="name"
          value={values.name}
          onChange={(e) => setField("name", e.target.value)}
          placeholder="Acme Consulting Inc."
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="naics">NAICS industry code</Label>
        <Select
          id="naics"
          value={values.naicsCode}
          onChange={(e) => {
            const code = e.target.value;
            const match = COMMON_NAICS.find((n) => n.code === code);
            onChange({
              ...values,
              naicsCode: code,
              sector: match ? match.sector : values.sector,
            });
          }}
        >
          {COMMON_NAICS.map((n) => (
            <option key={n.code} value={n.code}>
              {n.code} — {n.title}
            </option>
          ))}
        </Select>
        <p className="text-xs text-muted-foreground">
          Improves grant matching precision based on industry classification.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sector">Sector</Label>
          <Select
            id="sector"
            value={values.sector}
            onChange={(e) => setField("sector", e.target.value)}
          >
            {SECTORS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="province">Province</Label>
          <Select
            id="province"
            value={values.province}
            onChange={(e) => setField("province", e.target.value)}
          >
            {PROVINCES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label>Company size</Label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {SIZE_BANDS.map((b) => (
            <button
              type="button"
              key={b}
              onClick={() => setField("sizeBand", b)}
              className={cn(
                "rounded-md border px-3 py-2 text-sm transition-colors",
                values.sizeBand === b
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent"
              )}
            >
              {b}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <Label>Primary activities</Label>
        <div className="flex flex-wrap gap-2">
          {ACTIVITIES.map((a) => {
            const active = values.activities.includes(a);
            return (
              <button
                type="button"
                key={a}
                onClick={() => toggleActivity(a)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input hover:bg-accent"
                )}
              >
                {active && <Check className="size-3.5" />}
                {a}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <p className="text-sm font-medium text-destructive">{error}</p>
      )}

      <Button type="submit" disabled={loading} size="lg" className="w-full">
        {loading ? "Saving…" : submitLabel}
      </Button>
    </form>
  );
}
