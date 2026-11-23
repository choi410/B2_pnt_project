import assert from "node:assert/strict";
import { matchesHistoryState, usedCategories, categoryChoices, categoryLabel } from "./history_filters.mjs";
const flow = (...states) => ({events: states.map(business_state => ({business_state}))});
assert.equal(matchesHistoryState(flow("보류", "확정"), "보류"), false);
assert.equal(matchesHistoryState(flow("보류", "확정"), "확정"), true);
assert.equal(matchesHistoryState(flow("확정", "요청"), "확정"), false);
assert.equal(matchesHistoryState(flow("요청", "철회"), "철회"), true);
assert.equal(matchesHistoryState(flow("요청", "철회"), "all"), true);
assert.deepEqual(new Set(usedCategories([{category:"미분류"},{category:"비용"},{category:"비용"}])),new Set(["미분류","비용"]));
assert.equal(categoryLabel("납기"), "일정·납기");
assert.equal(categoryLabel("품질"), "품질");
const choices = categoryChoices({id:"p1",change_categories:["교육"]},[
  {project_id:"p1",category:"비용"},{project_id:"p2",category:"다른 프로젝트 구분"}]);
assert(choices.includes("교육") && choices.includes("비용"));
assert(!choices.includes("다른 프로젝트 구분"));
console.log("PASS: latest-state filters, dynamic categories and project isolation");
