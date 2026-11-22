import { useEffect, useState } from "react";
import {
  Box,
  ChevronRight,
  Code2,
  Folder,
  GitCompareArrows,
  History,
  ShieldCheck,
  FileDown,
  Plus,
  RotateCw,
  Terminal,
} from "lucide-react";
import {
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { api, errorMessage } from "./services/api";
import type { Project } from "./types";
import { Workspace } from "./pages/Workspace";
import { Projects } from "./pages/Projects";
import { Recordings, RecordingDetail } from "./pages/Recordings";
import { ReplayWorkspace } from "./pages/ReplayWorkspace";
import { ReplayHistory } from "./pages/ReplayHistory";
import { ReplaySessionDetails } from "./pages/ReplaySessionDetails";
import { Compatibility } from "./pages/Compatibility";
import { Comparisons } from "./pages/Comparisons";
import { ComparisonDetails } from "./pages/ComparisonDetails";
import { ProjectDialog } from "./components/ProjectDialog";
export default function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [selected, setSelected] = useState(
      () => localStorage.getItem("atm-project") || "",
    ),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [dialog, setDialog] = useState<Project | "new" | null>(null),
    [healthy, setHealthy] = useState(false),
    [creating, setCreating] = useState(false),
    [sampleTarget, setSampleTarget] = useState<string | null>(null);
  const navigate = useNavigate(),
    location = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [location.pathname]);
  const project = projects.find((p) => p.id === selected) ?? projects[0];
  const load = () => {
    setLoading(true);
    api
      .projects()
      .then((p) => {
        setProjects(p);
        setError("");
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  useEffect(() => {
    let live = true;
    api
      .config()
      .then((c) => {
        if (live) setSampleTarget(c.sample_v1_base_url);
      })
      .catch(() => {
        if (live) setSampleTarget(null);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (project) localStorage.setItem("atm-project", project.id);
  }, [project?.id]);
  useEffect(() => {
    let active = true;
    const check = () =>
      api
        .health()
        .then((r) => {
          if (active) setHealthy(r.status === "ok");
        })
        .catch(() => {
          if (active) setHealthy(false);
        });
    void check();
    const timer = setInterval(check, 30000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  const select = (id: string) => {
    setSelected(id);
    navigate(
      location.pathname.startsWith("/reports")
        ? "/reports"
        : location.pathname.startsWith("/compatibility")
          ? "/compatibility"
          : location.pathname.startsWith("/comparisons")
            ? "/comparisons"
            : location.pathname.startsWith("/replay")
              ? "/replay"
              : "/",
    );
  };
  const saved = (p: Project) => {
    setProjects((items) => [p, ...items.filter((x) => x.id !== p.id)]);
    setSelected(p.id);
    setDialog(null);
    navigate("/");
  };
  const sample = async () => {
    if (!sampleTarget) {
      setError(
        "No allowed sample target is configured. Create a project using an approved target URL.",
      );
      return;
    }
    setCreating(true);
    setError("");
    try {
      saved(
        await api.createProject({
          name: "Sample Commerce API",
          base_url: sampleTarget || "",
          description:
            "Deterministic users, products, and an echo endpoint for your first captures.",
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCreating(false);
    }
  };
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("project");
    if (id && projects.some((p) => p.id === id)) setSelected(id);
  }, [location.search, projects]);
  const section = location.pathname.startsWith("/reports")
    ? "Reports"
    : location.pathname.startsWith("/projects")
      ? "Projects"
      : location.pathname.startsWith("/recordings")
        ? "Recordings"
        : location.pathname.startsWith("/replay")
          ? "Replay"
          : location.pathname.startsWith("/comparisons")
            ? "Comparisons"
            : location.pathname.startsWith("/compatibility")
              ? "Compatibility"
              : "Workspace";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <History size={24} strokeWidth={1.7} aria-hidden="true" />
          <span className="brand-name">API TimeMachine</span>
        </NavLink>
        <span className="workspace-label">Project</span>
        <div className="project-selector">
          <span className="selector-icon">
            <Box size={17} />
          </span>
          <select
            aria-label="Selected project"
            value={project?.id || ""}
            onChange={(e) => select(e.target.value)}
          >
            {!projects.length && <option value="">No project selected</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <nav aria-label="Main navigation">
          <span className="nav-label">Workspace</span>
          <NavLink to="/" end>
            <Terminal size={17} />
            Workspace
          </NavLink>
          <NavLink to="/projects">
            <Folder size={17} />
            Projects<span className="nav-count">{projects.length}</span>
          </NavLink>
          <NavLink to="/recordings">
            <History size={17} />
            Recordings
          </NavLink>
          <NavLink to="/replay">
            <RotateCw size={17} />
            Replay
          </NavLink>
          <span className="nav-label">Analysis</span>
          <NavLink to="/comparisons">
            <GitCompareArrows size={17} />
            Comparisons
          </NavLink>
          <NavLink to="/compatibility">
            <ShieldCheck size={17} />
            Compatibility
          </NavLink>
          <NavLink to="/reports">
            <FileDown size={17} />
            Reports
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-footer">
            <Code2 size={14} />
            <span>Local development</span>
            <span className="version">v1.0</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>{project?.name || "Personal workspace"}</span>
            <ChevronRight size={13} />
            <strong>{section}</strong>
          </div>
          <div className="topbar-status">
            <span className={`dot ${healthy ? "" : "offline"}`} />
            {healthy ? "Backend connected" : "Backend unavailable"}
          </div>
          <button
            className="button secondary small"
            onClick={() => setDialog("new")}
          >
            <Plus size={14} />
            New project
          </button>
        </header>
        <main>
          {error && (
            <div className="error-box mb-5" role="alert">
              {error}
              <button className="text-button ml-auto" onClick={load}>
                Retry
              </button>
            </div>
          )}
          {loading ? (
            <div className="empty-state">
              <span className="spinner" />
              <p>Opening your workspace…</p>
            </div>
          ) : (
            <Routes>
              <Route
                path="/reports"
                element={
                  project ? (
                    <Compatibility
                      key={project.id}
                      project={project}
                      reportsOnly
                    />
                  ) : (
                    <div className="empty-state">
                      Create a project to generate reports.
                    </div>
                  )
                }
              />
              <Route
                path="/compatibility"
                element={
                  project ? (
                    <Compatibility key={project.id} project={project} />
                  ) : (
                    <div className="empty-state">
                      Create a project to assess compatibility.
                    </div>
                  )
                }
              />
              <Route
                path="/comparisons/:id"
                element={<ComparisonDetails onProject={setSelected} />}
              />
              <Route
                path="/comparisons"
                element={
                  project ? (
                    <Comparisons key={project.id} project={project} />
                  ) : (
                    <Welcome
                      onCreate={() => setDialog("new")}
                      onSample={sample}
                      busy={creating}
                    />
                  )
                }
              />

              <Route
                path="/replay/sessions/:id"
                element={<ReplaySessionDetails onProject={setSelected} />}
              />
              <Route
                path="/replay/history"
                element={
                  project ? (
                    <ReplayHistory key={project.id} project={project} />
                  ) : (
                    <Welcome
                      onCreate={() => setDialog("new")}
                      onSample={sample}
                      busy={creating}
                    />
                  )
                }
              />
              <Route
                path="/replay"
                element={
                  project ? (
                    <ReplayWorkspace key={project.id} project={project} />
                  ) : (
                    <Welcome
                      onCreate={() => setDialog("new")}
                      onSample={sample}
                      busy={creating}
                    />
                  )
                }
              />
              <Route
                path="/projects"
                element={
                  <Projects
                    projects={projects}
                    selected={project?.id || ""}
                    onSelect={select}
                    onCreate={() => setDialog("new")}
                    onEdit={setDialog}
                  />
                }
              />
              <Route
                path="/recordings/:id"
                element={<RecordingDetail onProject={setSelected} />}
              />
              <Route
                path="/recordings"
                element={
                  project ? (
                    <Recordings key={project.id} project={project} />
                  ) : (
                    <Welcome
                      onCreate={() => setDialog("new")}
                      onSample={sample}
                      busy={creating}
                    />
                  )
                }
              />
              <Route
                path="/"
                element={
                  project ? (
                    <Workspace
                      key={`${project.id}:${project.updated_at}`}
                      project={project}
                    />
                  ) : (
                    <Welcome
                      onCreate={() => setDialog("new")}
                      onSample={sample}
                      busy={creating}
                    />
                  )
                }
              />
              <Route
                path="*"
                element={
                  <div className="empty-state">
                    <h1>Page not found</h1>
                    <NavLink to="/">Back to workspace</NavLink>
                  </div>
                }
              />
            </Routes>
          )}
        </main>
      </div>
      {dialog && (
        <ProjectDialog
          project={dialog === "new" ? undefined : dialog}
          defaultTarget={sampleTarget || ""}
          onClose={() => setDialog(null)}
          onSaved={saved}
        />
      )}
    </div>
  );
}
function Welcome({
  onCreate,
  onSample,
  busy,
}: {
  onCreate: () => void;
  onSample: () => void;
  busy: boolean;
}) {
  return (
    <div className="welcome">
      <History size={32} strokeWidth={1.5} aria-hidden="true" />
      <h1>Set up your API workspace</h1>
      <p>
        Record requests, replay them against another version, and review what
        changed.
      </p>
      <div className="welcome-actions">
        <button className="button primary" disabled={busy} onClick={onSample}>
          {busy ? "Creating…" : "Start with the sample API"}
        </button>
        <button className="button secondary" onClick={onCreate}>
          Create your own project
        </button>
      </div>
      <div className="welcome-guide">
        <h2>A workspace for API regression testing</h2>
        <p>
          Start with the included sample API or configure an approved target.
          Requests are saved automatically, and replay keeps the original
          response intact.
        </p>
        <div>
          <Terminal size={18} />
          <span>
            <strong>Record</strong>Save a reference response.
          </span>
        </div>
        <div>
          <GitCompareArrows size={18} />
          <span>
            <strong>Compare</strong>Inspect changes across versions.
          </span>
        </div>
        <div>
          <FileDown size={18} />
          <span>
            <strong>Report</strong>Export findings with their evidence.
          </span>
        </div>
      </div>
    </div>
  );
}
