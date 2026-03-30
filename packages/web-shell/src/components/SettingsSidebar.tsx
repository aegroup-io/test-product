import { NavLink } from "react-router-dom";
import {
  type LucideIcon,
} from "lucide-react";

import { cn } from "../lib/utils";

type SettingsSidebarItem = {
  to: string;
  label: string;
  icon: LucideIcon;
};

export default function SettingsSidebar({ items }: { items: SettingsSidebarItem[] }) {
  return (
    <aside className="w-64 shrink-0 border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="border-b border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Settings
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          System Configuration
        </p>
      </div>
      <nav className="space-y-1 p-4">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
