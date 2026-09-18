import { useEffect, useRef, useState, type FormEvent } from "react";
import type { PlantSession } from "../hooks/usePlantSession";
import { readStored, writeStored } from "../tutorial/state";
import "../styles/login.css";

interface LoginScreenProps {
  control: PlantSession;
  replay: () => void;
}

export function LoginScreen({ control, replay }: LoginScreenProps) {
  const { busy, error, notice } = control;
  const hasSavedSession = Boolean(readStored("sessionStorage", "plantops.activeSession"));

  const [operatorName, setOperatorName] = useState(() => {
    return localStorage.getItem("plantops.operatorName") ?? "";
  });
  const [mode, setMode] = useState<"open" | "tutorial" | "resume">(() => {
    return hasSavedSession ? "resume" : "open";
  });
  const [showModes, setShowModes] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [uptimeSeconds, setUptimeSeconds] = useState(120 * 3600 + 4 * 60 + 18);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mouseOffset, setMouseOffset] = useState({ x: 0, y: 0 });

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Live real-time clock and uptime ticker
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
      setUptimeSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Track fullscreen state
  useEffect(() => {
    const handler = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  // Ambient floating particles canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const onResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", onResize);

    const particleCount = 38;
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 1.8 + 0.6,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25 - 0.1,
      alpha: Math.random() * 0.45 + 0.15,
      baseAlpha: Math.random() * 0.45 + 0.15,
      phase: Math.random() * Math.PI * 2,
    }));

    const render = () => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.phase += 0.02;
        p.alpha = p.baseAlpha + Math.sin(p.phase) * 0.15;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.fillStyle = `rgba(180, 210, 240, ${Math.max(0.05, p.alpha)})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      animId = requestAnimationFrame(render);
    };
    render();

    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(animId);
    };
  }, []);

  // Parallax on mouse movement
  const handleMouseMove = (e: React.MouseEvent) => {
    const { clientX, clientY } = e;
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    const x = (clientX - cx) / cx;
    const y = (clientY - cy) / cy;
    setMouseOffset({ x, y });
  };

  const toggleFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      // Browser may restrict programmatic fullscreen without direct user gesture
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;

    const trimmed = operatorName.trim() || "Shift Operator";
    localStorage.setItem("plantops.operatorName", trimmed);
    writeStored("localStorage", "plantops.operatorName", trimmed);

    if (mode === "tutorial") {
      replay();
    } else if (mode === "resume" && hasSavedSession) {
      await control.restoreSession();
    } else {
      // Default to standard seeded shift (42)
      await control.newShift(42);
    }
  };

  // Format date: YYYY-MM-DD HH:MM:SS
  const pad = (n: number) => n.toString().padStart(2, "0");
  const dateStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(
    now.getHours()
  )}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

  // Format uptime: 120 04:18 (days hours:minutes:seconds)
  const upDays = Math.floor(uptimeSeconds / 86400);
  const upHours = Math.floor((uptimeSeconds % 86400) / 3600);
  const upMins = Math.floor((uptimeSeconds % 3600) / 60);
  const upSecs = uptimeSeconds % 60;

  return (
    <main
      className="login-viewport"
      onMouseMove={handleMouseMove}
      aria-label="PlantOps Operations Login"
    >
      {/* 3D Rendered Industrial Props Backdrop with Subtle Parallax */}
      <div
        className="login-backdrop"
        style={{
          transform: `translate3d(${mouseOffset.x * -12}px, ${mouseOffset.y * -8}px, 0) scale(1.02)`,
        }}
      />
      <div className="login-backdrop-overlay" />

      {/* Ambient Particle Canvas */}
      <canvas ref={canvasRef} className="login-particles" />

      {/* Top SCADA Telemetry Bar */}
      <header className="login-topbar">
        <div className="topbar-group topbar-left">
          <span className="topbar-brand">PlantOps</span>
          <span className="topbar-divider" aria-hidden="true">|</span>
          <span className="topbar-plant">PLANT 01</span>
          <span className="topbar-divider" aria-hidden="true">|</span>
          <div className="topbar-indicator">
            <span className="topbar-led pulsing" aria-hidden="true" />
            <span>PRODUCTION ONLINE</span>
          </div>
        </div>

        <div className="topbar-group topbar-center">
          <span className="topbar-divider" aria-hidden="true">|</span>
          <span className="topbar-stat">SHIFT B</span>
          <span className="topbar-divider" aria-hidden="true">|</span>
          <time className="topbar-clock">{dateStr}</time>
          <span className="topbar-divider" aria-hidden="true">|</span>
          <span className="topbar-uptime">
            UPTIME <strong>{upDays} {pad(upHours)}:{pad(upMins)}:{pad(upSecs)}</strong>
          </span>
        </div>

        <div className="topbar-group topbar-right">
          <div className="topbar-stat">
            <span className="topbar-led" aria-hidden="true" />
            <span>CELLS 6/6</span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-led" aria-hidden="true" />
            <span>CONVEYORS 12/12</span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-led" aria-hidden="true" />
            <span>ALARMS 0</span>
          </div>
          <button
            type="button"
            className="topbar-fullscreen-btn"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
            aria-label="Toggle Fullscreen"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {isFullscreen ? (
                <>
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                </>
              ) : (
                <>
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                </>
              )}
            </svg>
          </button>
        </div>
      </header>

      {/* Central Login Card */}
      <section className="login-content">
        <div
          className="login-card"
          style={{
            transform: `translate3d(${mouseOffset.x * 6}px, ${mouseOffset.y * 4}px, 0)`,
          }}
        >
          {/* Logo & Branding */}
          <div className="login-brand">
            <div className="login-logo-grid" aria-hidden="true">
              <div className="login-logo-tile" />
              <div className="login-logo-tile tile-empty" />
              <div className="login-logo-tile" />
              <div className="login-logo-tile" />
            </div>
            <div className="login-brand-meta">
              <h1 className="login-brand-title">PlantOps</h1>
              <p className="login-brand-sub">PLAN · SIMULATE · OPERATE</p>
            </div>
          </div>

          <hr className="login-card-divider" />

          {/* Heading */}
          <h2 className="login-card-heading">Start your shift</h2>

          {/* Form */}
          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field-group">
              <label htmlFor="operator-name-input" className="login-label">
                Your name
              </label>
              <div className="login-input-wrap">
                <svg
                  className="login-input-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <input
                  id="operator-name-input"
                  type="text"
                  className="login-input"
                  placeholder="Enter your name"
                  value={operatorName}
                  onChange={(e) => setOperatorName(e.target.value)}
                  autoComplete="name"
                  autoFocus
                />
              </div>
            </div>

            <button
              type="submit"
              className="login-btn-primary"
              disabled={Boolean(busy)}
            >
              {busy ? (
                <>
                  <span className="login-spinner" aria-hidden="true" />
                  <span>{busy}…</span>
                </>
              ) : (
                <>
                  <span>
                    {mode === "resume" && hasSavedSession
                      ? "Resume Shift"
                      : mode === "tutorial"
                      ? "Start Guided Shift"
                      : "Enter PlantOps"}
                  </span>
                  <svg
                    className="login-arrow-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                </>
              )}
            </button>

            {/* Shift Mode Quick Options */}
            <div className="login-modes">
              <button
                type="button"
                className="login-mode-toggle"
                onClick={() => setShowModes((v) => !v)}
              >
                <span>
                  Mode:{" "}
                  <strong>
                    {mode === "open"
                      ? "Open simulation"
                      : mode === "tutorial"
                      ? "Guided first shift"
                      : "Resume saved shift"}
                  </strong>
                </span>
                <span>{showModes ? "▲" : "▼"}</span>
              </button>

              {showModes && (
                <div className="login-mode-pills">
                  <button
                    type="button"
                    className={`login-mode-pill ${mode === "open" ? "active" : ""}`}
                    onClick={() => setMode("open")}
                  >
                    Open shift
                  </button>
                  <button
                    type="button"
                    className={`login-mode-pill ${mode === "tutorial" ? "active" : ""}`}
                    onClick={() => setMode("tutorial")}
                  >
                    Guided tutorial
                  </button>
                  {hasSavedSession && (
                    <button
                      type="button"
                      className={`login-mode-pill ${mode === "resume" ? "active" : ""}`}
                      onClick={() => setMode("resume")}
                    >
                      Resume saved
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Error or Notice message */}
            {(error || notice) && (
              <p
                className={`login-status-msg ${error ? "error" : "notice"}`}
                role={error ? "alert" : "status"}
              >
                {error ?? notice}
              </p>
            )}
          </form>

          {/* Plant Location & Footer */}
          <div className="login-footer">Artemis Manufacturing · Plant 01</div>
        </div>
      </section>
    </main>
  );
}
