import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button, Popconfirm } from "antd";
import {
  EyeOutlined,
  MenuUnfoldOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { budgetLabel, providerLabel } from "./admin-support.jsx";

const PARTICLE_COUNT = 34;
const ORBIT_COUNT = 9;

function randomWingBackdrop() {
  return Math.random() < 0.5 ? "wing-bg-single" : "wing-bg-wide";
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function GothicConsoleShell({
  activeMenu,
  activeMenuLabel,
  menuItems = [],
  setActiveMenu,
  status,
  display = {},
  gateway = {},
  budget = {},
  circuit = {},
  loading,
  onRefresh,
  onSetMode,
  onPauseResume,
  children,
}) {
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [navAwake, setNavAwake] = useState(false);
  const [isShifting, setIsShifting] = useState(false);
  const [wingBackdrop, setWingBackdrop] = useState(() => randomWingBackdrop());
  const [compactNav, setCompactNav] = useState(false);
  const shiftTimer = useRef(null);
  const navSleepTimer = useRef(null);
  const pointerFrame = useRef(null);
  const pendingPointer = useRef(null);
  const navAwakeRef = useRef(false);
  const navRef = useRef(null);
  const runtimeLabel = status?.runtime_mode || display.runtime_mode_zh || "DISCONNECTED";
  const agentLabel = status?.agent_paused ? "PAUSED" : status ? "RUNNING" : "UNKNOWN";
  const ledgerCount = status?.ledger?.persisted_records ?? status?.ledger?.records ?? 0;
  const pendingAppeals = status?.pending_appeals ?? 0;
  const consoleClassName = [
    "atee-shell",
    "gothic-console",
    `active-${activeMenu}`,
    activeMenu === "dashboard" ? "" : wingBackdrop,
    navAwake ? "nav-awake" : "",
    isShifting ? "page-shifting" : "",
  ].filter(Boolean).join(" ");
  const stageClassName = ["gothic-stage", `active-${activeMenu}`].join(" ");

  useEffect(() => () => {
    if (shiftTimer.current) {
      window.clearTimeout(shiftTimer.current);
    }
    if (navSleepTimer.current) {
      window.clearTimeout(navSleepTimer.current);
    }
    if (pointerFrame.current) {
      window.cancelAnimationFrame(pointerFrame.current);
    }
  }, []);

  useEffect(() => {
    navAwakeRef.current = navAwake;
  }, [navAwake]);

  useEffect(() => {
    const query = window.matchMedia?.("(max-width: 1120px)");
    if (!query) {
      return undefined;
    }
    const updateCompactNav = () => setCompactNav(query.matches);
    updateCompactNav();
    query.addEventListener?.("change", updateCompactNav);
    return () => query.removeEventListener?.("change", updateCompactNav);
  }, []);

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) {
      return;
    }
    if (compactNav) {
      nav.style.removeProperty("opacity");
      nav.style.removeProperty("transform");
      nav.style.removeProperty("filter");
      nav.style.removeProperty("--nav-marker-opacity");
      return;
    }
    nav.style.setProperty("--nav-marker-opacity", navAwake ? "0" : "1");
    nav.style.setProperty("opacity", navAwake ? "0.96" : "0.42", "important");
    nav.style.setProperty("transform", navAwake ? "translate3d(0px, -50%, 0)" : "translate3d(calc(-100% + 30px), -50%, 0)", "important");
    nav.style.setProperty("filter", navAwake ? "none" : "saturate(0.72)", "important");
  }, [compactNav, navAwake]);

  function wakeNavigation() {
    if (navSleepTimer.current) {
      window.clearTimeout(navSleepTimer.current);
      navSleepTimer.current = null;
    }
    setNavAwake(true);
  }

  function sleepNavigation(delay = 180) {
    if (navSleepTimer.current) {
      window.clearTimeout(navSleepTimer.current);
    }
    navSleepTimer.current = window.setTimeout(() => {
      setNavAwake(false);
      navSleepTimer.current = null;
    }, delay);
  }

  function handlePointerMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    pendingPointer.current = {
      x: clamp((event.clientX - rect.left) / rect.width - 0.5, -0.5, 0.5),
      y: clamp((event.clientY - rect.top) / rect.height - 0.5, -0.5, 0.5),
      left: event.clientX - rect.left,
    };
    if (pointerFrame.current) {
      return;
    }
    pointerFrame.current = window.requestAnimationFrame(() => {
      const next = pendingPointer.current;
      pointerFrame.current = null;
      if (!next) {
        return;
      }
      setPointer({ x: next.x, y: next.y });
      if (next.left < 240) {
        wakeNavigation();
      } else if (navAwakeRef.current) {
        sleepNavigation(260);
      }
    });
  }

  function beginPageShift() {
    setIsShifting(true);
    if (shiftTimer.current) {
      window.clearTimeout(shiftTimer.current);
    }
    shiftTimer.current = window.setTimeout(() => setIsShifting(false), 220);
  }

  function resetPageScroll(reduceMotion) {
    window.requestAnimationFrame(() => {
      window.scrollTo({
        top: 0,
        left: 0,
        behavior: reduceMotion ? "auto" : "smooth",
      });
    });
  }

  function changeMenu(nextKey) {
    if (!nextKey || nextKey === activeMenu) {
      return;
    }
    beginPageShift();
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const applyMenuChange = () => {
      if (nextKey !== "dashboard") {
        setWingBackdrop(randomWingBackdrop());
      }
      setActiveMenu(nextKey);
      resetPageScroll(reduceMotion);
    };
    if (!reduceMotion && document.startViewTransition) {
      document.startViewTransition(applyMenuChange);
      return;
    }
    applyMenuChange();
  }

  function handleMenuClick(event, nextKey) {
    event.currentTarget.blur();
    changeMenu(nextKey);
  }

  const navInlineStyle = compactNav ? undefined : {
    "--nav-marker-opacity": navAwake ? "0" : "1",
    opacity: navAwake ? 0.96 : 0.42,
    transform: navAwake ? "translate3d(0px, -50%, 0)" : "translate3d(calc(-100% + 30px), -50%, 0)",
    filter: navAwake ? "none" : "saturate(0.72)",
  };

  return (
    <main
      className={consoleClassName}
      aria-label="ATEE 管理控制台"
      onPointerMove={handlePointerMove}
      style={{
        "--cursor-x": pointer.x.toFixed(3),
        "--cursor-y": pointer.y.toFixed(3),
      }}
    >
      <InteractiveGothicBackdrop status={status} gateway={gateway} circuit={circuit} />
      <section className={stageClassName} aria-label="ATEE dark control stage">
        <header className="gothic-masthead">
          <div>
            <p className="gothic-kicker">ATEE / SECURITY RITUAL</p>
            <h1>ATEE Control Plane</h1>
          </div>
          <p id="statusText" className="gothic-connection" aria-hidden="true" />
        </header>

        <nav
          ref={navRef}
          className="gothic-nav"
          aria-label="Control modules"
          style={navInlineStyle}
          onPointerEnter={wakeNavigation}
          onPointerLeave={() => sleepNavigation(220)}
        >
          <button
            id="navCollapseBtn"
            type="button"
            className="gothic-nav-toggle"
            aria-label="Wake navigation"
            title="Move pointer to the left edge to wake navigation"
            onClick={wakeNavigation}
            onPointerEnter={wakeNavigation}
            onPointerLeave={() => sleepNavigation(220)}
          >
            <MenuUnfoldOutlined />
            <span>Modules</span>
          </button>
          {menuItems.map((item, index) => (
            <button
              key={item.key}
              type="button"
              className={`ant-menu-item gothic-nav-item${item.key === activeMenu ? " ant-menu-item-selected active" : ""}`}
              data-menu-id={item.key}
              onClick={(event) => handleMenuClick(event, item.key)}
              onPointerEnter={wakeNavigation}
              onPointerLeave={() => sleepNavigation(220)}
              title={item.label}
            >
              <span className="gothic-nav-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="gothic-nav-icon">{item.icon}</span>
              <span className="gothic-nav-label">{item.label}</span>
            </button>
          ))}
        </nav>

        <aside className="gothic-status-rail" aria-label="Runtime index">
          <StatusMetric label="Runtime" value={runtimeLabel} />
          <StatusMetric label="Agent" value={agentLabel} />
          <StatusMetric label="LLM" value={providerLabel(gateway.provider)} />
          <StatusMetric label="Budget" value={budgetLabel(budget)} />
          <StatusMetric label="Ledger" value={ledgerCount} />
          <StatusMetric label="Appeals" value={pendingAppeals} />
          <StatusMetric label="Circuit" value={circuit.open ? "OPEN" : "NORMAL"} danger={circuit.open} />
        </aside>

        <section className="gothic-control-strip" aria-label="Runtime controls">
          <Button id="refreshBtn" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
            Refresh
          </Button>
          <Button id="observeBtn" icon={<EyeOutlined />} onClick={() => onSetMode("observe")}>
            Observe
          </Button>
          <Popconfirm
            title="Switch to automatic mode"
            description="Automatic mode allows the backend to execute policy-approved actions. Confirm the environment is ready."
            okText="Confirm"
            cancelText="Cancel"
            onConfirm={() => onSetMode("auto")}
          >
            <Button id="autoBtn" type="primary" icon={<ThunderboltOutlined />}>
              Auto
            </Button>
          </Popconfirm>
          <Button id="degradedBtn" icon={<StopOutlined />} onClick={() => onSetMode("degraded")}>
            Degraded
          </Button>
          <Button id="readOnlyBtn" icon={<SafetyCertificateOutlined />} onClick={() => onSetMode("read_only")}>
            Read Only
          </Button>
          <Button id="pauseBtn" icon={status?.agent_paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />} onClick={onPauseResume}>
            {status?.agent_paused ? "Resume Agent" : "Pause Agent"}
          </Button>
        </section>

        <section className={`gothic-workspace gothic-workspace-${activeMenu}`} aria-label={`${activeMenuLabel} workspace`}>
          <div className="gothic-workspace-title">
            <span>{activeMenuLabel}</span>
            <strong>{activeMenu === "dashboard" ? "Operations" : activeMenuLabel}</strong>
          </div>
          {children}
        </section>
      </section>
    </main>
  );
}

