import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Upload, Link } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";
import { useAnalyze } from "@/hooks/useAnalyze";

export default function UploadAnalyze() {
  const navigate = useNavigate();
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig });

  const [inputMethod, setInputMethod] = useState<"file" | "url">("url");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [playbook, setPlaybook] = useState("default");
  const [customPlaybook, setCustomPlaybook] = useState("");

  const analyzer = useAnalyze();

  const handleAnalyze = () => {
    if (inputMethod === "file" && !file) return;
    if (inputMethod === "url" && !url.trim()) return;

    const fd = new FormData();
    if (inputMethod === "file" && file) {
      fd.append("file", file);
    } else {
      fd.append("url", url.trim());
    }
    fd.append("reviewer", reviewer);
    if (playbook !== "default" && customPlaybook.trim()) {
      fd.append("playbook", customPlaybook.trim());
    }
    analyzer.start(fd);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Upload & Analyze DPA</h1>
        <p className="text-muted-foreground">
          Compare an incoming DPA against ClearTax's standard DPA and internal rulebook using Claude.
        </p>
      </div>

      {!config?.llm_available && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          ANTHROPIC_API_KEY not set in .env. Analysis will not work.
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Left column: Input */}
        <div className="space-y-4">
          <div className="flex gap-2">
            <Button
              variant={inputMethod === "file" ? "default" : "outline"}
              size="sm"
              onClick={() => setInputMethod("file")}
            >
              <Upload className="mr-1 h-4 w-4" /> Upload .docx
            </Button>
            <Button
              variant={inputMethod === "url" ? "default" : "outline"}
              size="sm"
              onClick={() => setInputMethod("url")}
            >
              <Link className="mr-1 h-4 w-4" /> Google Doc URL
            </Button>
          </div>

          {inputMethod === "file" ? (
            <Input
              type="file"
              accept=".docx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          ) : (
            <Input
              placeholder="Google Doc URL or ID"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          )}
        </div>

        {/* Right column: Settings */}
        <div className="space-y-4">
          <Input
            placeholder="Reviewer name (optional)"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
          />

          <Select value={playbook} onValueChange={setPlaybook}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">ClearTax DPA (default)</SelectItem>
              <SelectItem value="custom">Custom Google Doc</SelectItem>
            </SelectContent>
          </Select>

          {playbook === "custom" && (
            <Input
              placeholder="Custom playbook Google Doc URL or ID"
              value={customPlaybook}
              onChange={(e) => setCustomPlaybook(e.target.value)}
            />
          )}

          <p className="text-xs text-muted-foreground">
            Analysis: Direct LLM comparison using Claude ({config?.llm_model ?? "N/A"})
          </p>
        </div>
      </div>

      <Separator />

      <Button
        className="w-full"
        size="lg"
        disabled={
          analyzer.running ||
          (inputMethod === "file" && !file) ||
          (inputMethod === "url" && !url.trim())
        }
        onClick={handleAnalyze}
      >
        {analyzer.running ? "Analyzing..." : "Analyze DPA"}
      </Button>

      {/* Progress section */}
      {(analyzer.running || analyzer.progress > 0) && (
        <div className="space-y-3">
          <Progress value={analyzer.progress * 100} />
          <p className="text-sm font-medium">{analyzer.message}</p>
          {analyzer.logs.length > 0 && (
            <pre className="max-h-60 overflow-y-auto rounded-md border bg-muted p-3 text-xs">
              {analyzer.logs.join("\n")}
            </pre>
          )}
        </div>
      )}

      {/* Error */}
      {analyzer.error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          Analysis failed: {analyzer.error}
        </div>
      )}

      {/* Success */}
      {analyzer.result && (
        <div className="space-y-4">
          <div className="rounded-md border border-green-300 bg-green-50 p-3 text-sm text-green-800 dark:bg-green-950 dark:text-green-200">
            Analysis complete! Review ID: #{analyzer.result.review_id} (
            {analyzer.result.metadata?.elapsed_seconds ?? "?"}s)
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCard
              title="Clauses Analyzed"
              value={analyzer.result.summary.total_clauses_analyzed}
            />
            <MetricCard title="High Risk" value={analyzer.result.summary.high_risk_count} />
            <MetricCard
              title="Non-Compliant"
              value={analyzer.result.summary.non_compliant_count}
            />
            <MetricCard
              title="Time"
              value={`${analyzer.result.metadata?.elapsed_seconds ?? "?"}s`}
            />
          </div>

          <Button onClick={() => navigate(`/dashboard?review=${analyzer.result!.review_id}`)}>
            Go to Review Dashboard
          </Button>
        </div>
      )}
    </div>
  );
}
