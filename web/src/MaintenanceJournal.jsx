import {useLiveRefresh} from './liveRefresh';
import React, {useEffect, useState} from 'react';
import {Download, RefreshCw} from 'lucide-react';
import {api, download, PREVIEW} from './api';
import {Field} from './components';

const headers = [
  '№ п/п', 'Вид проведённой работы', 'Дата проведения работы',
  'Ф.И.О., должность лица, выполнившего работы',
  'Подпись лица, выполнившего работы',
  'Подпись лица, ответственного за организацию обслуживания и ремонт объекта',
];

export default function MaintenanceJournal({lift, onOpenSource}) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const valid = !from || !to || from <= to;
  const base = 'maintenance/' + lift.id + '/journal/';
  const period = new URLSearchParams();
  if (from) period.set('from', from);
  if (to) period.set('to', to);
  const query = period.size ? '?' + period.toString() : '';
  const path = base + query;
  const report = result?.path === path && result.revision === revision ? result : null;

  useEffect(() => {
    if (!valid) return;
    const request = new AbortController();
    api(path, {signal: request.signal}).then(({rows}) => {
      if (!request.signal.aborted) setResult({path, revision, rows});
    }).catch(error => {
      if (!request.signal.aborted) setResult({path, revision, error: error.message});
    });
    return () => request.abort();
  }, [path, revision, valid]);

  useLiveRefresh(async signal=>{if(!valid)return;const {rows}=await api(path,{signal});if(!signal.aborted)setResult({path,revision,rows});},path,valid);

  async function exportPdf() {
    setExporting(true);
    setExportError('');
    try {
      download('LiftControl-TO-' + lift.id + '.pdf', await api(base + 'pdf/' + query, {blob: true}));
    } catch (error) {
      setExportError(error.message);
    } finally {
      setExporting(false);
    }
  }

  return <>
    <div className="range">
      <Field label="С"><input type="date" value={from} onChange={event => setFrom(event.target.value)}/></Field>
      <Field label="По"><input type="date" value={to} onChange={event => setTo(event.target.value)}/></Field>
      <button disabled={!valid} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>Обновить</button>
      {!PREVIEW && <button disabled={!valid || exporting} onClick={exportPdf}>
        <Download size={16}/>{exporting ? 'Формирование…' : 'Скачать PDF для печати'}
      </button>}
    </div>
    {!valid && <p className="error" role="alert">Дата окончания раньше даты начала.</p>}
    {valid && !report && <p role="status">Загрузка журнала…</p>}
    {valid && report?.error && <p className="error" role="alert">{report.error}</p>}
    {exportError && <p className="error" role="alert">{exportError}</p>}
    {valid && report?.rows && <div className="panel table-wrap">
      <table className="journal-table">
        <thead><tr>{headers.map(header => <th key={header} scope="col">{header}</th>)}</tr></thead>
        <tbody>{report.rows.map((row, index) => <tr key={row.source + '-' + row.source_id}>
          <td>{index + 1}</td>
          <td><button className="journal-source" onClick={() => onOpenSource(row)}>{row.description}</button></td>
          <td>{row.date.split('-').reverse().join('.')}</td>
          <td>{row.performer}</td>
          <td/><td/>
        </tr>)}</tbody>
      </table>
      {!report.rows.length && <p className="empty">За выбранный период выполненных работ нет.</p>}
    </div>}
  </>;
}
