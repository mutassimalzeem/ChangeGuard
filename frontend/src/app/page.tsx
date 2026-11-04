import { redirect } from "next/navigation";

/**
 * The landing route is a decision, not a page. A signed-in visitor belongs on
 * /projects; everyone else on /login. Which one applies is only known in the
 * browser (tokens are in memory), so the real choice happens in middleware.
 */
export default function HomePage() {
  redirect("/projects");
}
