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

type TokenFlowSegment = {
  key: 'prompts' | 'tools' | 'outputs' | 'stops';
  label: string;
  tokens: number;
  percent: number;
};

type DashboardInsights = {
  eventCount: number;
  lastEventTime: string | null;
  mostCommonTool: string | null;
  sessionCount: number;
  tokenFlow: TokenFlowSegment[];
};

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
        <BrandLockup />
        <nav className="nav" aria-label="Views">
          {(['dashboard', 'events', 'doctor', 'setup'] as View[]).map((item) => (
            <button key={item} className={view === item ? 'active' : ''} onClick={() => setView(item)}>
              {labelView(item)}
            </button>
          ))}
        </nav>
        <div className="sidebarFooter">
          <span className="localBadge">Localhost only</span>
          <p className="localOnly">Reads `.token-tithe/token-tithe.db`. No telemetry, upload, auth, or cloud backend.</p>
        </div>
      </aside>

      <section className="content">
        <header className="contentHeader">
          <div>
            <h2>{labelView(view)}</h2>
            <p className="projectRoot">{data?.setup.projectRoot ?? 'Loading project...'}</p>
          </div>
          <div className="actions">
            <button
              className="primaryAction"
              onClick={() =>
                void postAction<{ data: ApiData }>('/api/audit/run', (value) => {
                  setData(value.data);
                  return 'Audit recomputed from local database.';
                })
              }
            >
              Refresh Audit
            </button>
            <a className="buttonLink secondaryAction" href="/api/export/report.md">Export Report</a>
          </div>
        </header>

        {notice ? <div className="notice success">{notice}</div> : null}
        {error ? <div className="notice error">Error: {error}</div> : null}
        {!data && !error ? <div className="notice">Loading local audit data...</div> : null}

        {data && view === 'dashboard' ? (
          <Dashboard
            data={data}
            topFinding={topFinding}
            onRunAudit={() =>
              void postAction<{ data: ApiData }>('/api/audit/run', (value) => {
                setData(value.data);
                return 'Audit recomputed from local database.';
              })
            }
            onRunDoctor={() =>
              void postAction<{ result: { patchDir: string } }>('/api/doctor/run', (value) =>
                `Generated safe patch bundle: ${value.result.patchDir}`
              )
            }
            onViewEvents={() => setView('events')}
          />
        ) : null}
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

function BrandLockup() {
  return (
    <div className="brandLockup" aria-label="Mr Token">
      <div className="logoMark" aria-hidden="true">
        <span>MT</span>
      </div>
      <div>
        <p className="eyebrow">Local fuel regulator</p>
        <h1>Mr Token</h1>
      </div>
    </div>
  );
}

