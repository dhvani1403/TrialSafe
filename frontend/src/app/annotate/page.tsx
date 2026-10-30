import type { Metadata } from "next";
import { Annotator } from "@/components/annotate/annotator";

export const metadata: Metadata = { title: "Gold standard review", robots: { index: false } };

export default function AnnotatePage() {
  return <Annotator />;
}
