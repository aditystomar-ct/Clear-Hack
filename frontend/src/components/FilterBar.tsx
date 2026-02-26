import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface FilterBarProps {
  riskLevel: string;
  classification: string;
  reviewStatus: string;
  onRiskLevelChange: (v: string) => void;
  onClassificationChange: (v: string) => void;
  onReviewStatusChange: (v: string) => void;
}

export default function FilterBar({
  riskLevel,
  classification,
  reviewStatus,
  onRiskLevelChange,
  onClassificationChange,
  onReviewStatusChange,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-4">
      <Select value={riskLevel} onValueChange={onRiskLevelChange}>
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Risk Level" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="All">All Risks</SelectItem>
          <SelectItem value="High">High</SelectItem>
          <SelectItem value="Medium">Medium</SelectItem>
          <SelectItem value="Low">Low</SelectItem>
        </SelectContent>
      </Select>

      <Select value={classification} onValueChange={onClassificationChange}>
        <SelectTrigger className="w-[200px]">
          <SelectValue placeholder="Classification" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="All">All Classifications</SelectItem>
          <SelectItem value="compliant">Compliant</SelectItem>
          <SelectItem value="non_compliant">Non Compliant</SelectItem>
        </SelectContent>
      </Select>

      <Select value={reviewStatus} onValueChange={onReviewStatusChange}>
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder="Review Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="All">All Statuses</SelectItem>
          <SelectItem value="pending">Pending</SelectItem>
          <SelectItem value="accepted">Accepted</SelectItem>
          <SelectItem value="closed">Closed</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