function Dashboard({
  data,
  topFinding,
  onRunAudit,
  onRunDoctor,
  onViewEvents
}: {
  data: ApiData;
  topFinding: Finding | null;
  onRunAudit: () => void;
  onRunDoctor: () => void;
  onViewEvents: () => void;
}) {
  const dashboard = getDashboardInsights(data);

  return (
    <div className="dashboard">
      <section className="missionHero">
        <div className="heroCopy">
          <div className="heroBadges">
            <StatusBadge label="Local-only" tone="success" />
            <StatusBadge label="Claude Code" />
          </div>
          <p className="eyebrow">Session intelligence</p>
          <h2>Mission Brief</h2>
          <p>Local Claude Code usage intelligence for this project.</p>
          <span className="projectPill mono">{data.setup.projectRoot}</span>
        </div>
        <div className="heroPanel">
          <span className="heroPanelLabel">Fuel Score</span>
          <strong>{data.diagnosis.fuelScore}</strong>
          <span>{data.diagnosis.fuelRating}</span>
          <div className="heroActions">
            <button className="primaryAction" onClick={onRunAudit}>Run Audit</button>
            <button className="secondaryAction" onClick={onRunDoctor}>Run Doctor</button>
          </div>
        </div>
      </section>

      <section className="dashboardMetrics" aria-label="Audit summary">
        <MetricCard icon="TK" label="Total Estimated Tokens" value={formatNumber(data.summary.totalEstimatedTokens)} helper="Captured local burn across prompts, tools, and outputs." />
        <MetricCard icon="SS" label="Sessions" value={formatNumber(data.summary.sessions)} helper="Distinct Claude Code sessions in the ledger." />
        <MetricCard icon="PR" label="Prompts" value={formatNumber(data.summary.prompts)} helper="User prompt submissions available for inspection." />
        <MetricCard icon="TL" label="Tool Calls" value={formatNumber(data.summary.toolCalls)} helper="Observed tool activity and command execution." />
        <MetricCard icon="SV" label="Estimated Savings" value={hasSavings(data.summary.estimatedSavingsRange) ? formatRange(data.summary.estimatedSavingsRange) : 'None yet'} helper="Likely recoverable burn from deterministic findings." />
      </section>

      <section className="dashboardGrid">
        <TopTokenLeak finding={topFinding} />
        <ActivityStrip insights={dashboard} setup={data.setup} />
      </section>

      <section className="section">
        <div className="sectionHeader dashboardSectionHeader">
          <div>
            <h3>Token Flow</h3>
            <p>Where the local ledger saw burn in this project.</p>
          </div>
          <span className="ratingPill">{data.diagnosis.burnProfile.confidence} confidence</span>
        </div>
        <TokenFlowBar segments={dashboard.tokenFlow} />
      </section>

      <section className="dashboardTwoColumn">
        <FindingsPreview findings={data.findings} onViewEvents={onViewEvents} />
        <FuelDiagnosisPanel data={data} />
      </section>
    </div>
  );
}

function MetricCard({ icon, label, value, helper }: { icon: string; label: string; value: string; helper: string }) {
  return (
    <article className="dashboardMetric" tabIndex={0}>
      <div className="metricTopline">
        <span className="metricIcon">{icon}</span>
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      <p>{helper}</p>
    </article>
  );
}

function StatusBadge({ label, tone }: { label: string; tone?: 'success' }) {
  return <span className={`statusBadge ${tone === 'success' ? 'statusBadgeSuccess' : ''}`}>{label}</span>;
}

function TopTokenLeak({ finding }: { finding: Finding | null }) {
  return (
    <article className="tokenLeakCard">
      <div className="sectionHeader dashboardSectionHeader">
        <div>
          <p className="eyebrow">Top Waste</p>
          <h3>Top Token Leak</h3>
        </div>
        {finding ? <span className="chip">{finding.confidence} confidence</span> : null}
      </div>
      {finding ? (
        <>
          <strong className="leakCategory">{finding.category}</strong>
          <div className="leakStats">
            <span><b>{formatNumber(finding.estimatedWasteTokens)}</b> waste tokens</span>
            <span><b>{formatRange(finding.savingsRange)}</b> savings range</span>
          </div>
          <ul className="fixList">
            {finding.recommendedFixes.slice(0, 3).map((fix) => <li key={fix}>{fix}</li>)}
          </ul>
        </>
      ) : (
        <EmptyState
          title="No major leaks detected yet."
          body="Run a longer Claude Code session to build a richer profile, then run audit again."
          steps={['Initialize project', 'Use Claude Code normally', 'Run Audit']}
        />
      )}
    </article>
  );
}

function ActivityStrip({ insights, setup }: { insights: DashboardInsights; setup: SetupStatus }) {
  return (
    <article className="activityCard">
      <div className="sectionHeader dashboardSectionHeader">
        <div>
          <p className="eyebrow">Local audit</p>
          <h3>Activity Strip</h3>
        </div>
      </div>
      <div className="activityGrid">
        <ActivityItem label="Recent events" value={formatNumber(insights.eventCount)} />
        <ActivityItem label="Last capture" value={insights.lastEventTime ?? 'No events yet'} />
        <ActivityItem label="Common tool" value={insights.mostCommonTool ?? 'No tool data'} />
        <ActivityItem label="Sessions" value={formatNumber(insights.sessionCount)} />
        <ActivityItem label="Database" value={setup.databaseExists ? 'Ready' : 'Missing'} ok={setup.databaseExists} />
      </div>
    </article>
  );
}

