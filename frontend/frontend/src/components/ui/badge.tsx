"use client";

import React from "react";

export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Dot({ color = "green" }: { color?: string }) {
  return <i className={`status-dot status-dot--${color}`} />;
}

export function PageTitle({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>
          {title}
          <i>.</i>
        </h1>
        <p>{subtitle}</p>
      </div>
      {action && <div className="page-actions">{action}</div>}
    </div>
  );
}
