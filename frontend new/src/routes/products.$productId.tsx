import { createFileRoute } from "@tanstack/react-router";
import { UserApp } from "@/lib/assurex";
export const Route = createFileRoute("/products/$productId")({ component: UserApp });
