import type { Metadata } from "next";
import { Wizard } from "@/components/wizard/wizard";

export const metadata: Metadata = { title: "Your health profile" };

export default function MatchPage() {
  return <Wizard />;
}
