import type { Metadata } from "next";
import { Insights } from "@/components/insights/insights";

export const metadata: Metadata = { title: "Accuracy & fairness" };

export default function InsightsPage() {
  return <Insights />;
}
