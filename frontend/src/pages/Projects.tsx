import { Folder, Plus, Settings2 } from "lucide-react";
import type { Project } from "../types";
export function Projects({
  projects,
  selected,
  onSelect,
  onCreate,
  onEdit,
}: {
  projects: Project[];
  selected: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onEdit: (p: Project) => void;
}) {
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Projects</h1>
          <p>Manage API targets and their saved history.</p>
        </div>
        <button className="button primary" onClick={onCreate}>
          <Plus size={16} />
          New project
        </button>
      </div>
      <div className="project-list">
        <div className="section-heading">
          <h2>
            All projects <span>{projects.length}</span>
          </h2>
        </div>
        {projects.length ? (
          <div className="table-scroll">
            <table className="projects-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Target URL</th>
                  <th>Updated</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div className="project-name-cell">
                        <Folder size={18} aria-hidden="true" />
                        <div>
                          <button
                            className="project-name-button"
                            onClick={() => onSelect(p.id)}
                          >
                            {p.name}
                          </button>
                          {p.description && (
                            <p title={p.description}>{p.description}</p>
                          )}
                          {selected === p.id && (
                            <span className="project-active">
                              Current project
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <code className="project-target" title={p.base_url}>
                        {p.base_url}
                      </code>
                    </td>
                    <td className="muted">
                      {new Date(p.updated_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </td>
                    <td>
                      <div className="project-row-actions">
                        <button
                          className="button secondary small"
                          onClick={() => onSelect(p.id)}
                        >
                          Open workspace
                        </button>
                        <button
                          aria-label={`Edit ${p.name}`}
                          className="icon-button"
                          onClick={() => onEdit(p)}
                        >
                          <Settings2 size={17} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <Folder size={28} strokeWidth={1.5} />
            <h3>No projects yet</h3>
            <p>Create a project to start recording requests.</p>
            <button className="button secondary" onClick={onCreate}>
              Create a project
            </button>
          </div>
        )}
      </div>
    </>
  );
}
