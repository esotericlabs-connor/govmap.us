import Link from "next/link";

export default function AppHomePage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
      <h1 className="text-3xl font-bold">Welcome to GovMap</h1>
      <p className="text-slate-600">
        This is a proof of concept: one data source (members of Congress),
        pulled from the source, normalized, and served end to end. The rest
        of the platform — ZIP lookup, bills, the executive and judicial
        branches — gets built out from here; see the project&apos;s
        CODE-MANIFEST.md for what&apos;s next.
      </p>
      <Link
        href="/members"
        className="w-fit rounded-md bg-govnavy px-4 py-2 text-white hover:bg-govnavy/90"
      >
        View members of Congress
      </Link>
    </main>
  );
}
