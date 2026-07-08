"use client";

import { useActionState } from "react";
import { createRepositoryAction, type FormActionState } from "@/lib/actions/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

const initialState: FormActionState = {};

export function CreateRepositoryForm({ workspaceId }: { workspaceId: string }) {
  const action = createRepositoryAction.bind(null, workspaceId);
  const [state, formAction, pending] = useActionState(action, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      {state.error ? (
        <Alert variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <Label htmlFor="git_url">Git URL</Label>
        <Input id="git_url" name="git_url" placeholder="https://github.com/org/repo.git" required />
      </div>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Registering…" : "Register repository"}
      </Button>
    </form>
  );
}
