import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "default" | "outline" | "destructive" | "ghost";
const styles: Record<Variant, string> = {
  default: "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300",
  outline: "border border-zinc-300 bg-transparent hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800",
  destructive: "bg-red-600 text-white hover:bg-red-500",
  ghost: "hover:bg-zinc-100 dark:hover:bg-zinc-800",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }
>(({ variant = "default", className = "", ...props }, ref) => (
  <button
    ref={ref}
    className={`inline-flex h-9 items-center justify-center rounded-md px-3 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 ${styles[variant]} ${className}`}
    {...props}
  />
));
Button.displayName = "Button";
