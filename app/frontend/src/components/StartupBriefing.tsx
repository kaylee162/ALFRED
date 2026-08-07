import { Activity, ArrowRight, Loader2, RefreshCw } from "lucide-react";

import type { StartupBriefingData } from "../types/startupBriefing";
import "./StartupBriefing.css";

type StartupBriefingProps = {
  briefing: StartupBriefingData | null;
  loading: boolean;
  error?: string;
  onAction: (command: string) => void;
  onRefresh: () => void;
};

export function StartupBriefing({
  briefing,
  loading,
  error,
  onAction,
  onRefresh,
}: StartupBriefingProps) {
  if (loading) {
    return (
      <section className="startup-briefing startup-briefing-loading">
        <Loader2 size={18} className="startup-briefing-spinner" />
        <span>Compiling your status briefing</span>
      </section>
    );
  }

  if (error && !briefing) {
    return (
      <section className="startup-briefing startup-briefing-error">
        <div>
          <p className="startup-briefing-kicker">briefing unavailable</p>
          <p>{error}</p>
        </div>
        <button type="button" onClick={onRefresh}>
          <RefreshCw size={16} />
          Retry
        </button>
      </section>
    );
  }

  if (!briefing) return null;

  const systems = Object.values(briefing.systems || {});
  const onlineCount = systems.filter((system) => system.online).length;

  return (
    <section className="startup-briefing">
      <div className="startup-briefing-heading">
        <div className="startup-briefing-icon">
          <Activity size={20} />
        </div>
        <div>
          <p className="startup-briefing-kicker">startup briefing</p>
          <h2>{briefing.greeting}, Kaylee.</h2>
        </div>
        <span className="startup-briefing-status">
          {onlineCount}/{systems.length} systems
        </span>
      </div>

      <p className="startup-briefing-message">{briefing.message}</p>

      <div className="startup-briefing-actions">
        {briefing.action && (
          <button
            type="button"
            className="startup-briefing-primary"
            onClick={() => onAction(briefing.action!.command)}
          >
            {briefing.action.label}
            <ArrowRight size={16} />
          </button>
        )}

        <button
          type="button"
          className="startup-briefing-secondary"
          onClick={onRefresh}
          aria-label="Refresh startup briefing"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
    </section>
  );
}
