import { useEffect, useMemo, useState } from 'react';
import { endpoints, getJson, mediaUrl, postForm, postJson } from './api.js';

const sections = [
  { id: 'identity', label: 'Identity Search', hint: 'Search records and prepare OSINT targets' },
  { id: 'document', label: 'Document Validation', hint: 'OCR, DB match, risk and review' },
  { id: 'face', label: 'Face Intelligence', hint: 'Image and video face verification' },
  { id: 'news', label: 'News Intelligence', hint: 'Clusters, topics, sources and articles' },
  { id: 'drishti', label: 'DRISHTI Intelligence', hint: 'Threat narratives, geo signals and response drafts' },
  { id: 'admin', label: 'Admin Records', hint: 'Review identity database records' }
];

const searchFieldOptions = [
  ['full_name', 'Full Name'],
  ['email', 'Email'],
  ['phone_number', 'Phone Number'],
  ['username', 'Username'],
  ['aadhar_number', 'Aadhaar Number'],
  ['pan_number', 'PAN Number'],
  ['voter_id_number', 'Voter ID Number'],
  ['driving_license_number', 'Driving Licence Number'],
  ['passport_number', 'Passport Number']
];

const docTypes = [
  ['aadhaar', 'Aadhaar Card'],
  ['pan', 'PAN Card'],
  ['voter_id', 'Voter ID'],
  ['driving_license', 'Driving Licence'],
  ['passport', 'Passport']
];

function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: false, error: '', data: null });
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: '' }));
    fn()
      .then((data) => active && setState({ loading: false, error: '', data }))
      .catch((error) => active && setState({ loading: false, error: error.message, data: null }));
    return () => { active = false; };
  }, deps);
  return state;
}

function useSessionState(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const stored = sessionStorage.getItem(key);
      if (stored !== null) return JSON.parse(stored);
    } catch {
      // Ignore damaged browser session state and fall back to a clean value.
    }
    return typeof initialValue === 'function' ? initialValue() : initialValue;
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Session persistence is a convenience; UI should still work without it.
    }
  }, [key, value]);

  return [value, setValue];
}

function createNewsViewId() {
  const stamp = new Date().toISOString().slice(0, 10).replaceAll('-', '');
  return `NEWS${stamp}-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
}

function useJobPolling(fetcher, jobId, enabled = true, intervalMs = 2500) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!jobId || !enabled) return undefined;
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const payload = await fetcher(jobId);
        const nextJob = unwrapJobPayload(payload);
        if (cancelled) return;
        setJob(nextJob);
        setError('');
        const status = String(nextJob?.status || '').toUpperCase();
        if (!['COMPLETED', 'FAILED', 'REJECTED', 'APPROVED'].includes(status)) {
          timer = setTimeout(tick, intervalMs);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          timer = setTimeout(tick, intervalMs + 1500);
        }
      }
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, enabled, intervalMs]);
  return { job, setJob, error };
}

function Shell({ active, setActive, children }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-card">
          <div className="brand-mark">ID</div>
          <div>
            <h1>Identity Command</h1>
            <p>Verification, OSINT, face and news intelligence in one console.</p>
          </div>
        </div>
        <nav className="nav-list">
          {sections.map((section) => (
            <button
              key={section.id}
              className={`nav-item ${active === section.id ? 'active' : ''}`}
              onClick={() => setActive(section.id)}
            >
              <span>{section.label}</span>
              <small>{section.hint}</small>
            </button>
          ))}
        </nav>
      </aside>
      <main className="main-panel">
        <TopBar active={active} />
        {children}
      </main>
    </div>
  );
}

function TopBar({ active }) {
  const section = sections.find((item) => item.id === active) || sections[0];
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Identity Verification Suite</span>
        <h2>{section.label}</h2>
        <p>{section.hint}</p>
      </div>
      <div className="live-chip"><span /> FastAPI connected UI</div>
    </header>
  );
}

function StatCard({ label, value, tone = 'blue', sub }) {
  return (
    <div className={`stat-card ${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      {sub && <span>{sub}</span>}
    </div>
  );
}

function Alert({ type = 'info', children }) {
  if (!children) return null;
  return <div className={`alert ${type}`}>{children}</div>;
}

function ProgressBar({ value = 0, message }) {
  const safeValue = Math.max(0, Math.min(100, Number(value || 0)));
  return (
    <div className="progress-wrap">
      <div className="progress-meta"><span>{message || 'Processing'}</span><strong>{safeValue}%</strong></div>
      <div className="progress-track"><div style={{ width: `${safeValue}%` }} /></div>
    </div>
  );
}

