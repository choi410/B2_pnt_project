import React from "react";
import { Plus, Tag } from "lucide-react";
import { categoryChoices, categoryLabel, sameSubject } from "./history_filters.mjs";

export function HistoryCategoryEditor({ group, project, records, canEdit, api, onSaved }) {
  const [open, setOpen] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const [category, setCategory] = React.useState(group.category || "미분류");
  const [name, setName] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    setOpen(false); setAdding(false); setCategory(group.category || "미분류"); setName(""); setError("");
  }, [group.key]);
  if (!canEdit) return null;
  const choices = categoryChoices(project, records);
  async function submit(event) {
    event.preventDefault();
    const value = adding ? name.trim().replace(/\s+/g, " ") : category;
    if (!value || value.length > 20) { setError("구분 이름을 1~20자로 입력해 주세요."); return; }
    setBusy(true); setError("");
    try {
      const versions = records.filter(e => sameSubject(e, group) && e.review_state !== "제외")
        .map(e => ({ id: e.id, version: e.version }));
      const result = await api("/v3/changes/" + group.events[0].id + "/category", "PATCH",
        { category: value, create: adding, records: versions });
      await onSaved(result);
      setOpen(false); setAdding(false); setName("");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <div className="history-category-editor">
    <button type="button" className="history-category-toggle" aria-expanded={open} disabled={busy}
      onClick={() => { setOpen(!open); setError(""); }}>
      <Tag size={15} aria-hidden="true" />{group.category === "미분류" ? "구분 지정" : "구분 변경"}
    </button>
    {open && <form className="history-category-form" onSubmit={submit} aria-label="항목 구분 변경">
      <label>구분
        <select aria-label="항목에 지정할 구분" value={category} disabled={busy || adding}
          onChange={event => setCategory(event.target.value)}>
          {choices.map(value => <option key={value} value={value}>{categoryLabel(value)}</option>)}
        </select>
      </label>
      {adding ? <label>새 구분 이름
        <input autoFocus aria-label="새 구분 이름" placeholder="예: 비용, 품질, 교육·지원" maxLength={20}
          value={name} onChange={event => setName(event.target.value)} required disabled={busy} />
        <small>이 프로젝트에서 사용할 구분으로 추가합니다.</small>
      </label> : <button type="button" className="history-category-add" disabled={busy}
        onClick={() => { setAdding(true); setError(""); }}><Plus size={15} aria-hidden="true" />새 구분 추가</button>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="history-category-actions">
        <button type="button" disabled={busy} onClick={() => { setOpen(false); setAdding(false); setError(""); }}>취소</button>
        <button type="submit" className="primary" disabled={busy}>{busy ? "저장 중…" : adding ? "추가하고 적용" : "적용"}</button>
      </div>
    </form>}
  </div>;
}
