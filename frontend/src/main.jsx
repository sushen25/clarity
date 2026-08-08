import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle, ArrowLeft, Check, ChevronRight, ClipboardCheck, FileText,
  FolderOpen, LogOut, Plus, RefreshCw, ShieldCheck, Upload, UserRound,
} from "lucide-react";
import { criteriaGroups, criteriaLabels, criterionOutcomeLabels } from "./clinical";
import "./styles.css";

let csrfToken = "";
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && options.body) headers["Content-Type"] = "application/json";
  if (csrfToken && !["GET", "HEAD"].includes(options.method || "GET")) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(`/api${path}`, { credentials: "same-origin", ...options, headers });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(data.message || data.error || "Request failed"), { data, status: response.status });
  return data;
}

function Notice({ tone = "info", children }) { return <div className={`notice ${tone}`}><AlertTriangle size={17}/><span>{children}</span></div>; }
function Button({ variant = "primary", icon: Icon, children, ...props }) {
  return <button className={`button ${variant}`} {...props}>{Icon && <Icon size={16}/>} {children}</button>;
}

function Login({ onLogin }) {
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError("");
    try { const result = await api("/auth/login", { method: "POST", body: JSON.stringify(form) }); csrfToken = result.csrf_token; onLogin(result.user); }
    catch (err) { setError(err.data?.error === "account_locked" ? "Account temporarily locked. Try again later." : "The username or password was not recognised."); }
    finally { setBusy(false); }
  }
  return <main className="login-shell">
    <section className="login-brand"><div className="brand-mark">C</div><p>CLINICAL REPORT WORKSPACE</p><h1>Clear evidence.<br/>Clinician judgement.</h1><p className="lede">A focused workspace for preparing adult and adolescent ADHD assessment reports.</p></section>
    <section className="login-panel"><form className="login-card" onSubmit={submit}>
      <div className="eyebrow">SECURE CLINICIAN ACCESS</div><h2>Welcome back</h2><p>Sign in with the account created by your administrator.</p>
      {error && <Notice tone="danger">{error}</Notice>}
      <label>Username<input autoComplete="username" value={form.username} onChange={e=>setForm({...form,username:e.target.value})} required/></label>
      <label>Password<input type="password" autoComplete="current-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} required/></label>
      <Button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      <p className="security-note"><ShieldCheck size={15}/>Protected health information. Authorised clinicians only.</p>
    </form></section>
  </main>;
}

function Shell({ user, children, onLogout }) {
  return <div className="app-shell"><header className="topbar"><div className="wordmark"><span>C</span><div><strong>Clarity</strong><small>ADHD report workspace</small></div></div><div className="user-menu"><UserRound size={17}/><span>{user.full_name}</span><button onClick={onLogout} title="Sign out"><LogOut size={17}/></button></div></header>{children}</div>;
}

function CaseList({ onOpen }) {
  const [cases, setCases] = useState([]); const [showNew, setShowNew] = useState(false); const [error, setError] = useState("");
  async function load(){ try{ setCases(await api("/cases")); }catch(e){setError(e.message)} }
  useEffect(()=>{load()},[]);
  return <main className="page"><div className="page-head"><div><div className="eyebrow">CLINICIAN DASHBOARD</div><h1>Assessment cases</h1><p>Prepare, review and approve evidence-grounded reports.</p></div><Button icon={Plus} onClick={()=>setShowNew(true)}>New case</Button></div>
    {error && <Notice tone="danger">{error}</Notice>}
    <div className="case-grid">{cases.map(item=><button key={item.id} className="case-card" onClick={()=>onOpen(item.id)}><div className="case-icon"><FolderOpen/></div><div><div className="case-top"><span className={`pill ${item.status}`}>{item.status.replaceAll("-"," ")}</span><small>{item.cohort}</small></div><h3>{item.patient_initials}</h3><p>{item.referral_question || "Referral question not yet entered"}</p><small>Updated {new Date(item.updated_at).toLocaleDateString()}</small></div><ChevronRight/></button>)}</div>
    {!cases.length && <div className="empty"><FileText size={36}/><h3>No assessment cases yet</h3><p>Create the first case to begin organising evidence.</p></div>}
    {showNew && <NewCase onClose={()=>setShowNew(false)} onCreated={id=>onOpen(id)}/>}</main>;
}

