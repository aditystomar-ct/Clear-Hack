import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";

export default function History() {
  const navigate = useNavigate();

  const { data: reviews } = useQuery({
    queryKey: ["reviews"],
    queryFn: api.listReviews,
  });

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
  });

  const { data: ruleData } = useQuery({
    queryKey: ["ruleEffectiveness"],
    queryFn: api.getRuleEffectiveness,
  });

  if (!reviews?.length) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        No reviews yet.
      </div>
    );
  }

  const common = stats?.common_deviations ?? {};
  const topDev = Object.keys(common).length
    ? Object.entries(common).sort((a, b) => b[1] - a[1])[0][0]
    : "N/A";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Review History</h1>

      {/* Aggregate stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard title="Total Reviews" value={stats?.total_reviews ?? 0} />
        <MetricCard
          title="Avg Flags/Contract"
          value={stats?.avg_flags_per_contract ?? 0}
        />
        <MetricCard
          title="Most Common Deviation"
          value={
            topDev !== "N/A"
              ? topDev.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
              : "N/A"
          }
        />
      </div>

      <Separator />

      {/* Past reviews */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Past Reviews</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Contract</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Mode</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {reviews.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-medium">#{r.id}</TableCell>
                <TableCell>{r.contract_name}</TableCell>
                <TableCell>{r.date?.slice(0, 10) ?? "N/A"}</TableCell>
                <TableCell>{r.analysis_mode ?? "N/A"}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/dashboard?review=${r.id}`)}
                  >
                    Open
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Separator />

      {/* Rule effectiveness */}
      <div>
        <h2 className="mb-1 text-lg font-semibold">Rule Effectiveness Report</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Track which rules trigger most and how often they are rejected (false positives).
        </p>

        {ruleData && ruleData.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule ID</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Clause</TableHead>
                <TableHead className="text-right">Triggered</TableHead>
                <TableHead className="text-right">Accepted</TableHead>
                <TableHead className="text-right">Rejected</TableHead>
                <TableHead className="text-right">FP Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ruleData.map((r) => (
                <TableRow key={r.rule_id}>
                  <TableCell className="font-mono text-xs">{r.rule_id}</TableCell>
                  <TableCell>{r.source}</TableCell>
                  <TableCell className="max-w-xs truncate">{r.clause}</TableCell>
                  <TableCell className="text-right">{r.triggered}</TableCell>
                  <TableCell className="text-right">{r.accepted}</TableCell>
                  <TableCell className="text-right">{r.rejected}</TableCell>
                  <TableCell className="text-right">{r.false_positive_rate}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="py-4 text-sm text-muted-foreground">
            No reviewer actions recorded yet. Review some flags to see rule effectiveness data.
          </p>
        )}
      </div>
    </div>
  );
}
