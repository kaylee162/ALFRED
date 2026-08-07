import type { StartupBriefingData } from "../types/startupBriefing";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getStartupBriefing(
  signal?: AbortSignal,
): Promise<StartupBriefingData> {
  const response = await fetch(`${API_BASE}/startup/briefing`, {
    signal,
    cache: "no-store",
  });

  let data: StartupBriefingData;
  try {
    data = await response.json();
  } catch {
    throw new Error("ALFRED returned an unreadable startup briefing.");
  }

  if (!response.ok) {
    throw new Error(
      (data as StartupBriefingData & { error?: string }).error ||
        "The startup briefing could not be loaded.",
    );
  }

  return data;
}
