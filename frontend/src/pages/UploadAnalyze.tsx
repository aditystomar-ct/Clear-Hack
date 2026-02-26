import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ScanSearch, FileText, ArrowRight, AlertTriangle, CheckCircle2,
  Clock, ShieldAlert, BookOpen, FileSearch, Brain, Flag, Database,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";
import { useAnalyze } from "@/hooks/useAnalyze";

export default function UploadAnalyze() {
  const navigate = useNavigate();
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig });

  const [url, setUrl] = useState("");
  const [playbook, setPlaybook] = useState("default");
  const [customPlaybook, setCustomPlaybook] = useState("");

  const analyzer = useAnalyze();

  const handleAnalyze = () => {
    if (!url.trim()) return;
    const fd = new FormData();
    fd.append("url", url.trim());
    if (playbook !== "default" && customPlaybook.trim()) {
      fd.append("playbook", customPlaybook.trim());
    }
    analyzer.start(fd);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && url.trim() && !analyzer.running) handleAnalyze();
  };

  // Idle state — show the main input form
  const showForm = !analyzer.running && !analyzer.result && !analyzer.error;

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center">
      {/* Hero header */}
      <div className="mt-12 mb-10 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
          <ScanSearch className="h-7 w-7 text-primary" />
        </div>
        <h1 className="text-3xl font-bold tracking-tight">Analyze DPA</h1>
        <p className="mt-2 text-muted-foreground">
          Paste a Google Doc link and ClearTax's AI will compare it against your standard DPA
          and internal rulebook.
        </p>
      </div>

      {!config?.llm_available && (
        <div className="mb-6 flex w-full items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          ANTHROPIC_API_KEY is not configured. Analysis won't work until it's set in <code className="mx-1 rounded bg-amber-100 px-1 font-mono text-xs dark:bg-amber-900">.env</code>.
        </div>
      )}

      {/* ---------- Input card ---------- */}
      {showForm && (
        <Card className="w-full">
          <CardContent className="space-y-5 pt-6">
            {/* Google Doc URL */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Google Doc URL</label>
              <div className="relative">
                <FileText className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="https://docs.google.com/document/d/..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Paste the full URL or just the document ID
              </p>
            </div>

            {/* Playbook selector */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Playbook</label>
              <Select value={playbook} onValueChange={setPlaybook}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">ClearTax DPA (default)</SelectItem>
                  <SelectItem value="custom">Custom Google Doc</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {playbook === "custom" && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Custom Playbook URL</label>
                <Input
                  placeholder="Google Doc URL or ID for your custom playbook"
                  value={customPlaybook}
                  onChange={(e) => setCustomPlaybook(e.target.value)}
                />
              </div>
            )}

            <Button
              className="w-full"
              size="lg"
              disabled={!url.trim() || analyzer.running}
              onClick={handleAnalyze}
            >
              <ScanSearch className="mr-2 h-4 w-4" />
              Analyze DPA
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              Powered by Claude <span className="font-mono">({config?.llm_model ?? "..."})</span>
            </p>
          </CardContent>
        </Card>
      )}

      {/* ---------- Progress ---------- */}
      {analyzer.running && <ProgressPanel step={analyzer.step} message={analyzer.message} progress={analyzer.progress} logs={analyzer.logs} />}

      {/* ---------- Error ---------- */}
      {analyzer.error && (
        <Card className="w-full border-red-200 dark:border-red-900">
          <CardContent className="space-y-4 pt-6">
            <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <p className="text-sm font-semibold">Analysis failed</p>
            </div>
            <p className="text-sm text-muted-foreground">{analyzer.error}</p>
            <Button variant="outline" onClick={analyzer.reset}>
              Try Again
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ---------- Success ---------- */}
      {analyzer.result && (
        <div className="w-full space-y-6">
          {/* Success banner */}
          <Card className="border-green-200 dark:border-green-900">
            <CardContent className="flex items-center gap-3 pt-6">
              <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              <div>
                <p className="text-sm font-semibold text-green-800 dark:text-green-300">
                  Analysis complete — Review #{analyzer.result.review_id}
                </p>
                <p className="text-xs text-muted-foreground">
                  Finished in {analyzer.result.metadata?.elapsed_seconds ?? "?"}s
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Metric cards */}
          <div className="grid grid-cols-2 gap-4">
            <MetricCard title="Clauses Analyzed" value={analyzer.result.summary.total_clauses_analyzed} />
            <MetricCard title="High Risk" value={analyzer.result.summary.high_risk_count} />
            <MetricCard title="Non-Compliant" value={analyzer.result.summary.non_compliant_count} />
            <MetricCard
              title="Compliant"
              value={analyzer.result.summary.classification_breakdown?.compliant ?? 0}
            />
          </div>

          {/* Quick breakdown */}
          <div className="flex flex-wrap justify-center gap-3 text-sm">
            {Object.entries(analyzer.result.summary.risk_breakdown ?? {}).map(([level, count]) => (
              <span
                key={level}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-medium ${
                  level === "High"
                    ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
                    : level === "Medium"
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                      : "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"
                }`}
              >
                {level === "High" ? (
                  <ShieldAlert className="h-3.5 w-3.5" />
                ) : (
                  <Clock className="h-3.5 w-3.5" />
                )}
                {count} {level}
              </span>
            ))}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Button className="flex-1" onClick={() => navigate(`/dashboard?review=${analyzer.result!.review_id}`)}>
              Open Review Dashboard
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button variant="outline" onClick={analyzer.reset}>
              Analyze Another
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Animated progress panel                                           */
/* ------------------------------------------------------------------ */

const PIPELINE_STEPS = [
  { key: 1, label: "Loading rulebook", icon: BookOpen },
  { key: 2, label: "Fetching documents", icon: FileSearch },
  { key: 3, label: "Analyzing with Claude", icon: Brain },
  { key: 4, label: "Building flags", icon: Flag },
  { key: 5, label: "Saving review", icon: Database },
];

function ProgressPanel({
  step,
  message,
  progress,
  logs,
}: {
  step: number;
  message: string;
  progress: number;
  logs: string[];
}) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    startRef.current = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  return (
    <Card className="w-full overflow-hidden">
      {/* Animated top bar */}
      <div className="h-1 w-full bg-muted">
        <div
          className="h-full bg-primary transition-all duration-700 ease-out"
          style={{ width: `${Math.max(progress * 100, 2)}%` }}
        />
      </div>

      <CardContent className="space-y-6 pt-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <div className="absolute inset-0 animate-ping rounded-full bg-primary/20" />
              <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <ScanSearch className="h-5 w-5 text-primary animate-pulse" />
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold">Analyzing your DPA</p>
              <p className="text-xs text-muted-foreground">{timeStr} elapsed</p>
            </div>
          </div>
          <span className="text-xs font-medium text-muted-foreground">
            {Math.round(progress * 100)}%
          </span>
        </div>

        {/* Step tracker */}
        <div className="space-y-1">
          {PIPELINE_STEPS.map((s) => {
            const Icon = s.icon;
            const isDone = step > s.key;
            const isCurrent = step === s.key;

            return (
              <div
                key={s.key}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-300 ${
                  isCurrent
                    ? "bg-primary/5 font-medium text-foreground"
                    : isDone
                      ? "text-muted-foreground"
                      : "text-muted-foreground/40"
                }`}
              >
                {/* Status indicator */}
                <div className="flex h-6 w-6 shrink-0 items-center justify-center">
                  {isDone ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                  ) : isCurrent ? (
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  ) : (
                    <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
                  )}
                </div>

                <Icon className={`h-4 w-4 shrink-0 ${isCurrent ? "text-primary" : ""}`} />
                <span>{s.label}</span>

                {isCurrent && (
                  <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                    In progress
                  </span>
                )}
                {isDone && (
                  <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-green-500/60" />
                )}
              </div>
            );
          })}
        </div>

        {/* Current message */}
        {message && (
          <p className="text-center text-xs text-muted-foreground animate-pulse">
            {message}
          </p>
        )}

        {/* Logs */}
        {logs.length > 0 && (
          <div className="max-h-32 overflow-y-auto rounded-lg border bg-muted/30 p-3">
            {logs.map((log, i) => (
              <p key={i} className="font-mono text-xs leading-relaxed text-muted-foreground">
                {log}
              </p>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
