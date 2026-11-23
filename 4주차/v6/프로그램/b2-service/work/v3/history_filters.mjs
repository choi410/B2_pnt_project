export const CATEGORY_LABELS = { 요구사항: "고객 요구", 사양: "사양·성능", 납기: "일정·납기", 미분류: "미분류" };
export const HISTORY_STATES = ["all", "요청", "확정", "보류", "철회"];
export const stateLabel = value => ({ all: "전체", 확정: "합의" }[value] || value);
export const categoryLabel = value => CATEGORY_LABELS[value] || value || "미분류";
export const subjectName = value => String(value || "").replace(/[\s·_().-]/g, "").toLowerCase();
export const groupKey = (project, category, title) => project + "|" + category + "|" + subjectName(title);
export const sameSubject = (record, group) => record.project_id === group.project_id &&
  record.category === group.category && subjectName(record.title) === subjectName(group.title);
export const latestState = group => group.events.at(-1)?.business_state || "";
export const matchesHistoryState = (group, filter) => !filter || filter === "all" || latestState(group) === filter;
export function usedCategories(groups) {
  return [...new Set(groups.map(g => g.category || "미분류"))]
    .sort((a, b) => (a === "미분류") - (b === "미분류") || categoryLabel(a).localeCompare(categoryLabel(b), "ko"));
}
export function categoryChoices(project, records) {
  return [...new Set([...Object.keys(CATEGORY_LABELS), ...(project?.change_categories || []),
    ...records.filter(e => e.project_id === project?.id && e.review_state !== "제외").map(e => e.category).filter(Boolean)])];
}
