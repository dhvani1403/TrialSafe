"use client";

import { useSyncExternalStore } from "react";

// Saved studies live in this browser only (localStorage), never on the server.
export interface Saved {
  nct_id: string;
  title: string;
  added: string;
}

const KEY = "trialmatch.saved.v1";
const listeners = new Set<() => void>();
let cache: { raw: string | null; value: Saved[] } = { raw: null, value: [] };
const EMPTY: Saved[] = [];

function read(): Saved[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEY);
  } catch {
    return cache.value;
  }
  if (raw !== cache.raw) {
    try {
      cache = { raw, value: raw ? (JSON.parse(raw) as Saved[]) : [] };
    } catch {
      cache = { raw, value: [] };
    }
  }
  return cache.value;
}

function write(list: Saved[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    cache = { raw: null, value: list };
  }
  listeners.forEach((l) => l());
}

export function toggleSaved(item: { nct_id: string; title: string }) {
  const list = read();
  write(
    list.some((s) => s.nct_id === item.nct_id)
      ? list.filter((s) => s.nct_id !== item.nct_id)
      : [...list, { ...item, added: new Date().toISOString() }],
  );
}

export function removeSaved(id: string) {
  write(read().filter((s) => s.nct_id !== id));
}

export function useSaved(): Saved[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      const onStorage = (e: StorageEvent) => e.key === KEY && l();
      window.addEventListener("storage", onStorage);
      return () => {
        listeners.delete(l);
        window.removeEventListener("storage", onStorage);
      };
    },
    read,
    () => EMPTY,
  );
}
