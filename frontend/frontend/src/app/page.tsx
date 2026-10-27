"use client";

import dynamic from "next/dynamic";

const FleetStudio = dynamic(() => import("@/components/fleet-studio"), {
  ssr: false,
  loading: () => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#f5f7f6", color: "#236f66", fontFamily: "sans-serif" }}>
      <div style={{ textAlign: "center" }}>
        <h2 style={{ fontSize: "16px", marginBottom: "8px", fontWeight: 600 }}>Loading Fleet Studio...</h2>
        <p style={{ fontSize: "12px", color: "#778580" }}>Initializing mission control and runtime telemetry</p>
      </div>
    </div>
  ),
});

export default function Home() {
  return <FleetStudio />;
}

