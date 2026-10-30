import { Suspense } from "react";
import { TrialView } from "@/components/trial/trial-view";

export default function TrialPage({ params }: PageProps<"/trials/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-6xl px-6 py-16 text-ink-2">Loading study…</div>}>
      <TrialFromParams params={params} />
    </Suspense>
  );
}

async function TrialFromParams({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TrialView id={id.toUpperCase()} />;
}
