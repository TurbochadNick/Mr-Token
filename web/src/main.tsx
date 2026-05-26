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
  summaryPath: string;
  diffPath: string;
  summary: string;
  diff: string;
} | null;

type SetupStatus = {
  projectRoot: string;
  dbPath: string;
  databaseExists: boolean;
  eventsPath: string;
  eventsJsonlExists: boolean;
  settingsPath: string;
  claudeSettingsExists: boolean;
  hooksInstalled: boolean;
};

type DiagnosisFinding = {
  category: string;
  severity: string;
  confidence: string;
  estimatedWasteTokens: number;
  savingsRange: [number, number];
  evidence: string[];
  whyThisMatters: string;
  recommendedFixes: string[];
  patchableAction?: string;
};

const DIAGNOSIS_LABELS: Record<string, string> = {
  'Huge Tool Output': 'Exhaust Flood',
  'Repeated Instructions': 'Idle Repetition',
  'Bloated Project Context': 'Heavy Chassis',
  'Broad Prompt': 'Wide Throttle',
  'Unnecessary Full File Reads': 'Full-Tank File Reads',
  'Re-read Loop': 'Context Reburn',
  'Multi-Deliverable Prompt': 'Multi-Load Turn',
  'Late Compaction / Long Session Drift': 'Stale Load',
  'Subagent Overkill': 'Parallel Burn',
  'Style/Boilerplate Overhead': 'Cabin Noise',
  'Missing Acceptance Criteria': 'No Stop Line',
  'Premature Architecture Debate': 'Bench Racing'
};

type Diagnosis = {
  generatedAt: string;
  fuelScore: number;
  fuelRating: string;
  burnProfile: {
    usefulEstimatedTokens: number;
    suspectedWasteTokens: number;
    wastePercentage: number;
    topBurnCauses: string[];
    confidence: string;
  };
  generalDiagnosis: string;
  findings: DiagnosisFinding[];
  whatToChangeNext: string[];
};

type ApiData = {
  summary: Summary;
  findings: Finding[];
  events: EventRow[];
  doctorLatest: DoctorLatest;
  setup: SetupStatus;
  diagnosis: Diagnosis;
};

type View = 'dashboard' | 'events' | 'doctor' | 'setup';

const COMMANDS = ['token-tithe init', 'token-tithe audit', 'token-tithe doctor', 'token-tithe ui'];