function NewCase({ onClose, onCreated }) {
  const [form,setForm]=useState({cohort:"adult",patient_initials:"",referral_question:"",cloud_consent:false}); const [error,setError]=useState("");
  async function submit(e){e.preventDefault();try{const value=await api("/cases",{method:"POST",body:JSON.stringify(form)});onCreated(value.id)}catch(err){setError(err.message)}}
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}><div className="eyebrow">NEW ASSESSMENT</div><h2>Create a case</h2>{error&&<Notice tone="danger">{error}</Notice>}
    <label>Patient initials<input value={form.patient_initials} onChange={e=>setForm({...form,patient_initials:e.target.value})} maxLength={12} required/></label>
    <label>Cohort<select value={form.cohort} onChange={e=>setForm({...form,cohort:e.target.value})}><option value="adult">Adult</option><option value="adolescent">Adolescent</option></select></label>
    <label>Referral question<textarea rows="3" value={form.referral_question} onChange={e=>setForm({...form,referral_question:e.target.value})}/></label>
    <label className="check"><input type="checkbox" checked={form.cloud_consent} onChange={e=>setForm({...form,cloud_consent:e.target.checked})}/><span>The patient privacy notice permits AI processing within Australia.</span></label>
    <div className="actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button>Create case</Button></div></form></div>;
}

function CaseWorkspace({ caseId, onBack }) {
  const [data,setData]=useState(null), [tab,setTab]=useState("overview"), [error,setError]=useState("");
  async function load(){try{setData(await api(`/cases/${caseId}`));setError("")}catch(e){setError(e.message)}}
  useEffect(()=>{load()},[caseId]);
  useEffect(()=>{if(!data?.jobs?.some(j=>["queued","running"].includes(j.status)))return;const id=setInterval(load,2500);return()=>clearInterval(id)},[data?.jobs]);
  if(!data)return <main className="page"><Button variant="ghost" icon={ArrowLeft} onClick={onBack}>Cases</Button>{error?<Notice tone="danger">{error}</Notice>:<p>Loading case…</p>}</main>;
  const tabs=[['overview','Overview'],['sources','Sources'],['evidence',`Evidence (${data.evidence.length})`],['criteria','Criteria'],['report','Report']];
  return <main className="workspace"><aside className="case-nav"><Button variant="ghost" icon={ArrowLeft} onClick={onBack}>All cases</Button><div className="case-identity"><span>{data.case.cohort}</span><h2>{data.case.patient_initials}</h2><p>{data.case.referral_question||"No referral question"}</p></div><nav>{tabs.map(([key,label])=><button key={key} className={tab===key?"active":""} onClick={()=>setTab(key)}>{label}<ChevronRight size={15}/></button>)}</nav><div className="case-status"><small>REPORT STATUS</small><strong>{data.case.status.replaceAll("-"," ")}</strong></div></aside>
    <section className="workspace-main">{error&&<Notice tone="danger">{error}</Notice>}{tab==='overview'&&<Overview data={data} reload={load}/>} {tab==='sources'&&<Sources data={data} reload={load}/>} {tab==='evidence'&&<Evidence data={data} reload={load}/>} {tab==='criteria'&&<Criteria data={data} reload={load}/>} {tab==='report'&&<Report data={data} reload={load}/>}</section></main>;
}

