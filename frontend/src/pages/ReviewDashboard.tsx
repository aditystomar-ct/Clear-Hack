import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import MetricCard from "@/components/MetricCard";
import FilterBar from "@/components/FilterBar";
import FlagCard from "@/components/FlagCard";
import { api } from "@/lib/api";
import type { Flag, FlagAction } from "@/types";

export default function ReviewDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const reviewIdParam = searchParams.get("review");

  // Filters
  const [riskLevel, setRiskLevel] = useState("All");
  const [classification, setClassification] = useState("All");
  const [reviewStatus, setReviewStatus] = useState("All");

  // Fetch reviews list
  const { data: reviews } = useQuery({
    queryKey: ["reviews"],
    queryFn: api.listReviews,
  });

  const selectedReviewId = reviewIdParam
    ? parseInt(reviewIdParam, 10)
    : reviews?.[0]?.id ?? null;

  // Fetch selected review detail
  const { data: review, isLoading } = useQuery({
    queryKey: ["review", selectedReviewId],
    queryFn: () => api.getReview(selectedReviewId!),
    enabled: selectedReviewId !== null,
  });

  // Fetch flag actions
  const { data: flagActions } = useQuery({
    queryKey: ["reviewFlags", selectedReviewId],
    queryFn: () => api.getReviewFlags(selectedReviewId!),
    enabled: selectedReviewId !== null,
  });

  // Fetch team emails
  const { data: teamEmails } = useQuery({
    queryKey: ["teams"],
    queryFn: api.getTeams,
  });

  const flagActionMap = useMemo(() => {
    const map: Record<string, FlagAction> = {};
    flagActions?.forEach((fa) => {
      map[fa.flag_id] = fa;
    });
    return map;
  }, [flagActions]);

  // Is Google Doc?
  const isGoogleDoc = useMemo(() => {
    if (!review) return false;
    const src = review.metadata?.input_source ?? "";
    return src.length > 15 && !src.endsWith(".docx");
  }, [review]);

  // Split flags into categories
  const { legalFlags, infosecFlags, generalFlags } = useMemo(() => {
    const flags = review?.flags ?? [];
    return {
      legalFlags: flags.filter((f: Flag) =>
        f.triggered_rules.some((r) => r.source === "legal")
      ),
      infosecFlags: flags.filter((f: Flag) =>
        f.triggered_rules.some((r) => r.source === "infosec")
      ),
      generalFlags: flags.filter(
        (f: Flag) => !f.triggered_rules || f.triggered_rules.length === 0
      ),
    };
  }, [review]);

  // Apply filters
  const applyFilters = (flags: Flag[]) => {
    let result = flags;
    if (riskLevel !== "All") result = result.filter((f) => f.risk_level === riskLevel);
    if (classification !== "All")
      result = result.filter((f) => f.classification === classification);
    if (reviewStatus !== "All")
      result = result.filter(
        (f) => (flagActionMap[f.flag_id]?.reviewer_action ?? "pending") === reviewStatus
      );
    return result;
  };

  const legalFiltered = applyFilters(legalFlags);
  const infosecFiltered = applyFilters(infosecFlags);
  const generalFiltered = applyFilters(generalFlags);

  // Counts
  const pending = flagActions?.filter((fa) => fa.reviewer_action === "pending").length ?? 0;
  const accepted = flagActions?.filter((fa) => fa.reviewer_action === "accepted").length ?? 0;
  const closed = flagActions?.filter((fa) => fa.reviewer_action === "closed").length ?? 0;

  if (!reviews?.length) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        No reviews yet. Go to Upload & Analyze to run your first review.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Review Dashboard</h1>

      {/* Review selector */}
      <Select
        value={String(selectedReviewId ?? "")}
        onValueChange={(v) => setSearchParams({ review: v })}
      >
        <SelectTrigger className="w-full max-w-lg">
          <SelectValue placeholder="Select a review" />
        </SelectTrigger>
        <SelectContent>
          {reviews?.map((r) => (
            <SelectItem key={r.id} value={String(r.id)}>
              #{r.id} - {r.contract_name} ({r.date.slice(0, 10)})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {isLoading && <p className="text-muted-foreground">Loading...</p>}

      {review && (
        <>
          {/* Summary metrics */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <MetricCard
              title="Clauses"
              value={review.summary.total_clauses_analyzed ?? review.flags.length}
            />
            <MetricCard
              title="High Risk"
              value={review.summary.risk_breakdown?.High ?? 0}
            />
            <MetricCard
              title="Medium Risk"
              value={review.summary.risk_breakdown?.Medium ?? 0}
            />
            <MetricCard
              title="Low Risk"
              value={review.summary.risk_breakdown?.Low ?? 0}
            />
            <MetricCard
              title="Non-Compliant"
              value={review.summary.non_compliant_count ?? 0}
            />
            <MetricCard title="Pending" value={pending} />
          </div>

          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Accepted:</span> {accepted} |{" "}
            <span className="font-medium text-foreground">Marked as Closed:</span> {closed}
          </p>

          <Separator />

          {/* Filters */}
          <FilterBar
            riskLevel={riskLevel}
            classification={classification}
            reviewStatus={reviewStatus}
            onRiskLevelChange={setRiskLevel}
            onClassificationChange={setClassification}
            onReviewStatusChange={setReviewStatus}
          />

          {/* Tabs */}
          <Tabs defaultValue={searchParams.get("tab") || "legal"}>
            <TabsList>
              <TabsTrigger value="legal">Legal ({legalFiltered.length})</TabsTrigger>
              <TabsTrigger value="infosec">Infosec ({infosecFiltered.length})</TabsTrigger>
              <TabsTrigger value="general">General ({generalFiltered.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="legal" className="mt-4 space-y-1">
              <p className="mb-3 text-sm text-muted-foreground">
                Legal team flags — email: {teamEmails?.legal ?? "not configured"}
              </p>
              {legalFiltered.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No legal flags match current filters.
                </p>
              )}
              {legalFiltered.map((f) => (
                <FlagCard
                  key={f.flag_id}
                  flag={f}
                  action={flagActionMap[f.flag_id]}
                  reviewId={selectedReviewId!}
                  isGoogleDoc={isGoogleDoc}
                  teamEmails={teamEmails ?? {}}
                />
              ))}
            </TabsContent>

            <TabsContent value="infosec" className="mt-4 space-y-1">
              <p className="mb-3 text-sm text-muted-foreground">
                Infosec team flags — email: {teamEmails?.infosec ?? "not configured"}
              </p>
              {infosecFiltered.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No infosec flags match current filters.
                </p>
              )}
              {infosecFiltered.map((f) => (
                <FlagCard
                  key={f.flag_id}
                  flag={f}
                  action={flagActionMap[f.flag_id]}
                  reviewId={selectedReviewId!}
                  isGoogleDoc={isGoogleDoc}
                  teamEmails={teamEmails ?? {}}
                />
              ))}
            </TabsContent>

            <TabsContent value="general" className="mt-4 space-y-1">
              <p className="mb-3 text-sm text-muted-foreground">
                Flags with no specific rulebook match — email sent to all teams on accept
              </p>
              {generalFiltered.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No general flags match current filters.
                </p>
              )}
              {generalFiltered.map((f) => (
                <FlagCard
                  key={f.flag_id}
                  flag={f}
                  action={flagActionMap[f.flag_id]}
                  reviewId={selectedReviewId!}
                  isGoogleDoc={isGoogleDoc}
                  teamEmails={teamEmails ?? {}}
                />
              ))}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
