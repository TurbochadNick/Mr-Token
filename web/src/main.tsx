import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Summary = {
  totalEstimatedTokens: number;
  sessions: number;
  prompts: number;
  toolCalls: number;
  estimatedSavingsRange: [number, number];
};

type Finding = {
  category: string;
  confidence: string;
  estimatedWasteTokens: number;
  savingsRange: [number, number];
  recommendedFixes: string[];
  evidence: string[];
};

type EventRow = {
  id: number;
  eventType: string;
  toolName: string | null;
  estimatedTokens: number;
  filePath: string | null;
  command: string | null;
  timestamp: string;
};

type DoctorLatest = {
  patchDir: string;
  summary: string;
  diff: string;
} | null;

type ApiData = {
  summary: Summary;
  findings: Finding[];
  events: EventRow[];
  doctorLatest: DoctorLatest;
};

type View = 'dashboard' | 'doctor';

function App() {
  const [data, setData] = useState<ApiData | null>(null);
  const [view, setView] = useState<View>('dashboard');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/all')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<ApiData>;
      })
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load audit data.');
      });
  }, []);

  const topFindings = useMemo(() => data?.findings.slice(0, 8) ?? [], [data]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local audit console</p>
          <h1>Mr Token</h1>
        </div>
        <nav className="tabs" aria-label="Views">
          <button className={view === 'dashboard' ? 'active' : ''} onClick={() => setView('dashboard')}>
            Dashboard
          </button>
          <button className={view === 'doctor' ? 'active' : ''} onClick={() => setView('doctor')}>
            Doctor
          </button>
        </nav>
      </header>

      {error ? <div className="notice">Could not load data: {error}</div> : null}
      {!data && !error ? <div className="notice">Loading local audit data...</div> : null}

      {data && view === 'dashboard' ? (
        <>
          <section className="metrics" aria-label="Audit summary">
            <Metric label="Total estimated tokens" value={formatNumber(data.summary.totalEstimatedTokens)} />
            <Metric label="Sessions" value={formatNumber(data.summary.sessions)} />
            <Metric label="Prompts" value={formatNumber(data.summary.prompts)} />
            <Metric label="Tool calls" value={formatNumber(data.summary.toolCalls)} />
            <Metric label="Estimated savings" value={formatRange(data.summary.estimatedSavingsRange)} />
          </section>

          <section className="section">
            <div className="sectionHeader">
              <h2>Findings</h2>
              <span>{topFindings.length} shown</span>
            </div>
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Confidence</th>
                    <th>Estimated waste</th>
                    <th>Recommended fixes</th>
                  </tr>
                </thead>
                <tbody>
                  {topFindings.length === 0 ? (
                    <tr>
                      <td colSpan={4}>No deterministic waste patterns detected yet.</td>
                    </tr>
                  ) : (
                    topFindings.map((finding) => (
                      <tr key={finding.category}>
                        <td>{finding.category}</td>
                        <td>{finding.confidence}</td>
                        <td>{formatNumber(finding.estimatedWasteTokens)} tokens</td>
                        <td>{finding.recommendedFixes.join(' ')}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <div className="sectionHeader">
              <h2>Event Explorer</h2>
              <span>{data.events.length} events</span>
            </div>
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>Event type</th>
                    <th>Tool</th>
                    <th>Tokens</th>
                    <th>File path / command</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {data.events.length === 0 ? (
                    <tr>
                      <td colSpan={5}>No hook events collected yet.</td>
                    </tr>
                  ) : (
                    data.events.map((event) => (
                      <tr key={event.id}>
                        <td>{event.eventType}</td>
                        <td>{event.toolName ?? '-'}</td>
                        <td>{formatNumber(event.estimatedTokens)}</td>
                        <td className="mono">{event.filePath ?? event.command ?? '-'}</td>
                        <td>{event.timestamp}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}

      {data && view === 'doctor' ? <Doctor latest={data.doctorLatest} /> : null}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric">
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function Doctor({ latest }: { latest: DoctorLatest }) {
  if (!latest) {
    return (
      <section className="section">
        <div className="sectionHeader">
          <h2>Doctor</h2>
        </div>
        <div className="notice">No patch bundle found. Run token-tithe doctor to generate proposals.</div>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="sectionHeader">
        <div>
          <h2>Latest Patch Bundle</h2>
          <p className="path">{latest.patchDir}</p>
        </div>
      </div>
      <div className="codeGrid">
        <div>
          <h3>SUMMARY.md</h3>
          <pre>{latest.summary || 'No summary found.'}</pre>
        </div>
        <div>
          <h3>patch.diff</h3>
          <pre>{latest.diff || 'No diff found.'}</pre>
        </div>
      </div>
    </section>
  );
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatRange(range: [number, number]): string {
  return `${formatNumber(range[0])}-${formatNumber(range[1])}`;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
