import type { Metadata, Viewport } from "next";
import { Public_Sans, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { SiteNav, SiteNavFallback } from "@/components/site-nav";
import "./globals.css";

const publicSans = Public_Sans({ variable: "--font-public-sans", subsets: ["latin"], display: "swap" });
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "TrialMatch", template: "%s · TrialMatch" },
  description:
    "Find open clinical trials that fit your health profile, with every eligibility rule explained in plain language.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f7f6" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1a1a" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${publicSans.variable} ${sourceSerif.variable} antialiased`}>
      <body className="flex min-h-dvh flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[2000] focus:rounded focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <Suspense fallback={<SiteNavFallback />}>
          <SiteNav />
        </Suspense>
        <main id="main" className="flex-1">
          {children}
        </main>
        <footer className="border-t border-rule">
          <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm text-ink-2 sm:px-6 md:grid-cols-[1.4fr_1fr]">
            <p className="max-w-prose">
              <strong className="font-semibold text-ink">TrialMatch is not medical advice.</strong> It is a research
              prototype that reads public listings from ClinicalTrials.gov and can be wrong. Only a study team can
              confirm eligibility. Talk with your doctor before making any decision about your care.
            </p>
            <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 md:justify-end">
              <Link className="hover:text-ink" href="/about">How it works</Link>
              <Link className="hover:text-ink" href="/insights">Accuracy & fairness</Link>
              <a className="hover:text-ink" href="https://clinicaltrials.gov" target="_blank" rel="noreferrer">
                Data: ClinicalTrials.gov
              </a>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
