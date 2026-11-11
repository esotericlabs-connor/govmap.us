import { serverApiBase } from "@/lib/api";
import { healthResponse } from "@/lib/health.mjs";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return healthResponse(serverApiBase(), process.env.APP_COMMIT_SHA);
}
