"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { ACTIVITIES, PROVINCES, SECTORS, SIZE_BANDS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export default function OnboardingPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [sector, setSector] = useState("IT_SOFTWARE");
  const [province, setProvince] = useState("ON");
  const [sizeBand, setSizeBand] = useState("11-50");
  const [activities, setActivities] = useState<string[]>(["R&D"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleActivity(a: string) {
    setActivities((prev) =>
      prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await api.createProfile({
        name: name || undefined,
        sector,
        province,
        size_band: sizeBand,
        activities,
      });
      localStorage.setItem("publicus_session", session_id);
      router.push("/dashboard");
    } catch {
      setError("Could not create your profile. Is the API running?");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight">
          Find the grants your company is winning blind
        </h1>
        <p className="mt-3 text-muted-foreground">
          Tell us about your business. We&apos;ll match you to eligible federal
          programs and show what similar companies have received.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Company profile</CardTitle>
          <CardDescription>
            No account needed — this creates a private session profile.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="name">
                Company name{" "}
                <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Acme Consulting Inc."
              />
            </div>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="sector">Sector</Label>
                <Select
                  id="sector"
                  value={sector}
                  onChange={(e) => setSector(e.target.value)}
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
                  value={province}
                  onChange={(e) => setProvince(e.target.value)}
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
                    onClick={() => setSizeBand(b)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-sm transition-colors",
                      sizeBand === b
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
                  const active = activities.includes(a);
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
              {loading ? "Building your dashboard…" : "See my grant matches"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
