import React from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { categoryLabel, HISTORY_STATES, stateLabel } from "./history_filters.mjs";

export function HistoryToolbar({
  projectId, history, meetings, counts, categories,
  resultCount, canExpand, allExpanded, onToggleAll, onChange,
}) {
  const [expanded, setExpanded] = React.useState(false);
  const details = React.useRef(null), trigger = React.useRef(null), panelId = React.useId();
  React.useEffect(() => {
    if (!expanded) return;
    const outside = event => { if (!details.current?.contains(event.target)) setExpanded(false); };
    const escape = event => { if (event.key === "Escape") { setExpanded(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [expanded]);
  React.useEffect(() => { setExpanded(false); }, [projectId]);
  const update = (key, value) => { history[key] = value; history.page = 0; onChange(); };
  const applied = [
    history.filter && history.filter !== "all" && { key: "filter", label: stateLabel(history.filter) },
    history.cat && { key: "cat", label: categoryLabel(history.cat) },
    history.mt && { key: "mt", label: meetings.find(m => m.id === history.mt)?.t || "선택한 회의록" },
    history.q && { key: "q", label: "검색: " + history.q },
  ].filter(Boolean);
  const detailCount = Number(!!history.cat) + Number(!!history.mt);
  const clear = () => {
    history.filter = "all"; history.cat = history.mt = history.rv = history.q = "";
    history.page = 0; onChange();
  };
  return <div className="history-toolbar">
    <div className="history-toolbar-main">
      <label className="history-search-field"><Search size={17} aria-hidden="true" />
        <input type="search" aria-label="변경 항목 검색" placeholder="항목·내용 검색"
          value={history.q || ""} onChange={event => update("q", event.target.value)} />
      </label>
      <div className="history-detail-conditions" ref={details}>
        <button type="button" ref={trigger} className="history-filter-toggle" aria-expanded={expanded}
          aria-controls={panelId} onClick={() => setExpanded(v => !v)}>
          <SlidersHorizontal size={17} aria-hidden="true" />상세 조건
          {detailCount > 0 && <span className="history-filter-count">{detailCount}</span>}
        </button>
        <div id={panelId} className="history-filter-panel" hidden={!expanded}>
          <div className="history-filter-heading"><b>상세 조건</b>
            <button type="button" aria-label="상세 조건 닫기" onClick={() => setExpanded(false)}><X size={17} /></button>
          </div>
          <label>구분
            <select aria-label="변경 구분" value={history.cat || ""} onChange={event => update("cat", event.target.value)}>
              <option value="">전체 구분</option>
              {categories.map(category => <option key={category} value={category}>{categoryLabel(category)}</option>)}
            </select>
          </label>
          <label>근거 회의록
            <select aria-label="변경 근거 회의록" value={history.mt || ""} onChange={event => update("mt", event.target.value)}>
              <option value="">전체 회의록</option>
              {meetings.map(m => <option key={m.id} value={m.id}>{(m.d ? m.d.replace(/-/g, ".") + " · " : "") + m.t}</option>)}
            </select>
          </label>
          <div className="history-filter-actions">
            <button type="button" onClick={() => { history.cat = history.mt = ""; history.page = 0; onChange(); }}>조건 초기화</button>
            <button type="button" onClick={() => setExpanded(false)}>닫기</button>
          </div>
        </div>
      </div>
    </div>
    <div className="history-state-row">
      <div className="history-state-filters" role="group" aria-label="항목의 최신 상태">
        {HISTORY_STATES.map(value => <button type="button" key={value} aria-pressed={(history.filter || "all") === value}
          onClick={() => update("filter", value)}>{stateLabel(value)} <span>{counts[value] || 0}</span></button>)}
      </div>
      <span className="history-result-count" aria-live="polite">항목 {resultCount}개</span>
      <button type="button" className="hx-expand" disabled={!canExpand} onClick={onToggleAll}>{allExpanded ? "모두 접기" : "모두 펼치기"}</button>
    </div>
    {applied.length > 0 && <div className="history-active-filters" aria-label="적용된 검색 조건">
      {applied.map(filter => <button type="button" key={filter.key} className="history-filter-chip"
        aria-label={filter.label + " 조건 해제"} title={filter.label}
        onClick={() => update(filter.key, filter.key === "filter" ? "all" : "")}>
        <span>{filter.label}</span><X size={13} aria-hidden="true" />
      </button>)}
      <button type="button" className="history-clear-filters" onClick={clear}>조건 초기화</button>
    </div>}
  </div>;
}
