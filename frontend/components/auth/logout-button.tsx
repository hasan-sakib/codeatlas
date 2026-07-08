import { logoutAction } from "@/lib/actions/auth";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  return (
    <form action={logoutAction}>
      <Button type="submit" variant="ghost" size="sm">
        Log out
      </Button>
    </form>
  );
}
