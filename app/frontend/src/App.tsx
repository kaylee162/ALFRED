import { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  FolderOpen,
  Radio,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
} from "lucide-react";
import "./App.css";

function ClockPanel() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="panel-block clock-panel">
      <p className="panel-label">local time</p>
      <div className="digital-time">
        {now.toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit",
          hour12: true,
        })}
      </div>
      <div className="digital-date">
        {now.toLocaleDateString([], {
          weekday: "long",
          month: "long",
          day: "numeric",
          year: "numeric",
        })}
      </div>
    </div>
  );
}

function App() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("Systems online. Awaiting command.");

  async function submitCommand() {
    if (!command.trim()) return;

    setResponse("Processing command...");

    const res = await fetch("http://localhost:8000/command", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ command }),
    });

    const data = await res.json();
    setResponse(data.response);
    setCommand("");
  }

  return (
    <main className="alfred-shell">
      <div className="grid-overlay" />
      <div className="scanline" />

      <section className="hud">
        <aside className="side-panel left-panel">
          <div className="panel-block">
            <p className="panel-label">core status</p>
            <div className="status-row">
              <Cpu size={18} />
              <span>local backend active</span>
            </div>
            <div className="status-row">
              <ShieldCheck size={18} />
              <span>confirmations enabled</span>
            </div>
            <div className="status-row">
              <Radio size={18} />
              <span>voice offline</span>
            </div>
          </div>

          <div className="panel-block">
            <p className="panel-label">available tools</p>
            <div className="tool-chip">
              <FolderOpen size={16} />
              <span>project launcher</span>
            </div>
            <div className="tool-chip disabled">file search soon</div>
            <div className="tool-chip disabled">notes soon</div>
          </div>
        </aside>

        <section className="center-console">
          <div className="orbit-system">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="core">
              <Sparkles size={42} />
            </div>
          </div>

          <div className="title-group">
            <h1>A.L.F.R.E.D.</h1>
            <p className="subtitle">
            Adaptive Learning Framework for Responsive Executive Decisions V.2
            </p>
          </div>

          <div className="command-console">
            <div className="console-header">
              <Terminal size={18} />
              <span>command input</span>
            </div>

            <div className="command-input-row">
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitCommand();
                }}
                placeholder='Try: "Open TrailTales"'
              />
              <button onClick={submitCommand} aria-label="Send command">
                <Send size={18} />
              </button>
            </div>
          </div>

          <div className="response-console">
            <p className="panel-label">system response</p>
            <p>{response}</p>
          </div>
        </section>

        <aside className="side-panel right-panel">
          <ClockPanel />

          <div className="panel-block">
            <p className="panel-label">system load</p>

            <div className="radial-stat">
              <div className="radial-ring">
                <span>24%</span>
              </div>
              <p>assistant readiness</p>
            </div>

            <div className="activity-meter">
              <Activity size={18} />
              <span>agent idle · monitoring input</span>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

export default App;