function ActivityItem({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="activityItem">
      <span>{label}</span>
      <strong className={ok === undefined ? '' : ok ? 'okText' : 'badText'}>{value}</strong>
    </div>
  );
}

function TokenFlowBar({ segments }: { segments: TokenFlowSegment[] }) {
  const total = segments.reduce((sum, segment) => sum + segment.tokens, 0);

  return (
    <article className="tokenFlowCard">
      {total === 0 ? (
        <EmptyState
          title="No token flow yet."
          body="Initialize the project, use Claude Code normally, then run audit to populate the ledger."
          steps={['Initialize project', 'Use Claude Code', 'Run Audit']}
        />
      ) : (
        <>
          <div className="flowBar" aria-label="Token flow by event type">
            {segments.map((segment) => (
              <span
                key={segment.label}
                className={`flowSegment flow-${segment.key}`}
                style={{ width: `${Math.max(segment.percent, 2)}%` }}
                title={`${segment.label}: ${formatNumber(segment.tokens)} tokens`}
              />
            ))}
          </div>
          <div className="flowLegend">
            {segments.map((segment) => (
              <div key={segment.label}>
                <span className={`legendDot flow-${segment.key}`} />
                <div>
                  <strong>{segment.label}</strong>
                  <p>{formatNumber(segment.tokens)} tokens · {segment.percent}%</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </article>
  );
}

function FindingsPreview({ findings, onViewEvents }: { findings: Finding[]; onViewEvents: () => void }) {
  return (
    <section className="previewPanel">
      <div className="sectionHeader dashboardSectionHeader">
        <div>
          <p className="eyebrow">Context hygiene</p>
          <h3>Findings Preview</h3>
        </div>
        <button className="secondaryAction compactButton" onClick={onViewEvents}>View Events</button>
      </div>
      {findings.length === 0 ? (
        <EmptyState
          title="No findings yet."
          body="Mr Token needs captured Claude Code activity before it can identify token leaks."
          steps={['Initialize project', 'Use Claude Code normally', 'Run Audit']}
        />
      ) : (
        <div className="findingPreviewList">
          {findings.slice(0, 3).map((finding) => (
            <article className="findingPreviewCard" key={finding.category}>
              <div>
                <strong>{finding.category}</strong>
                <p>{finding.recommendedFixes[0] ?? 'Tighten the prompt and rerun the audit.'}</p>
              </div>
              <div className="findingPreviewMeta">
                <span className="chip subtle">{finding.confidence}</span>
                <b>{formatNumber(finding.estimatedWasteTokens)}</b>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function FuelDiagnosisPanel({ data }: { data: ApiData }) {
  return (
    <section className="previewPanel">
      <div className="sectionHeader dashboardSectionHeader">
        <div>
          <p className="eyebrow">Safe patch suggestions</p>
          <h3>What To Change Next</h3>
        </div>
        <span className="ratingPill">{data.doctorLatest ? 'Patch bundle ready' : 'No patch yet'}</span>
      </div>
      <p className="diagnosisLead">{data.diagnosis.generalDiagnosis}</p>
      <div className="burnGrid dashboardBurnGrid">
        <span>Useful: {formatNumber(data.diagnosis.burnProfile.usefulEstimatedTokens)}</span>
        <span>Waste: {formatNumber(data.diagnosis.burnProfile.suspectedWasteTokens)}</span>
        <span>Waste: {data.diagnosis.burnProfile.wastePercentage}%</span>
      </div>
      {data.diagnosis.whatToChangeNext.length === 0 ? (
        <EmptyState
          title="No immediate tune-up."
          body="Run Doctor after more session activity to generate safe patch suggestions."
          steps={['Use Claude Code', 'Run Audit', 'Run Doctor']}
        />
      ) : (
        <ol className="nextList">
          {data.diagnosis.whatToChangeNext.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
        </ol>
      )}
    </section>
  );
}

function EmptyState({ title, body, steps }: { title: string; body: string; steps: string[] }) {
  return (
    <div className="dashboardEmpty">
      <strong>{title}</strong>
      <p>{body}</p>
      <div>
        {steps.map((step) => <span key={step}>{step}</span>)}
      </div>
    </div>
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
              <span className={`severity severity-${finding.severity}`}>{finding.severity} / {finding.confidence}</span>
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
              <tr><td colSpan={4}><span className="emptyInline">No findings yet.</span></td></tr>
            ) : (
              findings.map((finding) => (
                <tr key={finding.category}>
                  <td>{finding.category}</td>
                  <td><span className="chip subtle">{finding.confidence}</span></td>
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
              <tr><td colSpan={5}><span className="emptyInline">No events match the selected filters.</span></td></tr>
            ) : (
              events.map((event) => (
                <tr key={event.id}>
                  <td><span className="chip">{event.eventType}</span></td>
                  <td>{event.toolName ? <span className="chip subtle">{event.toolName}</span> : '-'}</td>
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
          <button className="primaryAction" onClick={onRun}>Run Doctor</button>
          <button className="secondaryAction" onClick={() => window.location.reload()}>View Latest Patch</button>
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
          <article className="panel safetyPanel">
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
        <div className="emptyState">No patch bundle found. Run Doctor to generate manual-review proposals.</div>
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
          <button className="primaryAction" onClick={onInit}>Initialize Project</button>
        </div>
        <div className="notice warning">Mr Token is local-only. It may record Claude Code hook payloads that include file paths, commands, and tool output snippets. Use only where you are authorized.</div>
        <article className="panel setupFlow">
          <h4>Operating Sequence</h4>
          <ol>
            <li>Initialize this project.</li>
            <li>Use Claude Code normally.</li>
            <li>Run audit to inspect token burn.</li>
            <li>Run Doctor for safe patch proposals.</li>
          </ol>
        </article>
        <div className="clientGuideGrid">
          <article className="panel clientGuide">
            <h4>Connect a Claude Code Project</h4>
            <pre className="inlineCommands">{`cd /path/to/client-project
token-tithe ui

# In the browser:
# Setup -> Initialize Project

# Then use Claude Code in this same folder.
token-tithe audit`}</pre>
            <ol>
              <li>Open a terminal in the exact project folder the client wants analyzed.</li>
              <li>Run <code>token-tithe ui</code> from that folder.</li>
              <li>On this Setup page, confirm Project root matches the client project.</li>
              <li>Click <strong>Initialize Project</strong> to install project-local Claude Code hooks.</li>
              <li>Have the client use Claude Code in that same project folder.</li>
              <li>Return to Mr Token and click <strong>Refresh Audit</strong>.</li>
            </ol>
            <p>Full Claude Code analysis depends on hooks being installed in each specific project that needs measurement.</p>
          </article>
          <article className="panel clientGuide">
            <h4>Codex Threads / Projects</h4>
            <p>Codex automatic thread capture is not enabled in this MVP. Do not promise full Codex token-use analysis to clients yet.</p>
            <pre className="inlineCommands">{`cd /path/to/codex-workspace
token-tithe ui

# Use this as the local project audit surface.
# Full automatic session capture currently requires Claude Code hooks.`}</pre>
            <ol>
              <li>For now, run Mr Token from the same local repo or workspace used by the Codex thread.</li>
              <li>Use the dashboard as the project audit surface for local files, patches, and Doctor recommendations.</li>
              <li>Use Claude Code hook capture for full session/tool/prompt token analysis.</li>
            </ol>
            <p>The codebase is prepared for adapters, but Codex needs its own event adapter before thread-level capture is complete.</p>
          </article>
        </div>
        <article className="panel clientGuide">
          <h4>Client 1 / Client 2 Handoff Checklist</h4>
          <pre className="inlineCommands">{`node --version
token-tithe ui

# Optional terminal equivalents:
token-tithe init
token-tithe audit
token-tithe doctor`}</pre>
          <ol>
            <li>Install Mr Token on the client machine or inside the client-approved development environment.</li>
            <li>Start from a test repository first if the project is sensitive.</li>
            <li>Confirm the localhost URL, project root, database path, and hooks-installed status on Setup.</li>
            <li>Explain that data stays local, but hook payloads may include prompts, paths, commands, and tool output snippets.</li>
            <li>Have the client run one normal Claude Code session, then click Refresh Audit.</li>
            <li>Run Doctor only after reviewing the audit. Doctor writes patch proposals only; it does not apply them.</li>
          </ol>
        </article>
        <div className="statusGrid">
          <Status label="Project root" value={setup.projectRoot} />
          <Status label="Database" value={setup.dbPath} ok={setup.databaseExists} />
          <Status label="Events JSONL" value={setup.eventsPath} ok={setup.eventsJsonlExists} />
          <Status label="Claude settings" value={setup.settingsPath} ok={setup.claudeSettingsExists} />
          <Status label="Hooks installed" value={setup.hooksInstalled ? 'yes' : 'no'} ok={setup.hooksInstalled} />
        </div>
      </section>
      <section className="section">
        <div className="sectionHeader">
          <h3>Privacy / Data Captured</h3>
        </div>
        <article className="panel">
          <p>Data stays in this project by default. Events are written to <code>.token-tithe/token-tithe.db</code> and <code>.token-tithe/events.jsonl</code>. Claude hooks are written to <code>.claude/settings.local.json</code>.</p>
          <p>Captured data can include hook metadata, tool names, commands, file paths, estimated token counts, and raw Claude Code hook payloads. AI review is disabled by default.</p>
        </article>
      </section>
      <section className="section">
        <div className="sectionHeader">
          <h3>Uninstall Instructions</h3>
        </div>
        <article className="panel">
          <ol>
            <li>Remove <code>.token-tithe/</code>.</li>
            <li>Remove <code>token-tithe watch --stdin</code> hooks from <code>.claude/settings.local.json</code>.</li>
            <li>Run <code>npm unlink -g token-tithe</code>.</li>
            <li>Restore any <code>settings.local.json.*.bak</code> file if needed.</li>
          </ol>
        </article>
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
        <button className="secondaryAction" onClick={() => void copyCommands()}>Copy</button>
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

function getDashboardInsights(data: ApiData): DashboardInsights {
  const eventCount = data.events.length;
  const lastEvent = [...data.events].sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0];
  const toolCounts = new Map<string, number>();
  const flowTotals: Record<TokenFlowSegment['key'], number> = {
    prompts: 0,
    tools: 0,
    outputs: 0,
    stops: 0
  };

  for (const event of data.events) {
    if (event.toolName) toolCounts.set(event.toolName, (toolCounts.get(event.toolName) ?? 0) + 1);
    flowTotals[classifyEventForFlow(event.eventType)] += event.estimatedTokens;
  }

  const flowTotal = Object.values(flowTotals).reduce((sum, tokens) => sum + tokens, 0);
  const tokenFlow = [
    { key: 'prompts' as const, label: 'Prompts', tokens: flowTotals.prompts },
    { key: 'tools' as const, label: 'Tool calls', tokens: flowTotals.tools },
    { key: 'outputs' as const, label: 'Outputs/results', tokens: flowTotals.outputs },
    { key: 'stops' as const, label: 'Stop/final events', tokens: flowTotals.stops }
  ].map((segment) => ({
    ...segment,
    percent: flowTotal === 0 ? 0 : Math.round((segment.tokens / flowTotal) * 100)
  }));

  const mostCommonTool = [...toolCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

  return {
    eventCount,
    lastEventTime: lastEvent ? formatTimestamp(lastEvent.timestamp) : null,
    mostCommonTool,
    sessionCount: data.summary.sessions,
    tokenFlow
  };
}

function classifyEventForFlow(eventType: string): TokenFlowSegment['key'] {
  if (eventType === 'UserPromptSubmit') return 'prompts';
  if (eventType === 'PostToolUse') return 'outputs';
  if (eventType === 'PreToolUse') return 'tools';
  return 'stops';
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });
}

function hasSavings(range: [number, number]): boolean {
  return range[0] > 0 || range[1] > 0;
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
