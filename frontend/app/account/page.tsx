import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export const metadata = {
  title: "Sign in",
  description: "GovMap.us accounts are coming soon.",
};

export default function AccountPage() {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="flex min-h-screen items-center justify-center bg-white px-6 pb-16 pt-24">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-card">
          <h1 className="font-display text-2xl font-bold text-govnavy">
            Accounts are coming soon
          </h1>
          <p className="mt-3 text-slate-600">
            Sign-in isn&apos;t live yet. A free GovMap account will let you
            personalize and keep up with your government — we&apos;re building it
            now and will open it up shortly.
          </p>
          <a
            href="/"
            className="mt-6 inline-block rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-govnavy/90"
          >
            Back to home
          </a>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
