import * as AvatarPrimitive from "@radix-ui/react-avatar";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import {
  ChevronDown,
  CircleIcon,
  LogIn,
  Monitor,
  Moon,
  Sun,
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import type { ThemePreference } from "@aegroup/agent-core-web-shell";
import { useTheme } from "@aegroup/agent-core-web-shell";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function Badge({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex w-fit items-center justify-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-colors",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Button({
  className,
  children,
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "success";
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition-all outline-none disabled:pointer-events-none disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-ring/50",
        variant === "outline"
          ? "border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:hover:bg-input/50"
          : variant === "success"
            ? "bg-emerald-600 text-white hover:bg-emerald-500"
            : "bg-primary text-primary-foreground hover:bg-primary/90",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cx(
        "border-input file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 md:text-sm",
        props.className,
      )}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cx(
        "border-input text-foreground h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50",
        props.className,
      )}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cx(
        "border-input placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground min-h-24 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50",
        props.className,
      )}
    />
  );
}

export function FormField({
  className,
  label,
  htmlFor,
  description,
  error,
  required = false,
  children,
}: {
  className?: string;
  label: string;
  htmlFor?: string;
  description?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  const labelClassName = "text-base font-semibold leading-tight text-foreground";

  return (
    <div className={cx("space-y-2", className)}>
      <div className="inline-flex items-center gap-1">
        {htmlFor ? (
          <label htmlFor={htmlFor} className={labelClassName}>
            {label}
          </label>
        ) : (
          <p className={labelClassName}>{label}</p>
        )}
        {required ? (
          <span aria-hidden="true" className="text-rose-600 dark:text-rose-400">
            *
          </span>
        ) : null}
      </div>
      {children}
      {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      {error ? (
        <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Card({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cx(
        "bg-card text-card-foreground flex flex-col gap-6 rounded-xl border py-6 shadow-sm",
        className,
      )}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cx(
        "grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6",
        className,
      )}
    />
  );
}

export function CardTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 {...props} className={cx("leading-none font-semibold", className)} />;
}

export function CardDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return <p {...props} className={cx("text-sm text-muted-foreground", className)} />;
}

export function CardContent({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("px-6", className)} />;
}

export function Avatar({
  className,
  ...props
}: AvatarPrimitive.AvatarProps) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      className={cx("relative flex size-8 shrink-0 overflow-hidden rounded-full", className)}
      {...props}
    />
  );
}

export function AvatarFallback({
  className,
  ...props
}: AvatarPrimitive.AvatarFallbackProps) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cx("bg-muted flex size-full items-center justify-center rounded-full", className)}
      {...props}
    />
  );
}

export function DropdownMenu(
  props: DropdownMenuPrimitive.DropdownMenuProps,
) {
  return <DropdownMenuPrimitive.Root data-slot="dropdown-menu" {...props} />;
}

export function DropdownMenuTrigger(
  props: DropdownMenuPrimitive.DropdownMenuTriggerProps,
) {
  return (
    <DropdownMenuPrimitive.Trigger data-slot="dropdown-menu-trigger" {...props} />
  );
}

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: DropdownMenuPrimitive.DropdownMenuContentProps) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        className={cx(
          "bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 max-h-(--radix-dropdown-menu-content-available-height) min-w-[8rem] origin-(--radix-dropdown-menu-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-md border p-1 shadow-md",
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className,
  inset,
  variant = "default",
  ...props
}: DropdownMenuPrimitive.DropdownMenuItemProps & {
  inset?: boolean;
  variant?: "default" | "destructive";
}) {
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-inset={inset}
      data-variant={variant}
      className={cx(
        "focus:bg-accent focus:text-accent-foreground data-[variant=destructive]:text-destructive data-[variant=destructive]:focus:bg-destructive/10 dark:data-[variant=destructive]:focus:bg-destructive/20 data-[variant=destructive]:focus:text-destructive data-[variant=destructive]:*:[svg]:!text-destructive [&_svg:not([class*='text-'])]:text-muted-foreground relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:pl-8 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({
  className,
  inset,
  ...props
}: DropdownMenuPrimitive.DropdownMenuLabelProps & {
  inset?: boolean;
}) {
  return (
    <DropdownMenuPrimitive.Label
      data-slot="dropdown-menu-label"
      data-inset={inset}
      className={cx("px-2 py-1.5 text-sm font-medium data-[inset]:pl-8", className)}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: DropdownMenuPrimitive.DropdownMenuSeparatorProps) {
  return (
    <DropdownMenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cx("bg-border -mx-1 my-1 h-px", className)}
      {...props}
    />
  );
}

export function DropdownMenuRadioGroup(
  props: DropdownMenuPrimitive.DropdownMenuRadioGroupProps,
) {
  return (
    <DropdownMenuPrimitive.RadioGroup
      data-slot="dropdown-menu-radio-group"
      {...props}
    />
  );
}

export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: DropdownMenuPrimitive.DropdownMenuRadioItemProps) {
  return (
    <DropdownMenuPrimitive.RadioItem
      data-slot="dropdown-menu-radio-item"
      className={cx(
        "focus:bg-accent focus:text-accent-foreground relative flex cursor-default items-center gap-2 rounded-sm py-1.5 pr-2 pl-8 text-sm outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    >
      <span className="pointer-events-none absolute left-2 flex size-3.5 items-center justify-center">
        <DropdownMenuPrimitive.ItemIndicator>
          <CircleIcon className="size-2 fill-current" />
        </DropdownMenuPrimitive.ItemIndicator>
      </span>
      {children}
    </DropdownMenuPrimitive.RadioItem>
  );
}

export function LoginPrompt({
  onLogin,
  message,
  configured,
  loading = false,
  title,
  logoLightSrc,
  logoDarkSrc,
}: {
  onLogin: () => void;
  message?: string;
  configured: boolean;
  loading?: boolean;
  title: string;
  logoLightSrc: string;
  logoDarkSrc: string;
}) {
  const { resolvedDark } = useTheme();

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-md items-center justify-center">
        <div className="w-full space-y-6 rounded-xl border bg-card p-8 text-center shadow-sm">
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
            <p className="text-sm text-muted-foreground">
              Sign in with Microsoft Entra ID to open the Orcha operator shell.
            </p>
          </div>
          <Button
            onClick={onLogin}
            disabled={!configured || loading}
            className="w-full justify-center"
          >
            <LogIn className="size-4" />
            {loading ? "Signing in..." : "Sign in"}
          </Button>
          {!configured ? (
            <p className="text-xs text-muted-foreground">
              Auth is not configured. Set `VITE_ENTRA_CLIENT_ID`,
              `VITE_ENTRA_TENANT_ID`, and `VITE_ENTRA_SCOPE`.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

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
          className="flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 dark:focus:ring-zinc-100"
        >
          <Avatar>
            <AvatarFallback>{initialFor(label)}</AvatarFallback>
          </Avatar>
          <span className="hidden text-sm font-medium text-zinc-700 dark:text-zinc-300 md:block">
            {label}
          </span>
          <ChevronDown className="hidden h-3 w-3 text-zinc-600 dark:text-zinc-400 md:block" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <div className="border-b border-zinc-200 px-2 py-1.5 dark:border-zinc-800">
          <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {label}
          </div>
          {email && email !== label ? (
            <div className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
              {email}
            </div>
          ) : null}
          {roles.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {roles.map((role) => (
                <span
                  key={role}
                  className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
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
