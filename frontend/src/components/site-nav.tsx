"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProfile } from "@/lib/profile";
import { useSaved } from "@/lib/shortlist";

const links = [
  { href: "/results", label: "Your matches", needsProfile: true },
  { href: "/insights", label: "Accuracy & fairness" },
  { href: "/about", label: "How it works" },
];

export function SiteNav() {
  const path = usePathname();
  const profile = useProfile();
  const saved = useSaved();
  return (
    <header className="sticky top-0 z-[1100] border-b border-rule bg-paper/90 backdrop-blur supports-[backdrop-filter]:bg-paper/75">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Logo />
          <span>TrialMatch</span>
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 text-sm">
          {links
            .filter((l) => !l.needsProfile || profile)
            .map((l) => (
              <Link
                key={l.href}
                href={l.href}
                aria-current={path.startsWith(l.href) ? "page" : undefined}
                className="hidden rounded-md px-3 py-1.5 text-ink-2 hover:bg-paper-2 hover:text-ink aria-[current=page]:text-ink aria-[current=page]:font-semibold sm:block"
              >
                {l.label}
              </Link>
            ))}
          {saved.length > 0 && (
            <Link
              href="/saved"
              aria-current={path.startsWith("/saved") ? "page" : undefined}
              className="rounded-md px-3 py-1.5 text-ink-2 hover:bg-paper-2 hover:text-ink aria-[current=page]:font-semibold aria-[current=page]:text-ink"
            >
              Saved <span className="tabular-nums">{saved.length}</span>
            </Link>
          )}
          <Link
            href="/match"
            className="ml-2 rounded-md bg-pine px-3.5 py-1.5 font-medium text-on-pine hover:bg-pine-hover"
          >
            {profile ? "Edit profile" : "Find trials"}
          </Link>
        </nav>
      </div>
    </header>
  );
}

/** Static shell rendered while the active route is resolved. */
export function SiteNavFallback() {
  return (
    <header className="sticky top-0 z-[1100] border-b border-rule bg-paper/90">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Logo />
          <span>TrialMatch</span>
        </Link>
        <Link href="/match" className="rounded-md bg-pine px-3.5 py-1.5 text-sm font-medium text-on-pine">
          Find trials
        </Link>
      </div>
    </header>
  );
}

function Logo() {
  // a page of fine print with one line highlighted
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <rect x="3" y="1.5" width="16" height="19" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <rect x="5" y="9" width="12" height="4.5" rx="1" fill="var(--mark-check)" />
      <path d="M6.5 6h9M6.5 11.25h9M6.5 16.5h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
