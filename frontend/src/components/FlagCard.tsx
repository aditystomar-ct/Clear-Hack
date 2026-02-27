import { useState, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Check, X, MessageSquareText, Pencil } from "lucide-react";
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

/** Mirrors _build_professional_comment from google_doc.py */
function buildCommentPreview(flag: Flag, teamEmails: TeamEmails): string {
  if (flag.classification === "compliant") {
    return "No concerns. This clause aligns with our standard DPA.";
  }
  let comment = `Concern: ${flag.explanation}`;
  if (flag.suggested_redline) {
    comment += `\n\nProposed Amendment: ${flag.suggested_redline}`;
  }

  // Tag relevant team emails
  const taggedTeams = new Set(flag.triggered_rules.map((r) => r.source));
  const teams = taggedTeams.size ? taggedTeams : new Set(Object.keys(teamEmails));
  const tags = [...teams]
    .sort()
    .filter((t) => teamEmails[t])
    .map((t) => `@${teamEmails[t]}`);
  if (tags.length) {
    comment += "\n\n" + tags.join(" ");
  }

  return comment;
}

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
  const queryClient = useQueryClient();
  const actionStatus = action?.reviewer_action ?? "pending";

  const autoComment = useMemo(() => buildCommentPreview(flag, teamEmails), [flag, teamEmails]);
  const [comment, setComment] = useState(autoComment);
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState(false);

  const handleCommentChange = (value: string) => {
    setComment(value);
    setEdited(true);
  };

  const resetComment = () => {
    setComment(autoComment);
    setEdited(false);
    setEditing(false);
  };

  const statusIcon: Record<string, string> = {
    pending: "\u23F3",
    accepted: "\u2705",
    closed: "\u274C",
  };

  const acceptMut = useMutation({
    mutationFn: () => api.acceptFlag(reviewId, flag.flag_id, comment, ""),
    onSuccess: () => {
      toast.success(`${flag.flag_id} accepted.`);
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

            {/* Google Doc comment preview — only show edit option when pending */}
            {isGoogleDoc && actionStatus === "pending" && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MessageSquareText className="h-4 w-4 text-muted-foreground" />
                    <p className="text-sm font-semibold">
                      Comment to post on Google Doc
                    </p>
                  </div>
                  {!editing ? (
                    <button
                      onClick={() => setEditing(true)}
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <Pencil className="h-3 w-3" />
                      Edit
                    </button>
                  ) : edited ? (
                    <button
                      onClick={resetComment}
                      className="text-xs text-muted-foreground underline hover:text-foreground"
                    >
                      Reset to auto-generated
                    </button>
                  ) : null}
                </div>
                {editing ? (
                  <Textarea
                    value={comment}
                    onChange={(e) => handleCommentChange(e.target.value)}
                    className="min-h-24 font-mono text-sm"
                    autoFocus
                  />
                ) : (
                  <div className="whitespace-pre-wrap rounded-md border bg-muted/50 p-3 text-sm">
                    {comment}
                  </div>
                )}
              </div>
            )}

            {/* Action buttons — only show when still pending */}
            {actionStatus === "pending" ? (
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
            ) : (
              <p className="text-sm text-muted-foreground">
                {actionStatus === "accepted" ? "\u2705 Accepted" : "\u274C Closed"}
                {action?.action_timestamp ? ` on ${new Date(action.action_timestamp).toLocaleDateString()}` : ""}
              </p>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
