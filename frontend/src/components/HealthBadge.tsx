import { useEffect, useState } from "react";
import { api } from "../api/client";

type Status = "checking" | "online" | "offline";

export function HealthBadge() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let active = true;
    const check = () => {
      api
        .health()
        .then(() => active && setStatus("online"))
        .catch(() => active && setStatus("offline"));
    };
    check();
    const id = setInterval(check, 10_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const label = {
    checking: "Checking backend…",
    online: "Backend online",
    offline: "Backend offline",
  }[status];

  return (
    <span className={`badge badge-${status}`}>
      <span className="dot" /> {label}
      <span className="badge-url">{api.baseUrl}</span>
    </span>
  );
}
