import { NavLink } from "react-router-dom";
import { ScanSearch, LayoutDashboard, History } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const links = [
  { to: "/", label: "Analyze", icon: ScanSearch },
  { to: "/dashboard", label: "Review Dashboard", icon: LayoutDashboard },
  { to: "/history", label: "History", icon: History },
];

export default function Sidebar() {
  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
  });

  return (
    <aside className="flex h-screen w-56 flex-col border-r bg-card px-3 py-6">
      <h2 className="mb-6 px-2 text-lg font-bold tracking-tight">DPA Review</h2>

      <nav className="flex flex-1 flex-col gap-1">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent hover:text-accent-foreground"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto space-y-1 px-2 text-xs text-muted-foreground">
        <p className="font-semibold text-foreground">DPA Contract Review Tool</p>
        <p>LLM: {config?.llm_available ? "Available" : "Not configured"}</p>
      </div>
    </aside>
  );
}
