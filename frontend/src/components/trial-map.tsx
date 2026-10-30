"use client";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  title: string;
  subtitle?: string;
  href?: string;
}

const pinIcon = (active: boolean) =>
  L.divIcon({ className: "", html: `<div class="pin ${active ? "pin-active" : ""}"></div>`, iconSize: [14, 14], iconAnchor: [7, 7] });
const homeIcon = L.divIcon({ className: "", html: `<div class="pin pin-home"></div>`, iconSize: [18, 18], iconAnchor: [9, 9] });

function FitBounds({ points, home }: { points: MapPoint[]; home?: { lat: number; lon: number } | null }) {
  const map = useMap();
  const key = points.map((p) => p.id).join("|") + (home ? `${home.lat},${home.lon}` : "");
  useEffect(() => {
    const coords: [number, number][] = points.map((p) => [p.lat, p.lon]);
    if (home) coords.push([home.lat, home.lon]);
    if (coords.length === 0) return;
    if (coords.length === 1) map.setView(coords[0], 9);
    else map.fitBounds(L.latLngBounds(coords), { padding: [36, 36], maxZoom: 11 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

function FlyTo({ point }: { point?: MapPoint }) {
  const map = useMap();
  useEffect(() => {
    if (point && !map.getBounds().pad(-0.1).contains([point.lat, point.lon])) {
      map.panTo([point.lat, point.lon], { animate: true });
    }
  }, [point, map]);
  return null;
}

export default function TrialMap({
  points,
  home,
  activeId,
  onSelect,
  className = "h-full w-full",
}: {
  points: MapPoint[];
  home?: { lat: number; lon: number; label?: string } | null;
  activeId?: string | null;
  onSelect?: (id: string) => void;
  className?: string;
}) {
  const active = useMemo(() => points.find((p) => p.id === activeId), [points, activeId]);
  const center: [number, number] = home ? [home.lat, home.lon] : [39.5, -98.35];
  return (
    <MapContainer center={center} zoom={home ? 8 : 4} scrollWheelZoom={false} className={className}>
      {/* OSM standard tiles, muted (and inverted in dark mode) by CSS so the pins carry the color */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={18}
      />
      <FitBounds points={points} home={home} />
      <FlyTo point={active} />
      {home && (
        <Marker position={[home.lat, home.lon]} icon={homeIcon} zIndexOffset={-100}>
          <Popup>{home.label || "You"}</Popup>
        </Marker>
      )}
      {points.map((p) => (
        <Marker
          key={p.id}
          position={[p.lat, p.lon]}
          icon={pinIcon(p.id === activeId)}
          zIndexOffset={p.id === activeId ? 1000 : 0}
          eventHandlers={{ click: () => onSelect?.(p.id) }}
        >
          <Popup>
            <strong className="block">{p.title}</strong>
            {p.subtitle && <span className="text-ink-2">{p.subtitle}</span>}
            {p.href && (
              <a href={p.href} className="mt-1 block font-medium" style={{ color: "var(--pine)" }}>
                Open study
              </a>
            )}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
