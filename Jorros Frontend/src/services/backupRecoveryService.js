import { httpClient } from './httpClient.js';
const root = '/backup-recovery';
const fresh = { cache: 'no-store' };
export const backupRecoveryService = Object.freeze({
    overview: () => httpClient.get(root + '/overview', fresh),
    notices: () => httpClient.get(root + '/notices', fresh),
    saveSettings: value => httpClient.put(root + '/settings', value),
    readiness: () => httpClient.post(root + '/readiness', {}, { timeoutMs: 60000 }),
    create: (value, key) => httpClient.post(root + '/backups', value, { headers: { 'Idempotency-Key': key } }),
    protect: (id, keep) => httpClient.patch(`${root}/backups/${id}/keep`, { keep }),
    remove: (id, confirmation) => httpClient.post(`${root}/backups/${id}/delete`, { confirmation }),
    upload: id => httpClient.post(`${root}/backups/${id}/upload`, {}),
    retry: id => httpClient.post(`${root}/jobs/${id}/retry`, {}),
    download: (id, kind, decrypt = false) => httpClient.download(`${root}/backups/${id}/download/${kind}`, { ...fresh, timeoutMs: 300000, query: { decrypt } }),
    recoveryKey: credentials => httpClient.post(root + '/recovery-key', credentials, { ...fresh, responseType: 'blob' }),
    connectDrive: () => httpClient.post(root + '/drive/connect', {}),
    disconnectDrive: () => httpClient.post(root + '/drive/disconnect', {}),
    driveStorage: () => httpClient.get(root + '/drive/storage', fresh),
    driveFolder: value => httpClient.put(root + '/drive/folder', value),
    cloudBackups: () => httpClient.get(root + '/drive/backups', { ...fresh, timeoutMs: 60000 }),
    prepareCloud: value => httpClient.post(root + '/drive/prepare', value),
    prepare: (id, format) => httpClient.post(`${root}/backups/${id}/prepare`, { format }, { timeoutMs: 300000 }),
    importBackup: form => httpClient.upload(root + '/candidates/import', form, { timeoutMs: 300000 }),
    test: id => httpClient.post(`${root}/candidates/${id}/test`, {}),
    activate: (id, value) => httpClient.post(`${root}/candidates/${id}/activate`, value),
    discard: id => httpClient.post(`${root}/candidates/${id}/discard`, {}),
    rollback: id => httpClient.post(`${root}/rollbacks/${id}/prepare`, {}),
});
export function saveBackupDownload(value, filename) {
    if (!(value instanceof Blob)) throw new Error('The backup download was not received.');
    const url = URL.createObjectURL(value), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
