import type { Metadata } from "next";
import { Results } from "@/components/results/results";

export const metadata: Metadata = { title: "Your matches" };

export default function ResultsPage() {
  return <Results />;
}
