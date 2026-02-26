import type {
  AcceptResponse,
  AppConfig,
  FlagAction,
  ReviewDetail,
  ReviewListItem,
  ReviewStats,
  RuleEffectiveness,
  TeamEmails,
} from "@/types";

const BASE = "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getConfig: () => fetchJSON<AppConfig>("/config"),

  listReviews: () => fetchJSON<ReviewListItem[]>("/reviews"),

  getReview: (id: number) => fetchJSON<ReviewDetail>(`/reviews/${id}`),

  getReviewFlags: (id: number) => fetchJSON<FlagAction[]>(`/reviews/${id}/flags`),

  markFlagClosed: (reviewId: number, flagId: string, reviewerName: string) =>
    fetchJSON<{ flag_id: string; status: string }>(`/reviews/${reviewId}/flags/${flagId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "closed", reviewer_name: reviewerName }),
    }),

  acceptFlag: (reviewId: number, flagId: string, comment: string, reviewerName: string) =>
    fetchJSON<AcceptResponse>(`/reviews/${reviewId}/flags/${flagId}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment, reviewer_name: reviewerName }),
    }),

  getStats: () => fetchJSON<ReviewStats>("/stats"),

  getRuleEffectiveness: () => fetchJSON<RuleEffectiveness[]>("/rules/effectiveness"),

  getTeams: () => fetchJSON<TeamEmails>("/teams"),
};
