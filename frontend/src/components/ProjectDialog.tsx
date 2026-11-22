import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { api, errorMessage } from "../services/api";
import type { Project } from "../types";
export function ProjectDialog({
  project,
  defaultTarget = "",
  onClose,
  onSaved,
}: {
  project?: Project;
  defaultTarget?: string;
  onClose: () => void;
  onSaved: (project: Project) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(project?.name ?? ""),
    [url, setUrl] = useState(project?.base_url ?? defaultTarget),
    [description, setDescription] = useState(project?.description ?? ""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSaved(
        await (project
          ? api.updateProject(project.id, { name, base_url: url, description })
          : api.createProject({ name, base_url: url, description })),
      );
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };
  return (
    <dialog ref={dialog} className="project-dialog" onCancel={onClose}>
      <form onSubmit={submit}>
        <div className="flex items-center justify-between">
          <span className="eyebrow">Project settings</span>
          <button
            type="button"
            aria-label="Close dialog"
            className="icon-button"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <h2>{project ? "Project settings" : "Create a project"}</h2>
        <p className="muted mb-6">Configure the API target for this project.</p>
        <label>
          Project name
          <input
            autoFocus
            required
            maxLength={120}
            placeholder="e.g. Commerce API"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Target base URL
          <input
            required
            type="url"
            maxLength={2048}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <p className="field-note">
          Use an explicitly approved target. The sample default follows your
          backend configuration.
        </p>
        <label>
          Description <span className="muted">(optional)</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}
        <div className="dialog-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button disabled={busy} className="button primary">
            {busy ? "Saving…" : project ? "Save project" : "Create project"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
