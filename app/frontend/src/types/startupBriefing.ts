export type StartupSystemStatus = {
  online: boolean;
};

export type StartupBriefingAction = {
  label: string;
  command: string;
  kind: "command";
};

export type StartupBriefingData = {
  type: "startup_briefing";
  generated_at?: string;
  greeting: string;
  message: string;
  action: StartupBriefingAction | null;
  systems: Record<string, StartupSystemStatus>;
  calendar?: {
    today_count: number;
    remaining_count: number;
    events: unknown[];
  } | null;
  gmail?: {
    unread_count: number;
    unread_preview: unknown[];
  } | null;
  weather?: {
    location?: string;
    temperature?: number;
    high?: number;
    low?: number;
    rain_chance?: number;
  } | null;
};
