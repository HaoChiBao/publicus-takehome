"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import CompanyProfileForm, {
  type ProfileFormValues,
} from "@/components/CompanyProfileForm";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function OnboardingPage() {
  const router = useRouter();
  const [values, setValues] = useState<ProfileFormValues>({
    name: "",
    sector: "IT_SOFTWARE",
    province: "ON",
    sizeBand: "11-50",
    activities: ["R&D"],
    naicsCode: "541510",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await api.createProfile({
        name: values.name || undefined,
        sector: values.sector,
        province: values.province,
        size_band: values.sizeBand,
        activities: values.activities,
        naics_code: values.naicsCode || undefined,
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
          <CompanyProfileForm
            values={values}
            onChange={setValues}
            onSubmit={onSubmit}
            loading={loading}
            error={error}
            submitLabel="See my grant matches"
          />
        </CardContent>
      </Card>
    </div>
  );
}