function DataTable({ rows = [], columns = [], empty = 'No records found.' }) {
  if (!rows.length) return <div className="empty-state">{empty}</div>;
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.employee_id || row.job_id || row.id || index}>
              {columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : display(row[column.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function createId() {
  return globalThis.crypto?.randomUUID?.() || `row-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function splitCsv(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function display(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function unwrapJobPayload(payload) {
  return payload?.job || payload?.osint_job || payload || {};
}

function resultPayload(job) {
  return job?.result || job?.results || {};
}

function identityPhotoPath(identity = {}) {
  return identity.photo_path || identity.image_path || identity.photo_url || identity.profile_photo || identity.avatar_path || identity.face_path || identity.database_face_path || identity.matched_photo_path || '';
}

function arrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function ImageBox({ src, alt = 'Preview', size = 'md' }) {
  const [failed, setFailed] = useState(false);
  const url = mediaUrl(src);
  useEffect(() => setFailed(false), [url]);
  if (!url || failed) return <span className="muted">-</span>;
  return <img className={`image-box ${size}`} src={url} alt={alt} onError={() => setFailed(true)} />;
}

function Overview() {
  const health = useAsync(() => getJson(endpoints.healthFull, { check_osint_network: false }), []);
  const payload = health.data || {};
  const api = payload.api || {};
  const database = payload.database || {};
  const news = payload.news_database || {};
  const osint = payload.osint || {};
  return (
    <section className="page-grid">
      <div className="hero-card wide-card">
        <div>
          <span className="eyebrow">Modern React Workspace</span>
          <h3>Secure identity operations with live intelligence workflows</h3>
          <p>Search records, validate documents, run face intelligence, inspect OSINT evidence and monitor news clusters from one professional console.</p>
        </div>
        <div className="orbital-visual"><span /><span /><span /></div>
      </div>
      {health.error && <Alert type="danger">{health.error}</Alert>}
      <div className="stat-grid">
        <StatCard label="API" value={api.status || payload.status || 'Checking'} sub="FastAPI service" tone="green" />
        <StatCard label="Database" value={database.status || 'Unknown'} sub={database.message || 'PostgreSQL'} tone="blue" />
        <StatCard label="OSINT" value={osint.configured ? 'Configured' : 'Not configured'} sub={osint.message} tone="purple" />
        <StatCard label="News DB" value={news.status || 'Unknown'} sub={news.message || 'External feed'} tone="amber" />
      </div>
      <div className="workflow-strip wide-card">
        {['Identity', 'Document OCR', 'Face Engine', 'OSINT', 'News'].map((step, index) => (
          <div className="workflow-node" key={step}><span>{index + 1}</span><strong>{step}</strong></div>
        ))}
      </div>
    </section>
  );
}

function IdentitySearch() {
  const [rows, setRows] = useSessionState('identity.rows', [{ id: createId(), field: 'full_name', value: '' }]);
  const [result, setResult] = useSessionState('identity.result', null);
  const [approvedTargets, setApprovedTargets] = useSessionState('identity.approvedTargets', []);
  const [jobInput, setJobInput] = useSessionState('identity.jobInput', '');
  const [loadedJobId, setLoadedJobId] = useSessionState('identity.loadedJobId', '');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { job: osintJob, error: osintError, setJob: setOsintJob } = useJobPolling((id) => getJson(`${endpoints.osintJobs}/${id}`), loadedJobId, Boolean(loadedJobId), 3500);

  const addRow = () => setRows((items) => [...items, { id: createId(), field: 'email', value: '' }]);
  const updateRow = (id, patch) => setRows((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item));
  const removeRow = (id) => setRows((items) => items.length === 1 ? items : items.filter((item) => item.id !== id));

  const criteria = rows.map(({ field, value }) => ({ field, value: value.trim() })).filter((item) => item.value);

  async function submitSearch() {
    setError('');
    if (!criteria.length) {
      setError('Please fill at least one search field.');
      return;
    }
    setLoading(true);
    try {
      const form = new FormData();
      form.append('criteria_json', JSON.stringify(criteria));
      form.append('submit_osint', 'false');
      const payload = await postForm(endpoints.advancedSearch, form);
      setResult(payload);
      setApprovedTargets(criteria);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitApprovedOsint() {
    setError('');
    if (!approvedTargets.length) return setError('Approve at least one field before sending it to OSINT.');
    setLoading(true);
    try {
      const form = new FormData();
      form.append('targets_json', JSON.stringify(approvedTargets));
      const payload = await postForm(endpoints.osintJobs, form);
      const jobId = payload.osint_job?.job_id;
      setResult((current) => ({ ...(current || {}), osint_job: payload.osint_job }));
      if (jobId) {
        setJobInput(jobId);
        setLoadedJobId(jobId);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleTarget(target, checked) {
    setApprovedTargets((items) => {
      const exists = items.some((item) => item.field === target.field && item.value === target.value);
      if (checked && !exists) return [...items, target];
      if (!checked) return items.filter((item) => !(item.field === target.field && item.value === target.value));
      return items;
    });
  }

  return (
    <section className="content-card">
      <SectionTitle title="Identity Search" subtitle="Search database records first, review matched fields, then approve exactly what should be sent to the OSINT engine." />
      <div className="form-stack">
        {rows.map((row, index) => (
          <div className="search-row" key={row.id}>
            <label>Field {index + 1}<select value={row.field} onChange={(e) => updateRow(row.id, { field: e.target.value })}>{searchFieldOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label>Value {index + 1}<input value={row.value} onChange={(e) => updateRow(row.id, { value: e.target.value })} placeholder="Type search value" /></label>
            <button className="ghost-button danger" onClick={() => removeRow(row.id)}>Remove</button>
          </div>
        ))}
        <div className="action-row two-actions">
          <button className="ghost-button" onClick={addRow}>Add Search Field</button>
          <button className="primary-button" onClick={submitSearch} disabled={loading}>{loading ? 'Searching...' : 'Search Database'}</button>
        </div>
      </div>
      <Alert type="danger">{error || osintError}</Alert>
      {result && <IdentityResults result={result} />}
      {result && <OSINTApprovalPanel criteria={criteria} approvedTargets={approvedTargets} toggleTarget={toggleTarget} submitApprovedOsint={submitApprovedOsint} loading={loading} />}
      <div className="content-card compact-card padded-top">
        <h4>Load OSINT Job</h4>
        <div className="inline-form"><input value={jobInput} onChange={(e) => setJobInput(e.target.value.toUpperCase())} placeholder="JOB00056" /><button className="primary-button" onClick={() => setLoadedJobId(jobInput.trim())}>View Job</button></div>
      </div>
      {result?.osint_job && <Alert type="success">OSINT job queued successfully. Job ID: {result.osint_job.job_id}</Alert>}
      {osintJob && <OSINTJob job={osintJob} setJob={setOsintJob} />}
    </section>
  );
}

function OSINTApprovalPanel({ criteria, approvedTargets, toggleTarget, submitApprovedOsint, loading }) {
  if (!criteria.length) return null;
  return (
    <div className="content-card compact-card padded-top">
      <h4>Approve OSINT Targets</h4>
      <Alert type="info">Database search is complete. Select only the fields you want to send to the OSINT engine.</Alert>
      <div className="approval-grid">
        {criteria.map((item) => {
          const checked = approvedTargets.some((target) => target.field === item.field && target.value === item.value);
          return <label className="approval-chip" key={`${item.field}-${item.value}`}><input type="checkbox" checked={checked} onChange={(event) => toggleTarget(item, event.target.checked)} /><strong>{fieldLabel(item.field)}</strong><span>{item.value}</span></label>;
        })}
      </div>
      <button className="primary-button full-width" onClick={submitApprovedOsint} disabled={loading}>{loading ? 'Submitting...' : 'Submit Approved Fields To OSINT'}</button>
    </div>
  );
}

function IdentityResults({ result }) {
  const rows = result.results || [];
  const columns = [
    { key: 'photo_path', label: 'Photo', render: (row) => <ImageBox src={identityPhotoPath(row)} size="lg" /> },
    { key: 'employee_id', label: 'Employee ID' },
    { key: 'full_name', label: 'Full Name' },
    { key: 'date_of_birth', label: 'DOB' },
    { key: 'aadhar_number', label: 'Aadhaar' },
    { key: 'pan_number', label: 'PAN' },
    { key: 'voter_id_number', label: 'Voter ID' },
    { key: 'driving_license_number', label: 'Driving Licence' },
    { key: 'passport_number', label: 'Passport' },
    { key: 'phone_number', label: 'Phone' },
    { key: 'email', label: 'Email' },
    { key: 'department', label: 'Department' },
    { key: 'state', label: 'State' }
  ];
  return (
    <div className="result-zone">
      <div className="result-header"><strong>{result.total_matches || rows.length} database matches</strong><span>These results are from PostgreSQL database search only.</span></div>
      <DataTable rows={rows} columns={columns} empty="No identity records matched your criteria." />
    </div>
  );
}

function fieldLabel(field) {
  return (searchFieldOptions.find(([value]) => value === field) || [field, field])[1];
}

function IdentityProfile({ identity, title = 'Identity Details' }) {
  if (!identity || !Object.keys(identity).length) return null;
  return (
    <div className="identity-profile">
      {title && <h4>{title}</h4>}
      <div className="identity-profile-grid">
        <ImageBox src={identityPhotoPath(identity)} size="xl" />
        <div>
          <h3>{identity.full_name || identity.name || '-'}</h3>
          <p>Employee ID: <strong>{identity.employee_id || '-'}</strong></p>
          <dl>
            <div><dt>DOB</dt><dd>{display(identity.date_of_birth)}</dd></div>
            <div><dt>Department</dt><dd>{display(identity.department)}</dd></div>
            <div><dt>Aadhaar</dt><dd>{display(identity.aadhar_number)}</dd></div>
            <div><dt>PAN</dt><dd>{display(identity.pan_number)}</dd></div>
            <div><dt>Voter ID</dt><dd>{display(identity.voter_id_number)}</dd></div>
            <div><dt>Driving Licence</dt><dd>{display(identity.driving_license_number)}</dd></div>
            <div><dt>Passport</dt><dd>{display(identity.passport_number)}</dd></div>
            <div><dt>Phone</dt><dd>{display(identity.phone_number)}</dd></div>
            <div><dt>Email</dt><dd>{display(identity.email)}</dd></div>
            <div><dt>State</dt><dd>{display(identity.state)}</dd></div>
          </dl>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ title, subtitle }) {
  return <div className="section-title"><h3>{title}</h3><p>{subtitle}</p></div>;
}

function DocumentValidation() {
  const [documentType, setDocumentType] = useState('aadhaar');
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useSessionState('document.jobId', '');
  const [error, setError] = useState('');
  const preview = useObjectUrl(file);
  const { job, error: pollError } = useJobPolling((id) => getJson(`${endpoints.documentJobs}/${id}`), jobId);

  async function submit() {
    setError('');
    if (!file) return setError('Please upload a document image first.');
    try {
      const form = new FormData();
      form.append('document_type', documentType);
      form.append('document', file);
      const payload = await postForm(endpoints.documentJobs, form);
      setJobId(payload.job?.job_id);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="content-card">
      <SectionTitle title="Validate Government Document" subtitle="Async OCR, document type checking, database verification, face scoring and risk decision." />
      <div className="split-grid">
        <div className="form-stack">
          <label>Document type<select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>{docTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label>Upload document<input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
          <button className="primary-button" onClick={submit}>Validate Document</button>
          <Alert type="danger">{error || pollError}</Alert>
        </div>
        <div className="preview-panel">{preview ? <img src={preview} alt="Document preview" /> : <span>Upload preview appears here</span>}</div>
      </div>
      {job && <JobResultCard job={job} kind="document" />}
    </section>
  );
}

function JobResultCard({ job, kind }) {
  const currentJob = unwrapJobPayload(job);
  const result = resultPayload(currentJob);
  const decision = currentJob.decision || result.decision || {};
  const risk = currentJob.risk_assessment || result.risk_assessment || decision.risk_assessment || {};
  const extracted = currentJob.extracted_data || result.extracted_data || {};
  const dbMatch = currentJob.database_match || result.database_match || result.best_match || result.best_database_candidate || {};
  const uploadedImage = currentJob.uploaded_image_path || currentJob.uploaded_document_path || result.uploaded_image_path || result.uploaded_document_path || result.uploaded_face_image_path || result.query_image_path || currentJob.image_path;
  const candidateImage = identityPhotoPath(dbMatch) || result.best_candidate_photo_path || result.best_match_photo_path || currentJob.best_candidate_photo_path;
  return (
    <div className="job-card">
      <div className="job-header"><strong>{currentJob.job_id}</strong><StatusPill status={currentJob.status} /></div>
      <ProgressBar value={currentJob.progress_percent} message={currentJob.progress_message} />
      {currentJob.error_message && <Alert type="danger">{currentJob.error_message}</Alert>}
      {kind === 'document' && result && (
        <DocumentResultDetails job={currentJob} result={result} decision={decision} risk={risk} extracted={extracted} dbMatch={dbMatch} uploadedImage={uploadedImage} />
      )}
      {kind === 'face' && result && (
        <div className="result-zone">
          <Alert type={result.matched ? 'success' : 'danger'}>{result.matched ? 'Yes, the uploaded face matched a database user. Details are shared below.' : 'No confident face match was found in the database.'}</Alert>
          <div className="face-result-pair">
            <div><h4>Uploaded Face Image</h4><ImageBox src={uploadedImage} size="xl" /></div>
            <div><h4>Best Database Candidate</h4><ImageBox src={candidateImage} size="xl" /></div>
          </div>
          {dbMatch && Object.keys(dbMatch).length > 0 && <IdentityProfile identity={dbMatch} title="Matched User Details" />}
        </div>
      )}
    </div>
  );
}

function DocumentResultDetails({ job, decision, risk, extracted, dbMatch, uploadedImage }) {
  const checks = risk.checks || {};
  const reasons = arrayValue(risk.reasons);
  const flags = arrayValue(risk.flags);
  const extractedRows = Object.entries(extracted || {})
    .filter(([key, value]) => key !== 'raw_text' && key !== 'model_output' && value !== null && value !== undefined && value !== '')
    .map(([field, value]) => ({ field: field.replaceAll('_', ' '), value: display(value) }));
  const checkRows = Object.entries(checks).map(([field, value]) => ({ field: field.replaceAll('_', ' '), points: value }));
  return (
    <div className="result-zone">
      <div className="summary-grid">
        <StatCard label="Decision" value={decision.status || risk.decision || job.status} tone={(decision.status || risk.decision) === 'APPROVED' ? 'green' : 'amber'} />
        <StatCard label="Risk Score" value={risk.risk_score ?? risk.score ?? '-'} tone="purple" />
        <StatCard label="Document" value={extracted.document_type || job.document_type || '-'} />
      </div>
      <div className="face-result-pair">
        <div><h4>Uploaded Document</h4><ImageBox src={uploadedImage} size="xl" /></div>
        <div><h4>Database Record For Review</h4>{Object.keys(dbMatch).length ? <IdentityProfile identity={dbMatch} title="" /> : <div className="empty-state">No database record was matched.</div>}</div>
      </div>
      <h4>Extracted Document Fields</h4>
      <DataTable rows={extractedRows} empty="No extracted fields were returned." columns={[{ key: 'field', label: 'Field' }, { key: 'value', label: 'Value' }]} />
      <h4>Score Breakdown</h4>
      <DataTable rows={checkRows} empty="No score breakdown available." columns={[{ key: 'field', label: 'Check' }, { key: 'points', label: 'Points' }]} />
      <div className="two-column-notes">
        <div><h4>Passed Checks</h4>{reasons.length ? reasons.map((item) => <Alert type="success" key={item}>{item}</Alert>) : <div className="empty-state">No positive checks were confirmed.</div>}</div>
        <div><h4>Risk Flags</h4>{flags.length ? flags.map((item) => <Alert type="warning" key={item}>{item}</Alert>) : <div className="empty-state">No risk flags were returned.</div>}</div>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const normalized = String(status || 'PENDING').toLowerCase();
  return <span className={`status-pill ${normalized}`}>{status || 'PENDING'}</span>;
}

function FaceIntelligence() {
  const [mode, setMode] = useState('image');
  return (
    <section className="content-card">
      <SectionTitle title="Face Intelligence" subtitle="Search a single image or detect faces from video, then approve selected crops for database verification." />
      <div className="segmented"><button className={mode === 'image' ? 'active' : ''} onClick={() => setMode('image')}>Image Search</button><button className={mode === 'video' ? 'active' : ''} onClick={() => setMode('video')}>Video Detection</button></div>
      {mode === 'image' ? <FaceImageSearch /> : <VideoFaceSearch />}
    </section>
  );
}

function FaceImageSearch() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useSessionState('face.imageJobId', '');
  const [error, setError] = useState('');
  const preview = useObjectUrl(file);
  const { job, error: pollError } = useJobPolling((id) => getJson(`${endpoints.faceJobs}/${id}`), jobId);

  async function submit() {
    setError('');
    if (!file) return setError('Please upload a face image first.');
    const form = new FormData();
    form.append('image', file);
    try {
      const payload = await postForm(endpoints.faceJobs, form);
      setJobId(payload.job?.job_id);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="split-grid padded-top">
      <div className="form-stack"><label>Face image<input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label><button className="primary-button" onClick={submit}>Search By Face</button><Alert type="danger">{error || pollError}</Alert></div>
      <div className="preview-panel face-preview">{preview ? <img src={preview} alt="Face preview" /> : <span>Face preview</span>}</div>
      {job && <div className="wide-span"><JobResultCard job={job} kind="face" /></div>}
    </div>
  );
}

function VideoFaceSearch() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useSessionState('face.videoJobId', '');
  const [selected, setSelected] = useSessionState('face.videoSelected', []);
  const [error, setError] = useState('');
  const { job, error: pollError, setJob } = useJobPolling((id) => getJson(`${endpoints.videoFaceJobs}/${id}`), jobId, Boolean(jobId), 2200);

  async function submit() {
    setError('');
    if (!file) return setError('Please upload a video first.');
    const form = new FormData();
    form.append('video', file);
    try {
      const payload = await postForm(endpoints.videoFaceJobs, form);
      setJobId(payload.job?.job_id);
      setSelected([]);
    } catch (err) {
      setError(err.message);
    }
  }

  async function verifyFaces() {
    setError('');
    if (!selected.length) return setError('Select at least one detected face.');
    try {
      const payload = await postJson(`${endpoints.videoFaceJobs}/${jobId}/verify-faces`, { face_ids: selected });
      setJob(unwrapJobPayload(payload));
    } catch (err) {
      setError(err.message);
    }
  }

  const faces = job?.detected_faces || [];
  return (
    <div className="padded-top">
      <div className="split-grid">
        <div className="form-stack"><label>Video file<input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label><button className="primary-button" onClick={submit}>Detect Faces</button><Alert type="danger">{error || pollError}</Alert></div>
        {job && <div className="job-card"><div className="job-header"><strong>{job.job_id}</strong><StatusPill status={job.status} /></div><ProgressBar value={job.progress_percent} message={job.progress_message} /><div className="summary-grid"><StatCard label="Frames" value={job.sampled_frames_processed || 0} /><StatCard label="Faces" value={job.unique_faces_detected || faces.length} tone="green" /></div></div>}
      </div>
      {!!faces.length && <div className="face-grid">{faces.map((face) => <label className="face-tile" key={face.face_id}><ImageBox src={face.face_image_path} size="lg" /><strong>Face {face.face_id}</strong><small>{face.verification_status}</small><input type="checkbox" checked={selected.includes(face.face_id)} onChange={(e) => setSelected((items) => e.target.checked ? [...items, face.face_id] : items.filter((id) => id !== face.face_id))} />Approve for DB verification</label>)}</div>}
      {!!faces.length && <button className="primary-button floating-action" onClick={verifyFaces}>Verify Selected Faces</button>}
    </div>
  );
}

function useObjectUrl(file) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!file) { setUrl(''); return undefined; }
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);
  return url;
}

function OSINTResults() {
  const [jobId, setJobId] = useSessionState('osint.jobInput', '');
  const [loadedId, setLoadedId] = useSessionState('osint.loadedJobId', '');
  const { job, error } = useJobPolling((id) => getJson(`${endpoints.osintJobs}/${id}`), loadedId, Boolean(loadedId), 3500);
  return (
    <section className="content-card">
      <SectionTitle title="OSINT Job Review" subtitle="Load social, phone, email, avatar and enriched evidence returned by the external OSINT engine." />
      <div className="inline-form"><input value={jobId} onChange={(e) => setJobId(e.target.value.toUpperCase())} placeholder="JOB00056" /><button className="primary-button" onClick={() => setLoadedId(jobId.trim())}>View Job</button></div>
      <Alert type="danger">{error}</Alert>
      {job && <OSINTJob job={job} />}
    </section>
  );
}

function OSINTJob({ job, setJob = () => {} }) {
  const [approvedAvatars, setApprovedAvatars] = useState([]);
  const [verification, setVerification] = useState(null);
  const [verifyError, setVerifyError] = useState('');
  const [verifying, setVerifying] = useState(false);
  const currentJob = unwrapJobPayload(job);
  const normalized = currentJob.normalized || {};
  const raw = currentJob.results?.results || currentJob.results || {};
  const normalizedProfiles = arrayValue(normalized.profiles);
  const profiles = normalizedProfiles.length ? normalizedProfiles : flattenRawSocialResults(raw);
  const contacts = arrayValue(normalized.contacts);
  const avatarCandidates = uniqueAvatarCandidates([...normalizedProfiles, ...arrayValue(normalized.matches), ...flattenRawSocialResults(raw)]);
  const normalizedPhoneRows = contacts.filter((row) => contactKind(row).includes('phone') || /^\+?\d{7,}$/.test(String(row.target || '').replace(/\s+/g, '')));
  const normalizedEmailRows = contacts.filter((row) => contactKind(row).includes('email') || String(row.target || '').includes('@'));
  const phoneRows = normalizedPhoneRows.length ? normalizedPhoneRows : flattenRawContactResults(raw.phone_results || raw.phoneResults || raw.phone, 'phone');
  const emailRows = normalizedEmailRows.length ? normalizedEmailRows : flattenRawContactResults(raw.email_results || raw.emailResults || raw.email, 'email');

  useEffect(() => {
    setApprovedAvatars(avatarCandidates);
  }, [currentJob.job_id, avatarCandidates.length]);

  function toggleAvatar(profile, checked) {
    setApprovedAvatars((items) => {
      const key = avatarKey(profile);
      if (checked && !items.some((item) => avatarKey(item) === key)) return [...items, profile];
      if (!checked) return items.filter((item) => avatarKey(item) !== key);
      return items;
    });
  }

  async function verifyAvatars() {
    setVerifyError('');
    if (!approvedAvatars.length) return setVerifyError('Approve at least one OSINT avatar before database face verification.');
    setVerifying(true);
    try {
      const payload = await postJson(`${endpoints.osintJobs}/${currentJob.job_id}/verify-avatars`, { approved_avatars: approvedAvatars });
      setVerification(payload);
      if (payload.normalized) setJob({ ...currentJob, normalized: payload.normalized });
    } catch (err) {
      setVerifyError(err.message);
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="result-zone osint-zone">
      <div className="job-header"><strong>OSINT Job: {currentJob.job_id}</strong><StatusPill status={currentJob.status} /></div>
      <Alert type={String(currentJob.status).toUpperCase() === 'COMPLETED' ? 'success' : 'info'}>{String(currentJob.status).toUpperCase() === 'COMPLETED' ? 'OSINT search completed and the result was stored.' : 'OSINT job is waiting for results from the external engine.'}</Alert>
      <div className="summary-grid"><StatCard label="Social Media" value={profiles.length} /><StatCard label="Phone Results" value={phoneRows.length} tone="green" /><StatCard label="Email Results" value={emailRows.length} tone="purple" /></div>
      <h4>Social Media Results</h4>
      <DataTable rows={profiles} columns={[{ key: 'target', label: 'Target' }, { key: 'platform', label: 'Platform' }, { key: 'avatar_image_path', label: 'Avatar Image', render: (row) => <ImageBox src={avatarSource(row)} size="md" /> }, { key: 'bio', label: 'Bio / Extracted Text', render: (row) => display(row.bio || row.extracted_text || row.details) }, { key: 'profile_url', label: 'Profile URL', render: (row) => linkView(row.profile_url || row.url) }, { key: 'avatar_url', label: 'Avatar URL', render: (row) => linkView(row.avatar_url) }]} />
      <h4>Phone Results</h4>
      <DataTable rows={phoneRows} columns={[{ key: 'target', label: 'Target' }, { key: 'input_type', label: 'Input Type', render: (row) => row.contact_type || row.input_type || row.type || '-' }, { key: 'status', label: 'Result Status', render: (row) => row.status || row.result_status || '-' }, { key: 'platform', label: 'Platform' }, { key: 'details', label: 'Details' }]} />
      <h4>Email Results</h4>
      <DataTable rows={emailRows} columns={[{ key: 'target', label: 'Target' }, { key: 'input_type', label: 'Input Type', render: (row) => row.contact_type || row.input_type || row.type || '-' }, { key: 'status', label: 'Result Status', render: (row) => row.status || row.result_status || '-' }, { key: 'platform', label: 'Platform' }, { key: 'details', label: 'Details' }]} />
      <h4>OSINT Images For Verification</h4>
      <Alert type="info">Review the OSINT avatar images below. Approve only the images you want to compare with registered database faces.</Alert>
      {avatarCandidates.length ? <div className="avatar-grid">{avatarCandidates.map((profile) => {
        const checked = approvedAvatars.some((item) => avatarKey(item) === avatarKey(profile));
        return <div className="avatar-card" key={avatarKey(profile)}><strong>{profile.platform || 'Social Profile'}</strong><small>Target: {profile.target || '-'}</small><ImageBox src={avatarSource(profile)} size="lg" />{linkView(profile.profile_url || profile.url, 'Open profile')}<label className="switch-line"><input type="checkbox" checked={checked} onChange={(event) => toggleAvatar(profile, event.target.checked)} />Approve for face search</label></div>;
      })}</div> : <div className="empty-state">No valid OSINT avatar images are available for face verification.</div>}
      <button className="primary-button full-width" onClick={verifyAvatars} disabled={verifying || !avatarCandidates.length}>{verifying ? 'Verifying...' : 'Verify Approved OSINT Avatars With Database Faces'}</button>
      <Alert type="danger">{verifyError}</Alert>
      {verification && <OSINTVerificationResult verification={verification} />}
    </div>
  );
}


function flattenRawContactResults(items, fallbackType) {
  const rows = [];
  for (const item of items || []) {
    const matches = Array.isArray(item.matches) && item.matches.length ? item.matches : [item];
    for (const match of matches) {
      rows.push({
        target: item.target || match.target || '-',
        contact_type: item.input_type || fallbackType,
        status: match.status || item.status || item.result_status,
        platform: match.platform || item.platform,
        details: match.details || item.details || item.message
      });
    }
  }
  return rows;
}

function flattenRawSocialResults(results) {
  const rows = [];
  const sectionKeys = ['username_results', 'instagram_results', 'facebook_results', 'social_media_results'];
  for (const sectionKey of sectionKeys) {
    for (const row of results?.[sectionKey] || []) {
      rows.push({
        target: row.target || row.target_username || row.username,
        platform: row.platform || sectionKey.replaceAll('_', ' '),
        status: row.status,
        profile_url: row.profile_url || row.url,
        avatar_url: row.avatar_url || row.extracted_data?.avatar_url,
        avatar_path: row.avatar_path || row.local_avatar_path,
        bio: row.bio || row.extracted_data?.bio,
        extracted_text: row.details || row.message
      });
    }
  }
  if (results?.profile_url) {
    rows.unshift({ target: '-', platform: 'OSINT', status: 'found', profile_url: results.profile_url, avatar_url: results.avatar_url });
  }
  return rows;
}

function uniqueAvatarCandidates(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    const image = avatarSource(row);
    if (!isUsableAvatarSource(image)) return false;
    const key = avatarKey(row);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function avatarSource(row = {}) {
  return row.avatar_image_path || row.avatar_path || row.local_avatar_path || row.avatar_url || row.image_url || row.image_path || '';
}

function isUsableAvatarSource(value) {
  const image = String(value || '').trim().toLowerCase();
  if (!image || image === '-') return false;
  return !['logo.svg', 'placeholder', 'default', 'silhouette', 'no-image', 'kpb0jgkr4ve.webp'].some((token) => image.includes(token));
}

function normalizedUrlKey(value) {
  return String(value || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/$/, '');
}

function avatarKey(row) {
  const profile = normalizedUrlKey(row.profile_url || row.url);
  if (profile) return `profile:${profile}`;
  const image = normalizedUrlKey(avatarSource(row));
  if (image) return `image:${image}`;
  return [row.platform, row.target, row.username].map((value) => String(value || '').toLowerCase()).join('|');
}

function contactKind(row = {}) {
  return String(row.contact_type || row.input_type || row.type || row.result_type || '').toLowerCase();
}

function linkView(url, label = 'View') {
  return url ? <a href={url} target="_blank" rel="noreferrer">{label}</a> : '-';
}

function OSINTVerificationResult({ verification }) {
  const conclusion = verification.conclusion || {};
  const rows = verification.avatar_verifications || [];
  const matches = rows.filter((row) => row.matched);
  return (
    <div className="result-zone">
      <Alert type={conclusion.decision === 'VERIFIED' ? 'success' : 'danger'}>{conclusion.summary || conclusion.decision}</Alert>
      <div className="summary-grid"><StatCard label="Approved Avatars Checked" value={rows.length} /><StatCard label="Face Matches" value={matches.length} tone="green" /><StatCard label="Decision" value={conclusion.decision || '-'} tone={conclusion.decision === 'VERIFIED' ? 'green' : 'amber'} /></div>
      {verification.verified_identity && <IdentityProfile identity={verification.verified_identity} title="Final Verified Profile Summary" />}
      <h4>Avatar Match Evidence</h4>
      <DataTable rows={rows} columns={[{ key: 'platform', label: 'Platform' }, { key: 'target', label: 'Target' }, { key: 'avatar_path', label: 'OSINT Avatar', render: (row) => <ImageBox src={avatarSource(row)} size="md" /> }, { key: 'profile_url', label: 'Profile URL', render: (row) => linkView(row.profile_url) }, { key: 'matched', label: 'Matched', render: (row) => row.matched ? 'Yes' : 'No' }, { key: 'best_score', label: 'Best Score' }, { key: 'database_match', label: 'DB Employee ID', render: (row) => row.database_match?.employee_id || '-' }, { key: 'message', label: 'Message' }]} />
    </div>
  );
}

function NewsIntelligence() {
  const [limit, setLimit] = useSessionState('news.limit', 10);
  const [query, setQuery] = useSessionState('news.query', '');
  const [selectedCluster, setSelectedCluster] = useSessionState('news.selectedCluster', null);
  const [searchResult, setSearchResult] = useSessionState('news.searchResult', null);
  const [newsViewId, setNewsViewId] = useSessionState('news.viewJobId', createNewsViewId);
  const clustersState = useAsync(() => getJson(endpoints.newsTopClusters, { limit }), [limit]);
  const topicsState = useAsync(() => getJson(endpoints.newsTopics, { limit: 80 }), []);
  const syncState = useAsync(() => getJson(endpoints.newsSync), []);

  async function search() {
    if (!query.trim()) return setSearchResult(null);
    const payload = await getJson(endpoints.newsSearch, { q: query.trim(), limit: 20 });
    setNewsViewId(createNewsViewId());
    setSearchResult(payload);
    setSelectedCluster(null);
  }

  async function openCluster(clusterId) {
    const payload = await getJson(`${endpoints.newsClusters}/${clusterId}`);
    setSelectedCluster(payload.cluster || payload);
  }

  const clusters = searchResult?.clusters || clustersState.data?.clusters || [];
  const topics = topicsState.data?.topics || [];
  useEffect(() => {
    const firstCluster = clusters[0];
    if (firstCluster && !selectedCluster) {
      // Auto-open the strongest/latest news item like the Streamlit dashboard.
      openCluster(firstCluster.cluster_id);
    }
  }, [clustersState.data, searchResult]);
  return (
    <section className="content-card">
      <SectionTitle title="News Intelligence" subtitle="Display latest news first, search by topic/source/entity, and open a news item to review summary, source spread, entities, and related articles." />
      <div className="news-toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search news, article title, source, or entity" /><button className="primary-button" onClick={search}>Search News</button><select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>{[10, 20, 30, 40, 50].map((item) => <option key={item} value={item}>{item} latest news</option>)}</select></div>
      <div className="topic-strip">{topics.slice(0, 14).map((topic) => <button key={topic.topic || topic.keyword} onClick={() => setQuery(topic.topic || topic.keyword)}>{topic.topic || topic.keyword}</button>)}</div>
      <div className="job-header news-session"><strong>News View Job: {newsViewId}</strong><StatusPill status={searchResult ? 'SEARCHED' : 'LIVE'} /></div>
      {syncState.data?.event && <Alert type="info">Latest news batch: {syncState.data.event.batch_id} | {syncState.data.event.status}</Alert>}
      {searchResult && <Alert type="success">Search results for {searchResult.query}: {searchResult.total_clusters} news clusters found.</Alert>}
      <div className="news-layout"><div className="cluster-list">{clusters.map((cluster) => <button className="cluster-card" key={cluster.cluster_id} onClick={() => openCluster(cluster.cluster_id)}><strong>{clusterTitle(cluster)}</strong><span>News {cluster.cluster_id} - {clusterArticleCount(cluster)} articles - {cluster.top_source || cluster.source || 'Mixed sources'}</span><small>Updated: {clusterUpdatedAt(cluster)}</small><p>{clusterSummary(cluster)}</p></button>)}</div><ClusterDetail cluster={selectedCluster} /></div>
    </section>
  );
}

function clusterTitle(cluster) {
  return cluster.title || cluster.cluster_name || cluster.name || `News ${cluster.cluster_id}`;
}

function clusterSummary(cluster) {
  return cluster.summary || cluster.cluster_summary || cluster.key_entities || 'Open news item for details';
}

function clusterArticleCount(cluster = {}) {
  const candidates = [
    cluster.actual_article_count,
    cluster.total_articles,
    cluster.article_total,
    cluster.articles_count,
    cluster.article_count,
    Array.isArray(cluster.articles) ? cluster.articles.length : null
  ];
  const value = candidates.find((item) => Number.isFinite(Number(item)) && Number(item) >= 0);
  return Number(value || 0);
}

function clusterUpdatedAt(cluster = {}) {
  const value = cluster.updated_at || cluster.last_updated || cluster.created_at || cluster.published_at || cluster.latest_article_date;
  return formatDateTime(value);
}

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function ClusterDetail({ cluster }) {
  if (!cluster) return <div className="cluster-detail empty-state">Select a news item to inspect summary, entities, sources and related articles.</div>;
  const articles = cluster.articles || [];
  const sources = cluster.sources || [];
  const entities = cluster.entities || [];
  return <div className="cluster-detail"><h3>{clusterTitle(cluster)}</h3><div className="news-meta">Updated: {clusterUpdatedAt(cluster)}</div><p>{clusterSummary(cluster)}</p><div className="summary-grid"><StatCard label="Articles" value={clusterArticleCount(cluster)} /><StatCard label="Sources" value={sources.length || cluster.source_count || 0} tone="green" /><StatCard label="Entities" value={entities.length || cluster.entity_count || 0} tone="purple" /></div><h4>Source Breakdown</h4><DataTable rows={sources} empty="No source breakdown available." columns={[{ key: 'source', label: 'Source' }, { key: 'article_count', label: 'Articles' }]} /><h4>Key Entities</h4><div className="tag-cloud">{entities.slice(0, 30).map((entity, index) => <span key={index}>{entity.entity_name || entity.entity || entity.name || display(entity)}</span>)}</div><h4>Related Articles</h4><DataTable rows={articles} columns={[{ key: 'title', label: 'Title' }, { key: 'source', label: 'Source' }, { key: 'published_at', label: 'Published' }, { key: 'url', label: 'URL', render: (row) => linkView(row.url) }]} /></div>;
}


function DrishtiIntelligence() {
  const [refreshTick, setRefreshTick] = useState(0);
  const [query, setQuery] = useState('');
  const [locations, setLocations] = useState('');
  const [emotions, setEmotions] = useState('');
  const [language, setLanguage] = useState('');
  const [searchPayload, setSearchPayload] = useState(null);
  const [generationPayload, setGenerationPayload] = useState(null);
  const [narrative, setNarrative] = useState('public trust and information integrity');
  const [contentType, setContentType] = useState('Short Post');
  const [tone, setTone] = useState('Calm');
  const [includeImage, setIncludeImage] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const overviewState = useAsync(() => getJson(endpoints.drishtiOverview), [refreshTick]);

  async function refreshSources() {
    setError('');
    setBusy('refresh');
    try {
      await postJson(endpoints.drishtiRefresh, {});
      setRefreshTick((value) => value + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function runSearch() {
    setError('');
    setBusy('search');
    try {
      const payload = await postJson(endpoints.drishtiSearch, {
        query: query.trim(),
        locations: splitCsv(locations),
        emotions: splitCsv(emotions),
        languages: language ? [language] : []
      });
      setSearchPayload(payload.search);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function generateContent() {
    setError('');
    setBusy('content');
    try {
      const payload = await postJson(endpoints.drishtiContent, {
        narrative,
        content_type: contentType,
        language: language === 'hi' ? 'Hindi' : 'English',
        tone,
        include_image: includeImage
      });
      setGenerationPayload(payload.generation);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  const overview = overviewState.data?.overview || {};
  const acquisition = overview.acquisition || {};
  const metrics = overview.metrics || {};
  const search = searchPayload || {};
  const posts = search.results || [];
  const narratives = search.narratives || overview.narratives || [];
  const graph = search.knowledge_graph || overview.knowledge_graph || {};
  const heatmap = search.heatmap || overview.heatmap || [];
  const keywords = search.keyword_recommendations || overview.trending_keywords || [];

  return (
    <section className="content-card">
      <SectionTitle title="DRISHTI Intelligence" subtitle="Monitor threat narratives, location signals, public sentiment and analyst-ready response drafts from the DRISHTI workflow." />
      <Alert type="danger">{error || overviewState.error}</Alert>
      <div className="drishti-actions">
        <button className="primary-button" onClick={refreshSources} disabled={busy === 'refresh'}>{busy === 'refresh' ? 'Refreshing...' : 'Refresh Sources'}</button>
        <span className="muted">Data source: {overview.data_source || search.data_source || 'loading'}</span>
      </div>
      <div className="stat-grid">
        <StatCard label="Posts Analyzed" value={metrics.posts_analyzed ?? '-'} />
        <StatCard label="Alerts Triggered" value={metrics.alerts_triggered ?? '-'} tone="amber" />
        <StatCard label="Languages" value={metrics.languages ?? '-'} tone="purple" />
        <StatCard label="Sources Available" value={`${acquisition.available_sources ?? '-'}/${acquisition.total_sources ?? '-'}`} tone="green" />
      </div>

      <div className="drishti-layout padded-top">
        <div className="form-stack">
          <div className="content-card compact-card">
            <h4>Intelligence Search</h4>
            <div className="drishti-search-grid">
              <label>Query<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Narrative, keyword, place, author" /></label>
              <label>Locations<input value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="Delhi, Jaipur" /></label>
              <label>Emotions<input value={emotions} onChange={(e) => setEmotions(e.target.value)} placeholder="Anxiety, Anger" /></label>
              <label>Language<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="">Any language</option><option value="en">English</option><option value="hi">Hindi</option></select></label>
            </div>
            <button className="primary-button full-width" onClick={runSearch} disabled={busy === 'search'}>{busy === 'search' ? 'Searching...' : 'Search DRISHTI'}</button>
            {search.parsed_query && <Alert type="info">{search.parsed_query}</Alert>}
          </div>

          <div className="content-card compact-card">
            <h4>Detected Posts</h4>
            <DataTable rows={posts} empty="Run a DRISHTI search to inspect matched posts." columns={[
              { key: 'created_at', label: 'Time' },
              { key: 'source', label: 'Source' },
              { key: 'location', label: 'Location' },
              { key: 'sentiment', label: 'Sentiment' },
              { key: 'risk_score', label: 'Risk' },
              { key: 'text', label: 'Text' }
            ]} />
          </div>
        </div>

        <aside className="source-stack">
          <div className="content-card compact-card">
            <h4>Source Health</h4>
            {(acquisition.sources || []).map((source) => <div className="source-card" key={source.name}><strong>{source.name}</strong><StatusPill status={source.status} /><small>{source.type} | attempts {source.attempts}</small>{source.last_error && <span>{source.last_error}</span>}</div>)}
          </div>
          <div className="content-card compact-card">
            <h4>Trending Keywords</h4>
            <div className="tag-cloud">{keywords.map((item) => <span key={item.keyword || item}>{item.keyword || item}</span>)}</div>
          </div>
        </aside>
      </div>

      <div className="drishti-layout padded-top">
        <div className="content-card compact-card">
          <h4>Narrative Cards</h4>
          <div className="narrative-grid">{narratives.map((item, index) => <div className="narrative-card" key={`${item.narrative || item.topic}-${index}`}><strong>{item.narrative || item.topic}</strong><span>{item.fault_line || item.summary || 'Narrative signal'}</span><ProgressBar value={Math.round(Number(item.risk_score || item.score || 0) * 100)} message="Risk confidence" /></div>)}</div>
        </div>
        <div className="content-card compact-card">
          <h4>Graph And Geo Signals</h4>
          <div className="summary-grid"><StatCard label="Graph Nodes" value={(graph.nodes || []).length} /><StatCard label="Graph Edges" value={(graph.edges || []).length} tone="purple" /><StatCard label="Heat Points" value={heatmap.length} tone="amber" /></div>
          <DataTable rows={heatmap.slice(0, 8)} empty="No geo heat points available." columns={[{ key: 'location', label: 'Location' }, { key: 'lat', label: 'Lat' }, { key: 'lon', label: 'Lon' }, { key: 'risk_score', label: 'Risk' }]} />
        </div>
      </div>

      <div className="content-card compact-card padded-top">
        <h4>Response Content Generator</h4>
        <div className="drishti-search-grid">
          <label>Narrative<input value={narrative} onChange={(e) => setNarrative(e.target.value)} /></label>
          <label>Content type<select value={contentType} onChange={(e) => setContentType(e.target.value)}><option>Short Post</option><option>Public Advisory</option><option>Briefing Note</option></select></label>
          <label>Tone<select value={tone} onChange={(e) => setTone(e.target.value)}><option>Calm</option><option>Urgent</option><option>Reassuring</option><option>Neutral</option></select></label>
          <label className="switch-line"><input type="checkbox" checked={includeImage} onChange={(e) => setIncludeImage(e.target.checked)} /> Include image prompt</label>
        </div>
        <button className="primary-button full-width" onClick={generateContent} disabled={busy === 'content'}>{busy === 'content' ? 'Generating...' : 'Generate Review Drafts'}</button>
        {generationPayload && <div className="generation-list">{(generationPayload.outputs || []).map((item) => <div className="generation-card" key={item.model}><strong>{item.model}</strong><p>{item.content}</p><span>Confidence: {item.confidence}</span></div>)}{generationPayload.image_prompt && <Alert type="info">Image prompt: {generationPayload.image_prompt}</Alert>}</div>}
      </div>
    </section>
  );
}

function AdminRecords() {
  const [limit, setLimit] = useState(200);
  const [tab, setTab] = useState('create');
  const [refreshTick, setRefreshTick] = useState(0);
  const [showRecords, setShowRecords] = useState(false);
  const [hiddenIds, setHiddenIds] = useState([]);
  const [message, setMessage] = useState(null);
  const [createForm, setCreateForm] = useState(emptyIdentityForm());
  const [createPhoto, setCreatePhoto] = useState(null);
  const [lookupId, setLookupId] = useState('');
  const [updateRecord, setUpdateRecord] = useState(null);
  const [updatePhoto, setUpdatePhoto] = useState(null);
  const [deleteId, setDeleteId] = useState('');
  const state = useAsync(() => getJson(endpoints.adminIdentities, { limit }), [limit, refreshTick]);
  const records = (state.data?.records || []).filter((record) => !hiddenIds.includes(record.employee_id));

  function formDataFromIdentity(values, photo, includeEmployee = true) {
    const form = new FormData();
    if (includeEmployee) form.append('employee_id', values.employee_id || '');
    identityFields.filter((field) => includeEmployee || field.key !== 'employee_id').forEach((field) => form.append(field.key, values[field.key] || ''));
    if (photo) form.append('photo', photo);
    return form;
  }

  async function createIdentity() {
    setMessage(null);
    try {
      const payload = await postForm(endpoints.adminIdentities, formDataFromIdentity(createForm, createPhoto));
      setMessage({ type: 'success', text: payload.message || 'Identity created successfully.' });
      setRefreshTick((value) => value + 1);
    } catch (err) {
      setMessage({ type: 'danger', text: err.message });
    }
  }

  async function loadIdentity() {
    setMessage(null);
    if (!lookupId.trim()) return setMessage({ type: 'danger', text: 'Enter Employee ID to load identity.' });
    try {
      const payload = await getJson(`${endpoints.adminIdentities}/${lookupId.trim()}`);
      setUpdateRecord(payload.record || {});
      setMessage({ type: 'success', text: `Loaded identity ${lookupId.trim()}.` });
    } catch (err) {
      setUpdateRecord(null);
      setMessage({ type: 'danger', text: err.message });
    }
  }

  async function updateIdentity() {
    setMessage(null);
    if (!updateRecord?.employee_id) return setMessage({ type: 'danger', text: 'Load an identity before updating.' });
    try {
      const payload = await postForm(`${endpoints.adminIdentities}/${updateRecord.employee_id}/update`, formDataFromIdentity(updateRecord, updatePhoto, false));
      setUpdateRecord(payload.record || updateRecord);
      setMessage({ type: 'success', text: payload.message || 'Identity updated successfully.' });
      setRefreshTick((value) => value + 1);
    } catch (err) {
      setMessage({ type: 'danger', text: err.message });
    }
  }

  async function deleteIdentity() {
    setMessage(null);
    if (!deleteId.trim()) return setMessage({ type: 'danger', text: 'Select or type Employee ID to delete.' });
    try {
      const payload = await postForm(`${endpoints.adminIdentities}/${deleteId.trim()}/delete`, new FormData());
      setMessage({ type: 'success', text: payload.message || 'Identity deleted successfully.' });
      setRefreshTick((value) => value + 1);
    } catch (err) {
      setMessage({ type: 'danger', text: err.message });
    }
  }

  return (
    <section className="content-card">
      <SectionTitle title="Admin Identity Operations" subtitle="Create, update, delete, review, or hide loaded identity records without leaving the dashboard." />
      <Alert type="info">Only Employee ID and Full Name are required. Leave optional government IDs blank when a person does not have that document.</Alert>
      {message && <Alert type={message.type}>{message.text}</Alert>}
      <div className="summary-grid"><StatCard label="Identity Records Loaded" value={state.data?.total_records ?? records.length} /><StatCard label="Visible Records" value={records.length} tone="green" /><StatCard label="Hidden This Session" value={hiddenIds.length} tone="amber" /></div>
      <div className="action-row padded-top"><select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>{[50, 100, 200, 500].map((item) => <option key={item} value={item}>{item} records</option>)}</select><button className="ghost-button" onClick={() => setShowRecords((value) => !value)}>{showRecords ? 'Hide Loaded Records' : 'View Loaded Records'}</button><button className="ghost-button" onClick={() => setHiddenIds([])}>Reset Hidden Records</button></div>
      <Alert type="danger">{state.error}</Alert>
      {showRecords && <DataTable rows={records} columns={[{ key: 'photo_path', label: 'Photo', render: (row) => <ImageBox src={identityPhotoPath(row)} size="lg" /> }, { key: 'employee_id', label: 'Employee ID' }, { key: 'full_name', label: 'Full Name' }, { key: 'date_of_birth', label: 'DOB' }, { key: 'department', label: 'Department' }, { key: 'state', label: 'State' }, { key: 'email', label: 'Email' }, { key: 'phone_number', label: 'Phone' }, { key: 'hide', label: 'Hide', render: (row) => <button className="ghost-button" onClick={() => setHiddenIds((items) => [...new Set([...items, row.employee_id])])}>Hide</button> }]} />}
      <div className="segmented padded-top"><button className={tab === 'create' ? 'active' : ''} onClick={() => setTab('create')}>Create Identity</button><button className={tab === 'update' ? 'active' : ''} onClick={() => setTab('update')}>Update Identity</button><button className={tab === 'delete' ? 'active' : ''} onClick={() => setTab('delete')}>Delete Identity</button></div>
      {tab === 'create' && <IdentityForm title="Create Identity" values={createForm} setValues={setCreateForm} photo={createPhoto} setPhoto={setCreatePhoto} onSubmit={createIdentity} submitLabel="Create Identity" includeEmployee />}
      {tab === 'update' && <div className="form-stack padded-top"><div className="inline-form"><input value={lookupId} onChange={(e) => setLookupId(e.target.value)} placeholder="Employee ID to update" /><button className="primary-button" onClick={loadIdentity}>Load Identity</button></div>{updateRecord && <IdentityForm title="Update Identity" values={updateRecord} setValues={setUpdateRecord} photo={updatePhoto} setPhoto={setUpdatePhoto} onSubmit={updateIdentity} submitLabel="Update Identity" />}</div>}
      {tab === 'delete' && <div className="form-stack padded-top"><label>Select identity to delete<select value={deleteId} onChange={(e) => setDeleteId(e.target.value)}><option value="">Select Employee ID</option>{records.map((record) => <option key={record.employee_id} value={record.employee_id}>{record.employee_id} - {record.full_name}</option>)}</select></label>{deleteId && <IdentityProfile identity={records.find((record) => record.employee_id === deleteId)} title="Selected Identity" />}<button className="ghost-button danger" onClick={deleteIdentity}>Delete Identity</button></div>}
    </section>
  );
}

const identityFields = [
  { key: 'employee_id', label: 'Employee ID' },
  { key: 'full_name', label: 'Full Name' },
  { key: 'date_of_birth', label: 'Date of Birth' },
  { key: 'aadhar_number', label: 'Aadhaar Number' },
  { key: 'pan_number', label: 'PAN Number' },
  { key: 'voter_id_number', label: 'Voter ID Number' },
  { key: 'driving_license_number', label: 'Driving Licence Number' },
  { key: 'passport_number', label: 'Passport Number' },
  { key: 'phone_number', label: 'Phone Number' },
  { key: 'email', label: 'Email' },
  { key: 'department', label: 'Department' },
  { key: 'state', label: 'State' }
];

function emptyIdentityForm() {
  return Object.fromEntries(identityFields.map((field) => [field.key, '']));
}

function IdentityForm({ title, values, setValues, photo, setPhoto, onSubmit, submitLabel, includeEmployee = false }) {
  const fields = identityFields.filter((field) => includeEmployee || field.key !== 'employee_id');
  const preview = useObjectUrl(photo);
  return (
    <div className="content-card compact-card padded-top">
      <h4>{title}</h4>
      <div className="admin-form-grid">
        {fields.map((field) => <label key={field.key}>{field.label}<input value={values[field.key] || ''} onChange={(e) => setValues((current) => ({ ...(current || {}), [field.key]: e.target.value }))} /></label>)}
        <label>Profile Photo<input type="file" accept="image/*" onChange={(e) => setPhoto(e.target.files?.[0] || null)} /></label>
      </div>
      {preview && <ImageBox src={preview} size="md" />}
      <button className="primary-button full-width" onClick={onSubmit}>{submitLabel}</button>
    </div>
  );
}

export default function App() {
  const [active, setActive] = useSessionState('app.activeSection', 'identity');
  const page = useMemo(() => ({
    identity: <IdentitySearch />,
    document: <DocumentValidation />,
    face: <FaceIntelligence />,
    news: <NewsIntelligence />,
    drishti: <DrishtiIntelligence />,
    admin: <AdminRecords />
  }[active] || <IdentitySearch />), [active]);

  return <Shell active={active} setActive={setActive}>{page}</Shell>;
}
