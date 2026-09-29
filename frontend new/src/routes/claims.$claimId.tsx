import { createFileRoute } from "@tanstack/react-router";
import { UserApp } from "@/lib/assurex";
export const Route = createFileRoute("/claims/$claimId")({ component: UserApp });