function App() {
  const [data, setData] = useState<ApiData | null>(null);
  const [view, setView] = useState<View>('dashboard');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [toolFilter, setToolFilter] = useState('');

  useEffect(() => {
    void refreshData();
  }, []);

  async function refreshData(message?: string) {
    setError(null);
    const next = await fetchJson<ApiData>('/api/all');
    setData(next);
    if (message) setNotice(message);
  }

  async function postAction<T>(path: string, done: (value: T) => string | Promise<string>) {
    setError(null);
    setNotice('Working...');
    try {
      const response = await fetch(path, { method: 'POST' });
      const value = (await response.json()) as T & { ok?: boolean; error?: string };
      if (!response.ok || value.ok === false) throw new Error(value.error ?? `HTTP ${response.status}`);
      setNotice(await done(value));
      await refreshData();
    } catch (err) {
      setNotice(null);
      setError(err instanceof Error ? err.message : 'Action failed.');
    }
  }

  const topFinding = data?.findings[0] ?? null;
  const eventTypes = useMemo(() => unique(data?.events.map((event) => event.eventType) ?? []), [data]);
  const toolNames = useMemo(() => unique(data?.events.map((event) => event.toolName).filter(Boolean) as string[]), [data]);
  const filteredEvents = useMemo(() => {
    const events = data?.events ?? [];
    return events.filter((event) => {
      const eventMatch = eventTypeFilter ? event.eventType === eventTypeFilter : true;
      const toolMatch = toolFilter ? event.toolName === toolFilter : true;
      return eventMatch && toolMatch;
    });
  }, [data, eventTypeFilter, toolFilter]);

  return (
    <main className="appFrame">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Local control panel</p>
          <h1>Mr Token</h1>
        </div>
        <nav className="nav" aria-label="Views">
          {(['dashboard', 'events', 'doctor', 'setup'] as View[]).map((item) => (
            <button key={item} className={view === item ? 'active' : ''} onClick={() => setView(item)}>
              {labelView(item)}
            </button>
          ))}
        </nav>
        <p className="localOnly">Bound to localhost. Reads `.token-tithe/token-tithe.db`. No telemetry, upload, auth, or cloud backend.</p>
      </aside>

      <section className="content">
        <header className="contentHeader">
          <div>
            <h2>{labelView(view)}</h2>
            <p>{data?.setup.projectRoot ?? 'Loading project...'}</p>
          </div>
          <div className="actions">
            <button
              onClick={() =>
                void postAction<{ data: ApiData }>('/api/audit/run', (value) => {
                  setData(value.data);
                  return 'Audit recomputed from local database.';
                })
              }
            >
              Refresh Audit
            </button>
            <a className="buttonLink" href="/api/export/report.md">Export Report</a>
          </div>
        </header>

        {notice ? <div className="notice success">{notice}</div> : null}
        {error ? <div className="notice error">Error: {error}</div> : null}
        {!data && !error ? <div className="notice">Loading local audit data...</div> : null}

        {data && view === 'dashboard' ? <Dashboard data={data} topFinding={topFinding} /> : null}
        {data && view === 'events' ? (
          <Events
            events={filteredEvents}
            eventTypes={eventTypes}
            toolNames={toolNames}
            eventTypeFilter={eventTypeFilter}
            toolFilter={toolFilter}
            onEventTypeFilter={setEventTypeFilter}
            onToolFilter={setToolFilter}
          />
        ) : null}
        {data && view === 'doctor' ? (
          <Doctor
            latest={data.doctorLatest}
            onRun={() =>
              void postAction<{ result: { patchDir: string } }>('/api/doctor/run', (value) =>
                `Generated safe patch bundle: ${value.result.patchDir}`
              )
            }
          />
        ) : null}
        {data && view === 'setup' ? (
          <Setup
            setup={data.setup}
            onInit={() =>
              void postAction<{ result: { hooksChanged: boolean } }>('/api/init', (value) =>
                value.result.hooksChanged ? 'Project initialized and hooks updated.' : 'Project already initialized.'
              )
            }
          />
        ) : null}
      </section>
    </main>
  );
}

