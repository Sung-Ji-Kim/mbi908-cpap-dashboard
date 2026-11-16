import React, { useCallback, useEffect, useState } from 'react';

// Night Log: patient view of 7 nights, read from the cloud API.
// URL options: ?patient=P02  ?run=B-Medium-s03  ?as_of=2026-11-05T00:00:00Z  ?refresh=60 (seconds, default 900 = 15 min)
const params = new URLSearchParams(window.location.search);
const RUN = params.get('run');
const AS_OF = params.get('as_of');
const REFRESH_S = Math.max(5, Number(params.get('refresh')) || 900);

const TEAL = '#0E5E62';
const ORANGE = '#E8701A';
const COLOR = { t: TEAL, m: ORANGE, i: '#DDE3E4' };
const HATCH = 'repeating-linear-gradient(135deg, #5E6E70 0 2px, #FFFFFF 2px 5px)';
const GOAL_MIN = 240;

const card = { background: '#FFFFFF', borderRadius: 12, padding: 18, display: 'flex', flexDirection: 'column' };
const tileBase = { display: 'flex', flexDirection: 'column', gap: 4, padding: 14, borderRadius: 12, minHeight: 112, boxSizing: 'border-box' };
const TILE_OK = { ...tileBase, background: TEAL, color: '#FFFFFF' };
const TILE_WARN = { ...tileBase, background: '#FFF0E5', color: '#7A2A0C', border: `2px solid ${ORANGE}` };
const tab = (on) => ({
    minHeight: 44, border: 0, borderRadius: 8, cursor: 'pointer', fontSize: 16,
    background: on ? '#FFFFFF' : 'transparent', color: on ? '#0A4548' : '#34484B', fontWeight: on ? 700 : 500,
});

function clock(m) {
    const t = (12 * 60 + m) % 1440;
    return String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0');
}
function span(min) {
    if (min < 60) return min + ' min';
    const h = Math.floor(min / 60), r = min % 60;
    return h + ' h' + (r ? ' ' + r + ' min' : '');
}
function hm(min) { return Math.floor(min / 60) + ':' + String(min % 60).padStart(2, '0'); }

// '2026-11-02' -> {day: 'Mon', num: 2, label: 'Mon 2 Nov'}
function dayInfo(iso) {
    const d = new Date(iso + 'T00:00:00Z');
    const day = d.toLocaleDateString('en-NZ', { weekday: 'short', timeZone: 'UTC' });
    const mon = d.toLocaleDateString('en-NZ', { month: 'short', timeZone: 'UTC' });
    return { day, num: d.getUTCDate(), mon, label: `${day} ${d.getUTCDate()} ${mon}` };
}
function nextDayLabel(iso) {
    const d = new Date(iso + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + 1);
    return dayInfo(d.toISOString().slice(0, 10)).label;
}
function localTime(isoUtc, tz) {
    if (!isoUtc) return null;
    const d = new Date(isoUtc);
    const date = d.toLocaleDateString('en-NZ', { weekday: 'short', day: 'numeric', month: 'short', timeZone: tz });
    const time = d.toLocaleTimeString('en-NZ', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz });
    return `${date} ${time}`;
}

function Swatch({ kind, size = 16 }) {
    const style = { display: 'block', flex: 'none', width: size, height: size, borderRadius: size > 12 ? 4 : 3, boxSizing: 'border-box' };
    return <span style={kind === 'n' ? { ...style, border: '1px solid #5E6E70', background: HATCH } : { ...style, background: COLOR[kind] }} />;
}

function sessionsOf(segs) {
    const out = [];
    segs.filter((g) => g[0] !== 'n').forEach((g) => {
        const last = out[out.length - 1];
        if (last && last.end === g[1]) { last.end = g[1] + g[2]; last.use += g[0] === 't' ? g[2] : 0; }
        else out.push({ start: g[1], end: g[1] + g[2], use: g[0] === 't' ? g[2] : 0 });
    });
    return out;
}

