import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Check, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import RiskBadge from "./RiskBadge";
import { api } from "@/lib/api";
import type { Flag, FlagAction, TeamEmails } from "@/types";

interface FlagCardProps {
  flag: Flag;
  action: FlagAction | undefined;
  reviewId: number;
  isGoogleDoc: boolean;
  teamEmails: TeamEmails;
}

export default function FlagCard({
  flag,
  action,
  reviewId,
  isGoogleDoc,
  teamEmails,
}: FlagCardProps) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const queryClient = useQueryClient();
  const actionStatus = action?.reviewer_action ?? "pending";

  const statusIcon: Record<string, string> = {
    pending: "\u23F3",
    accepted: "\u2705",
    closed: "\u274C",
  };

  const acceptMut = useMutation({
    mutationFn: () => api.acceptFlag(reviewId, flag.flag_id, comment, ""),
    onSuccess: (res) => {
      const msgs = res.messages.join(". ");
      toast.success(`${flag.flag_id} accepted. ${msgs}`);
      if (res.errors.length) toast.error(res.errors.join(" | "));
      queryClient.invalidateQueries({ queryKey: ["review", reviewId] });
      queryClient.invalidateQueries({ queryKey: ["reviewFlags", reviewId] });
    },
    onError: (err: Error) => toast.error(`Accept failed: ${err.message}`),
  });

  const closeMut = useMutation({
    mutationFn: () => api.markFlagClosed(reviewId, flag.flag_id, ""),
    onSuccess: () => {
      toast.success(`${flag.flag_id} marked as closed.`);
      queryClient.invalidateQueries({ queryKey: ["review", reviewId] });
      queryClient.invalidateQueries({ queryKey: ["reviewFlags", reviewId] });
    },
    onError: (err: Error) => toast.error(`Close failed: ${err.message}`),
  });

  const taggedTeams = new Set(flag.triggered_rules.map((r) => r.source));
  const teamTags = taggedTeams.size
    ? [...taggedTeams].sort().map((t) => t.toUpperCase()).join(" | ")
    : "General";

  const notifyTeams = taggedTeams.size ? taggedTeams : new Set(Object.keys(teamEmails));
  const emailList = [...notifyTeams]
    .sort()
    .filter((t) => teamEmails[t])
    .map((t) => `${t.toUpperCase()}: ${teamEmails[t]}`);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="mb-2">
        <CollapsibleTrigger asChild>
          <button className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-accent/50 transition-colors">
            {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
            <span className="font-mono text-xs">{statusIcon[actionStatus]}</span>
            <span className="font-semibold">{flag.flag_id}</span>
            <RiskBadge level={flag.risk_level} />
            <span className="text-xs text-muted-foreground">{teamTags}</span>
            <span className="truncate text-xs text-muted-foreground">
              {(flag.input_clause_section || "N/A").slice(0, 40)}
            </span>
            <span className="ml-auto text-xs">
              {flag.classification.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>
            <span className="text-xs text-muted-foreground">
              {(flag.confidence * 100).toFixed(0)}%
            </span>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="space-y-4 pt-0">
            {/* Side-by-side clause comparison */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="mb-1 text-sm font-semibold">Incoming Clause</p>
                <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/50 p-3 text-sm whitespace-pre-wrap">
                  {flag.input_text || "N/A"}
                </div>
              </div>
              <div>
                <p className="mb-1 text-sm font-semibold">ClearTax Standard Clause</p>
                <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/50 p-3 text-sm whitespace-pre-wrap">
                  {flag.matched_playbook_text || "No playbook match"}
                </div>
              </div>
            </div>

            {/* Match info */}
            <p className="text-sm">
              <span className="font-medium">Match Type:</span> {flag.match_type || "N/A"} |{" "}
              <span className="font-medium">Risk:</span>{" "}
              <span className={flag.risk_level === "High" ? "text-red-600 font-semibold" : flag.risk_level === "Medium" ? "text-amber-600 font-semibold" : "text-green-600 font-semibold"}>
                {flag.risk_level}
              </span>{" "}
              | <span className="font-medium">Classification:</span>{" "}
              {flag.classification.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </p>

            {/* Explanation */}
            <div>
              <p className="text-sm font-semibold">Explanation</p>
              <p className="text-sm text-muted-foreground">{flag.explanation}</p>
            </div>

            {/* Triggered rules */}
            {flag.triggered_rules.length > 0 && (
              <div>
                <p className="text-sm font-semibold">Triggered Rules</p>
                <ul className="list-disc pl-5 text-sm text-muted-foreground">
                  {flag.triggered_rules.map((r, i) => {
                    const email = teamEmails[r.source] ?? "";
                    return (
                      <li key={i}>
                        [{r.source.toUpperCase()}]{email ? ` — ${email}` : ""} {r.clause} (Risk: {r.risk})
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Email notification targets */}
            {emailList.length > 0 && (
              <p className="text-sm">
                <span className="font-medium">Email notification to:</span>{" "}
                {emailList.join(", ")}
              </p>
            )}

            {/* Suggested redline */}
            {flag.suggested_redline && (
              <div>
                <p className="text-sm font-semibold">Suggested Redline</p>
                <div className="rounded-md border-l-4 border-blue-400 bg-blue-50 p-3 text-sm dark:bg-blue-950">
                  {flag.suggested_redline}
                </div>
              </div>
            )}

            <Separator />

            {/* Review status */}
            <p className="text-sm font-semibold">
              Review Status: {statusIcon[actionStatus]} {actionStatus.toUpperCase()}
            </p>

            {/* Comment box for Google Docs */}
            {isGoogleDoc && (
              <Textarea
                placeholder="Write a custom comment... Leave empty to use the auto-generated review comment."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="h-20"
              />
            )}

            {/* Action buttons */}
            <div className="flex gap-3">
              <Button
                onClick={() => acceptMut.mutate()}
                disabled={acceptMut.isPending || closeMut.isPending}
              >
                <Check className="mr-1 h-4 w-4" />
                {acceptMut.isPending ? "Accepting..." : "Accept"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => closeMut.mutate()}
                disabled={acceptMut.isPending || closeMut.isPending}
              >
                <X className="mr-1 h-4 w-4" />
                {closeMut.isPending ? "Closing..." : "Mark as Closed"}
              </Button>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
