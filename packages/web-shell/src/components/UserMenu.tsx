import { ChevronDown, Monitor, Moon, Sun } from "lucide-react";

import type { ThemePreference } from "../lib/theme-context";
import { Avatar, AvatarFallback } from "./ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

function initialFor(label: string) {
  return label.trim().charAt(0).toUpperCase() || "U";
}

export function UserMenu({
  label,
  email,
  roles,
  themePreference,
  onThemeChange,
  authDisabled,
  onLogin,
  onLogout,
}: {
  label: string;
  email?: string | null;
  roles: string[];
  themePreference: ThemePreference;
  onThemeChange: (value: ThemePreference) => void;
  authDisabled: boolean;
  onLogin: () => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-100 focus:ring-offset-2"
        >
          <Avatar>
            <AvatarFallback>{initialFor(label)}</AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300 hidden md:block">
            {label}
          </span>
          <ChevronDown className="h-3 w-3 text-zinc-600 dark:text-zinc-400 hidden md:block" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <div className="px-2 py-1.5 border-b border-zinc-200 dark:border-zinc-800">
          <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {label}
          </div>
          {email && email !== label ? (
            <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              {email}
            </div>
          ) : null}
          {roles.length ? (
            <div className="flex flex-wrap gap-1 mt-2">
              {roles.map((role) => (
                <span
                  key={role}
                  className="text-xs px-2 py-0.5 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 rounded"
                >
                  {role}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-zinc-500 dark:text-zinc-400">
          Theme
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={themePreference}
          onValueChange={(value) => onThemeChange(value as ThemePreference)}
        >
          <DropdownMenuRadioItem value="light" className="cursor-pointer">
            <Sun className="h-4 w-4" />
            Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark" className="cursor-pointer">
            <Moon className="h-4 w-4" />
            Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system" className="cursor-pointer">
            <Monitor className="h-4 w-4" />
            System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        {authDisabled ? (
          <DropdownMenuItem onClick={() => void onLogin()} className="cursor-pointer">
            Sign in
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem
            onClick={() => void onLogout()}
            className="cursor-pointer text-red-600"
          >
            Sign out
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