function Overview({data,reload}) {
  const c=data.case; const [form,setForm]=useState({referral_question:c.referral_question,final_diagnostic_conclusion:c.final_diagnostic_conclusion,cloud_consent:c.cloud_consent,assessment_dates:(c.assessment_dates||[]).join(', '),instruments:(c.instruments||[]).join(', ')});
  async function save(){await api(`/cases/${c.id}`,{method:"PATCH",body:JSON.stringify({...form,assessment_dates:form.assessment_dates.split(',').map(x=>x.trim()).filter(Boolean),instruments:form.instruments.split(',').map(x=>x.trim()).filter(Boolean)})});reload()}
  return <div><PageTitle eyebrow="CASE INTAKE" title="Overview" text="Clinical context and completion safeguards."/><div className="stats"><Stat value={data.sources.length} label="Sources"/><Stat value={data.evidence.filter(e=>e.verified).length} label="Verified evidence"/><Stat value={data.criteria.filter(c=>c.clinician_outcome!=="unreviewed").length+"/18"} label="Criteria reviewed"/></div>
    {!!data.warnings.length&&<section className="panel"><h3>Clinical completeness</h3>{data.warnings.map((w,i)=><Notice key={i}>{w}</Notice>)}</section>}
    <section className="panel form-grid"><label className="wide">Referral question<textarea rows="4" value={form.referral_question} onChange={e=>setForm({...form,referral_question:e.target.value})}/></label><label>Assessment dates<input value={form.assessment_dates} onChange={e=>setForm({...form,assessment_dates:e.target.value})} placeholder="2026-08-01, 2026-08-03"/></label><label>Instruments<input value={form.instruments} onChange={e=>setForm({...form,instruments:e.target.value})} placeholder="DIVA-5, ASRS"/></label><label className="wide">Clinician diagnostic conclusion<textarea rows="5" value={form.final_diagnostic_conclusion} onChange={e=>setForm({...form,final_diagnostic_conclusion:e.target.value})} placeholder="Entered by the approving clinician; the model cannot decide this."/></label><label className="check wide"><input type="checkbox" checked={form.cloud_consent} onChange={e=>setForm({...form,cloud_consent:e.target.checked})}/><span>Cloud-processing consent acknowledged</span></label><div className="wide actions"><Button onClick={save}>Save overview</Button></div></section><InstrumentPanel data={data} reload={reload}/></div>;
}
function InstrumentPanel({data,reload}){const[form,setForm]=useState({instrument:"",version:"",respondent:"",interpretation:"",verified:false});async function add(e){e.preventDefault();await api(`/cases/${data.case.id}/instruments`,{method:'POST',body:JSON.stringify({...form,scores:{}})});setForm({instrument:"",version:"",respondent:"",interpretation:"",verified:false});reload()}return <section className="panel"><h3>Scored instrument summaries</h3><p className="muted">Enter only authorised, already-scored results. The application does not calculate proprietary scores.</p><div className="list">{data.instruments.map(x=><div className="list-row" key={x.id}><div className="file-badge"><ClipboardCheck/></div><div><strong>{x.instrument} {x.version}</strong><p>{x.respondent||'Respondent not set'} · {x.interpretation||'No clinician interpretation'}</p></div><span className={`pill ${x.verified?'verified':''}`}>{x.verified?'verified':'unverified'}</span></div>)}</div><form className="form-grid instrument-form" onSubmit={add}><label>Instrument<input required value={form.instrument} onChange={e=>setForm({...form,instrument:e.target.value})}/></label><label>Version<input value={form.version} onChange={e=>setForm({...form,version:e.target.value})}/></label><label>Respondent<input value={form.respondent} onChange={e=>setForm({...form,respondent:e.target.value})}/></label><label className="check"><input type="checkbox" checked={form.verified} onChange={e=>setForm({...form,verified:e.target.checked})}/><span>Scores independently verified</span></label><label className="wide">Clinician interpretation<textarea rows="3" value={form.interpretation} onChange={e=>setForm({...form,interpretation:e.target.value})}/></label><div className="wide actions"><Button variant="secondary">Add summary</Button></div></form></section>}
function Stat({value,label}){return <div className="stat"><strong>{value}</strong><span>{label}</span></div>}
function PageTitle({eyebrow,title,text,action}){return <div className="section-head"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{text}</p></div>{action}</div>}