function eventsFor(segs, nd) {
    if (nd >= 1440) {
        return [{
            k: 'n', s: 0, time: '12:00 to 12:00 next day', length: '24 h', what: 'No data received for this night',
            note: 'The device keeps the data and sends it once it reconnects.'
        }];
    }
    const out = [];
    const sessions = sessionsOf(segs);
    if (!sessions.length) {
        out.push({
            k: 'i', s: 0, time: '12:00 to 12:00 next day', length: '', what: 'Device not used this night',
            note: 'Data was received, so this is a real night without therapy.'
        });
    }
    sessions.forEach((s, i) => {
        out.push({
            k: 't', s: s.start, time: clock(s.start) + ' to ' + clock(s.end), length: span(s.use),
            what: sessions.length > 1 ? 'Session ' + (i + 1) + ': using CPAP' : 'Using CPAP', note: ''
        });
        const next = sessions[i + 1];
        if (next) out.push({
            k: 'i', s: s.end, time: clock(s.end) + ' to ' + clock(next.start), length: span(next.start - s.end),
            what: 'Break, device paused', note: ''
        });
    });
    segs.forEach((g) => {
        if (g[0] === 'm') out.push({
            k: 'm', s: g[1] + 0.5, time: clock(g[1]) + ' to ' + clock(g[1] + g[2]), length: span(g[2]),
            what: 'Mask off', note: 'Therapy pauses while the mask is off.'
        });
        if (g[0] === 'n') out.push({
            k: 'n', s: g[1], time: clock(g[1]) + ' to ' + clock(g[1] + g[2]) + (g[1] + g[2] >= 1440 ? ' next day' : ''),
            length: span(g[2]), what: 'Data not received yet', note: 'Not a problem with your therapy. It will appear when the device reconnects.'
        });
    });
    return out.sort((a, b) => a.s - b.s);
}

function Tiles({ tiles }) {
    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
            {tiles.map((t) => (
                <div key={t.label} style={t.ok ? TILE_OK : TILE_WARN}>
                    <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: 0.6 }}>{t.label}</span>
                    <span style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.1 }}>{t.value}</span>
                    <span style={{ fontSize: 13, lineHeight: 1.4 }}>{t.note}</span>
                </div>
            ))}
        </div>
    );
}

