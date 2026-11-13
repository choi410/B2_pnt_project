export const PROJECT_STAGES = ['수주', '설계 및 변경', '구매', '제작', '검수', '납품', '현장', '종료'];

export function projectStages(overview) {
  return overview?.stages?.length ? overview.stages : PROJECT_STAGES;
}