function Sources({data,reload}) {
  const [file,setFile]=useState(null),[meta,setMeta]=useState({source_type:"transcript",reporter:"",setting:"unspecified",instrument:""}),[busy,setBusy]=useState(false),[error,setError]=useState("");
  async function upload(e){e.preventDefault();if(!file)return;setBusy(true);setError("");const body=new FormData();body.append('file',file);Object.entries(meta).forEach(([k,v])=>body.append(k,v));try{await api(`/cases/${data.case.id}/sources`,{method:'POST',body});setFile(null);await reload()}catch(err){setError(err.message)}finally{setBusy(false)}}
  return <div><PageTitle eyebrow="SOURCE MATERIAL" title="Documents" text="TXT, DOCX and text-based PDFs. Maximum 25 MB each."/>{error&&<Notice tone="danger">{error}</Notice>}<form className="upload-panel" onSubmit={upload}><Upload size={28}/><div><h3>Add source material</h3><p>Raw proprietary test responses and macro-enabled files are not accepted.</p></div><input type="file" accept=".txt,.docx,.pdf" onChange={e=>setFile(e.target.files[0])}/><select value={meta.source_type} onChange={e=>setMeta({...meta,source_type:e.target.value})}><option value="transcript">Session transcript</option><option value="questionnaire">Questionnaire narrative</option><option value="collateral">Collateral report</option><option value="instrument_export">Scored instrument export</option></select><input placeholder="Reporter (e.g. parent)" value={meta.reporter} onChange={e=>setMeta({...meta,reporter:e.target.value})}/><select value={meta.setting} onChange={e=>setMeta({...meta,setting:e.target.value})}>{['unspecified','home','school','work','social','clinical','other'].map(x=><option key={x}>{x}</option>)}</select><Button disabled={!file||busy}>{busy?'Uploading…':'Upload & extract'}</Button></form>
  <div className="list">{data.sources.map(s=><div className="list-row" key={s.id}><div className="file-badge"><FileText/></div><div><strong>{s.original_filename}</strong><p>{s.source_type} · {s.reporter||'Reporter not set'} · {s.setting||'Setting not set'}</p></div><span className={`pill ${s.extraction_status}`}>{s.extraction_status}</span></div>)}</div></div>;
}

function Evidence({data,reload}) {
  const [filter,setFilter]=useState('all'),[error,setError]=useState('');
  const domainOptions=data.evidence_domains||[]; const items=data.evidence.filter(e=>filter==='all'||e.domain===filter);
  async function update(item,patch){setError('');try{await api(`/cases/${data.case.id}/evidence/${item.id}`,{method:'PATCH',body:JSON.stringify(patch)});await reload()}catch(err){setError(err.message)}}
  return <div><PageTitle eyebrow="EVIDENCE LEDGER" title="Verify extracted evidence" text="Review the extracted domain and evidence before verification."/>{error&&<Notice tone="danger">{error}</Notice>}<div className="toolbar"><select aria-label="Filter evidence by domain" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All domains</option>{domainOptions.map(d=><option key={d.value} value={d.value}>{d.label}</option>)}</select><span>{items.filter(i=>i.verified).length} verified in this view</span></div><div className="evidence-list">{items.map(item=><article className={`evidence-card ${item.verified?'verified':''}`} key={item.id}><div className="evidence-meta"><label className="evidence-domain">Domain<select aria-label="Evidence domain" value={item.domain} title={domainOptions.find(d=>d.value===item.domain)?.description} onChange={e=>update(item,{domain:e.target.value})}>{domainOptions.map(d=><option key={d.value} value={d.value}>{d.label}</option>)}</select></label><small>{item.reporter||'Unknown reporter'} · {item.setting}</small></div><p>“{item.supporting_text}”</p><div className="evidence-foot"><small>{item.source_location} · confidence {Math.round(item.confidence*100)}%</small><label className="check"><input type="checkbox" checked={item.verified} onChange={e=>update(item,{verified:e.target.checked})}/><span>{item.verified?'Verified':'Verify'}</span></label></div></article>)}</div>{!items.length&&<div className="empty"><ClipboardCheck/><h3>No extracted evidence</h3><p>Upload and process a source document first.</p></div>}</div>;
}

