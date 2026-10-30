"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window` at import time, so the map only ever renders in the browser.
export const TrialMap = dynamic(() => import("./trial-map"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-paper-2" />,
});
export type { MapPoint } from "./trial-map";