function StatusMetric({ label, value, danger = false }) {
  return (
    <dl className={danger ? "gothic-status danger" : "gothic-status"}>
      <dt>{label}</dt>
      <dd>{value ?? "-"}</dd>
    </dl>
  );
}

export function GothicPageFrame({
  pageKey,
  title,
  domain,
  endpoints = [],
  children,
}) {
  const headingId = `atee-page-${pageKey}-title`;
  return (
    <section className={`gothic-page-frame page-frame-${pageKey}`} aria-labelledby={headingId}>
      <h2 id={headingId} className="sr-only">{title || pageKey}</h2>
      <div className="gothic-page-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <header className="gothic-page-head">
        <p>{domain}</p>
        <div className="gothic-route-list">
          {endpoints.map((endpoint) => (
            <span key={endpoint} className="gothic-route-chip">{endpoint}</span>
          ))}
        </div>
      </header>
      <div className="gothic-page-body">{children}</div>
    </section>
  );
}

export function InteractiveGothicBackdrop({ status, gateway = {}, circuit = {} }) {
  const particles = useMemo(
    () => Array.from({ length: PARTICLE_COUNT }, (_, index) => ({
      id: index,
      x: (index * 37) % 100,
      y: (index * 61) % 100,
      size: 2 + (index % 5),
      delay: (index % 9) * -0.7,
    })),
    [],
  );
  const orbitLines = useMemo(
    () => Array.from({ length: ORBIT_COUNT }, (_, index) => ({
      id: index,
      rotation: -32 + index * 8,
      length: 34 + index * 7,
    })),
    [],
  );
  const activeSignal = status?.runtime_mode === "auto" || circuit.open || gateway.last_ok === false;

  return (
    <div className={activeSignal ? "gothic-backdrop signal-hot" : "gothic-backdrop"} aria-hidden="true">
      <GothicFallbackBackdrop />
      <div className="gothic-figure" />
      <div className="gothic-light gothic-light-top" />
      <div className="gothic-light gothic-light-core" />
      <div className="gothic-vignette" />
      <div className="gothic-fragments">
        <span className="fragment fragment-a" />
        <span className="fragment fragment-b" />
        <span className="fragment fragment-c" />
        <span className="fragment fragment-d" />
        <span className="fragment fragment-e" />
      </div>
      <div className="gothic-risk-web">
        {orbitLines.map((item) => (
          <span
            key={item.id}
            style={{
              "--line-rotation": `${item.rotation}deg`,
              "--line-length": `${item.length}vw`,
            }}
          />
        ))}
      </div>
      <svg className="gothic-red-sigil" viewBox="0 0 520 320" role="presentation">
        <path d="M88 210 C168 126 236 120 300 166 S394 242 482 88" />
        <path d="M110 76 C208 118 280 122 330 170 S402 216 470 214" />
        <path d="M160 276 C220 194 266 168 326 168 S424 130 504 34" />
        <circle cx="326" cy="168" r="13" />
        <circle cx="258" cy="136" r="5" />
        <circle cx="386" cy="196" r="5" />
        <circle cx="470" cy="214" r="4" />
        <circle cx="504" cy="34" r="5" />
      </svg>
      <div className="gothic-particles">
        {particles.map((particle) => (
          <span
            key={particle.id}
            style={{
              left: `${particle.x}%`,
              top: `${particle.y}%`,
              width: `${particle.size}px`,
              height: `${particle.size}px`,
              animationDelay: `${particle.delay}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function GothicFallbackBackdrop() {
  return (
    <div className="gothic-fallback-backdrop">
      <span />
      <span />
      <span />
    </div>
  );
}