function Criteria({data,reload}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  async function change(item,outcome){setError("");try{await api(`/cases/${data.case.id}/criteria/${item.criterion_id}`,{method:'PUT',body:JSON.stringify({...item,clinician_outcome:outcome})});await reload()}catch(err){setError(err.message)}}
  async function setAllMet(){setBusy(true);setError("");try{await Promise.all(data.criteria.map(item=>api(`/cases/${data.case.id}/criteria/${item.criterion_id}`,{method:'PUT',body:JSON.stringify({...item,clinician_outcome:'met'})})));await reload()}catch(err){setError(err.message)}finally{setBusy(false)}}
  const allMet=data.criteria.every(item=>item.clinician_outcome==='met');
  return <div><PageTitle eyebrow="CLINICIAN DECISION" title="Diagnostic criteria" text="The clinician—not the model—sets each criterion outcome." action={<Button variant="secondary" icon={Check} onClick={setAllMet} disabled={busy||allMet}>{busy?'Setting all to Met…':allMet?'All criteria Met':'Set all to Met'}</Button>}/>{error&&<Notice tone="danger">{error}</Notice>}<Notice>Rating scales are supporting evidence and cannot independently establish a diagnosis.</Notice><div className="criteria-grid">{data.criteria.map(item=><div className="criterion" key={item.criterion_id}><div><strong>{item.criterion_id}</strong><span>{criteriaLabels[item.criterion_id]}</span></div><select className={item.clinician_outcome} value={item.clinician_outcome} disabled={busy} onChange={e=>change(item,e.target.value)}><option value="unreviewed">Unreviewed</option><option value="met">Met</option><option value="not_met">Not met</option><option value="insufficient">Insufficient evidence</option></select></div>)}</div></div>;
}

function CriteriaReportTable({criteria}) {
  const byId=new Map(criteria.map(item=>[item.criterion_id,item]));
  return <div className="criteria-report">{criteriaGroups.map(group=><table key={group.prefix}><thead><tr><th>{group.title}</th><th>Clinician outcome</th></tr></thead><tbody>{Object.entries(criteriaLabels).filter(([id])=>id.startsWith(group.prefix)).map(([id,label],index)=>{const outcome=byId.get(id)?.clinician_outcome||'unreviewed';return <tr key={id}><td><span>{String.fromCharCode(97+index)}.</span>{label}</td><td className={outcome}>{outcome==='met'&&<Check size={15}/>} {criterionOutcomeLabels[outcome]||criterionOutcomeLabels.unreviewed}</td></tr>})}</tbody></table>)}</div>;
}

