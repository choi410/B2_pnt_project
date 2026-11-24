// 주간보고 작성 탭: ① 메모 입력 → ② 회의록 연결 확인 → ③ 초안 수정 → ④ Word 저장.
// React와 api를 밖에서 받는다. 같은 파일을 앱 번들에서도, 기존 화면 파일에 끼워 넣는 패치에서도 쓰기 위해서다.
const STATUSES = ["완료", "진행", "예정", "보류"];
const GROUPS = [
  ["next", "다음 주에 기한이 있는 조치", "차주 계획과 조치사항에 들어갑니다."],
  ["due", "이번 주가 기한인 조치", "조치사항에 들어갑니다. 끝난 일이면 빼 주세요."],
  ["schedule", "다음 주 확정 일정", "차주 계획에 들어갑니다."],
  ["open", "담당자·기한이 정해지지 않은 조치", "조치사항에 '미정'으로 들어갑니다."],
  ["decided", "이번 주 회의의 결정·변경", "금주 실적에 들어갑니다."],
  ["meeting", "이번 주에 열린 회의", "금주 실적의 회의 건수에 들어갑니다."],
];
const LEVEL = { high: ["높음", "ok"], mid: ["확인 필요", "warn"], low: ["낮음", "low"] };
const SOURCE = { memo: "메모", linked: "메모 + 회의록", meeting: "회의록", manual: "직접 입력" };
const md = (iso) => (iso && iso.length >= 10 ? Number(iso.slice(5, 7)) + "/" + Number(iso.slice(8, 10)) : "");
const defaultTitle = (s, e) => "주간 업무보고 (" + md(s) + "~" + md(e) + ")";
const blankRow = () => ({ id: "", date: "", text: "", status: "" });
const initial = () => ({
  step: "input", start: "", end: "", title: "", titleTouched: false, rows: [blankRow(), blankRow(), blankRow()], paste: "",
  note: "", matched: null, picks: {}, extraPicks: {}, added: {}, onlyMine: false, report: null, draft: null, dirty: false,
  openEvidence: {}, proposals: null, finder: null,
});

