"use client";

import { useSyncExternalStore } from "react";
import type { Profile } from "./api";

// The profile lives only in this browser tab (sessionStorage). It is sent to the API
// with each search and never stored server-side.
const KEY = "trialmatch.profile.v1";
const listeners = new Set<() => void>();
let cache: { raw: string | null; value: Profile | null } = { raw: null, value: null };

function read(): Profile | null {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(KEY);
  } catch {
    return cache.value;
  }
  if (raw !== cache.raw) {
    try {
      cache = { raw, value: raw ? (JSON.parse(raw) as Profile) : null };
    } catch {
      cache = { raw, value: null };
    }
  }
  return cache.value;
}

export function saveProfile(p: Profile | null) {
  try {
    if (p) sessionStorage.setItem(KEY, JSON.stringify(p));
    else sessionStorage.removeItem(KEY);
  } catch {
    cache = { raw: null, value: p };
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** undefined while hydrating, null when there is no profile yet. */
export function useProfile(): Profile | null | undefined {
  return useSyncExternalStore(subscribe, read, () => undefined);
}

export const emptyProfile: Profile = {
  conditions: [],
  age: 45,
  sex: "female",
  location: null,
  max_distance_mi: 100,
  comorbidities: null,
  treatments: null,
  medications: null,
};