function Dashboard({ data, topFinding }: { data: ApiData; topFinding: Finding | null }) {
  return (
    <>
      <section className="gettingStarted">
        <h3>Getting Started</h3>
        <ol>
          <li>Open a project folder in terminal.</li>
          <li>Run <code>token-tithe ui</code>.</li>
          <li>Click Initialize Project if hooks are not installed.</li>
          <li>Use Claude Code normally.</li>
          <li>Refresh dashboard or Run Audit.</li>
          <li>Run Doctor to generate safe patches.</li>
        </ol>
      </section>

      <section className="metrics" aria-label="Audit summary">
        <Metric label="Fuel score" value={`${data.diagnosis.fuelScore}/100`} />
        <Metric label="Total tokens" value={formatNumber(data.summary.totalEstimatedTokens)} />
        <Metric label="Sessions" value={formatNumber(data.summary.sessions)} />
        <Metric label="Prompts" value={formatNumber(data.summary.prompts)} />
        <Metric label="Tool calls" value={formatNumber(data.summary.toolCalls)} />
        <Metric label="Estimated savings" value={formatRange(data.summary.estimatedSavingsRange)} />
      </section>

      <section className="section">
        <div className="sectionHeader">
          <h3>Fuel Diagnosis</h3>
          <span>{data.diagnosis.fuelRating}</span>
        </div>
        <article className="panel">
          <p>{data.diagnosis.generalDiagnosis}</p>
          <div className="burnGrid">
            <span>Useful: {formatNumber(data.diagnosis.burnProfile.usefulEstimatedTokens)}</span>
            <span>Waste: {formatNumber(data.diagnosis.burnProfile.suspectedWasteTokens)}</span>
            <span>Waste %: {data.diagnosis.burnProfile.wastePercentage}%</span>
            <span>Confidence: {data.diagnosis.burnProfile.confidence}</span>
          </div>
          <h4>Top Causes</h4>
          <ul>
            {data.diagnosis.burnProfile.topBurnCauses.length === 0 ? (
              <li>No major burn causes detected.</li>
            ) : (
              data.diagnosis.burnProfile.topBurnCauses.map((cause) => <li key={cause}>{diagnosisLabel(cause)}</li>)
            )}
          </ul>
        </article>
      </section>

      <section className="section">
        <div className="sectionHeader">
          <h3>Top Finding</h3>
        </div>
        {topFinding ? (
          <article className="panel">
            <div className="findingHero">
              <strong>{topFinding.category}</strong>
              <span>{topFinding.confidence} confidence</span>
            </div>
            <p>{formatNumber(topFinding.estimatedWasteTokens)} estimated waste tokens</p>
            <ul>
              {topFinding.recommendedFixes.map((fix) => (
                <li key={fix}>{fix}</li>
              ))}
            </ul>
          </article>
        ) : (
          <div className="notice">No deterministic waste patterns detected yet.</div>
        )}
      </section>

      <Findings findings={data.findings} />
      <DiagnosisCards findings={data.diagnosis.findings} next={data.diagnosis.whatToChangeNext} />
      <CommandCard />
    </>
  );
}

