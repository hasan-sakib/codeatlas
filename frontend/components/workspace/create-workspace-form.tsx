"use client";

import { useActionState } from "react";
import { createWorkspaceAction, type FormActionState } from "@/lib/actions/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

const initialState: FormActionState = {};

export function CreateWorkspaceForm() {
  const [state, formAction, pending] = useActionState(createWorkspaceAction, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      {state.error ? (
        <Alert variant="destructive">
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Name</Label>
        <Input id="name" name="name" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="description">Description</Label>
        <Input id="description" name="description" />
      </div>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Creating…" : "Create workspace"}
      </Button>
    </form>
  );
}
