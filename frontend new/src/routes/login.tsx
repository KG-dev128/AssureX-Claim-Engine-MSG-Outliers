import { createFileRoute } from "@tanstack/react-router";
import { UserApp } from "@/lib/assurex";
export const Route = createFileRoute("/login")({ component: UserApp });
