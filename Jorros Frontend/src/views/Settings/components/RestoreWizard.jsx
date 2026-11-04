'use client';
import { useEffect, useState } from 'react';
import { backupRecoveryService as api } from '../../../services/backupRecoveryService.js';
import { RecoveryDialog, CredentialsForm, Status, backupDate } from './RecoveryDialog.jsx';
export default function RestoreWizard({ overview, initial, pendingJob, onClose, onRefresh }) {
    const [selected, setSelected] = useState(initial), [jobId, setJobId] = useState(pendingJob), [step, setStep] = useState(initial?.status === 'Ready' ? 4 : initial ? 2 : pendingJob ? 3 : 1);
    const [source, setSource] = useState('computer'), [format, setFormat] = useState('zip'), [file, setFile] = useState(null), [assets, setAssets] = useState(null), [key, setKey] = useState('');
    const [cloud, setCloud] = useState([]), [cloudId, setCloudId] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
    const candidate = overview.drills.find(value => value.id === selected?.id) || selected, job = overview.jobs.find(value => value.id === jobId);
    const activating = job?.kind === 'activate' && ['Queued', 'Running'].includes(job.status), expired = candidate?.expires_at && new Date(candidate.expires_at).getTime() <= Date.now();
    useEffect(() => {
        if (job?.status === 'Completed') {
            const id = job.result?.id || job.result?.candidate_id, found = overview.drills.find(value => value.id === id);
            if (found) setSelected(found);
            setStep(job.kind === 'activate' ? 5 : job.kind === 'cloud_import' ? 2 : 4);
        }
        if (job && ['Failed', 'Incomplete', 'Partial'].includes(job.status)) setError(job.error || 'This recovery step did not complete.');
    }, [job, overview.drills]);
    const run = async action => { if (busy) return; setBusy(true); setError(''); try { await action(); } catch (failure) { setError(failure.message); } finally { setBusy(false); } };
    return <RecoveryDialog title="Restore Backup" onClose={onClose} busy={busy || activating} wide>
        <p>Validate and test a separate copy before replacing farm data.</p>
        <ol className="br-steps" aria-label="Recovery steps">{['Choose', 'Preview', 'Test', 'Confirm', 'Activate'].map((label, i) => <li className={step === i + 1 ? 'active' : ''} aria-current={step === i + 1 ? 'step' : undefined} key={label}><span>{i + 1}</span>{label}</li>)}</ol>
        {error && <p className="br-error" role="alert">{error}</p>}
        {step === 1 && <form className="br-form" onSubmit={event => { event.preventDefault(); run(async () => {
            if (source === 'drive') { const value = await api.prepareCloud({ backup_id: cloudId, format, recovery_key: key }); setJobId(value.id); setStep(3); }
            else {
                if (!file || (format === 'bak' && !assets)) throw new Error('Select the backup and matching photo package when using BAK.');
                const form = new FormData(); form.append('primary', file); if (format === 'bak') form.append('companion', assets); if (key) form.append('recovery_key', key);
                setSelected(await api.importBackup(form)); setStep(2);
            }
            await onRefresh();
        }); }}>
            <fieldset className="br-source"><legend>Backup source</legend><label><input type="radio" checked={source === 'computer'} onChange={() => setSource('computer')}/>This computer</label><label><input type="radio" checked={source === 'drive'} disabled={overview.drive.status !== 'Connected'} onChange={() => run(async () => { setSource('drive'); setCloud(await api.cloudBackups()); })}/>Google Drive</label></fieldset>
            <label>Backup format<select value={format} onChange={event => { setFormat(event.target.value); setFile(null); setAssets(null); }}><option value="zip">Recovery ZIP — records and photos</option><option value="bak">SQL Server BAK + matching photo package</option></select></label>
            {source === 'computer' ? <><label>{format === 'zip' ? 'Recovery ZIP file' : 'SQL Server BAK file'}<input key={format} type="file" required accept={format === 'zip' ? '.zip,.enc' : '.bak,.enc'} onChange={event => setFile(event.target.files[0])}/></label>{format === 'bak' && <label>Matching photos and manifest package<input type="file" required accept=".zip,.enc" onChange={event => setAssets(event.target.files[0])}/><small>A BAK alone does not contain evidence photos. Use its matching .photos.zip.</small></label>}</> : <label>Google Drive recovery set<select required value={cloudId} onChange={event => setCloudId(event.target.value)}><option value="">Choose a backup</option>{cloud.filter(value => value.artifacts[format] && (format !== 'bak' || value.artifacts.assets)).map(value => <option key={value.id} value={value.id}>{backupDate(value.created_at)} · {value.id.slice(0, 12)}</option>)}</select></label>}
            <label>Recovery key file (if this server needs the matching key)<input type="file" accept=".key" onChange={event => { const value = event.target.files[0]; run(async () => { if (value?.size > 1024) throw new Error('Choose the small Joross recovery key file.'); setKey(value ? (await value.text()).trim() : ''); }); }}/></label>
            <p className="br-note">The current farm stays in place during validation and testing.</p><footer><button className="br-primary" disabled={busy}>{busy ? 'Validating...' : source === 'drive' ? 'Download & Validate' : 'Validate Backup'}</button></footer>
        </form>}
        {step === 2 && candidate && <><div className="br-preview">{[['Backup date', backupDate(candidate.source_date)], ['Format', candidate.format.toUpperCase()], ['Records', candidate.row_count], ['Tables', candidate.table_count], ['Photo files and thumbnails', candidate.photo_count]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}<div><span>File checks</span><Status value={candidate.file_validated ? 'File validated' : 'Needs attention'}/></div></div>
            {candidate.status === 'Test failed' && <p className="br-error">{candidate.error} Discard this staged copy before preparing another test.</p>}
            <footer><button type="button" onClick={() => { setSelected(null); setStep(1); }}>Choose another backup</button><button type="button" className="br-primary" disabled={busy || candidate.status !== 'Validated'} onClick={() => run(async () => { const value = await api.test(candidate.id); setJobId(value.id); setStep(3); await onRefresh(); })}>Test Restore</button></footer></>}
        {step === 3 && <div role="status" className="br-progress"><h3>{job?.kind === 'cloud_import' ? 'Downloading and validating' : 'Testing the separate recovery copy'}</h3><p>{job?.stage || 'Waiting for the background worker'}</p><p>This job can continue after you close this window.</p></div>}
        {step === 4 && candidate && <><div className="br-success"><strong>Restore test passed</strong><p>Record checksums, relationships, photos and administrator access checks passed in the separate copy.</p></div><p>Tested {backupDate(candidate.tested_at)}. Available until {backupDate(candidate.expires_at)}.</p>
            {expired ? <p className="br-notice">This test expired. Discard this staged copy and prepare a fresh test.</p> : !overview.readiness.activation_enabled ? <p className="br-notice">Activation is disabled until recovery testing and server setup are completed on this installation.</p> : <CredentialsForm action="Restore and Activate" confirmation onBusy={setBusy} onSubmit={async credentials => { const value = await api.activate(candidate.id, credentials); setJobId(value.id); setStep(5); await onRefresh(); }}/>}</>}
        {step === 5 && <div className="br-progress" role="status"><h3>{job?.status === 'Completed' ? 'Recovery copy activated' : 'Activation requested'}</h3><p>{job?.stage || 'Preparing the safety backup and maintenance window'}</p><p>Keep the server running. Everyone must sign in again after activation.</p></div>}
    </RecoveryDialog>;
}
