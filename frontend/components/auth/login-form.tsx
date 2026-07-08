"use client";

import { useActionState } from "react";
import Link from "next/link";
import { loginAction, type AuthFormState } from "@/lib/actions/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

const initialState: AuthFormState = {};

export function LoginForm({ nextPath }: { nextPath: string }) {
  const [state, formAction, pending] = useActionState(loginAction, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={nextPath} />
      {state.error ? (
        <Alert variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input id="password" name="password" type="password" autoComplete="current-password" required />
      </div>
      <Button type="submit" disabled={pending} className="mt-2">
        {pending ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-muted-foreground text-center text-sm">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="text-foreground underline underline-offset-4">
          Register
        </Link>
      </p>
    </form>
  );
}
