import React from "react";
import { Bell, ChevronDown, FileText } from "lucide-react";

const endpoint = "/v3/management";
const statuses = { pending: "승인 대기", approved: "승인됨", rejected: "반려됨" };
const time = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "short",
});
const timestamp = value => Number.isFinite(Date.parse(value)) ? time.format(new Date(value)) : value;
const completedNews = {
  stage: "진행 단계가 변경됐어요",
  source: "회의록 정정 요청이 승인됐어요",
  trash: "회의록이 휴지통으로 이동했어요",
  undo: "변경 항목 확인이 취소됐어요",
  exclude: "변경 항목이 제외됐어요",
};

export function useManagement(api, userId) {
  const [data, setData] = React.useState({ items: [], count: 0, requests: [], error: "" });
  const generation = React.useRef(0);
  const refresh = React.useCallback(async () => {
    if (!userId) return;
    const current = ++generation.current;
    try {
      const [news, requests] = await Promise.all([api(endpoint + "/news"), api(endpoint + "/requests")]);
      if (current === generation.current) setData({ ...news, requests, error: "" });
    } catch (err) {
      if (current === generation.current) setData(old => ({ ...old, error: err.message }));
    }
  }, [api, userId]);
  React.useEffect(() => {
    setData({ items: [], count: 0, requests: [], error: "" });
    if (!userId) return;
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => { generation.current++; window.clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [userId, refresh]);
  return { ...data, refresh };
}

export function ManagementBell({ data, userId, onSelect, onHistory }) {
  const [open, setOpen] = React.useState(false);
  const [recentOnly, setRecentOnly] = React.useState(true);
  const root = React.useRef(null);
  const trigger = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    const click = e => { if (!root.current?.contains(e.target)) setOpen(false); };
    const key = e => { if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", click);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", click);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  const requests = new Map(data.requests.map(request => [request.id, request]));
  const pending = [];
  const recent = [];
  for (const row of data.items) {
    const request = requests.get(row.request_id);
    const received = request && request.requested_by !== userId && row.label.endsWith(" 요청");
    if (received) {
      if (request.status === "pending") pending.push(row);
    } else {
      recent.push(row);
    }
  }
  const unread = [...pending, ...recent].filter(row => row.unread).length;
  const renderRow = row => {
    const request = requests.get(row.request_id);
    const title = row.title || row.project_name;
    const action = row.label.replace(/ 요청( 승인| 반려)?$/, "");
    let headline = row.label;
    let person = row.person;
    if (request?.status === "pending") {
      headline = action + " 요청이 왔어요";
      person = person && "요청자 " + person;
    } else if (request?.status === "approved") {
      headline = completedNews[request.action] || action + " 요청이 승인됐어요";
      person = person && "승인 " + person;
    } else if (request?.status === "rejected") {
      headline = (request.action === "trash" ? "휴지통 이동" : action) + " 요청이 반려됐어요";
      person = person && "반려 " + person;
    }
    return <button key={row.id} type="button" className="management-news-row"
      aria-label={[row.unread && "읽지 않음", headline, title, person].filter(Boolean).join(", ")}
      onClick={() => { setOpen(false); onSelect(row); }}>
      <span className="management-news-dot" data-unread={row.unread} aria-hidden="true" />
      <strong>{headline}</strong>
      <span className="management-news-context">
        <span className="management-news-title" title={title}>{title}</span>
        {person && <span className="management-news-person"> · {person}</span>}
      </span>
    </button>;
  };
  return <div ref={root} className="management-bell">
    <button ref={trigger} type="button" className="icon-button management-trigger"
      aria-label={unread ? `새 소식 ${unread}건` : "새 소식"} aria-expanded={open}
      aria-controls={open ? "management-news" : undefined} onClick={() => {
        if (!open) { setRecentOnly(true); void data.refresh(); }
        setOpen(!open);
      }}>
      <Bell size={19} aria-hidden="true" />
      {unread > 0 && <span className="management-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
    </button>
    {open && <section id="management-news" className="management-popover" aria-label="새 소식 목록">
      <header><h2>새 소식</h2></header>
      {data.error && <p role="alert">{data.error}</p>}
      <div className="management-news-list">
        {pending.map(renderRow)}
        {(recentOnly ? recent.slice(0, 8) : recent).map(renderRow)}
        {recentOnly && recent.length > 8 && <button type="button" className="button" onClick={() => setRecentOnly(false)}>이전 소식 더 보기</button>}
        {!pending.length && !recent.length && !data.error && <p className="muted">새 소식이 없어요.</p>}
      </div>
      <button type="button" className="button management-history-link" onClick={() => { setOpen(false); onHistory(); }}>
        통합 기록 보기 <span aria-hidden="true">→</span>
      </button>
    </section>}
  </div>;
}

function MeetingPreview({ api, meetingId }) {
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const [meeting, setMeeting] = React.useState(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (!open || meeting) return;
    let active = true;
    api("/meetings/" + encodeURIComponent(meetingId))
      .then(result => { if (active) setMeeting(result); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [api, meetingId, open, meeting]);

  return <div className="management-preview">
    <button type="button" className="button management-preview-toggle" aria-expanded={open}
      aria-controls={open ? id : undefined}
      onClick={() => { setError(""); setOpen(!open); }}>
      <FileText size={16} aria-hidden="true" />
      {open ? "회의록 접기" : "회의록 열기"}
      <ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && <section id={id} className="management-preview-content" aria-label="회의록 원문">
      {error ? <p role="alert">{error}</p> : !meeting ? <p role="status">회의록을 불러오는 중이에요.</p> :
        <>
          <div className="management-preview-header">
            <strong>{meeting.revision > 1 ? "수정 본문" : "회의록 원문"}</strong>
            {meeting.date && <time dateTime={meeting.date}>{meeting.date}</time>}
          </div>
          <div className="management-preview-text" tabIndex={0} aria-label="회의록 본문">
            {meeting.source || meeting.lines?.map(line => line.text).join("\n") || "표시할 본문이 없어요."}
          </div>
        </>}
    </section>}
  </div>;
}

const historyFilters = [["", "전체"], ["request", "요청·승인"], ["edit", "수정"], ["trash", "삭제·복원"], ["mail", "메일"]];

function HistoryCard({ row, api, openRequest }) {
  const events = row.events || [];
  const request = events.find(event => event.kind === "request" && event.label.endsWith(" 요청"));
  const decision = events.find(event => event.kind === "request" && / 요청 (승인|반려)$/.test(event.label));
  const applied = events.find(event => event.kind === "trash" || event.kind === "edit");
  const action = request ? request.label.replace(/ 요청$/, "") : row.label;
  const status = request && (!decision ? "승인 대기" : decision.label.endsWith(" 반려") ? "반려됨" :
    applied?.kind === "trash" ? "이동 완료" : applied ? "반영 완료" : "승인됨");
  const reason = request ? request.reason : row.reason;
  const processed = decision || request || row;
  const subject = row.title || row.project_name;

  return <li className="management-history-card">
    <details>
      <summary>
        <span className="management-history-summary">
          <strong className="management-history-title">{subject}</strong>
          <span className="management-history-action">
            <span>{action}</span>
            {status && <span className={"status" + (!decision ? " warning" : "")}>{status}</span>}
          </span>
        </span>
        <time className="muted" dateTime={processed.at}>{timestamp(processed.at)}</time>
        <span className="management-history-expand"><span className="history-show">상세 보기</span><span className="history-hide">접기</span>
          <ChevronDown size={14} aria-hidden="true" />
        </span>
      </summary>
      <div className="management-history-details">
        <p className="management-history-meta">
          {row.project_name !== subject && <span>프로젝트 {row.project_name}</span>}
          {processed.person && <span>{!decision && request ? "요청자" : "처리자"} {processed.person}</span>}
        </p>
        {reason && <p className="management-history-reason"><span>{request ? "요청 사유" : "사유"}</span> {reason}</p>}
        {(applied?.detail || (!request && row.detail)) && <p>{applied?.detail || row.detail}</p>}
        {decision?.reason && decision.reason !== reason &&
          <p className="management-history-reason"><span>처리 사유</span> {decision.reason}</p>}
        {events.length > 1 && <div className="management-history-steps">
          <strong>처리 과정</strong>
          <ol>{[...events.filter(event => event.kind === "request"), ...events.filter(event => event.kind !== "request")].map(event => (
            <li key={event.id}>
              <strong>{event === request ? "요청 접수" : event === decision ?
                event.label.endsWith(" 반려") ? "팀장 반려" : "팀장 승인" :
                event === applied ? event.kind === "trash" ? "휴지통으로 이동" : "변경 반영" : event.label}</strong>
              <span>{[event.person, timestamp(event.at)].filter(Boolean).join(" · ")}</span>
            </li>
          ))}</ol>
        </div>}
        {(row.can_open || row.can_review) && <div className="management-history-actions">
          {row.can_open && <MeetingPreview api={api} meetingId={row.meeting_id} />}
          {row.can_review && <button type="button" className="button" onClick={() => openRequest(row.request_id)}>
            {request && !decision ? "요청 확인" : "요청 상세"}
          </button>}
        </div>}
      </div>
    </details>
  </li>;
}

export function ManagementHistory({ api, Modal, close, projects, initialProject, initialMeeting, openRequest }) {
  const [project, setProject] = React.useState(initialProject || "");
  const [meeting, setMeeting] = React.useState(initialMeeting || "");
  const [kind, setKind] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [projectChoices, setProjectChoices] = React.useState(projects);
  const resultsRef = React.useRef(null);
  React.useEffect(() => {
    let active = true;
    if (resultsRef.current) resultsRef.current.scrollTop = 0;
    setResult(null);
    setError("");
    const query = new URLSearchParams({ project_id: project, meeting_id: meeting, kind, offset, group_requests: true });
    api(endpoint + "/history?" + query).then(data => { if (active) { setResult(data); setProjectChoices(data.projects); } })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [api, project, meeting, kind, offset]);
  return <Modal title="통합 기록" close={close} className="management-history-modal">
    <div className="management-filters">
      <label>프로젝트 <select value={project} onChange={e => { setProject(e.target.value); setMeeting(""); setOffset(0); }}>
        <option value="">전체 프로젝트</option>
        {project && !projectChoices.some(item => item.id === project) && <option value={project}>{project}</option>}
        {projectChoices.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      {meeting && <button type="button" className="button" onClick={() => { setMeeting(""); setOffset(0); }}>이 회의록만 보기 해제</button>}
    </div>
    <div className="management-filters" aria-label="기록 종류">
      {historyFilters.map(([key,label]) => <button type="button" key={label} aria-pressed={key === kind}
        className={"button" + (key === kind ? " primary" : "")} onClick={() => { setKind(key); setOffset(0); }}>{label}</button>)}
    </div>
    <div ref={resultsRef} className="management-history-results" role="region" aria-label="기록 목록"
      aria-busy={!error && !result} tabIndex={0}>
      {error ? <p role="alert">{error}</p> : !result ? <p role="status">기록을 불러오는 중이에요.</p> :
        !result.items.length ? <p>이 범위에 기록이 없어요.</p> :
        <ol className="management-timeline">{result.items.map(row =>
          <HistoryCard key={row.request_id || row.id} row={row} api={api} openRequest={openRequest} />)}</ol>}
      {result && (offset > 0 || result.more) && <div className="management-filters">
        <button type="button" className="button" disabled={!offset} onClick={() => setOffset(offset-50)}>이전</button>
        <button type="button" className="button" disabled={!result.more} onClick={() => setOffset(offset+50)}>다음</button>
      </div>}
    </div>
  </Modal>;
}

export function ManagementRequest({ api, Modal, close, row, event, userId, changed, meetingAvailable, onViewed }) {
  const [reason, setReason] = React.useState("");
  const [rejecting, setRejecting] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const rendered = React.useRef(false);
  React.useEffect(() => {
    if (event?.unread && !rendered.current) {
      rendered.current = true;
      onViewed(event.id);
    }
  }, [event, onViewed]);

  async function decide(approved) {
    setBusy(true);
    setError("");
    try {
      await api(endpoint + "/requests/" + row.id + "/decision", "POST", {
        approved, reason: approved ? "" : reason.trim(),
      });
    } catch (err) {
      setError(err.message);
      setBusy(false);
      return;
    }
    close();
    await changed(row, approved);
  }

  const awaiting = row?.status === "pending" && row.requested_by !== userId;
  const meetingId = row?.meeting_id || event?.meeting_id;
  const footer = awaiting && (rejecting ? <>
    <button type="button" className="button" disabled={busy}
      onClick={() => { setRejecting(false); setError(""); }}>돌아가기</button>
    <button type="button" className="button primary" disabled={busy || !reason.trim()}
      onClick={() => decide(false)}>반려 확정</button>
  </> : <>
    <button type="button" className="button" disabled={busy}
      onClick={() => { setRejecting(true); setError(""); }}>반려</button>
    <button type="button" className="button primary" disabled={busy}
      onClick={() => decide(true)}>승인·반영</button>
  </>);

  return <Modal title={event?.label || row?.label || "처리 요청"} close={close} footer={footer}
    className={"management-request-modal" + (row?.current ? " management-compare-modal" : "")}>
    <div className="management-request-context">
      <div className="management-row-head">
        {row && <span className={"status" + (awaiting ? " warning" : "")}>{statuses[row.status]}</span>}
        {row ? <span className="muted">요청자 {row.requester}</span> : event?.person && <span className="muted">{event.person}</span>}
      </div>
      <h3>{row?.title || event?.title}</h3>
      {event?.project_name && event.project_name !== (row?.title || event?.title) && <small className="muted">{event.project_name}</small>}
    </div>
    {row ? <>
      <dl className="management-request-fields">
        <dt>요청 사유</dt><dd>{row.reason}</dd>
        {row.action === "stage" && <><dt>단계 변경</dt><dd>{row.before || "자동 판단"} → {row.proposal.stage || "자동 판단"}</dd></>}
        {row.decision_reason && <><dt>처리 사유</dt><dd>{row.decision_reason}</dd></>}
      </dl>
      {row.action === "source" && row.current && <div className="management-source">
        <div><strong>현재 회의록</strong><p>{row.current.title} · {row.current.date}</p><pre>{row.current.source}</pre></div>
        <div><strong>정정 요청</strong><p>{row.proposal.title} · {row.proposal.date}</p><pre>{row.proposal.source}</pre></div>
      </div>}
      {row.action === "trash" && row.status === "pending" && <p className="management-request-impact">
        승인하면 회의록이 휴지통으로 이동하고, 연결된 변경 기록은 목록에서 숨겨져요.
      </p>}
    </> : <p>{event?.reason || event?.detail}</p>}
    {meetingAvailable && meetingId && !row?.current && <MeetingPreview key={meetingId} api={api} meetingId={meetingId} />}
    {awaiting && rejecting && <label className="management-rejection">반려 사유
      <textarea autoFocus rows="2" maxLength="500" required value={reason}
        onChange={e => setReason(e.target.value)} />
    </label>}
    {error && <p role="alert">{error}</p>}
  </Modal>;
}

export function ManagementAction({ Modal, close, modal, api, saved }) {
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  async function submit(event) {
    event.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true); setError("");
    try {
      if (modal.execute) await modal.execute(reason.trim());
      else await api(endpoint + "/requests", "POST", { ...modal.proposal, reason: reason.trim() });
      close();
      await saved(modal.execute ? "처리했습니다." : "팀장에게 요청을 보냈습니다.");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <Modal title={modal.title} close={close}>
    <form onSubmit={submit}>
      {modal.description && <p>{modal.description}</p>}
      <label>사유<textarea value={reason} onChange={e => setReason(e.target.value)} required maxLength="500" rows="2" /></label>
      <button type="submit" className="button primary" disabled={busy || !reason.trim()}>{modal.execute ? "반영" : "요청 보내기"}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  </Modal>;
}