function NightView({ nights, sel, setSel }) {
    const n = nights[sel];
    const info = dayInfo(n.night);
    const hasNight = n.not_received_min < 1440;
    const sessions = sessionsOf(n.segments);
    const removals = Math.round(n.mask_off_min / 15);

    let tiles = [];
    if (hasNight && n.sessions > 0 && sessions.length) {
        const leak = n.avg_leak_lpm ?? 0, ahi = n.ahi ?? 0;
        tiles = [
            {
                label: 'THERAPY HOURS', value: hm(n.therapy_min), ok: n.therapy_min >= GOAL_MIN,
                note: 'From ' + clock(sessions[0].start) + ' to ' + clock(sessions[sessions.length - 1].end)
            },
            {
                label: 'MASK FIT', value: leak > 60 ? 'Check' : 'Good', ok: leak <= 60,
                note: (leak > 60 ? 'Air escaping, avg leak ' : 'Avg leak ') + Math.round(leak) + ' L/min'
            },
            { label: 'BREATHING EVENTS', value: ahi.toFixed(1), ok: ahi <= 5, note: 'Per hour. Under 5 is the usual target' },
            {
                label: 'MASK OFF', value: removals ? removals + (removals > 1 ? ' times' : ' time') : 'None', ok: !removals,
                note: removals ? n.mask_off_min + ' min in total' : (n.sessions > 1 ? n.sessions + ' sessions, mask stayed on' : 'Mask stayed on')
            },
        ];
    } else if (hasNight) {
        tiles = [{ label: 'THERAPY HOURS', value: '0:00', ok: false, note: 'Device not used this night' }];
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${nights.length}, minmax(0, 1fr))`, gap: 4 }}>
                {nights.map((x, i) => {
                    const on = i === sel;
                    const none = x.not_received_min >= 1440;
                    const d = dayInfo(x.night);
                    const mark = none ? { border: '1px solid #5E6E70', background: HATCH }
                        : { background: x.therapy_min >= GOAL_MIN ? (on ? '#FFFFFF' : TEAL) : ORANGE };
                    return (
                        <button key={x.night} type="button" onClick={() => setSel(i)}
                            aria-label={d.label + (none ? ', not received' : ', ' + (x.therapy_min / 60).toFixed(1) + ' hours')}
                            style={{
                                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, minHeight: 64, padding: '6px 0', cursor: 'pointer',
                                borderRadius: 10, border: `1px solid ${on ? TEAL : '#CBD6D7'}`, background: on ? TEAL : '#FFFFFF', color: on ? '#FFFFFF' : '#172224'
                            }}>
                            <span style={{ fontSize: 12 }}>{d.day}</span>
                            <span style={{ fontSize: 17, fontWeight: 700 }}>{d.num}</span>
                            <span style={{ display: 'block', width: 18, height: 6, borderRadius: 3, boxSizing: 'border-box', ...mark }} />
                        </button>
                    );
                })}
            </div>

            <div style={{ fontSize: 15, fontWeight: 600, color: '#34484B' }}>
                Night of {info.label}{sel === nights.length - 1 ? ' (last night)' : ''}
            </div>

            {hasNight ? <Tiles tiles={tiles} /> : (
                <div style={{ ...card, gap: 4 }}>
                    <span style={{ fontSize: 22, fontWeight: 700 }}>Not received yet</span>
                    <span style={{ fontSize: 15, color: '#34484B' }}>This does not mean the device was off.</span>
                </div>
            )}

            <section style={{ ...card, gap: 12 }}>
                <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Your night, hour by hour</h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ position: 'relative', height: 28, borderRadius: 6, background: '#DDE3E4', overflow: 'hidden' }}>
                        {n.segments.map((g, i) => (
                            <div key={i} style={{
                                position: 'absolute', top: 0, bottom: 0, left: g[1] / 14.4 + '%', width: g[2] / 14.4 + '%',
                                background: g[0] === 'n' ? HATCH : COLOR[g[0]]
                            }} />
                        ))}
                    </div>
                    <div style={{ position: 'relative', height: 16, fontSize: 12, color: '#4F6164' }}>
                        <span style={{ position: 'absolute', left: 0 }}>12:00</span>
                        {['18:00', '00:00', '06:00'].map((t, i) => (
                            <span key={t} style={{ position: 'absolute', left: (i + 1) * 25 + '%', transform: 'translateX(-50%)' }}>{t}</span>
                        ))}
                        <span style={{ position: 'absolute', right: 0 }}>12:00</span>
                    </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '8px 12px', fontSize: 14 }}>
                    {[['t', 'Using CPAP'], ['m', 'Mask off'], ['i', 'Not using'], ['n', 'Data not received']].map(([k, label]) => (
                        <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Swatch kind={k} />{label}</span>
                    ))}
                </div>
            </section>

            <section style={{ ...card, gap: 4 }}>
                <h2 style={{ margin: '0 0 8px', fontSize: 17, fontWeight: 700 }}>What happened</h2>
                {eventsFor(n.segments, n.not_received_min).map((e, i) => (
                    <div key={i} style={{ display: 'grid', gridTemplateColumns: '16px minmax(0, 1fr)', gap: 12, padding: '10px 0', borderTop: '1px solid #E4E9EA' }}>
                        <span style={{ marginTop: 3 }}><Swatch kind={e.k} /></span>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '4px 12px' }}>
                                <span style={{ fontSize: 15, fontWeight: 700 }}>{e.time}</span>
                                <span style={{ fontSize: 14, color: '#4F6164' }}>{e.length}</span>
                            </div>
                            <span style={{ fontSize: 15 }}>{e.what}</span>
                            {e.note && <span style={{ fontSize: 13, color: '#4F6164', lineHeight: 1.45 }}>{e.note}</span>}
                        </div>
                    </div>
                ))}
            </section>
        </div>
    );
}

function WeekView({ nights, pick }) {
    const withData = nights.filter((x) => x.not_received_min < 1440);
    const met = withData.filter((x) => x.therapy_min >= GOAL_MIN).length;
    const missing = nights.length - withData.length;
    const thSum = withData.reduce((a, x) => a + x.therapy_min, 0);
    const evSum = withData.reduce((a, x) => a + (x.ahi || 0) * x.therapy_min / 60, 0);
    const leakAvg = thSum ? withData.reduce((a, x) => a + (x.avg_leak_lpm || 0) * x.therapy_min, 0) / thSum : 0;
    const wAhi = thSum ? evSum / (thSum / 60) : 0;
    const moSum = withData.reduce((a, x) => a + x.mask_off_min, 0);
    const first = dayInfo(nights[0].night), last = dayInfo(nights[nights.length - 1].night);

    const tiles = [
        { label: 'NIGHTS 4 H OR MORE', value: `${met} / ${nights.length}`, ok: met >= 5, note: met >= 5 ? 'On track (5 or more)' : 'Goal is 5 or more nights' },
        { label: 'AVERAGE USE', value: withData.length ? hm(Math.round(thSum / withData.length)) : '–', ok: true, note: 'Per night with data' },
        { label: 'BREATHING EVENTS', value: wAhi.toFixed(1), ok: wAhi <= 5, note: 'Per hour, whole week' },
        {
            label: 'MASK FIT', value: leakAvg > 60 ? 'Check' : 'Good', ok: leakAvg <= 60,
            note: 'Avg leak ' + Math.round(leakAvg) + ' L/min' + (moSum ? ', mask off ' + moSum + ' min' : '')
        },
    ];

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <section style={{ ...card, gap: 12 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{first.num} to {last.num} {last.mon}</h2>
                    <div style={{ fontSize: 15, color: '#34484B' }}>
                        Goal met on {met} of {withData.length} nights{missing ? `. ${missing} ${missing > 1 ? 'nights' : 'night'} not received yet.` : '.'}
                    </div>
                    <div style={{ fontSize: 13, color: '#4F6164' }}>Tap a night to open it.</div>
                </div>
                <div style={{ position: 'relative', height: 176 }}>
                    <div style={{ position: 'absolute', left: 0, right: 0, bottom: 75, borderTop: '2px dashed #34484B' }} />
                    <div style={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: `repeat(${nights.length}, minmax(0, 1fr))`, gap: 6, alignItems: 'end' }}>
                        {nights.map((x, i) => {
                            const none = x.not_received_min >= 1440;
                            const h = x.therapy_min / 60;
                            const px = none ? 120 : Math.max(Math.min(h, 9) / 9 * 120, 3);
                            const bg = none ? HATCH : (x.therapy_min >= GOAL_MIN ? TEAL : (x.therapy_min === 0 ? '#C4CDCE' : ORANGE));
                            const d = dayInfo(x.night);
                            return (
                                <button key={x.night} type="button" onClick={() => pick(i)} aria-label={d.label + ', ' + (none ? 'not received' : h.toFixed(1) + ' hours')}
                                    style={{
                                        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 4, height: '100%', minHeight: 44,
                                        padding: '0 0 2px', cursor: 'pointer', borderRadius: 6, background: 'transparent', border: '2px solid transparent'
                                    }}>
                                    <span style={{ fontSize: 12, color: '#34484B' }}>{none ? '?' : h.toFixed(1)}</span>
                                    <span style={{
                                        display: 'block', width: '100%', maxWidth: 32, height: px, borderRadius: '4px 4px 0 0', boxSizing: 'border-box',
                                        background: bg, border: none ? '1px solid #5E6E70' : 'none'
                                    }} />
                                    <span style={{ fontSize: 12, color: '#34484B', height: 16 }}>{d.day}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', fontSize: 13 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Swatch kind="t" size={12} />4 h or more</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Swatch kind="m" size={12} />Under 4 h</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Swatch kind="n" size={12} />Not received</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 14, borderTop: '2px dashed #34484B' }} />4 h goal</span>
                </div>
            </section>
            <Tiles tiles={tiles} />
        </div>
    );
}

export default function App() {
    const [patients, setPatients] = useState([]);
    const [patient, setPatient] = useState(params.get('patient') || 'P02');
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);
    const [checkedAt, setCheckedAt] = useState(null);
    const [sel, setSel] = useState(null);
    const [view, setView] = useState('night');

    useEffect(() => {
        fetch('/api/patients').then((r) => (r.ok ? r.json() : [])).then(setPatients).catch(() => { });
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        const q = new URLSearchParams();
        if (RUN) q.set('run_id', RUN);
        if (AS_OF) q.set('as_of', AS_OF);
        try {
            const r = await fetch(`/api/patients/${encodeURIComponent(patient)}/nights?${q}`);
            const body = await r.json().catch(() => ({}));
            if (r.status === 403) { setData(null); setError({ consent: true, text: body.error }); return; }
            if (!r.ok) throw new Error(body.error || `Server replied ${r.status}`);
            setData(body);
            setError(null);
            setSel((s) => (s == null || s >= body.nights.length ? body.nights.length - 1 : s));
        } catch (e) {
            setError({ consent: false, text: String(e.message || e) });
        } finally {
            setLoading(false);
            setCheckedAt(new Date());
        }
    }, [patient]);

    useEffect(() => {
        setData(null);
        setSel(null);
        load();
        const id = setInterval(load, REFRESH_S * 1000);
        return () => clearInterval(id);
    }, [load]);

    const nights = data?.nights || [];
    const tz = data?.timezone || 'Pacific/Auckland';
    const lastNight = nights[nights.length - 1];
    const lastIn = lastNight && lastNight.not_received_min < 1440;
    const lastRecv = localTime(data?.last_received, tz) || 'never';
    const banner = { borderRadius: 12, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4 };

    return (
        <div style={{ fontFamily: "'Figtree', system-ui, sans-serif", color: '#172224', background: '#F2F5F5', minHeight: '100vh' }}>
            <header style={{ background: TEAL, color: '#FFFFFF' }}>
                <div style={{ maxWidth: 560, margin: '0 auto', padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
                            <circle cx="15" cy="15" r="14" fill="none" stroke="#FFFFFF" strokeWidth="2" />
                            <path d="M19 8a8 8 0 1 0 3 12a6.5 6.5 0 1 1 -3 -12z" fill="#FFFFFF" />
                        </svg>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: 0.2 }}>Night Log</span>
                            <span style={{ fontSize: 12, color: '#CFE6E6' }}>
                                {lastNight ? nextDayLabel(lastNight.night) + ' · ' : ''}updates every {REFRESH_S >= 60 ? Math.round(REFRESH_S / 60) + ' min' : REFRESH_S + ' s'}
                            </span>
                        </div>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600, padding: '4px 8px', borderRadius: 999, background: '#0A4548', color: '#E3F1F1' }}>RESEARCH PROTOTYPE</span>
                </div>
            </header>

            <main style={{ maxWidth: 560, margin: '0 auto', padding: '16px 16px 32px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, fontSize: 13, color: '#4F6164', flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        Patient
                        <select value={patient} onChange={(e) => setPatient(e.target.value)}
                            style={{ minHeight: 36, padding: '0 8px', borderRadius: 8, border: '1px solid #CBD6D7', background: '#FFFFFF', color: '#172224' }}>
                            {(patients.length ? patients.map((p) => p.patient_id) : ['P01', 'P02', 'P03', 'P04', 'P05']).map((p) => (
                                <option key={p} value={p}>{p}</option>
                            ))}
                        </select>
                    </label>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {checkedAt && <span>Checked {checkedAt.toLocaleTimeString('en-NZ', { hour: '2-digit', minute: '2-digit', hour12: false })}</span>}
                        <button type="button" onClick={load} disabled={loading}
                            style={{ minHeight: 36, padding: '0 12px', borderRadius: 8, border: `1px solid ${TEAL}`, background: '#FFFFFF', color: TEAL, fontWeight: 600, cursor: 'pointer' }}>
                            {loading ? 'Checking…' : 'Refresh'}
                        </button>
                    </span>
                </div>

                {error && error.consent && (
                    <div style={{ ...banner, background: '#ECEFF0', color: '#26383A' }}>
                        <div style={{ fontSize: 16, fontWeight: 600 }}>Data not shown</div>
                        <div style={{ fontSize: 14, lineHeight: 1.45 }}>This patient has withdrawn consent, so their data is no longer shown or stored.</div>
                    </div>
                )}
                {error && !error.consent && (
                    <div style={{ ...banner, background: '#FDECEC', color: '#7A1C1C' }}>
                        <div style={{ fontSize: 16, fontWeight: 600 }}>Could not load the data</div>
                        <div style={{ fontSize: 14, lineHeight: 1.45 }}>{error.text}. The database may be waking up; this can take up to a minute. It will try again.</div>
                    </div>
                )}

                {!data && !error && <div style={{ ...card, fontSize: 15 }}>Loading the last 7 nights…</div>}

                {data && nights.length > 0 && sel != null && (
                    <>
                        <div style={{ ...banner, ...(lastIn ? { background: '#E3F1F1', color: '#0A3F41' } : { background: '#FFF0E5', color: '#6B2410' }) }}>
                            <div style={{ fontSize: 16, fontWeight: 600 }}>{lastIn ? 'Your data is up to date' : 'We haven’t received last night’s data yet'}</div>
                            <div style={{ fontSize: 15, lineHeight: 1.45 }}>
                                {lastIn ? `Last update received ${lastRecv}.`
                                    : `The last update arrived ${lastRecv}. Your device keeps the data and sends it once it reconnects. Nothing needs to be done right now.`}
                            </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 4, padding: 4, background: '#DCE6E6', borderRadius: 10 }}>
                            <button type="button" onClick={() => setView('night')} style={tab(view === 'night')}>Night</button>
                            <button type="button" onClick={() => setView('week')} style={tab(view === 'week')}>Week</button>
                        </div>

                        {view === 'night'
                            ? <NightView nights={nights} sel={sel} setSel={setSel} />
                            : <WeekView nights={nights} pick={(i) => { setSel(i); setView('night'); }} />}
                    </>
                )}

                <p style={{ margin: 0, fontSize: 13, color: '#4F6164', lineHeight: 1.45 }}>Questions about these numbers? Contact your care team.</p>
                <p style={{ margin: 0, fontSize: 12, color: '#4F6164', lineHeight: 1.45 }}>
                    Research prototype for MBI908, built on synthetic data{data?.run_id ? ` (run ${data.run_id})` : ''}. Not affiliated with or endorsed by Fisher &amp; Paykel Healthcare.
                </p>
            </main>
        </div>
    );
}