function DiagnosisCards({ findings, next }: { findings: DiagnosisFinding[]; next: string[] }) {
  return (
    <section className="section">
      <div className="sectionHeader">
        <h3>What To Change Next</h3>
      </div>
      <article className="panel">
        <ol>
          {next.length === 0 ? <li>No immediate changes recommended.</li> : next.map((item) => <li key={item}>{item}</li>)}
        </ol>
      </article>
      <div className="diagnosisCards">
        {findings.map((finding) => (
          <article className="panel" key={finding.category}>
            <div className="findingHero">
              <strong>{diagnosisLabel(finding.category)}</strong>
              <span>{finding.severity} / {finding.confidence}</span>
            </div>
            <p className="path">Technical category: {finding.category}</p>
            <p>{finding.whyThisMatters}</p>
            <p>{formatNumber(finding.estimatedWasteTokens)} suspected waste tokens, {formatRange(finding.savingsRange)} likely savings.</p>
            {finding.patchableAction ? <p>Patch suggestion: {finding.patchableAction}</p> : null}
            <h4>Fixes</h4>
            <ul>{finding.recommendedFixes.map((fix) => <li key={fix}>{fix}</li>)}</ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function Findings({ findings }: { findings: Finding[] }) {
  return (
    <section className="section">
      <div className="sectionHeader">
        <h3>Findings</h3>
        <span>{findings.length} categories</span>
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
            {findings.length === 0 ? (
              <tr><td colSpan={4}>No findings yet.</td></tr>
            ) : (
              findings.map((finding) => (
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
  );
}

function Events({
  events,
  eventTypes,
  toolNames,
  eventTypeFilter,
  toolFilter,
  onEventTypeFilter,
  onToolFilter
}: {
  events: EventRow[];
  eventTypes: string[];
  toolNames: string[];
  eventTypeFilter: string;
  toolFilter: string;
  onEventTypeFilter: (value: string) => void;
  onToolFilter: (value: string) => void;
}) {
  return (
    <section className="section flush">
      <div className="filters">
        <label>
          Event type
          <select value={eventTypeFilter} onChange={(event) => onEventTypeFilter(event.target.value)}>
            <option value="">All events</option>
            {eventTypes.map((eventType) => <option key={eventType}>{eventType}</option>)}
          </select>
        </label>
        <label>
          Tool name
          <select value={toolFilter} onChange={(event) => onToolFilter(event.target.value)}>
            <option value="">All tools</option>
            {toolNames.map((toolName) => <option key={toolName}>{toolName}</option>)}
          </select>
        </label>
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
            {events.length === 0 ? (
              <tr><td colSpan={5}>No events match the selected filters.</td></tr>
            ) : (
              events.map((event) => (
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
  );
}

function Doctor({ latest, onRun }: { latest: DoctorLatest; onRun: () => void }) {
  return (
    <section className="section flush">
      <div className="sectionHeader">
        <div>
          <h3>Doctor</h3>
          <p>Generates safe patch proposals only. Nothing is applied automatically.</p>
        </div>
        <div className="actions">
          <button onClick={onRun}>Run Doctor</button>
          <button onClick={() => window.location.reload()}>View Latest Patch</button>
        </div>
      </div>
      {latest ? (
        <>
          <article className="panel">
            <strong>Latest patch bundle</strong>
            <p className="path">{latest.patchDir}</p>
            <p className="path">Summary: {latest.summaryPath}</p>
            <p className="path">Diff: {latest.diffPath}</p>
          </article>
          <article className="panel">
            <strong>Patch suggestions are diagnosis-driven</strong>
            <p>Doctor proposals target project context, repeated workflows, broad prompts, tool-output caps, and acceptance-criteria templates when those burn patterns are detected.</p>
          </article>
          <div className="codeGrid">
            <div>
              <h4>SUMMARY.md</h4>
              <pre>{latest.summary || 'No summary found.'}</pre>
            </div>
            <div>
              <h4>patch.diff</h4>
              <pre>{latest.diff || 'No diff found.'}</pre>
            </div>
          </div>
        </>
      ) : (
        <div className="notice">No patch bundle found. Run Doctor to generate proposals.</div>
      )}
    </section>
  );
}

function Setup({ setup, onInit }: { setup: SetupStatus; onInit: () => void }) {
  return (
    <>
      <section className="section flush">
        <div className="sectionHeader">
          <h3>Setup</h3>
          <button onClick={onInit}>Initialize Project</button>
        </div>
        <div className="statusGrid">
          <Status label="Project root" value={setup.projectRoot} />
          <Status label="Database" value={setup.dbPath} ok={setup.databaseExists} />
          <Status label="Events JSONL" value={setup.eventsPath} ok={setup.eventsJsonlExists} />
          <Status label="Claude settings" value={setup.settingsPath} ok={setup.claudeSettingsExists} />
          <Status label="Hooks installed" value={setup.hooksInstalled ? 'yes' : 'no'} ok={setup.hooksInstalled} />
        </div>
      </section>
      <CommandCard />
    </>
  );
}

function CommandCard() {
  const commandText = COMMANDS.join('\n');

  async function copyCommands() {
    await navigator.clipboard.writeText(commandText);
  }

  return (
    <section className="section">
      <div className="sectionHeader">
        <h3>Copy Commands</h3>
        <button onClick={() => void copyCommands()}>Copy</button>
      </div>
      <pre className="commands">{commandText}</pre>
    </section>
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

function Status({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <article className="statusItem">
      <span>{label}</span>
      <strong className={ok === undefined ? '' : ok ? 'ok' : 'bad'}>{ok === undefined ? '' : ok ? 'ready' : 'missing'}</strong>
      <p>{value}</p>
    </article>
  );
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function labelView(view: View): string {
  return view[0].toUpperCase() + view.slice(1);
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatRange(range: [number, number]): string {
  return `${formatNumber(range[0])}-${formatNumber(range[1])}`;
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function diagnosisLabel(category: string): string {
  return DIAGNOSIS_LABELS[category] ?? category;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
