import { LogIn } from "lucide-react";

import { useTheme } from "../lib/theme-context";
import { Button } from "./ui/button";

interface LoginPromptProps {
  onLogin: () => void;
  message?: string;
  configured: boolean;
  loading?: boolean;
  title: string;
  logoLightSrc: string;
  logoDarkSrc: string;
}

export default function LoginPrompt({
  onLogin,
  message,
  configured,
  loading = false,
  title,
  logoLightSrc,
  logoDarkSrc,
}: LoginPromptProps) {
  const { resolvedDark } = useTheme();

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="text-center max-w-md w-full space-y-6">
        <div className="flex justify-center">
          <img
            src={resolvedDark ? logoDarkSrc : logoLightSrc}
            alt={title}
            className="h-20 w-auto"
          />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold">
            {message || "Authentication required"}
          </h1>
          <p className="text-muted-foreground">
            Sign in with Microsoft Entra ID to access the shared platform shell.
          </p>
        </div>
        <Button
          onClick={onLogin}
          size="lg"
          className="gap-2"
          disabled={!configured || loading}
        >
          <LogIn className="size-5" />
          {loading ? "Signing in..." : "Sign in"}
        </Button>
        {!configured && (
          <p className="text-xs text-muted-foreground">
            Auth is not configured. Set `VITE_ENTRA_CLIENT_ID`,
            `VITE_ENTRA_TENANT_ID`, and `VITE_ENTRA_SCOPE`.
          </p>
        )}
      </div>
    </div>
  );
}
