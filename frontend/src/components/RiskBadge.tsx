import { Badge } from "@/components/ui/badge";

const variants: Record<string, string> = {
  High: "bg-red-600 text-white hover:bg-red-700",
  Medium: "bg-amber-500 text-white hover:bg-amber-600",
  Low: "bg-green-600 text-white hover:bg-green-700",
};

export default function RiskBadge({ level }: { level: string }) {
  return (
    <Badge className={variants[level] ?? "bg-gray-500 text-white"}>
      {level}
    </Badge>
  );
}