function Report({data,reload}) {
  const draft=data.drafts[0]; const draftJobs=data.jobs.filter(j=>j.job_type==='generate_draft'); const activeJob=draftJobs.find(j=>['queued','running'].includes(j.status)); const latestFailedJob=draftJobs.find(j=>j.status==='failed'); const [selectedEvidence,setSelectedEvidence]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
  async function generate(){setBusy(true);try{await api(`/cases/${data.case.id}/drafts`,{method:'POST',body:'{}'});await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function save(patch){setBusy(true);try{await api(`/cases/${data.case.id}/drafts/${draft.id}`,{method:'PATCH',body:JSON.stringify(patch)});await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function approve(){setBusy(true);try{await api(`/cases/${data.case.id}/drafts/${draft.id}/approve`,{method:'POST',body:'{}'});await reload()}catch(e){setError(e.data?.requirements?.join(' ')||e.message)}finally{setBusy(false)}}
  function editParagraph(si,pi,text){const sections=structuredClone(draft.sections);sections[si].paragraphs[pi].text=text;save({sections})}
  if(!draft)return <div><PageTitle eyebrow="REPORT DRAFT" title="Generate report" text="Drafting uses verified evidence and clinician-entered decisions only." action={<Button icon={RefreshCw} onClick={generate} disabled={busy||!!activeJob}>{activeJob?'Generating…':'Generate draft'}</Button>}/>{error&&<Notice tone="danger">{error}</Notice>}{activeJob&&<Notice>Draft generation is {activeJob.status}. Attempt {activeJob.attempts} of 3; this page will update automatically.</Notice>}{!activeJob&&latestFailedJob&&<Notice tone="danger">Draft generation failed ({latestFailedJob.last_error||'unknown error'}). No report was saved; review the worker log before retrying.</Notice>}<div className="empty"><FileText/><h3>{activeJob?'Draft generation in progress':'No draft generated'}</h3><p>{activeJob?'Bedrock is preparing the evidence-grounded sections.':'Verify source evidence before requesting a draft.'}</p></div></div>;
  const displaySections=draft.sections.map((section,index)=>({section,sourceIndex:index}));
  if(!displaySections.some(item=>item.section.key==='diagnostic_criteria')){const summaryIndex=displaySections.findIndex(item=>item.section.key==='summary');displaySections.splice(summaryIndex<0?displaySections.length:summaryIndex,0,{section:{key:'diagnostic_criteria',heading:'Diagnostic Criteria',paragraphs:[]},sourceIndex:null})}
  return <div><PageTitle eyebrow={`REPORT • VERSION ${draft.version}`} title="Review report" text={`${draft.model_id} · ${draft.prompt_version}`} action={<div className="actions"><Button variant="ghost" icon={RefreshCw} onClick={generate} disabled={busy}>New version</Button>{draft.docx_path&&<a className="button secondary" href={`/api/cases/${data.case.id}/drafts/${draft.id}/docx`}>Download DOCX</a>}</div>}/>{error&&<Notice tone="danger">{error}</Notice>}{draft.warnings.map((w,i)=><Notice key={i}>{w}</Notice>)}
  <div className="report-layout"><div className="report-paper">{displaySections.map(({section,sourceIndex})=>{const isCriteria=section.key==='diagnostic_criteria';return <section key={section.key}><h2>{section.heading}</h2>{isCriteria&&<CriteriaReportTable criteria={data.criteria}/>} {section.paragraphs.length?section.paragraphs.map((p,pi)=><div key={`${draft.updated_at}-${pi}`} className="draft-paragraph"><textarea defaultValue={p.text} rows={Math.max(3,Math.ceil(p.text.length/105))} disabled={draft.state==='clinician-approved'} onBlur={e=>e.target.value!==p.text&&editParagraph(sourceIndex,pi,e.target.value)}/><button onClick={()=>setSelectedEvidence(p.evidence_ids)}>{p.evidence_ids.length} source{p.evidence_ids.length===1?'':'s'}</button></div>):!isCriteria&&<p className="muted">Information not supplied or not yet verified.</p>}</section>})}</div><aside className="evidence-side"><h3>Supporting evidence</h3>{selectedEvidence.length?selectedEvidence.map(id=>{const e=data.evidence.find(x=>x.id===id);return e?<blockquote key={id}>“{e.supporting_text}”<small>{e.reporter||'Unknown'} · {e.setting} · {e.source_location}</small></blockquote>:null}):<p>Select a paragraph’s source count to inspect its evidence.</p>}</aside></div>
  <section className="approval-bar"><label className="check"><input type="checkbox" checked={draft.warnings_acknowledged} disabled={draft.state==='clinician-approved'} onChange={e=>save({warnings_acknowledged:e.target.checked})}/><span>I have reviewed and accept responsibility for unresolved warnings.</span></label><div className="actions">{draft.state==='draft'&&<Button variant="secondary" onClick={()=>save({state:'review-ready'})}>Mark review-ready</Button>}{draft.state==='review-ready'&&<Button icon={Check} onClick={approve}>Approve report</Button>}<span className={`pill ${draft.state}`}>{draft.state}</span></div></section></div>;
}

function App(){const[user,setUser]=useState(null),[selected,setSelected]=useState(null),[loading,setLoading]=useState(true);useEffect(()=>{api('/auth/session').then(r=>{csrfToken=r.csrf_token;setUser(r.user)}).catch(()=>{}).finally(()=>setLoading(false))},[]);async function logout(){await api('/auth/logout',{method:'POST',body:'{}'});csrfToken='';setUser(null)}if(loading)return null;if(!user)return <Login onLogin={setUser}/>;return <Shell user={user} onLogout={logout}>{selected?<CaseWorkspace caseId={selected} onBack={()=>setSelected(null)}/>:<CaseList onOpen={setSelected}/>}</Shell>}

createRoot(document.getElementById("root")).render(<App/>);