export function createWeeklyReport(React, { api }) {
  const { useState, useEffect, useRef, useCallback } = React;
  const memory = { state: null }; // 원문을 보러 다른 화면에 다녀와도 작업을 잇기 위해 탭 밖에 둔다.

  function Chip({ tone, children, title }) {
    return <span className={"wk-chip " + (tone || "")} title={title}>{children}</span>;
  }

  function Evidence({ list, openMeeting }) {
    if (!list.length) return <p className="wk-evidence-empty">연결된 회의록이 없습니다. 메모만으로 쓴 줄입니다.</p>;
    return (
      <ul className="wk-evidence">
        {list.map((ev, i) => (
          <li key={ev.unit_id + i}>
            <div className="wk-evidence-head">
              <Chip>{ev.kind_label}</Chip>
              <b>{ev.meeting_date} {ev.meeting_title}</b>
              <span className="muted">{ev.project_name}</span>
              {!ev.reviewed && <Chip tone="warn">검토 전 변경 이력</Chip>}
            </div>
            <blockquote>{ev.quote}</blockquote>
            <button type="button" className="wk-link" onClick={() => openMeeting(ev.meeting_id, ev.lines)}>회의록 원문에서 보기</button>
          </li>
        ))}
      </ul>
    );
  }

  function Candidate({ unit, checked, onToggle, extra }) {
    const [label, tone] = LEVEL[unit.confidence] || [];
    return (
      <label className={"wk-cand" + (checked ? " on" : "")}>
        <input type="checkbox" checked={!!checked} onChange={onToggle} />
        <span className="wk-cand-body">
          <span className="wk-cand-top">
            <Chip>{unit.kind_label}</Chip>
            {label && <Chip tone={tone} title={(unit.reasons || []).join(" · ")}>연관도 {label}</Chip>}
            {unit.mine && <Chip tone="ok">내 담당</Chip>}
            {unit.reviewed === false && <Chip tone="warn">검토 전</Chip>}
            <span className="muted">{md(unit.meeting_date)} {unit.meeting_title}{extra ? "" : " · " + unit.project_name}</span>
          </span>
          <span className="wk-cand-text">{unit.text}</span>
          {unit.reasons && unit.reasons.length > 0 && <span className="wk-cand-why">{unit.reasons.join(" · ")}</span>}
        </span>
      </label>
    );
  }

  return function WeeklyReport({ workspace, toast, openMeeting }) {
    const [s, setS] = useState(() => memory.state || initial());
    const [saved, setSaved] = useState([]);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [aiReady, setAiReady] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState("");
    const fileRef = useRef(null);
    const set = useCallback((patch) => setS((cur) => ({ ...cur, ...(typeof patch === "function" ? patch(cur) : patch) })), []);
    useEffect(() => { memory.state = s; }, [s]);

    const run = async (label, work) => {
      setBusy(label); setError("");
      try { return await work(); }
      catch (e) { setError(e.message || "요청을 처리하지 못했습니다."); return null; }
      finally { setBusy(""); }
    };
    const loadSaved = () => api("/v3/weekly/reports").then(setSaved).catch(() => {});
    useEffect(() => {
      loadSaved();
      api("/v3/weekly/status").then((st) => {
        setAiReady(st.ai_ready);
        set((cur) => (cur.start ? {} : { start: st.start, end: st.end, title: defaultTitle(st.start, st.end) }));
      }).catch(() => {});
    }, []);
    useEffect(() => {
      if (!s.dirty) return;
      const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
      window.addEventListener("beforeunload", warn);
      return () => window.removeEventListener("beforeunload", warn);
    }, [s.dirty]);

    const setPeriod = (key, value) => set((cur) => {
      const next = { ...cur, [key]: value };
      return { [key]: value, title: cur.titleTouched ? cur.title : defaultTitle(next.start, next.end), matched: null };
    });
    const editRow = (i, key, value) => set((cur) => ({ rows: cur.rows.map((r, n) => (n === i ? { ...r, [key]: value } : r)), matched: null }));
    const usable = s.rows.filter((r) => r.text.trim());
    const periodOk = s.start && s.end && s.start <= s.end;

    async function importText() {
      if (!s.paste.trim()) return;
      const res = await run("parse", () => api("/v3/weekly/parse", "POST", { text: s.paste, start: s.start, end: s.end }));
      if (res) set((cur) => ({ rows: [...cur.rows.filter((r) => r.text.trim()), ...res.rows], paste: "", matched: null, note: res.rows.length + "개 항목을 표에 넣었습니다. 일자와 상태를 확인해 주세요." }));
    }
    async function importFile(file) {
      if (!file) return;
      const form = new FormData();
      form.append("file", file); form.append("start", s.start); form.append("end", s.end);
      const res = await run("parse", () => api("/v3/weekly/parse-file", "POST", form));
      if (res) set((cur) => ({ rows: [...cur.rows.filter((r) => r.text.trim()), ...res.rows], matched: null, note: file.name + "에서 " + res.rows.length + "개 항목을 읽었습니다. " + (res.note || "") }));
      if (fileRef.current) fileRef.current.value = "";
    }
    async function findLinks() {
      const rows = usable.map((r, i) => ({ id: "R" + (i + 1), date: r.date || "", text: r.text.trim().slice(0, 300), status: STATUSES.includes(r.status) ? r.status : "" }));
      const res = await run("match", () => api("/v3/weekly/match", "POST", { rows, start: s.start, end: s.end }));
      if (!res) return;
      const picks = {}, extraPicks = {};
      res.rows.forEach((r) => { picks[r.id] = {}; r.candidates.forEach((c) => { if (c.selected) picks[r.id][c.id] = true; }); });
      res.extras.forEach((x) => { if (x.selected) extraPicks[x.id] = true; });
      set({ rows, matched: res, picks, extraPicks, added: {}, step: "confirm", report: null, draft: null, dirty: false, proposals: null, finder: null });
      window.scrollTo(0, 0);
    }
    const togglePick = (rowId, unitId) => set((cur) => ({ picks: { ...cur.picks, [rowId]: { ...cur.picks[rowId], [unitId]: !cur.picks[rowId]?.[unitId] } } }));
    const toggleExtra = (unitId) => set((cur) => ({ extraPicks: { ...cur.extraPicks, [unitId]: !cur.extraPicks[unitId] } }));
    async function openFinder(rowId, meetingId) {
      if (!meetingId) return set({ finder: { rowId, meetingId: "", units: [] } });
      const res = await run("units", () => api("/v3/weekly/units?meeting_id=" + encodeURIComponent(meetingId)));
      if (res) set({ finder: { rowId, meetingId, units: res.units } });
    }
    const addUnit = (rowId, unit) => set((cur) => {
      const have = (cur.added[rowId] || []).some((u) => u.id === unit.id) || cur.matched.rows.find((r) => r.id === rowId).candidates.some((c) => c.id === unit.id);
      return {
        added: have ? cur.added : { ...cur.added, [rowId]: [...(cur.added[rowId] || []), unit] },
        picks: { ...cur.picks, [rowId]: { ...cur.picks[rowId], [unit.id]: true } },
      };
    });
    const openReport = (report) => set({
      step: "draft", report, start: report.start, end: report.end, title: report.title, titleTouched: true, rows: report.rows,
      draft: { title: report.title, checked: report.checked, sections: report.sections, actions: report.actions },
      dirty: false, proposals: null, openEvidence: {}, matched: null,
    });
    async function makeDraft() {
      const links = {};
      Object.entries(s.picks).forEach(([rowId, units]) => { const ids = Object.keys(units).filter((id) => units[id]); if (ids.length) links[rowId] = ids; });
      const extras = Object.keys(s.extraPicks).filter((id) => s.extraPicks[id]);
      const report = await run("draft", () => api("/v3/weekly/reports", "POST", { title: s.title.trim() || defaultTitle(s.start, s.end), start: s.start, end: s.end, rows: s.rows, links, extras }));
      if (!report) return;
      const keep = { matched: s.matched, picks: s.picks, extraPicks: s.extraPicks, added: s.added };
      openReport(report); set(keep); loadSaved(); window.scrollTo(0, 0);
      toast("초안을 만들었습니다. 내용을 확인하고 고쳐 주세요.");
    }
    async function loadReport(id) {
      const report = await run("open", () => api("/v3/weekly/reports/" + id));
      if (report) { openReport(report); window.scrollTo(0, 0); }
    }
    const editDraft = (patch) => set((cur) => ({ draft: { ...cur.draft, ...(typeof patch === "function" ? patch(cur.draft) : patch) }, dirty: true }));
    const editItem = (key, index, patch) => editDraft((d) => ({ sections: d.sections.map((sec) => (sec.key !== key ? sec : { ...sec, items: sec.items.map((it, n) => (n === index ? { ...it, ...patch } : it)) })) }));
    const removeItem = (key, index) => editDraft((d) => ({ sections: d.sections.map((sec) => (sec.key !== key ? sec : { ...sec, items: sec.items.filter((_, n) => n !== index) })) }));
    const addItem = (key) => editDraft((d) => ({ sections: d.sections.map((sec) => (sec.key !== key ? sec : { ...sec, items: [...sec.items, { id: "", tmp: "t" + Date.now(), type: "item", text: "", level: 0, source: "manual", evidence: [] }] })) }));
    const editAction = (index, patch) => editDraft((d) => ({ actions: d.actions.map((a, n) => (n === index ? { ...a, ...patch } : a)) }));
    async function save(quiet) {
      const d = s.draft;
      const body = {
        version: s.report.version, title: d.title.trim() || s.report.title, checked: !!d.checked,
        sections: d.sections.map((sec) => ({ key: sec.key, items: sec.items.filter((it) => it.text.trim()).map((it) => ({ id: it.id || "", type: it.type, text: it.text.trim(), level: it.level })) })),
        actions: d.actions.filter((a) => a.task.trim()).map((a) => ({ task: a.task.trim(), owner: (a.owner || "").trim(), due: (a.due || "").trim() })),
      };
      const report = await run("save", () => api("/v3/weekly/reports/" + s.report.id, "PATCH", body));
      if (!report) return null;
      set({ report, draft: { title: report.title, checked: report.checked, sections: report.sections, actions: report.actions }, dirty: false });
      loadSaved();
      if (!quiet) toast("초안을 저장했습니다.");
      return report;
    }
    async function downloadWord() {
      const report = s.dirty ? await save(true) : s.report;
      if (!report) return;
      const link = document.createElement("a");
      link.href = "/api/v3/weekly/reports/" + report.id + "/word";
      link.download = "";
      document.body.appendChild(link); link.click(); link.remove();
      toast("Word 파일을 내려받습니다." + (report.checked ? "" : " 아직 '검토 전 초안'으로 표시됩니다."));
    }
    async function removeReport(id) {
      const ok = await run("delete", () => api("/v3/weekly/reports/" + id, "DELETE"));
      setConfirmDelete("");
      if (!ok) return;
      if (s.report && s.report.id === id) set({ ...initial(), start: s.start, end: s.end, title: defaultTitle(s.start, s.end) });
      loadSaved(); toast("초안을 삭제했습니다.");
    }
    async function polish() {
      const report = s.dirty ? await save(true) : s.report;
      if (!report) return;
      const res = await run("polish", () => api("/v3/weekly/reports/" + report.id + "/polish", "POST", { version: report.version }));
      if (res) set({ proposals: res.proposals.map((p) => ({ ...p, on: true })) });
    }
    const applyProposals = () => {
      const chosen = Object.fromEntries(s.proposals.filter((p) => p.on).map((p) => [p.id, p.after]));
      editDraft((d) => ({ sections: d.sections.map((sec) => ({ ...sec, items: sec.items.map((it) => (chosen[it.id] ? { ...it, text: chosen[it.id] } : it)) })) }));
      set({ proposals: null });
    };
    const startNew = () => { set({ ...initial(), start: s.start, end: s.end, title: defaultTitle(s.start, s.end) }); setError(""); };

    const steps = [["input", "1 입력"], ["confirm", "2 회의록 연결 확인"], ["draft", "3 초안 수정 · 저장"]];
    const locked = s.step !== "input";

    const inputPanel = (
      <section className="wk-panel wk-input" aria-label="입력: 업무 메모">
        <h2>입력: 업무 Excel / 메모</h2>
        <div className="wk-period">
          <label>보고 기간<input type="date" value={s.start} disabled={locked} onChange={(e) => setPeriod("start", e.target.value)} /></label>
          <span>~</span>
          <label><span className="wk-hidden">종료일</span><input type="date" value={s.end} disabled={locked} onChange={(e) => setPeriod("end", e.target.value)} /></label>
        </div>
        <table className="wk-table">
          <thead><tr><th style={{ width: "8.2em" }}>일자</th><th>업무 내용</th><th style={{ width: "5.6em" }}>상태</th>{!locked && <th style={{ width: "2em" }}><span className="wk-hidden">삭제</span></th>}</tr></thead>
          <tbody>
            {s.rows.map((r, i) => (
              <tr key={i}>
                <td>{locked ? md(r.date) || "—" : <input type="date" aria-label={"일자 " + (i + 1)} value={r.date} onChange={(e) => editRow(i, "date", e.target.value)} />}</td>
                <td>{locked ? r.text : <input aria-label={"업무 내용 " + (i + 1)} value={r.text} maxLength={300} placeholder="예: 롤프레스 속도 135 재협의" onChange={(e) => editRow(i, "text", e.target.value)} />}</td>
                <td>{locked ? r.status || "—" : (
                  <select aria-label={"상태 " + (i + 1)} value={r.status} onChange={(e) => editRow(i, "status", e.target.value)}>
                    <option value="">미정</option>{STATUSES.map((x) => <option key={x}>{x}</option>)}
                  </select>)}</td>
                {!locked && <td><button type="button" className="wk-x" aria-label={"행 " + (i + 1) + " 삭제"} onClick={() => set((cur) => ({ rows: cur.rows.filter((_, n) => n !== i), matched: null }))}>×</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        {!locked && (
          <React.Fragment>
            <div className="wk-row-tools">
              <button type="button" className="wk-link" onClick={() => set((cur) => ({ rows: [...cur.rows, blankRow()] }))}>+ 행 추가</button>
              <button type="button" className="wk-link" disabled={!periodOk || !!busy} onClick={() => fileRef.current && fileRef.current.click()}>파일 불러오기 (.xlsx · .docx · .txt)</button>
              <input ref={fileRef} type="file" hidden accept=".xlsx,.docx,.txt,.csv,.md" onChange={(e) => importFile(e.target.files[0])} />
            </div>
            <label className="wk-paste">회의 메모·업무 목록 붙여넣기
              <textarea value={s.paste} placeholder={"한 줄에 업무 하나씩 적어 주세요.\n예) 11/18 롤프레스 속도 135 재협의 - 완료\nExcel에서 복사한 표도 그대로 붙여넣을 수 있습니다."} onChange={(e) => set({ paste: e.target.value })} />
            </label>
            <button type="button" className="button" disabled={!s.paste.trim() || !periodOk || !!busy} onClick={importText}>표에 넣기</button>
            {s.note && <p className="wk-note">{s.note}</p>}
            <button type="button" className="button primary wk-main" disabled={!usable.length || !periodOk || !!busy} onClick={findLinks}>
              {busy === "match" ? "회의록에서 찾는 중…" : "회의록 연결 찾기"}
            </button>
            <p className="muted">겹치는 낱말과 뜻이 비슷한 문장(검색 모델이 있을 때)으로 후보를 찾습니다. 다음 화면에서 맞는 것만 골라 주세요.</p>
          </React.Fragment>
        )}
        {locked && <button type="button" className="button" disabled={!!busy} onClick={() => set({ step: "input" })}>입력 고치기</button>}
      </section>
    );

    const confirmPanel = s.matched && (
      <section className="wk-panel wk-output" aria-label="회의록 연결 확인">
        <div className="wk-panel-head">
          <h2>회의록 연결 확인</h2>
          <p className="muted">체크한 항목만 초안의 근거로 씁니다. 틀린 연결은 빼고, 빠진 회의록은 직접 찾아 넣어 주세요.</p>
          <p className="muted">
            {s.matched.semantic?.used
              ? "의미 검색 사용 중(" + (s.matched.semantic.store === "supabase" ? "Supabase 벡터 캐시" : "로컬 벡터 캐시") + ") · '뜻이 비슷함' 후보는 자동으로 체크하지 않습니다."
              : "의미 검색을 쓸 수 없어 낱말 대조로만 찾았습니다."}
          </p>
        </div>
        {s.matched.rows.map((row) => {
          const units = [...row.candidates, ...(s.added[row.id] || [])];
          const count = units.filter((u) => s.picks[row.id]?.[u.id]).length;
          const tone = count ? "ok" : row.match_state === "none" ? "low" : "warn";
          const state = count ? "연결 " + count + "건" : row.match_state === "none" ? "관련 회의록 없음 · 메모만 사용" : "확인 필요 · 고른 항목 없음";
          return (
            <article className="wk-row-card" key={row.id}>
              <header>
                <b>{row.date ? md(row.date) + " " : ""}{row.text}</b>
                <span className="wk-row-meta">{row.status && <Chip>{row.status}</Chip>}<Chip tone={tone}>{state}</Chip></span>
              </header>
              {units.length === 0 && <p className="muted">등록된 회의록에서 겹치는 내용을 찾지 못했습니다. 메모 내용 그대로 초안에 들어갑니다.</p>}
              {units.map((u) => <Candidate key={u.id} unit={u} checked={s.picks[row.id]?.[u.id]} onToggle={() => togglePick(row.id, u.id)} />)}
              {s.finder && s.finder.rowId === row.id ? (
                <div className="wk-finder">
                  <select aria-label="회의록 선택" value={s.finder.meetingId} onChange={(e) => openFinder(row.id, e.target.value)}>
                    <option value="">회의록을 선택하세요</option>
                    {s.matched.meetings.map((m) => <option key={m.id} value={m.id}>{m.date} {m.title} · {m.project_name}</option>)}
                  </select>
                  <button type="button" className="wk-link" onClick={() => set({ finder: null })}>닫기</button>
                  {s.finder.units.filter((u) => !units.some((x) => x.id === u.id)).map((u) => (
                    <button type="button" className="wk-finder-unit" key={u.id} onClick={() => addUnit(row.id, u)}>
                      <Chip>{u.kind_label}</Chip><span>{u.text}</span><em>+ 연결</em>
                    </button>
                  ))}
                </div>
              ) : <button type="button" className="wk-link" onClick={() => openFinder(row.id, "")}>다른 회의록에서 직접 찾기</button>}
            </article>
          );
        })}
        <div className="wk-extras">
          <div className="wk-panel-head">
            <h3>메모에 없는 회의록 항목</h3>
            <label className="wk-check"><input type="checkbox" checked={s.onlyMine} onChange={(e) => set({ onlyMine: e.target.checked })} />내 담당만 보기</label>
          </div>
          {GROUPS.map(([key, title, help]) => {
            const list = s.matched.extras.filter((x) => x.group === key && (!s.onlyMine || x.mine));
            if (!list.length) return null;
            const on = list.filter((x) => s.extraPicks[x.id]).length;
            return (
              <details key={key} open={key === "next" || on > 0}>
                <summary>{title} <small>{on}/{list.length}건 선택</small><span className="muted">{help}</span></summary>
                {list.map((x) => <Candidate key={x.id} unit={x} extra={false} checked={s.extraPicks[x.id]} onToggle={() => toggleExtra(x.id)} />)}
              </details>
            );
          })}
          {s.matched.extras.length === 0 && <p className="muted">보고 기간에 해당하는 다른 회의록 항목이 없습니다.</p>}
        </div>
        <div className="wk-actions">
          <label className="wk-title">보고서 제목<input value={s.title} maxLength={120} onChange={(e) => set({ title: e.target.value, titleTouched: true })} /></label>
          <button type="button" className="button primary wk-main" disabled={!!busy} onClick={makeDraft}>{busy === "draft" ? "초안 만드는 중…" : "보고서 초안 만들기"}</button>
        </div>
      </section>
    );

    const d = s.draft;
    const draftPanel = d && s.report && (
      <section className="wk-panel wk-output" aria-label="출력: 주간 업무보고서 초안">
        <div className="wk-panel-head">
          <h2>출력: 주간 업무보고서 초안 <small>직접 수정 가능</small></h2>
          <span className="wk-row-meta">
            <Chip tone="ok">메모 {s.report.stats.rows}줄 중 {s.report.stats.linked_rows}줄 회의록 연결</Chip>
            <Chip>회의 {s.report.stats.meetings}건</Chip>
            {s.dirty && <Chip tone="warn">저장하지 않은 수정</Chip>}
          </span>
        </div>
        <label className="wk-title">제목<input value={d.title} maxLength={120} onChange={(e) => editDraft({ title: e.target.value })} /></label>
        <p className="muted">■ 주간 업무보고 ({md(s.report.start)}~{md(s.report.end)}) · 작성 {s.report.author_name}</p>
        {d.sections.map((sec, n) => (
          <div className="wk-section" key={sec.key}>
            <h3>{n + 1}. {sec.heading}</h3>
            {sec.items.length === 0 && <p className="muted">기재 내용 없음</p>}
            {sec.items.map((it, i) => {
              const key = it.id || it.tmp || i;
              if (it.type === "group") return <div className="wk-group" key={key}>■ {it.text}</div>;
              const open = s.openEvidence[key];
              return (
                <div className={"wk-item" + (it.level ? " sub" : "")} key={key}>
                  <div className="wk-item-line">
                    <span aria-hidden="true">{it.level ? "-" : "·"}</span>
                    <textarea rows={Math.max(1, Math.ceil(it.text.length / 58))} aria-label={sec.heading + " " + (i + 1)} value={it.text} maxLength={600} onChange={(e) => editItem(sec.key, i, { text: e.target.value.replace(/\n/g, " ") })} />
                    <Chip tone={it.source === "memo" || it.source === "manual" ? "low" : "ok"}>{SOURCE[it.source] || ""}</Chip>
                    {it.edited && <Chip tone="warn" title="초안 생성 뒤 글을 고친 줄입니다. 근거와 맞는지 확인해 주세요.">수정됨</Chip>}
                    <button type="button" className="wk-link" aria-expanded={!!open} onClick={() => set((cur) => ({ openEvidence: { ...cur.openEvidence, [key]: !open } }))}>근거 {it.evidence.length}</button>
                    <button type="button" className="wk-x" aria-label="이 줄 삭제" onClick={() => removeItem(sec.key, i)}>×</button>
                  </div>
                  {open && <Evidence list={it.evidence} openMeeting={openMeeting} />}
                </div>
              );
            })}
            <button type="button" className="wk-link" onClick={() => addItem(sec.key)}>+ 줄 추가</button>
          </div>
        ))}
        <div className="wk-section">
          <h3>3. 조치사항 (담당자 / 기한)</h3>
          <table className="wk-table wk-actions-table">
            <thead><tr><th>조치사항</th><th style={{ width: "7em" }}>담당</th><th style={{ width: "7em" }}>기한</th><th style={{ width: "5.5em" }}>근거</th><th style={{ width: "2em" }}><span className="wk-hidden">삭제</span></th></tr></thead>
            <tbody>
              {d.actions.map((a, i) => {
                const key = "A" + i, open = s.openEvidence[key];
                return (
                  <React.Fragment key={key}>
                    <tr>
                      <td><textarea rows={Math.max(1, Math.ceil(a.task.length / 34))} aria-label={"조치사항 " + (i + 1)} value={a.task} maxLength={600} onChange={(e) => editAction(i, { task: e.target.value.replace(/\n/g, " ") })} /></td>
                      <td><input aria-label={"담당 " + (i + 1)} value={a.owner} maxLength={60} onChange={(e) => editAction(i, { owner: e.target.value })} /></td>
                      <td><input aria-label={"기한 " + (i + 1)} value={a.due} maxLength={40} onChange={(e) => editAction(i, { due: e.target.value })} /></td>
                      <td><button type="button" className="wk-link" aria-expanded={!!open} onClick={() => set((cur) => ({ openEvidence: { ...cur.openEvidence, [key]: !open } }))}>{(a.evidence || []).length ? "회의록" : "없음"}</button>{a.edited && <Chip tone="warn" title="회의록의 담당·기한과 다르게 고쳤습니다.">수정됨</Chip>}</td>
                      <td><button type="button" className="wk-x" aria-label="조치사항 삭제" onClick={() => editDraft((cur) => ({ actions: cur.actions.filter((_, x) => x !== i) }))}>×</button></td>
                    </tr>
                    {open && <tr><td colSpan={5}><Evidence list={a.evidence || []} openMeeting={openMeeting} /></td></tr>}
                  </React.Fragment>
                );
              })}
              {d.actions.length === 0 && <tr><td colSpan={5} className="muted">기재 내용 없음</td></tr>}
            </tbody>
          </table>
          <button type="button" className="wk-link" onClick={() => editDraft((cur) => ({ actions: [...cur.actions, { task: "", owner: "", due: "", evidence: [] }] }))}>+ 조치사항 추가</button>
        </div>
        {s.proposals && (
          <div className="wk-proposals">
            <h3>AI 문장 다듬기 제안 <small>{s.proposals.length}건</small></h3>
            {s.proposals.length === 0 && <p className="muted">고칠 문장이 없거나, 원문에 없는 내용이 섞여 모두 걸러졌습니다.</p>}
            {s.proposals.map((p, i) => (
              <label className="wk-cand on" key={p.id}>
                <input type="checkbox" checked={p.on} onChange={() => set((cur) => ({ proposals: cur.proposals.map((x, n) => (n === i ? { ...x, on: !x.on } : x)) }))} />
                <span className="wk-cand-body"><span className="wk-cand-why">{p.before}</span><span className="wk-cand-text">→ {p.after}</span></span>
              </label>
            ))}
            <div className="actions">
              {s.proposals.length > 0 && <button type="button" className="button primary" onClick={applyProposals}>선택한 제안 적용</button>}
              <button type="button" className="button" onClick={() => set({ proposals: null })}>닫기</button>
            </div>
          </div>
        )}
        <div className="wk-actions">
          <label className="wk-check"><input type="checkbox" checked={!!d.checked} onChange={(e) => editDraft({ checked: e.target.checked })} />내용 확인 완료 (Word에 '작성자 확인 완료'로 표시)</label>
          <span className="actions">
            {aiReady && <button type="button" className="button" disabled={!!busy} onClick={polish}>{busy === "polish" ? "다듬는 중…" : "AI로 문장 다듬기"}</button>}
            {s.matched && <button type="button" className="button" disabled={!!busy} onClick={() => set({ step: "confirm" })}>다시 생성</button>}
            <button type="button" className="button" disabled={!!busy || !s.dirty} onClick={() => save(false)}>{busy === "save" ? "저장 중…" : "저장"}</button>
            <button type="button" className="button primary" disabled={!!busy} onClick={downloadWord}>Word로 저장</button>
          </span>
        </div>
        {!aiReady && <p className="muted">AI 문장 다듬기는 AI 실행 환경이 준비된 PC에서만 보입니다. 초안은 AI 없이 만들어졌습니다.</p>}
      </section>
    );

    return (
      <div className="wk">
        <div className="page-heading">
          <div>
            <h1>주간보고 작성</h1>
            <p>업무 메모를 넣으면 등록된 회의록에서 관련 결정·조치를 찾아 주간 업무보고서 초안을 만듭니다.</p>
          </div>
          <div className="actions"><button type="button" className="button" disabled={!!busy} onClick={startNew}>새로 작성</button></div>
        </div>
        <ol className="wk-steps">
          {steps.map(([key, label]) => <li key={key} className={s.step === key ? "on" : ""} aria-current={s.step === key ? "step" : undefined}>{label}</li>)}
        </ol>
        {error && <div className="error-box" role="alert">{error}</div>}
        <div className="wk-grid">
          {inputPanel}
          {s.step === "confirm" && confirmPanel}
          {s.step === "draft" && draftPanel}
          {s.step === "input" && (
            <section className="wk-panel wk-output wk-placeholder" aria-label="안내">
              <h2>출력: 주간 업무보고서 초안</h2>
              <p className="muted">왼쪽에 이번 주 업무를 넣고 ‘회의록 연결 찾기’를 누르면, 연결을 확인한 뒤 여기에 초안이 만들어집니다.</p>
              <ul className="muted"><li>1. 금주 실적</li><li>2. 차주 계획</li><li>3. 조치사항 (담당자 / 기한)</li></ul>
              {s.report && <button type="button" className="button" onClick={() => set({ step: "draft" })}>작성 중인 초안으로 돌아가기</button>}
            </section>
          )}
        </div>
        <section className="wk-saved" aria-label="저장한 초안">
          <h2>저장한 초안 <small>{saved.length}</small></h2>
          {saved.length === 0 && <p className="muted">아직 저장한 초안이 없습니다. 초안은 작성자 본인에게만 보입니다.</p>}
          {saved.map((r) => (
            <div className={"wk-saved-row" + (s.report && s.report.id === r.id ? " on" : "")} key={r.id}>
              <button type="button" className="wk-saved-open" onClick={() => loadReport(r.id)}>
                <b>{r.title}</b>
                <span className="muted">{r.start} ~ {r.end} · 수정 {r.updated_at.slice(0, 16).replace("T", " ")} · {r.checked ? "확인 완료" : "검토 전"}</span>
              </button>
              {confirmDelete === r.id
                ? <span className="actions"><button type="button" className="button" onClick={() => removeReport(r.id)}>삭제 확인</button><button type="button" className="wk-link" onClick={() => setConfirmDelete("")}>취소</button></span>
                : <button type="button" className="wk-link" onClick={() => setConfirmDelete(r.id)}>삭제</button>}
            </div>
          ))}
        </section>
      </div>
    );
  };
}
