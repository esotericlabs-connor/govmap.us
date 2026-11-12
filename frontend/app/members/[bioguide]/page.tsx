import { notFound } from "next/navigation";
import { Suspense } from "react";

import { BackLink } from "@/components/DetailKit";
import { MemberProfileBody } from "@/components/MemberProfileBody";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { apiGet, HttpError, type MemberDetail } from "@/lib/api";

// Never prerendered — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

async function getMember(bioguide: string): Promise<MemberDetail | null> {
  try {
    return await apiGet<MemberDetail>(`/api/members/${encodeURIComponent(bioguide)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ bioguide: string }> }) {
  const { bioguide } = await params;
  const member = await getMember(bioguide).catch(() => null);
  return { title: member ? member.official_full_name : "Member" };
}

async function MemberDetailContent({ bioguide }: { bioguide: string }) {
  const member = await getMember(bioguide);
  if (!member) notFound();

  return (
    <Reveal>
      <MemberProfileBody member={member} variant="page" />
    </Reveal>
  );
}

export default async function MemberDetailPage({ params }: { params: Promise<{ bioguide: string }> }) {
  const { bioguide } = await params;
  return (
    <>
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/">Back to map</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <MemberDetailContent bioguide={bioguide} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
