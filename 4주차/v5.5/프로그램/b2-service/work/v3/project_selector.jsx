import React from "react";
import { Check, ChevronDown, Folder, Search, X } from "lucide-react";

const normalize = value => String(value || "").normalize("NFKC").toLocaleLowerCase().replace(/[\s-]/g, "");

export function ProjectSelector({ projects, projectId, onChange, disabled, contextKey }) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const root = React.useRef(null), trigger = React.useRef(null), input = React.useRef(null);
  const panelId = React.useId();
  const selected = projects.find(project => project.id === projectId);
  const matches = projects.filter(project => normalize(project.name + " " + project.id).includes(normalize(query)));
  const close = (focus = false) => { setOpen(false); if (focus) trigger.current?.focus(); };
  React.useEffect(() => { setOpen(false); setQuery(""); }, [projectId, contextKey, disabled]);
  React.useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const escape = event => { if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); } };
    const focusOutside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    document.addEventListener("focusin", focusOutside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      document.removeEventListener("focusin", focusOutside);
    };
  }, [open]);
  const choose = id => {
    if (onChange(id) === false) return;
    close(true);
    setQuery("");
  };
  return <div className="global-project" ref={root}>
    <button type="button" className="global-project-trigger" ref={trigger} disabled={disabled}
      title={selected?.name || "전체 프로젝트"} aria-label={selected ? `프로젝트 선택: ${selected.name} (${selected.id})` : "프로젝트 선택: 전체 프로젝트"}
      aria-haspopup="dialog" aria-expanded={open} aria-controls={panelId}
      onClick={() => { setQuery(""); setOpen(value => !value); }}>
      <Folder size={19} aria-hidden="true" />
      <span className="global-project-code">{selected?.id || "전체 프로젝트"}</span>
      <ChevronDown size={16} aria-hidden="true" />
    </button>
    {open && <section className="global-project-panel" id={panelId} role="dialog" aria-label="프로젝트 선택">
      <div className="global-project-heading"><b>프로젝트 선택</b>
        <button type="button" className="icon-button" aria-label="프로젝트 선택 닫기" onClick={() => close(true)}><X size={17} /></button>
      </div>
      <label className="global-project-search"><Search size={17} aria-hidden="true" />
        <input ref={input} type="search" value={query} onChange={event => setQuery(event.target.value)}
          placeholder="이름 또는 코드 검색" aria-label="프로젝트 이름 또는 코드 검색" />
      </label>
      <div className="global-project-options">
        <button type="button" className="global-project-option global-project-all" aria-pressed={!projectId} onClick={() => choose("")}>
          <span>전체 프로젝트</span><small>모든 프로젝트 조회</small>{!projectId && <Check size={16} aria-hidden="true" />}
        </button>
        {matches.map(project => <button type="button" key={project.id} className="global-project-option"
          aria-pressed={project.id === projectId} onClick={() => choose(project.id)}>
          <span>{project.name}</span><small>{project.id}</small>
          {project.id === projectId && <Check size={16} aria-hidden="true" />}
        </button>)}
        {!matches.length && <p className="global-project-empty" role="status">{projects.length ? "검색 결과가 없습니다." : "등록된 프로젝트가 없습니다."}</p>}
      </div>
    </section>}
  </div>;
}
