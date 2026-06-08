import { useState, useEffect, useCallback } from "react";
import { api, ProjectRecord as ApiProject } from "./api";

const LOCAL_STORAGE_KEY = "synkraken.console.v20.projects";

export type ProjectRecord = {
  project_id: string;
  title: string;
  purpose: string;
  status: string;
  room_id?: string;
  mission_id?: string;
  outcome_ids: string[];
  assignment_ids: string[];
  knowledge_ids: string[];
  worker_ids: string[];
  created_at: string;
  updated_at: string;
  local?: boolean;
};

function apiToProject(apiProject: ApiProject): ProjectRecord {
  return {
    project_id: apiProject.project_id,
    title: apiProject.name,
    purpose: apiProject.description,
    status: apiProject.status,
    room_id: undefined,
    mission_id: undefined,
    outcome_ids: [],
    assignment_ids: [],
    knowledge_ids: [],
    worker_ids: [],
    created_at: apiProject.created_at,
    updated_at: apiProject.updated_at,
    local: false,
  };
}

function readStoredProjects(): ProjectRecord[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_STORAGE_KEY) || "[]") as ProjectRecord[];
  } catch {
    return [];
  }
}

function writeStoredProjects(projects: ProjectRecord[]): void {
  localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(projects));
}

export function useProjects() {
  const [apiProjects, setApiProjects] = useState<ProjectRecord[]>([]);
  const [storedProjects, setStoredProjects] = useState<ProjectRecord[]>(() => readStoredProjects());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getProjects();
      const loaded = (response.projects || []).map(apiToProject);
      setApiProjects(loaded);

      // Migration: if API returns empty but localStorage has projects, push them to API
      const local = readStoredProjects();
      if (loaded.length === 0 && local.length > 0) {
        for (const project of local) {
          try {
            await api.createProject({
              name: project.title,
              description: project.purpose,
              status: project.status,
              project_id: project.project_id,
            });
          } catch {
            // Best effort migration
          }
        }
        // Reload after migration
        const reloaded = await api.getProjects();
        setApiProjects((reloaded.projects || []).map(apiToProject));
        // Clear localStorage now that API is source of truth
        writeStoredProjects([]);
        setStoredProjects([]);
      } else if (loaded.length > 0 && local.length > 0) {
        // Clear stale localStorage when API has data
        writeStoredProjects([]);
        setStoredProjects([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
      // Fall back to localStorage on API failure
      const local = readStoredProjects();
      setStoredProjects(local);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const createProject = useCallback(
    async (title: string, purpose: string): Promise<ProjectRecord | null> => {
      const now = new Date().toISOString();
      const roomId = title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || `project-${Date.now()}`;
      const project: ProjectRecord = {
        project_id: `local-${roomId}`,
        title,
        purpose,
        status: "active",
        room_id: roomId,
        mission_id: undefined,
        outcome_ids: [],
        assignment_ids: [],
        knowledge_ids: [],
        worker_ids: [],
        created_at: now,
        updated_at: now,
        local: true,
      };

      try {
        const apiProject = await api.createProject({
          name: title,
          description: purpose,
          status: "active",
        });
        const created = apiToProject(apiProject);
        created.room_id = roomId;
        created.local = false;
        setApiProjects((prev) => [created, ...prev]);
        return created;
      } catch {
        // Fall back to local storage if API fails
        const nextStored = [project, ...storedProjects.filter((p) => p.project_id !== project.project_id)];
        setStoredProjects(nextStored);
        writeStoredProjects(nextStored);
        setApiProjects((prev) => [project, ...prev]);
        return project;
      }
    },
    [storedProjects],
  );

  const updateProject = useCallback(
    async (projectId: string, updates: { title?: string; purpose?: string; status?: string }): Promise<void> => {
      const title = updates.title;
      const purpose = updates.purpose;
      const status = updates.status;

      // Update in API
      try {
        if (title || purpose || status) {
          await api.updateProject(projectId, {
            ...(title ? { name: title } : {}),
            ...(purpose ? { description: purpose } : {}),
            ...(status ? { status } : {}),
          });
        }
      } catch {
        // Continue with local update even if API fails
      }

      // Update local state
      setApiProjects((prev) =>
        prev.map((p) =>
          p.project_id === projectId
            ? {
                ...p,
                ...(title ? { title } : {}),
                ...(purpose ? { purpose } : {}),
                ...(status ? { status } : {}),
                updated_at: new Date().toISOString(),
              }
            : p,
        ),
      );
      setStoredProjects((prev) =>
        prev.map((p) =>
          p.project_id === projectId
            ? {
                ...p,
                ...(title ? { title } : {}),
                ...(purpose ? { purpose } : {}),
                ...(status ? { status } : {}),
                updated_at: new Date().toISOString(),
              }
            : p,
        ),
      );
      writeStoredProjects(storedProjects);
    },
    [storedProjects],
  );

  const deleteProject = useCallback(
    async (projectId: string): Promise<void> => {
      try {
        await api.deleteProject(projectId);
      } catch {
        // Continue with local delete even if API fails
      }

      setApiProjects((prev) => prev.filter((p) => p.project_id !== projectId));
      setStoredProjects((prev) => {
        const next = prev.filter((p) => p.project_id !== projectId);
        writeStoredProjects(next);
        return next;
      });
    },
    [],
  );

  return {
    apiProjects,
    storedProjects,
    loading,
    error,
    createProject,
    updateProject,
    deleteProject,
    refreshProjects: loadProjects,
  };
}
