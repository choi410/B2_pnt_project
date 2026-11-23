// Team v4 interface, migrated into editable source. AI uses our current conversation module.
import React from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  CloudUpload,
  Download,
  FileText,
  LoaderCircle,
  LogOut,
  MessageCircle,
  Moon,
  Pencil,
  Plus,
  Quote,
  Search,
  Settings,
  StickyNote,
  Sun,
  Trash2,
  X,
  Sparkles,
  History,
  Route,
  Users,
  Bell,
} from "lucide-react";
import logo from "./assets/pnt-logo.png";
import { QuestionPanel } from "./conversation_panel";
import { HistoryToolbar } from "./history_toolbar";
import { ProjectSelector } from "./project_selector";
import { HistoryCategoryEditor } from "./history_category_editor";
import { categoryLabel, groupKey, HISTORY_STATES, matchesHistoryState, usedCategories } from "./history_filters.mjs";
import { updateWorkspace } from "./workspace_state.mjs";
import workflow from "./team_ui/project_flow";
import createApproval from "./team_ui/approval";
import { AdminConsole } from "./admin_console";
import { createWeeklyReport } from "./weekly_report";
var isoDay = (a) => a.toISOString().slice(0, 10);
var eventsOn = (a, e) => a.filter((t) => t.start <= e && t.end >= e);
function calendarWeeks(a, e) {
  let [t, l] = a.split("-").map(Number),
    u = new Date(Date.UTC(t, l - 1, 1)),
    o = (u.getUTCDay() + 6) % 7,
    f = new Date(Date.UTC(t, l, 0)).getUTCDate();
  return Array.from(
    {
      length: Math.ceil((o + f) / 7),
    },
    (d, i) => {
      let m = Array.from(
          {
            length: 7,
          },
          (s, L) => isoDay(new Date(Date.UTC(t, l - 1, 1 - o + i * 7 + L))),
        ),
        p = [],
        x = e
          .filter((s) => s.start <= m[6] && s.end >= m[0])
          .map((s) => ({
            ...s,
            from: s.start < m[0] ? 0 : m.indexOf(s.start),
            to: s.end > m[6] ? 6 : m.indexOf(s.end),
          }))
          .sort(
            (s, L) =>
              s.from - L.from ||
              L.to - L.from - (s.to - s.from) ||
              s.id.localeCompare(L.id),
          )
          .map((s) => {
            let L = p.findIndex((v) => v < s.from);
            return (
              L < 0 && (L = p.length),
              (p[L] = s.to),
              {
                ...s,
                lane: L,
                continuesBefore: s.start < m[0],
                continuesAfter: s.end > m[6],
              }
            );
          });
      return {
        dates: m,
        segments: x.filter((s) => s.lane < 2),
        overflow: m.map(
          (s, L) =>
            x.filter((v) => v.lane >= 2 && v.from <= L && v.to >= L).length,
        ),
      };
    },
  );
}
function TrashPanel({ close: a, onChanged: e }) {
  let [t, l] = (0, React.useState)(null),
    [u, o] = (0, React.useState)("meetings"),
    [f, d] = (0, React.useState)(null),
    [i, m] = (0, React.useState)(!1),
    [p, x] = (0, React.useState)(""),
    [s, L] = (0, React.useState)(""),
    v = async () => l(await api("/v3/trash"));
  (0, React.useEffect)(() => {
    let r = !0;
    return (
      api("/v3/trash")
        .then((h) => {
          r && l(h);
        })
        .catch((h) => {
          r && x(h.message);
        }),
      () => {
        r = !1;
      }
    );
  }, []);
  async function A(r) {
    (m(!0), x(""), L(""));
    try {
      await r();
    } catch (h) {
      x(h.message);
    } finally {
      m(!1);
    }
  }
  async function D(r) {
    (await api(
      r.kind === "project"
        ? "/projects/" + r.id + "/restore"
        : "/v3/meetings/" + r.id + "/restore",
      "POST",
      r.kind === "project"
        ? {
            version: r.version,
          }
        : void 0,
    ),
      await v(),
      await e(),
      L("복원했습니다."));
  }
  async function g() {
    (await api("/v3/trash/" + f.kind + "/" + f.id, "DELETE", {
      version: f.version,
      confirmed: !0,
    }),
      d(null),
      await v(),
      await e(),
      L("영구 삭제했습니다."));
  }
  return (
    <Modal
      title={f ? "영구 삭제 확인" : "휴지통"}
      close={() => {
        i || a();
      }}
      footer={
        f ? (
          <React.Fragment>
            <Button
              disabled={i}
              onClick={() => {
                (d(null), x(""));
              }}
            >
              {"취소"}
            </Button>
            <Button
              className="danger-button"
              disabled={i || !!f.blocked}
              onClick={() => A(g)}
            >
              {"영구 삭제"}
            </Button>
          </React.Fragment>
        ) : null
      }
    >
      {p && (
        <p className="error-box" role="alert">
          {p}
        </p>
      )}
      {s && <p role="status">{s}</p>}
      {f ? (
        <React.Fragment>
          <h3>{f.title}</h3>
          <p className="muted">
            {f.kind === "project" ? f.id : f.project_name}
          </p>
          <p>
            {f.kind === "project"
              ? "프로젝트와 그 안의 회의록 " + f.counts.meeting + "개"
              : "이 회의록"}
            {", 연결된 변경 기록 "}
            {f.counts.change_event}
            {"개와 해당 원본 파일을 삭제합니다."}
            {f.counts.task > 0 &&
              ` \uC5C5\uBB34 ${f.counts.task}\uAC1C\uB3C4 \uD3EC\uD568\uB429\uB2C8\uB2E4.`}
            {f.counts.report > 0 &&
              ` \uBCF4\uACE0\uC11C ${f.counts.report}\uAC1C\uB3C4 \uD3EC\uD568\uB429\uB2C8\uB2E4.`}
          </p>
          <p className="warning">{"삭제 후에는 복원할 수 없습니다."}</p>
          {f.blocked && <p role="alert">{f.blocked}</p>}
        </React.Fragment>
      ) : (
        <React.Fragment>
          <div
            className="tabs trash-tabs"
            role="tablist"
            aria-label="휴지통 종류"
          >
            {[
              ["meetings", "회의록"],
              ["projects", "프로젝트"],
            ].map(([r, h]) => (
              <button
                role="tab"
                aria-selected={u === r}
                key={r}
                className={u === r ? "active" : ""}
                onClick={() => {
                  (o(r), x(""), L(""));
                }}
              >
                {h} <small>{t?.[r]?.length ?? 0}</small>
              </button>
            ))}
          </div>
          {t ? (
            t[u].length ? (
              t[u].map((r) => (
                <div className="trash-row" key={r.id}>
                  <div>
                    <b>{r.title}</b>
                    <p className="muted">
                      {r.kind === "meeting" ? r.project_name : r.id}
                      {" · "}
                      {r.deleted_at.slice(0, 10)}
                    </p>
                    {r.blocked && <small className="muted">{r.blocked}</small>}
                  </div>
                  <div className="trash-actions">
                    <Button disabled={i} onClick={() => A(() => D(r))}>
                      {"복원"}
                    </Button>
                    <Button
                      disabled={i || !!r.blocked}
                      onClick={() =>
                        A(async () =>
                          d(await api("/v3/trash/" + r.kind + "/" + r.id)),
                        )
                      }
                    >
                      {"영구 삭제"}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <Empty>{"휴지통이 비어 있습니다."}</Empty>
            )
          ) : (
            <p role="status">{"불러오는 중…"}</p>
          )}
        </React.Fragment>
      )}
    </Modal>
  );
}
function HistoryEditor({ event: a, meeting: e, close: t, onSaved: l }) {
  let [u, o] = (0, React.useState)({
      title: a.title,
      business_state: a.business_state,
      before: a.before || "",
      after: a.after,
      evidence: [...a.evidence],
    }),
    [f, d] = (0, React.useState)(!1),
    [i, m] = (0, React.useState)(!1),
    [p, x] = (0, React.useState)(""),
    s = e.lines || [],
    L = s.filter((h) => u.evidence.includes(h.id)),
    v = (h, C) =>
      o((b) => ({
        ...b,
        [h]: C,
      })),
    A =
      u.title.trim().length >= 2 &&
      u.after.trim() &&
      L.length > 0 &&
      L.length <= 20,
    D =
      ["title", "business_state", "before", "after"].some(
        (h) => u[h] !== String(a[h] || ""),
      ) || u.evidence.join("|") !== a.evidence.join("|"),
    g = () => {
      i || t();
    };
  async function r() {
    if (!(!A || !D || i)) {
      (m(!0), x(""));
      try {
        let h = await api("/v3/changes/" + a.id, "PATCH", {
          ...u,
          version: a.version,
          source_revision: a.source_revision,
        });
        l(h);
      } catch (h) {
        x(h.message);
      } finally {
        m(!1);
      }
    }
  }
  return (
    <Modal
      title="변경 기록 수정"
      className="history-edit-modal"
      close={g}
      footer={
        <React.Fragment>
          <Button disabled={i} onClick={g}>
            {"취소"}
          </Button>
          <Button primary={!0} disabled={i || !A || !D} onClick={r}>
            {i && <LoaderCircle size={16} className="spin" />}
            {i ? "저장 중" : "변경 저장"}
          </Button>
        </React.Fragment>
      }
    >
      <div className="history-editor">
        <p className="history-edit-source">
          {e.title}
          {" · "}
          {e.date || "날짜 미정"}
        </p>
        <div className="history-edit-heading">
          <label>
            {"항목명"}
            <input
              autoFocus={!0}
              maxLength={160}
              value={u.title}
              disabled={i}
              onChange={(h) => v("title", h.target.value)}
            />
          </label>
          <label>
            {"상태"}
            <select
              value={u.business_state}
              disabled={i}
              onChange={(h) => v("business_state", h.target.value)}
            >
              {[
                ["요청", "요청"],
                ["확정", "합의"],
                ["보류", "보류"],
                ["철회", "철회"],
              ].map(([h, C]) => (
                <option key={h} value={h}>
                  {C}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="history-edit-values">
          <label>
            <span>
              {"변경 전 "}
              <small>{"(선택)"}</small>
            </span>
            <textarea
              rows={3}
              maxLength={1500}
              value={u.before}
              disabled={i}
              placeholder="이전 내용이 없으면 비워 두세요."
              onChange={(h) => v("before", h.target.value)}
            />
          </label>
          <label>
            {"변경 내용"}
            <textarea
              rows={3}
              maxLength={1500}
              value={u.after}
              disabled={i}
              onChange={(h) => v("after", h.target.value)}
            />
          </label>
        </div>
        <section className="history-edit-evidence">
          <div className="section-head">
            <h3>
              {"원문 근거 "}
              <small>
                {L.length}
                {"개"}
              </small>
            </h3>
            <button type="button" disabled={i} onClick={() => d(!f)}>
              {f ? "선택 마침" : "근거 변경"}
            </button>
          </div>
          {f ? (
            <div
              className="history-evidence-options"
              role="group"
              aria-label="원문 근거 선택"
            >
              {s.map((h) => (
                <label key={h.id}>
                  <input
                    type="checkbox"
                    checked={u.evidence.includes(h.id)}
                    disabled={
                      i || (!u.evidence.includes(h.id) && L.length >= 20)
                    }
                    onChange={(C) =>
                      v(
                        "evidence",
                        C.target.checked
                          ? [...u.evidence, h.id]
                          : u.evidence.filter((b) => b !== h.id),
                      )
                    }
                  />
                  <span>{h.text}</span>
                </label>
              ))}
            </div>
          ) : (
            <div className="history-evidence-quotes">
              {L.map((h) => (
                <blockquote key={h.id}>{h.text}</blockquote>
              ))}
            </div>
          )}
        </section>
        <p className="history-edit-note">
          {"선택한 기록만 수정합니다. 회의록 원문과 수정 전 기록은 보관됩니다."}
        </p>
        {p && (
          <p role="alert" className="history-edit-error">
            {p}
          </p>
        )}
      </div>
    </Modal>
  );
}
function displayChange(a) {
  let e = (a.before || "").trim(),
    t = (a.after || "").trim(),
    l = !!e && ["확정", "요청"].includes(a.business_state) && e !== t,
    u = (d) =>
      d.match(
        /^([\d,]+(?:\.\d+)?)\s*(m\/min|mm|cm|kg|kW|rpm|℃|°C|%)(?:(?:으)?로\s*변경\s*(?:합의|확정)(?:했다|함)?\.?)?$/i,
      ),
    o = u(e),
    f = u(t);
  return {
    transition: l,
    before: l && o && f && o[2] === f[2] ? o[1] : e,
    after: l && o && f && o[2] === f[2] ? f[1] : t,
    unit: l && o && f && o[2] === f[2] ? f[2] : "",
    label:
      a.business_state === "요청"
        ? "요청"
        : a.business_state === "확정"
          ? "합의"
          : a.business_state,
  };
}
var sentences = (a) =>
    String(a || "")
      .trim()
      .split(/(?<=[.!?])\s+/)
      .filter(Boolean),
  trimSentence = (a) => a.replace(/[.]$/, "").trim();
function conciseValue(a) {
  let e = trimSentence(a);
  for (let t of [
    /^(.+?)(?:을|를)\s*(?:기본\s*(?:설계\s*)?사양으로\s*)?(?:합의했다|합의함|합의|확정했다|확정함|확정)$/,
    /^(.+?)(?:으)?로\s*(?:변경(?:하기로)?\s*)?(?:합의했다|합의함|합의|확정했다|확정함|확정)$/,
    /^(.+?)(?:을|를)\s*유지(?:한다|하기로 했다|함)?$/,
  ]) {
    let l = e.match(t);
    if (l && !/않|아니|미정|보류|철회|요청|조건|검토/.test(l[1]))
      return l[1].trim() + (t.source.includes("유지") ? " 유지" : "");
  }
  return e;
}
function cardSummary(a) {
  let e = sentences(a.after),
    t = a.business_state,
    l = 0;
  (t === "보류" &&
    (l = Math.max(
      0,
      e.findIndex((s) => s.includes("보류")),
    )),
    t === "철회" &&
      (l = Math.max(
        0,
        e.findIndex((s) => /철회|취소/.test(s)),
      )));
  let u = e[l] || "",
    o = ["요청", "확정"].includes(t) ? conciseValue(u) : trimSentence(u),
    f = conciseValue(a.before || ""),
    d = displayChange({
      ...a,
      before: f,
      after: o,
    }),
    i = e.filter((s, L) => L !== l).map(trimSentence),
    m = trimSentence(a.context || "");
  m && !i.length && !e.some((s) => s.includes(m)) && i.push(m);
  let p = d.after.match(
      /^((?:(?:최대|최소|상한|하한|약)\s*)?[\d,]+(?:\.\d+)?)\s*(m\/min|mm|cm|kg|kW|rpm|℃|°C|%)(\s*(?:이상|이하|미만|초과))?$/i,
    ),
    x = !d.transition && !!p;
  return {
    ...d,
    after: x ? p[1] : d.after,
    unit: x ? p[2] + (p[3] || "") : d.unit,
    numeric: x || !!d.unit,
    detail: i.join(" · "),
  };
}
var preferencesKey = "pnt-v3-display-preferences";
function readPreferences() {
  try {
    let a = JSON.parse(localStorage.getItem(preferencesKey) || "{}");
    return {
      theme: a?.theme === "light" ? "light" : "dark",
      size:
        a?.v === 2 && ["small", "normal", "large"].includes(a?.size)
          ? a.size
          : "large",
      v: 2,
    };
  } catch {
    return {
      theme: "dark",
      size: "large",
      v: 2,
    };
  }
}
function DisplaySettings() {
  let [a, e] = (0, React.useState)(readPreferences),
    [t, l] = (0, React.useState)(!1),
    u = (0, React.useRef)(),
    o = (0, React.useRef)();
  return (
    (0, React.useLayoutEffect)(() => {
      ((document.documentElement.dataset.theme = a.theme),
        (document.documentElement.dataset.textSize = a.size));
      try {
        localStorage.setItem(
          preferencesKey,
          JSON.stringify({
            ...a,
            v: 2,
          }),
        );
      } catch {}
    }, [a]),
    (0, React.useEffect)(() => {
      if (!t) return;
      let f = (i) => {
          u.current?.contains(i.target) || l(!1);
        },
        d = (i) => {
          i.key === "Escape" && (l(!1), o.current?.focus());
        };
      return (
        document.addEventListener("pointerdown", f),
        document.addEventListener("keydown", d),
        () => {
          (document.removeEventListener("pointerdown", f),
            document.removeEventListener("keydown", d));
        }
      );
    }, [t]),
    (
      <div className="display-settings" ref={u}>
        <button
          ref={o}
          className="icon-button settings-trigger"
          aria-label="화면 설정"
          title="화면 설정"
          aria-expanded={t}
          aria-controls="display-settings-panel"
          onClick={() => l((f) => !f)}
        >
          <Settings size={21} />
        </button>
        {t && (
          <section
            id="display-settings-panel"
            role="dialog"
            aria-label="화면 설정"
            className="settings-panel"
          >
            <div className="section-head">
              <h2>{"화면 설정"}</h2>
              <button
                className="icon-button"
                aria-label="설정 닫기"
                onClick={() => {
                  (l(!1), o.current?.focus());
                }}
              >
                <X size={17} />
              </button>
            </div>
            <fieldset>
              <legend>{"테마"}</legend>
              <div className="setting-options">
                {[
                  ["light", "밝게", Sun],
                  ["dark", "어둡게", Moon],
                ].map(([f, d, i]) => (
                  <button
                    key={f}
                    type="button"
                    aria-pressed={a.theme === f}
                    onClick={() =>
                      e((m) => ({
                        ...m,
                        theme: f,
                      }))
                    }
                  >
                    {React.createElement(i, {
                      size: 17,
                    })}
                    {d}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>{"글자 크기"}</legend>
              <div className="setting-options">
                {[
                  ["small", "작게"],
                  ["normal", "기본"],
                  ["large", "크게"],
                ].map(([f, d]) => (
                  <button
                    key={f}
                    type="button"
                    aria-pressed={a.size === f}
                    onClick={() =>
                      e((i) => ({
                        ...i,
                        size: f,
                      }))
                    }
                  >
                    {d}
                  </button>
                ))}
              </div>
            </fieldset>
            <p className="settings-note">
              {"이 브라우저에 설정이 저장됩니다."}
            </p>
          </section>
        )}
      </div>
    )
  );
}
var sortCollator = new Intl.Collator("ko", {
    numeric: !0,
    sensitivity: "base",
  }),
  normalizeQuery = (a) =>
    String(a || "")
      .replace(/[\s·_().-]/g, "")
      .toLowerCase(),
  hr = [
    ["title", "회의록"],
    ["date", "회의일"],
    ["approval", "합의"],
    ["author", "등록자"],
  ];
function nextMeetingSort(a, e) {
  return {
    key: e,
    direction:
      a.key === e
        ? a.direction === "asc"
          ? "desc"
          : "asc"
        : e === "date"
          ? "desc"
          : "asc",
  };
}
function meetingNeedsStatus(a) {
  return (
    ["queued", "running", "failed"].includes(a.analysis_state) ||
    !!a.analysis_stale
  );
}
var processingMeeting = (a) => ["queued", "running"].includes(a.analysis_state);
function meetingProgress(a) {
  if (!processingMeeting(a)) return null;
  if (a.analysis_state === "queued")
    return {
      stage: "queued",
      label: "분석 대기",
      detail:
        a.progress?.queue_ahead > 0
          ? `\uC55E\uC120 \uD68C\uC758\uB85D ${a.progress.queue_ahead}\uAC74 \uCC98\uB9AC \uC911`
          : "분석 시작을 기다리고 있습니다.",
    };
  if (a.analysis_phase === "loading")
    return {
      stage: "analyzing",
      label: "모델 준비 중",
      detail: "AI 모델을 불러오고 있습니다.",
    };
  if (a.analysis_phase === "retrying")
    return {
      stage: "analyzing",
      label: "추가 분석 중",
      detail: "빠진 내용과 근거를 다시 확인하고 있습니다.",
    };
  let e = /^combined:(\d+)\/(\d+)$/.exec(a.analysis_phase || "");
  if (e) {
    let t = Number(e[1]),
      l = Number(e[2]);
    if (l > 0 && t <= l)
      return t === l
        ? {
            stage: "applying",
            label: "분석 결과 반영 중",
            detail: "회의록 정리·변경이력·일정을 갱신하고 있습니다.",
          }
        : {
            stage: "analyzing",
            label: "AI 분석 중",
            detail: `${l}\uAC1C \uAD6C\uAC04 \uC911 ${t}\uAC1C \uBD84\uC11D \uC644\uB8CC`,
          };
  }
  return {
    stage: "analyzing",
    label: "AI 분석 중",
    detail: "핵심 내용과 요구·변경사항을 정리하고 있습니다.",
  };
}
function meetingSections(a, e, t, l) {
  let u = sortMeetings(a, e, t, l);
  return {
    processing: u
      .filter(processingMeeting)
      .sort(
        (o, f) =>
          compareValue(o.created_at || "", f.created_at || "", "desc") ||
          String(o.id).localeCompare(String(f.id)),
      ),
    registered: u.filter((o) => !processingMeeting(o)),
  };
}
function compareValue(a, e, t) {
  return !a || !e
    ? a
      ? -1
      : e
        ? 1
        : 0
    : sortCollator.compare(a, e) * (t === "desc" ? -1 : 1);
}
function sortMeetings(
  a,
  e,
  t,
  {
    projectId: l = "",
    query: u = "",
    sort: o = {
      key: "date",
      direction: "desc",
    },
  } = {},
) {
  let f = new Map(e.map((p) => [p.id, p.name])),
    d = new Map(t.map((p) => [p.id, p.name])),
    i = (p) =>
      o.key === "approval"
        ? String(
            {
              rejected: 1,
              sent: 2,
              expired: 3,
              approved: 4,
            }[p.approval?.status] || 9,
          )
        : o.key === "project"
          ? f.get(p.project_id) || ""
          : o.key === "author"
            ? d.get(p.author) || ""
            : o.key === "title"
              ? p.title || ""
              : p.date || "",
    m = normalizeQuery(u);
  return a
    .filter(
      (p) =>
        (!l || p.project_id === l) &&
        normalizeQuery(
          [
            p.title,
            f.get(p.project_id),
            ...(p.points || []).map((x) => x.text),
          ].join(" "),
        ).includes(m),
    )
    .sort(
      (p, x) =>
        compareValue(i(p), i(x), o.direction) ||
        compareValue(p.date || "", x.date || "", "desc") ||
        compareValue(p.created_at || "", x.created_at || "", "desc") ||
        sortCollator.compare(p.title || "", x.title || "") ||
        String(p.id).localeCompare(String(x.id)),
    );
}
function formatDuration(a) {
  let e = Math.max(0, Math.floor(a));
  if (e < 60) return e + "초";
  let t = Math.floor(e / 60),
    l = e % 60;
  return t + "분" + (l ? " " + l + "초" : "");
}
function progressTime(a, e = 0, t = !1) {
  if (!a)
    return {
      elapsed: "",
      remaining: "예상 시간 계산 중",
    };
  let l = Number.isFinite(a.elapsed_seconds)
    ? (t ? "대기 " : "") +
      formatDuration(a.elapsed_seconds + Math.max(0, e)) +
      " 경과"
    : "";
  if (e > 12)
    return {
      elapsed: l,
      remaining: "진행 상태를 다시 확인 중",
    };
  let u = a.remaining_seconds;
  if (u) {
    let o = Math.max(0, u[0] - e),
      f = u[1] - e;
    if (f <= 0)
      return {
        elapsed: l,
        remaining: "예상보다 오래 걸리고 있습니다.",
      };
    let d = Math.max(5, Math.ceil(f / 5) * 5),
      i = Math.max(0, Math.floor(o / 5) * 5);
    return {
      elapsed: l,
      remaining:
        i > 0
          ? "예상 남은 시간 약 " + formatDuration(i) + "~" + formatDuration(d)
          : "예상 남은 시간 약 " + formatDuration(d) + " 이내",
    };
  }
  return {
    elapsed: l,
    remaining:
      a.estimate_status === "overdue"
        ? "예상보다 오래 걸리고 있습니다."
        : a.estimate_status === "loading"
          ? "모델 준비 후 예상 시간 표시"
          : a.estimate_status === "retrying"
            ? "추가 분석 중 · 예상 시간 계산 중"
            : "예상 시간 계산 중",
  };
}
function uploadImports(a, e, t = () => new XMLHttpRequest()) {
  return new Promise((l, u) => {
    let o = t();
    (o.open("POST", "/api/v3/imports"),
      (o.withCredentials = !0),
      (o.responseType = "json"),
      o.setRequestHeader("X-B2-Request", "workspace"),
      (o.upload.onprogress = (f) =>
        e({
          stage: "uploading",
          percent:
            f.lengthComputable && f.total > 0
              ? Math.min(100, Math.floor((f.loaded / f.total) * 100))
              : null,
        })),
      (o.upload.onload = () =>
        e({
          stage: "reading",
          percent: null,
        })),
      (o.onload = () => {
        let f = o.response;
        if (o.status < 200 || o.status >= 300) {
          u(
            Error(
              typeof f?.detail == "string"
                ? f.detail
                : "파일을 불러오지 못했습니다. 다시 시도해 주세요.",
            ),
          );
          return;
        }
        if (!f || !Array.isArray(f.items) || !Array.isArray(f.errors)) {
          u(Error("서버 응답을 읽지 못했습니다."));
          return;
        }
        l(f);
      }),
      (o.onerror = () =>
        u(Error("파일 전송 중 연결이 끊어졌습니다. 다시 시도해 주세요."))),
      (o.onabort = () => u(Error("파일 전송이 취소되었습니다."))),
      o.send(a));
  });
}
function useClock() {
  let [a, e] = (0, React.useState)(() => performance.now());
  return (
    (0, React.useEffect)(() => {
      let t = setInterval(() => e(performance.now()), 1e3);
      return () => clearInterval(t);
    }, []),
    a
  );
}
function ProgressTime({ snapshot: a, queued: e }) {
  let t = (0, React.useMemo)(() => performance.now(), [a?.measured_at]),
    l = useClock(),
    u = progressTime(a, Math.max(0, (l - t) / 1e3), e);
  return (
    <div className="analysis-timing">
      {u.elapsed && <span>{u.elapsed}</span>}
      <span>{u.remaining}</span>
    </div>
  );
}
function TransferProgress({ transfer: a }) {
  let e = useClock();
  if (!a) return null;
  let t = a.stage === "uploading",
    l = t
      ? "파일 업로드 중"
      : a.stage === "saving"
        ? "회의록 저장 중"
        : "파일 내용 확인 중",
    u = t ? a.percent : null;
  return (
    <section className="transfer-progress" aria-label="회의록 등록 진행">
      <div className="meeting-progress-label">
        <strong>
          {l}
          {u !== null ? " · " + u + "%" : ""}
        </strong>
        <span>
          {formatDuration(Math.max(0, (e - a.startedAt) / 1e3))}
          {" 경과"}
        </span>
      </div>
      <div
        className={
          "meeting-progress-track " + (u !== null ? "determinate" : "")
        }
        role="progressbar"
        aria-label={l}
        aria-valuenow={u ?? void 0}
        aria-valuemin={u !== null ? 0 : void 0}
        aria-valuemax={u !== null ? 100 : void 0}
        aria-valuetext={u !== null ? u + "%" : l}
      >
        <span
          style={
            u !== null
              ? {
                  width: u + "%",
                }
              : void 0
          }
        />
      </div>
      <small>
        {t
          ? "파일 전송량 기준입니다."
          : a.stage === "saving"
            ? "저장 후 AI 분석이 시작됩니다."
            : "전송한 파일의 내용을 읽고 프로젝트를 확인하고 있습니다."}
      </small>
    </section>
  );
}
function BatchProgress({ batch: a }) {
  return !a || a.total < 2 || (!a.pending && !a.failed) ? null : (
    <p className="registration-batch" role="status">
      {"최근 등록 · 전체 "}
      {a.total}
      {"개 중 "}
      <b>
        {a.completed}
        {"개 완료"}
      </b>
      {a.failed > 0 && (
        <span className="warning">
          {" · "}
          {a.failed}
          {"개 실패"}
        </span>
      )}
      {a.removed > 0 && (
        <span>
          {" · "}
          {a.removed}
          {"개 삭제됨"}
        </span>
      )}
    </p>
  );
}
function MeetingProgress({ meeting: a }) {
  let e = meetingProgress(a);
  return e ? (
    <div className={"meeting-progress " + e.stage}>
      <div className="meeting-progress-label">
        <strong>{e.label}</strong>
        <span>{e.detail}</span>
      </div>
      <div
        className="meeting-progress-track"
        role="progressbar"
        aria-label={a.title + " 진행 상황"}
        aria-valuetext={e.label + " · " + e.detail}
      >
        <span />
      </div>
      <ProgressTime snapshot={a.progress} queued={e.stage === "queued"} />
      <ol className="meeting-progress-steps" aria-label="처리 단계">
        <li className="complete">
          <Check size={13} aria-hidden="true" />
          {"저장 완료"}
        </li>
        <li
          className={
            e.stage === "analyzing"
              ? "current"
              : e.stage === "applying"
                ? "complete"
                : ""
          }
        >
          {e.stage === "applying" && <Check size={13} aria-hidden="true" />}
          {"AI 분석"}
        </li>
        <li className={e.stage === "applying" ? "current" : ""}>
          {"결과 반영"}
        </li>
      </ol>
    </div>
  ) : null;
}
function ProcessingMeetings({
  meetings: a,
  projectName: e,
  onOpen: t,
  onCancel: z,
}) {
  let [ask, setAsk] = React.useState(null);
  if (!a.length) return null;
  return (
    <section className="processing-meetings" aria-label="등록·분석 중인 회의록">
      <div className="section-head">
        <h2>
          {"등록·분석 중 "}
          <small>{a.length}</small>
        </h2>
        <span className="pm-headtools">
          {"완료되면 아래 목록으로 이동합니다."}
          {z ? (
            <button
              type="button"
              className="pm-cancelall"
              onClick={() => setAsk(a)}
            >
              {"전체 등록 취소"}
            </button>
          ) : null}
        </span>
      </div>
      <div className="processing-meeting-list">
        {a.map((l) => (
          <div key={l.id} className="processing-row">
            <button className="processing-meeting" onClick={() => t(l.id)}>
              <div className="processing-meeting-heading">
                <div>
                  <b>{l.title}</b>
                  <small>{e(l.project_id)}</small>
                </div>
                <ChevronRight size={17} aria-hidden="true" />
              </div>
              <MeetingProgress meeting={l} />
            </button>
            {z ? (
              <button
                type="button"
                className="pm-cancel"
                aria-label={l.title + " 등록 취소"}
                onClick={() => setAsk([l])}
              >
                {"등록 취소"}
              </button>
            ) : null}
          </div>
        ))}
      </div>
      {ask ? (
        <div className="overlay" onClick={() => setAsk(null)}>
          <div
            className="modal rv-pop need"
            role="dialog"
            aria-modal="true"
            onClick={(v) => v.stopPropagation()}
          >
            <div className="modal-body">
              <i className="rv-pop-ic" aria-hidden="true">
                {"!"}
              </i>
              <h2>
                {ask.length > 1
                  ? "회의록 " + ask.length + "건의 등록을 취소할까요?"
                  : "이 회의록의 등록을 취소할까요?"}
              </h2>
              <p>
                {ask.length === 1 ? ask[0].title : "등록·분석 중인 회의록 전체"}
                <br />
                {
                  "분석을 멈추고 휴지통으로 옮깁니다. 휴지통에서 복원할 수 있습니다."
                }
              </p>
            </div>
            <footer>
              <button
                type="button"
                className="rv-btn"
                onClick={() => setAsk(null)}
              >
                {"닫기"}
              </button>
              <button
                type="button"
                className="rv-btn rv-pri"
                onClick={() => {
                  let L = ask;
                  setAsk(null);
                  z(L);
                }}
              >
                {"등록 취소"}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </section>
  );
}
async function api(a, e = "GET", t) {
  let l = await fetch("/api" + a, {
      method: e,
      credentials: "same-origin",
      headers: {
        "X-B2-Request": "workspace",
        ...(!(t instanceof FormData) && t
          ? {
              "Content-Type": "application/json",
            }
          : {}),
      },
      body: t instanceof FormData ? t : t ? JSON.stringify(t) : void 0,
    }),
    u;
  try {
    u = await l.json();
  } catch {
    throw Error("서버 응답을 읽지 못했습니다. 연결을 확인해 주세요.");
  }
  if (!l.ok) {
    let o = Error(
      typeof u.detail == "string" ? u.detail : JSON.stringify(u.detail || u),
    );
    throw ((o.status = l.status), o);
  }
  return u;
}
var norm = (a) =>
    String(a || "")
      .replace(/[\s·_().-]/g, "")
      .toLowerCase(),
  day = (a) => (a ? a.replaceAll("-", ".") : "날짜 미정"),
  at = (a) => ["running", "queued"].includes(a.analysis_state),
  g0 = (a) =>
    a.analysis_state === "queued"
      ? "분석 대기"
      : a.analysis_state === "running"
        ? meetingProgress(a).label
        : a.analysis_state === "failed"
          ? "분석 실패"
          : a.analysis_stale
            ? "다시 분석 필요"
            : a.analysis_state === "ready"
              ? "분석 완료"
              : "원문 보관",
  yg = (a, e) => {
    let [t, l] = a.split("-").map(Number);
    return new Date(Date.UTC(t, l - 1 + e, 1)).toISOString().slice(0, 7);
  },
  Ag = {
    meeting: {
      label: "회의",
      Icon: CalendarDays,
    },
    record: {
      label: "회의록 일정",
      Icon: FileText,
    },
    request: {
      label: "요청 일정",
      Icon: Clock3,
    },
  },
  x0 = (a) =>
    a.kind === "회의"
      ? "meeting"
      : a.kind === "요청 일정"
        ? "request"
        : "record";
function CalendarLegend() {
  return (
    <ul className="calendar-legend" aria-label="일정 범례">
      {Object.entries(Ag).map(([a, { label: e, Icon: t }]) => (
        <li key={a}>
          <span className={"legend-swatch " + a}>
            {React.createElement(t, {
              size: 12,
              "aria-hidden": "true",
            })}
          </span>
          {e}
        </li>
      ))}
      <li>
        <StickyNote className="legend-memo" size={15} aria-hidden="true" />
        {"메모"}
      </li>
    </ul>
  );
}
function CalendarBar({ event: a, projectName: e, onClick: t }) {
  let l = x0(a),
    { Icon: u } = Ag[l];
  return (
    <button
      className={"cal-bar " + l}
      style={{
        gridColumn: a.from + 1 + " / " + (a.to + 2),
        gridRow: a.lane + 1,
      }}
      aria-label={a.kind + ": " + a.title}
      title={e + " · " + a.kind + " · " + a.title}
      onClick={t}
    >
      {React.createElement(u, {
        size: 12,
        "aria-hidden": "true",
      })}
      <span>{a.title}</span>
    </button>
  );
}
function Button({ children: a, primary: e = !1, icon: t, ...l }) {
  return (
    <button
      {...l}
      className={"button " + (e ? "primary " : "") + (l.className || "")}
    >
      {t &&
        React.createElement(t, {
          size: 16,
        })}
      {a}
    </button>
  );
}
function Empty({ children: a }) {
  return <div className="empty">{a || "표시할 내용이 없습니다."}</div>;
}
function Modal({
  title: a,
  close: e,
  children: t,
  footer: l,
  wide: u = !1,
  className: o = "",
}) {
  return (
    (0, React.useEffect)(() => {
      let f = (d) => {
        d.key === "Escape" && e();
      };
      return (
        document.addEventListener("keydown", f),
        () => document.removeEventListener("keydown", f)
      );
    }, [e]),
    (
      <div
        className="overlay"
        onMouseDown={(f) => {
          f.target === f.currentTarget && e();
        }}
      >
        <section
          role="dialog"
          aria-modal="true"
          aria-label={a}
          className={"modal " + (u ? "wide-modal " : "") + o}
        >
          <header>
            <h2>{a}</h2>
            <button className="icon-button" aria-label="닫기" onClick={e}>
              <X />
            </button>
          </header>
          <div className="modal-body">{t}</div>
          {l && <footer>{l}</footer>}
        </section>
      </div>
    )
  );
}
function ChangeValue({ event: a, compact: e = !1 }) {
  let t = e ? cardSummary(a) : displayChange(a);
  return (
    <React.Fragment>
      <div
        className={
          "change-value " +
          (e ? "compact " : "") +
          (t.numeric ? "numeric " : "") +
          (t.transition ? "transition" : "statement")
        }
      >
        {t.transition ? (
          <React.Fragment>
            <span className="before">{t.before}</span>
            <ArrowRight size={e ? 18 : 20} />
            <strong>
              {t.after}
              {t.unit && <small> {t.unit}</small>}
            </strong>
          </React.Fragment>
        ) : (
          <strong>
            {t.after}
            {t.unit && <small> {t.unit}</small>}
          </strong>
        )}
      </div>
      {e && t.detail && (
        <p className="card-condition" title={t.detail}>
          {t.detail}
        </p>
      )}
    </React.Fragment>
  );
}
// 주간보고 탭은 React와 api를 받아 만든다(weekly_report.jsx 머리말 참고).
var WeeklyReport = createWeeklyReport(React, { api });
function App() {
  let [questionOpen, setQuestionOpen] = (0, React.useState)(!1),
    [transfer, setTransfer] = (0, React.useState)(null),
    [D, setWorkspace] = (0, React.useState)(null),
    [accounts, setAccounts] = (0, React.useState)([]),
    // Supabase 로그인 모드: 아이디(app_user_id)·비밀번호 로그인, 관리자는 설정 화면으로 이동
    [authMode, setAuthMode] = (0, React.useState)("demo"),
    [adminUser, setAdminUser] = (0, React.useState)(null),
    [loginId, setLoginId] = (0, React.useState)(""),
    [loginPw, setLoginPw] = (0, React.useState)(""),
    [page, setPage] = (0, React.useState)("home"),
    [pid, setPid] = (0, React.useState)(""),
    [meeting, setMeeting] = (0, React.useState)(null),
    [tab, setTab] = (0, React.useState)("ai"),
    [sourceText, setSourceText] = (0, React.useState)(!1),
    [focus, setFocus] = (0, React.useState)([]),
    [topic, setTopic] = (0, React.useState)(""),
    [query, setQuery] = (0, React.useState)(""),
    [listPage, setListPage] = (0, React.useState)(0),
    [meetingSort, setMeetingSort] = (0, React.useState)({
      key: "date",
      direction: "desc",
    }),
    [cardsPage, setCardsPage] = (0, React.useState)(0),
    [month, setMonth] = (0, React.useState)(
      new Date().toLocaleDateString("sv-SE").slice(0, 7),
    ),
    [selectedDay, setSelectedDay] = (0, React.useState)(
      new Date().toLocaleDateString("sv-SE"),
    ),
    [memos, setMemos] = (0, React.useState)({}),
    [memo, setMemo] = (0, React.useState)(""),
    [modal, setModal] = (0, React.useState)(null),
    [toast, setToast] = (0, React.useState)(""),
    [working, setWorking] = (0, React.useState)(!1),
    [queue, setQueue] = (0, React.useState)([]),
    [uploadErrors, setUploadErrors] = (0, React.useState)([]),
    [edit, setEdit] = (0, React.useState)(null),
    [activePoint, setActivePoint] = (0, React.useState)(null),
    [evidence, setEvidence] = (0, React.useState)(!1),
    [sourceZoom, setSourceZoom] = (0, React.useState)(100),
    [paste, setPaste] = (0, React.useState)(""),
    br = (0, React.useRef)(),
    Ar = (0, React.useRef)(null),
    y0 = (0, React.useRef)(""),
    Dg = (0, React.useRef)(queue);
  Dg.current = queue;
  const setD = React.useCallback((update) => setWorkspace((current) => updateWorkspace(current, update)), []);
  // 알림(회의록 등록·검수 완료 등): 로그인한 동안 15초마다 새로 받는다.
  const [notices, setNotices] = React.useState({ items: [], unread: 0 });
  const loadNotices = React.useCallback(
    () =>
      api("/notifications")
        .then(setNotices)
        .catch(() => {}),
    [],
  );
  React.useEffect(() => {
    if (!D?.user?.id) return;
    loadNotices();
    const timer = setInterval(loadNotices, 15000);
    return () => clearInterval(timer);
  }, [D?.user?.id, loadNotices]);
  let he = async () => {
    let c = await api("/v3/workspace");
    return (setD(c), c);
  };
  async function Ca(c) {
    setWorking(!0);
    try {
      await c();
    } catch (y) {
      setToast(y.message);
    } finally {
      setWorking(!1);
    }
  }
  ((0, React.useEffect)(() => {
    (async () => {
      let cfg = { mode: "demo" };
      try {
        cfg = await api("/auth/config");
      } catch (c) {}
      setAuthMode(cfg.mode);
      if (cfg.mode === "supabase") {
        // 이미 로그인한 세션이면 역할을 확인해 관리자는 설정 화면으로 보낸다.
        try {
          let me = await api("/auth/me");
          if (me.role === "admin") return setAdminUser(me);
        } catch (c) {
          c.status !== 401 && setToast(c.message);
          return;
        }
      } else
        api("/demo-accounts")
          .then(setAccounts)
          .catch((c) => setToast(c.message));
      he().catch((c) => {
        c.status !== 401 && setToast(c.message);
      });
    })();
  }, []),
    (0, React.useEffect)(() => {
      if (!D) return;
      let c = !1,
        y = setInterval(() => {
          c ||
            he().catch((I) => {
              I.status === 401 && setD(null);
            });
        }, 4e3);
      return () => {
        ((c = !0), clearInterval(y));
      };
    }, [D?.user?.id]),
    (0, React.useEffect)(() => {
      if (!toast) return;
      let c = setTimeout(() => setToast(""), 7e3);
      return () => clearTimeout(c);
    }, [toast]),
    (0, React.useEffect)(() => {
      if (!D) return;
      let c = month + "-01",
        y = new Date(
          Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5)), 0),
        )
          .toISOString()
          .slice(0, 10);
      api("/calendar/memos?start=" + c + "&end=" + y)
        .then(setMemos)
        .catch((I) => setToast(I.message));
    }, [month, D?.user.id]),
    (0, React.useEffect)(() => {
      setMemo(memos[selectedDay] || "");
    }, [selectedDay, memos]),
    (0, React.useEffect)(() => {
      if (page === "detail" && meeting && at(meeting)) {
        let c = setInterval(
          () =>
            api("/meetings/" + meeting.id)
              .then(setMeeting)
              .catch((y) => setToast(y.message)),
          4e3,
        );
        return () => clearInterval(c);
      }
    }, [page, meeting?.id, meeting?.analysis_state]),
    (0, React.useEffect)(() => {
      focus.length &&
        page === "detail" &&
        sourceText &&
        document.getElementById("source-" + focus[0])?.scrollIntoView({
          block: "center",
          behavior: "smooth",
        });
    }, [focus, sourceText, page, meeting?.id]));
  let et = (c) => D?.projects.find((y) => y.id === c)?.name || "프로젝트",
    Xu = (c) => D?.people.find((y) => y.id === c)?.name || "미정";
  function Be(c) {
    (setPage(c),
      setMeeting(null),
      setModal(null),
      setEdit(null),
      setActivePoint(null),
      window.scrollTo(0, 0));
  }
  function changeProject(projectId) {
    if (projectId && !D.projects.some(project => project.id === projectId)) return false;
    if (projectId === pid) return true;
    if (edit && !window.confirm("저장하지 않은 수정 내용이 있습니다. 수정을 취소하고 프로젝트를 변경할까요?")) return false;
    setPid(projectId);
    setTopic("");
    setQuery("");
    setListPage(0);
    Object.assign(workflow.hist, {
      mt: "", cat: "", q: "", rv: "", sel: "", filter: "all", page: 0,
      mrv: "", fm: "", fmid: "", fq: "", fpage: 0, mpage: 0,
    });
    // A detail belongs to one meeting; keep the meeting tab on its new project's list.
    if (page === "detail") {
      Ar.current = null;
      setFocus([]);
      Be("minutes");
    }
    return true;
  }
  async function ff(c, y = []) {
    Ar.current = {
      page: page,
      pid: pid,
      topic: topic,
    };
    let I = await api("/meetings/" + c);
    (setMeeting(I),
      setTab("source"),
      setFocus(y),
      setSourceText(!1),
      setPage("detail"),
      setActivePoint(null),
      setModal(null),
      setEdit(null),
      window.scrollTo(0, 0));
  }
  function Bg() {
    let c = Ar.current;
    (setMeeting(null),
      setPage(c?.page === "detail" ? "minutes" : c?.page || "minutes"),
      c && (setPid(c.pid), setTopic(c.topic)),
      setEdit(null),
      window.scrollTo(0, 0));
  }
  function Tr(c) {
    let y = new Map();
    return (
      (D?.changes || [])
        .filter((I) => I.review_state === "확인됨")
        .filter((I) => !workflow.pend(D)[I.meeting_id])
        .filter((I) => !c || I.project_id === c)
        .forEach((I) => {
          let E = I.project_id + "|" + I.category + "|" + norm(I.title);
          (y.has(E) ||
            y.set(E, {
              key: E,
              title: I.title,
              category: I.category,
              project_id: I.project_id,
              events: [],
            }),
            y.get(E).events.push(I));
        }),
      [...y.values()]
        .map((I) => ({
          ...I,
          events: I.events.sort(
            (E, Le) =>
              (E.effective_date || "").localeCompare(Le.effective_date || "") ||
              (E.created_at || "").localeCompare(Le.created_at || ""),
          ),
        }))
        .sort((I, E) =>
          (E.events.at(-1).effective_date || "").localeCompare(
            I.events.at(-1).effective_date || "",
          ),
        )
    );
  }
  let df = Tr(pid),
    ul = df.find((c) => c.key === topic) || df[0],
    Mr = (D?.calendar || [])
      .filter((c) => !pid || c.project_id === pid)
      .filter((c) => !(D && c.meeting_id && workflow.pend(D)[c.meeting_id])),
    un = eventsOn(Mr, selectedDay);
  async function on(c, y = "") {
    let I = new FormData();
    (Array.from(c || []).forEach((E) => I.append("files", E)),
      y && I.append("text", y),
      I.append("context", pid),
      setTransfer({
        stage: "uploading",
        percent: 0,
        startedAt: performance.now(),
      }));
    try {
      let E = await uploadImports(I, (Le) =>
        setTransfer(
          (ol) =>
            ol && {
              ...ol,
              ...Le,
            },
        ),
      );
      (setQueue((Le) => [
        ...Le,
        ...E.items.map((ol) => ({
          ...ol,
          selected: ol.project_id,
          confirmed: !ol.needs_check,
        })),
      ]),
        setUploadErrors(E.errors),
        setPaste(""));
    } finally {
      setTransfer(null);
    }
  }
  async function Og() {
    setTransfer({
      stage: "saving",
      percent: null,
      startedAt: performance.now(),
    });
    try {
      let c = await api("/v3/register", "POST", {
        items: queue.map((y) => ({
          id: y.id,
          project_id: y.selected,
          title: y.title,
          date: y.meeting_date || "",
          confirmed: y.confirmed,
        })),
      });
      if (c.errors.length) {
        let y = new Set(c.errors.map((I) => I.id));
        (setQueue((I) => I.filter((E) => y.has(E.id))),
          setUploadErrors(
            c.errors.map((I) => ({
              filename: queue.find((E) => E.id === I.id)?.filename,
              error: I.error,
            })),
          ));
      } else
        (setQueue([]), setPid(""), setQuery(""), setListPage(0), Be("minutes"));
      (setToast(
        c.registered.filter((y) => !y.duplicate).length +
          "개 저장 완료" +
          (c.registered.some((y) => y.duplicate)
            ? " · 중복 파일은 기존 회의록을 유지했습니다."
            : " · 분석이 끝나면 이 화면에서 바로 검수합니다."),
      ),
        await he());
      {
        const fresh = c.errors.length
          ? null
          : c.registered.find((y) => !y.duplicate);
        if (fresh) await ff(fresh.id, []);
      }
    } finally {
      setTransfer(null);
    }
  }
  let fn = (c, y) =>
      setQueue((I) =>
        I.map((E) =>
          E.id === c
            ? {
                ...E,
                ...y,
              }
            : E,
        ),
      ),
    dn = meeting
      ? D?.meetings.find((c) => c.id === meeting.id)?.points || []
      : [],
    wg = meeting
      ? Object.fromEntries((meeting.lines || []).map((c) => [c.id, c.text]))
      : {};
  async function Eg() {
    (await api("/v3/meetings/" + meeting.id + "/note", "PATCH", {
      version: meeting.version,
      point: edit.id,
      text: edit.value,
    }),
      setEdit(null),
      setMeeting(await api("/meetings/" + meeting.id)),
      await he(),
      setToast("정리 내용을 저장했습니다."));
  }
  async function Dr() {
    (await api("/v3/meetings/" + meeting.id + "/analyze", "POST"),
      setMeeting(await api("/meetings/" + meeting.id)),
      await he());
  }
  function I0(c) {
    (setPid(c.project_id), setTopic(c.key), Be("changes"));
  }
  let Br = (c, y = !1) =>
    y && !meetingNeedsStatus(c) ? null : (
      <span
        className={
          "status " +
          (at(c)
            ? "processing"
            : c.analysis_state === "failed" || c.analysis_stale
              ? "warning"
              : "")
        }
      >
        {at(c) && <LoaderCircle className="spin" size={12} />}
        {g0(c)}
      </span>
    );
  function zg(c) {
    (setMeetingSort((y) => nextMeetingSort(y, c)), setListPage(0));
  }
  let nf =
    meeting &&
    (meeting.author === D?.user.id ||
      D?.projects.find((c) => c.id === meeting.project_id)?.pm === D?.user.id);
  if (adminUser)
    return (
      <AdminConsole
        api={api}
        user={adminUser}
        logo={logo}
        onLogout={async () => {
          try {
            await api("/logout", "POST");
          } catch (c) {}
          (setAdminUser(null), setLoginPw(""));
        }}
      />
    );
  return D ? (
    <React.Fragment>
      <header className="topbar">
        <button
          className="brand"
          aria-label="PNT 홈"
          onClick={() => Be("home")}
        >
          <img src={logo} alt="PNT" />
        </button>
        <nav aria-label="주 메뉴">
          {[
            ["home", "홈"],
            ["minutes", "회의록"],
            ["changes", "변경이력"],
            ["weekly", "주간보고"],
          ].map(([c, y]) => (
            <button
              key={c}
              className={
                page === c ||
                (c === "minutes" && ["detail", "upload"].includes(page))
                  ? "active"
                  : ""
              }
              onClick={() => {
                if (c === "changes") {
                  workflow.hist.tab = "hist";
                  setTopic("");
                  setD((y) => ({ ...y }));
                }
                Be(c);
              }}
            >
              {y}
            </button>
          ))}
        </nav>
        <ProjectSelector projects={D.projects} projectId={pid} onChange={changeProject}
          disabled={working} contextKey={page} />
        <Button
          className="ai-question-trigger"
          aria-label="AI"
          icon={Sparkles}
          onClick={() => setQuestionOpen(!0)}
        >
          {"AI"}
        </Button>
        <button
          className="icon-button notice-button"
          aria-label={"알림 " + notices.unread + "건"}
          title="알림"
          onClick={() => (loadNotices(), setModal({ type: "notices" }))}
        >
          <Bell size={18} />
          {notices.unread > 0 && (
            <span className="notice-badge">
              {notices.unread > 99 ? "99+" : notices.unread}
            </span>
          )}
        </button>
        <button
          className="account"
          onClick={() =>
            setModal({
              type: "account",
            })
          }
        >
          <span className="avatar">{D.user.name.slice(-2)}</span>
          {D.user.name}
        </button>
        <button
          className="icon-button global-trash"
          aria-label="휴지통"
          title="휴지통"
          onClick={() =>
            setModal({
              type: "unifiedTrash",
            })
          }
        >
          <Trash2 size={19} />
        </button>
        <DisplaySettings />
      </header>
      <main>
        {page === "home" && (
          <React.Fragment>
            <div className="page-heading">
              <div>
                <h1>{"프로젝트 현황"}</h1>
              </div>
              <div className="actions">
                {D.can_create_project && (
                  <Button
                    icon={Plus}
                    onClick={() =>
                      setModal({
                        type: "project",
                        name: "",
                      })
                    }
                  >
                    {"프로젝트"}
                  </Button>
                )}
              </div>
            </div>
            <div className="section-head">
              <h2>
                {"진행 프로젝트 "}
                <small>{D.projects.length}</small>
              </h2>
              <div className="pager">
                <span className="project-order">{"최근 생성순"}</span>
                <span>
                  {D.projects.length ? Math.floor(cardsPage / 3) + 1 : 0}
                  {" / "}
                  {Math.ceil(D.projects.length / 3)}
                </span>
                <button
                  aria-label="이전 프로젝트"
                  disabled={cardsPage === 0}
                  onClick={() => setCardsPage(Math.max(0, cardsPage - 3))}
                >
                  <ChevronLeft />
                </button>
                <button
                  aria-label="다음 프로젝트"
                  disabled={cardsPage + 3 >= D.projects.length}
                  onClick={() => setCardsPage(cardsPage + 3)}
                >
                  <ChevronRight />
                </button>
              </div>
            </div>
            <div className="project-grid home-project-grid">
              {D.projects.slice(cardsPage, cardsPage + 3).map((c) => {
                let y = D.meetings.filter(
                    (Le) => Le.project_id === c.id && !workflow.pend(D)[Le.id],
                  ),
                  I = Tr(c.id)[0],
                  E = I?.events.at(-1);
                return (
                  <button
                    className="project-card home-project-card"
                    key={c.id}
                    aria-label={`${c.name} · PM ${Xu(c.pm)} · 회의록 ${y.length}건 · 프로젝트 흐름 보기`}
                    onClick={() => {
                      workflow.hist.tab = "flow";
                      changeProject(c.id);
                      (setTopic(""), Be("changes"));
                    }}
                  >
                    <span className="project-code">
                      <span title={c.created_at ? `생성 ${String(c.created_at).slice(0, 10).replace(/-/g, ".")}` : undefined}>{c.id}</span>
                      <span className="home-project-pm" title="프로젝트 PM">PM {Xu(c.pm)}</span>
                    </span>
                    <h2 title={`${c.name} · 회의록 ${y.length}건`}>{c.name}</h2>
                    {(() => {
                      const g = Tr(c.id),
                        pend = g.filter((z) =>
                          ["요청", "보류"].includes(
                            z.events[z.events.length - 1].business_state,
                          ),
                        ).length,
                        un = g.reduce(
                          (t, z) =>
                            t +
                            z.events.filter((e) => e.review_state !== "확인됨")
                              .length,
                          0,
                        );
                      return (
                        <div className="pf-cardstage">
                          {workflow.StageBar(
                            {
                              R: React,
                              u: D,
                              Q: api,
                              o: setD,
                            },
                            c.id,
                            !0,
                          )}
                          {(pend > 0 || un > 0) && <span className="pf-cardcnt">
                            {pend ? (
                              <em className="warn">{"미결 " + pend}</em>
                            ) : null}
                            {un ? <em>{"미확인 " + un}</em> : null}
                          </span>}
                        </div>
                      );
                    })()}
                    <div className="card-change">
                      {E ? (
                        <React.Fragment>
                          <div className="home-change-heading">
                            <b title={I.title}>{I.title}</b>
                            <span className={"status" + (["보류", "요청"].includes(E.business_state) ? " warning" : "")}>
                              {E.business_state === "확정" ? "합의" : E.business_state}
                            </span>
                          </div>
                          <ChangeValue event={E} compact={!0} />
                        </React.Fragment>
                      ) : (
                        <span className="muted">
                          {y.some(at)
                            ? "회의록을 분석하고 있습니다."
                            : "등록된 변경 기록이 없습니다."}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
            {!D.projects.length && (
              <Empty>{"프로젝트를 등록하고 회의록을 올려 보세요."}</Empty>
            )}
            <div className="calendar-layout">
              <section className="calendar">
                <div className="section-head">
                  <h2>
                    {month.slice(0, 4)}
                    {"년 "}
                    {Number(month.slice(5))}
                    {"월"}
                  </h2>
                  <div className="calendar-tools">
                    <span className="calendar-project-context" title={pid ? et(pid) : "전체 프로젝트"}>
                      {pid ? et(pid) : "전체 프로젝트"}
                    </span>
                    <button
                      aria-label="이전 달"
                      onClick={() => setMonth(yg(month, -1))}
                    >
                      <ChevronLeft />
                    </button>
                    <button
                      onClick={() => {
                        (setMonth(D.today.slice(0, 7)),
                          setSelectedDay(D.today));
                      }}
                    >
                      {"오늘"}
                    </button>
                    <button
                      aria-label="다음 달"
                      onClick={() => setMonth(yg(month, 1))}
                    >
                      <ChevronRight />
                    </button>
                  </div>
                </div>
                <CalendarLegend />
                <div className="weekdays">
                  {["월", "화", "수", "목", "금", "토", "일"].map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
                {calendarWeeks(month, Mr).map((c, y) => (
                  <div className="cal-week" key={y}>
                    <div className="cal-days">
                      {c.dates.map((I) => (
                        <button
                          key={I}
                          aria-label={I + " 일정"}
                          className={
                            (I === selectedDay ? "selected " : "") +
                            (I.slice(0, 7) !== month ? "outside " : "") +
                            (I === D.today ? "today" : "")
                          }
                          onClick={() => setSelectedDay(I)}
                        >
                          <span>{Number(I.slice(-2))}</span>
                          {memos[I] && <StickyNote size={12} />}
                        </button>
                      ))}
                    </div>
                    <div className="cal-bars">
                      {c.segments.map((I) => (
                        <CalendarBar
                          key={I.id}
                          event={I}
                          projectName={et(I.project_id)}
                          onClick={() => {
                            (setSelectedDay(
                              I.start.slice(0, 7) === month
                                ? I.start
                                : c.dates[0],
                            ),
                              setModal({
                                type: "event",
                                event: I,
                              }));
                          }}
                        />
                      ))}
                    </div>
                    <div className="cal-more">
                      {c.overflow.map((I, E) => (
                        <span key={E}>
                          {I > 0 && (
                            <button onClick={() => setSelectedDay(c.dates[E])}>
                              {"+"}
                              {I}
                              {"개"}
                            </button>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </section>
              <aside className="day-panel">
                <div className="section-head">
                  <h2>
                    {day(selectedDay).slice(5)}
                    {" 일정"}
                  </h2>
                  <span className="muted">
                    {un.length}
                    {"건"}
                  </span>
                </div>
                {un.length ? (
                  <div className="agenda">
                    {un.map((c) => (
                      <button
                        key={c.id}
                        onClick={() =>
                          setModal({
                            type: "event",
                            event: c,
                          })
                        }
                      >
                        <small>
                          {et(c.project_id)}
                          {" · "}
                          {c.kind}
                        </small>
                        <b>{c.title}</b>
                        {c.start !== c.end && (
                          <small>
                            {day(c.start)}
                            {" – "}
                            {day(c.end)}
                          </small>
                        )}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="muted">{"등록된 일정이 없습니다."}</p>
                )}
                <section className="memo">
                  <h2>
                    <StickyNote size={17} />
                    {" 내 메모"}
                  </h2>
                  <textarea
                    aria-label="선택 날짜의 내 메모"
                    placeholder="이 날짜에 기억할 내용을 남기세요."
                    maxLength={1e3}
                    value={memo}
                    onChange={(c) => setMemo(c.target.value)}
                  />
                  <Button
                    disabled={working || memo === (memos[selectedDay] || "")}
                    onClick={() =>
                      Ca(async () => {
                        (await api("/calendar/memos/" + selectedDay, "PUT", {
                          text: memo,
                        }),
                          setMemos({
                            ...memos,
                            [selectedDay]: memo,
                          }),
                          setToast("메모를 저장했습니다."));
                      })
                    }
                  >
                    {"저장"}
                  </Button>
                </section>
              </aside>
            </div>
          </React.Fragment>
        )}
        {page === "minutes" && (
          <React.Fragment>
            <div className="page-heading">
              <h1>
                {"회의록 "}
                <small>{D.meetings.length}</small>
              </h1>
              <div className="actions">
                <Button primary={!0} icon={Plus} onClick={() => Be("upload")}>
                  {"회의록 등록"}
                </Button>
              </div>
            </div>
            <div className="filters">
              <span className="meeting-project-context" title={pid ? et(pid) : "전체 프로젝트"}>
                {pid ? et(pid) : "전체 프로젝트"}
              </span>
              {(() => {
                const P = workflow.pend(D),
                  H = workflow.hist,
                  ms = D.meetings.filter((m) => !pid || m.project_id === pid),
                  nP = ms.filter((m) => P[m.id] > 0).length,
                  nD = ms.filter((m) => !P[m.id]).length,
                  tab = (k, label, cnt) => (
                    <button
                      type="button"
                      key={k}
                      className={(H.mrv || "") === k ? "on" : ""}
                      onClick={() => {
                        H.mrv = k;
                        setListPage(0);
                        setD((y) => ({
                          ...y,
                        }));
                      }}
                    >
                      {label}
                      {cnt == null ? null : <small>{cnt}</small>}
                    </button>
                  );
                return (
                  <div
                    className="hx-tabs mt-tabs"
                    role="group"
                    aria-label="검수 상태"
                  >
                    {tab("", "전체", ms.length)}
                    {tab("pend", "검수 필요", nP)}
                    {tab("done", "검수 완료", nD)}
                    <span className="mt-sep" aria-hidden="true" />
                    {tab(
                      "wait",
                      "회신 대기",
                      ms.filter((m) => m.approval?.status === "sent").length,
                    )}
                    {tab(
                      "rej",
                      "반려",
                      ms.filter((m) => m.approval?.status === "rejected")
                        .length,
                    )}
                  </div>
                );
              })()}
              <label className="search">
                <Search size={16} />
                <input
                  aria-label="회의록 검색"
                  placeholder="회의 제목·내용 검색"
                  value={query}
                  onChange={(c) => {
                    (setQuery(c.target.value), setListPage(0));
                  }}
                />
              </label>
              <label className="meeting-sort-mobile">
                {"정렬"}
                <select
                  aria-label="회의록 정렬 방식"
                  value={meetingSort.key + ":" + meetingSort.direction}
                  onChange={(c) => {
                    let [y, I] = c.target.value.split(":");
                    (setMeetingSort({
                      key: y,
                      direction: I,
                    }),
                      setListPage(0));
                  }}
                >
                  {hr.flatMap(([c, y]) =>
                    ["asc", "desc"].map((I) => (
                      <option key={c + I} value={c + ":" + I}>
                        {y}
                        {" · "}
                        {c === "date"
                          ? I === "asc"
                            ? "오래된순"
                            : "최신순"
                          : I === "asc"
                            ? "가나다순"
                            : "역순"}
                      </option>
                    )),
                  )}
                </select>
              </label>
            </div>
            {(() => {
              let { processing: c, registered: y } = meetingSections(
                D.meetings,
                D.projects,
                D.people,
                {
                  projectId: pid,
                  query: query,
                  sort: meetingSort,
                },
              );
              const __P = workflow.pend(D),
                __f = workflow.hist.mrv || "";
              if (__f)
                y = y.filter((E) =>
                  __f === "pend"
                    ? __P[E.id] > 0
                    : __f === "done"
                      ? !__P[E.id]
                      : __f === "wait"
                        ? E.approval?.status === "sent"
                        : __f === "rej"
                          ? E.approval?.status === "rejected"
                          : !0,
                );
              let I = Math.min(
                listPage * 8,
                Math.max(0, Math.ceil(y.length / 8) - 1) * 8,
              );
              return (
                <React.Fragment>
                  <BatchProgress batch={D.recent_batch} />
                  <ProcessingMeetings
                    meetings={c}
                    projectName={et}
                    onOpen={(E) => Ca(() => ff(E))}
                    onCancel={(L) =>
                      Ca(async () => {
                        let ok = 0,
                          bad = "";
                        for (const m of L) {
                          try {
                            await api("/v3/meetings/" + m.id, "DELETE");
                            ok++;
                          } catch (er) {
                            bad = er.message;
                          }
                        }
                        await he();
                        setToast(
                          ok +
                            "건의 등록을 취소하고 휴지통으로 옮겼습니다." +
                            (bad ? " 일부는 취소하지 못했습니다: " + bad : ""),
                        );
                      })
                    }
                  />
                  <div className="meeting-header">
                    {hr.map(([E, Le]) => (
                      <button
                        key={E}
                        className={
                          "sort-" +
                          E +
                          (meetingSort.key === E ? " selected" : "")
                        }
                        aria-label={Le + " 정렬"}
                        title={
                          meetingSort.key === E
                            ? meetingSort.direction === "asc"
                              ? "오름차순 · 다시 누르면 내림차순"
                              : "내림차순 · 다시 누르면 오름차순"
                            : Le + "순으로 정렬"
                        }
                        onClick={() => zg(E)}
                      >
                        {Le}
                        {meetingSort.key === E && (
                          <span className="sort-direction" aria-hidden="true">
                            {meetingSort.direction === "asc" ? "▲" : "▼"}
                          </span>
                        )}
                      </button>
                    ))}
                    <span />
                  </div>
                  {y.slice(I, I + 8).map((E) => (
                    <button
                      className="meeting-row"
                      key={E.id}
                      onClick={() => Ca(() => ff(E.id))}
                    >
                      <span className="meeting-name">
                        <span>
                          <b>{E.title}</b>
                          {Br(E, !0)}
                          {(() => {
                            const k = workflow.pend(D)[E.id];
                            return k > 0 ? (
                              <em className="mt-pend">
                                {"검수 필요 " + k + "건 · 등록 전"}
                              </em>
                            ) : null;
                          })()}
                        </span>
                      </span>
                      <span className="date-cell">{day(E.date)}</span>
                      {(() => {
                        const a = E.approval,
                          L = {
                            sent: "회신 대기",
                            approved: "합의",
                            rejected: "반려",
                            expired: "만료",
                          },
                          st = a && L[a.status] ? a.status : "",
                          md = (v) =>
                            v ? v.slice(5, 10).replace("-", ".") : "";
                        return (
                          <span
                            className="approval-cell"
                            title={
                              a
                                ? a.email +
                                  (a.comment ? " · 의견: " + a.comment : "")
                                : "합의 메일을 보내지 않았습니다"
                            }
                          >
                            {st ? (
                              <span className={"ap-st " + st}>{L[st]}</span>
                            ) : (
                              <span className="ap-none">{"—"}</span>
                            )}
                            {st ? (
                              <small>
                                {st === "sent"
                                  ? md(a.sent_at) + " 발송"
                                  : st === "expired"
                                    ? md(a.sent_at) + " 발송"
                                    : md(a.responded_at) + " 회신"}
                              </small>
                            ) : null}
                          </span>
                        );
                      })()}
                      <span className="author-cell">{Xu(E.author)}</span>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                  {!y.length && (
                    <Empty>
                      {c.length
                        ? "분석이 완료된 회의록이 이곳에 표시됩니다."
                        : D.meetings.length
                          ? "검색 결과가 없습니다."
                          : "회의록을 등록해 주세요."}
                    </Empty>
                  )}
                  <div className="pager">
                    <span>
                      {y.length ? I + 1 : 0}
                      {"–"}
                      {Math.min(I + 8, y.length)}
                      {" / "}
                      {y.length}
                    </span>
                    <button
                      aria-label="이전 회의록"
                      disabled={!I}
                      onClick={() => setListPage(Math.max(0, listPage - 1))}
                    >
                      <ChevronLeft />
                    </button>
                    <button
                      aria-label="다음 회의록"
                      disabled={I + 8 >= y.length}
                      onClick={() => setListPage(listPage + 1)}
                    >
                      <ChevronRight />
                    </button>
                  </div>
                </React.Fragment>
              );
            })()}
          </React.Fragment>
        )}
        {page === "upload" && (
          <React.Fragment>
            <button className="back" onClick={() => Be("minutes")}>
              <ArrowLeft size={16} />
              {"목록으로"}
            </button>
            <div className="page-heading">
              <div>
                <h1>{"회의록 등록"}</h1>
                <p>
                  {
                    "프로젝트를 자동으로 선택합니다. 확인이 필요한 파일만 선택해 주세요."
                  }
                </p>
              </div>
            </div>
            <div
              className="drop-zone"
              onDragOver={(c) => c.preventDefault()}
              onDrop={(c) => {
                (c.preventDefault(),
                  working || Ca(() => on(c.dataTransfer.files)));
              }}
            >
              <CloudUpload size={27} />
              <div>
                <b>{"회의록 파일을 여기에 놓으세요"}</b>
                <p>{"Word · PDF · Excel · 텍스트 / 한 번에 20개"}</p>
              </div>
              <Button disabled={working} onClick={() => br.current.click()}>
                {working ? "파일을 읽는 중…" : "파일 선택"}
              </Button>
              <input
                ref={br}
                type="file"
                multiple={!0}
                hidden={!0}
                accept=".docx,.pdf,.xlsx,.txt,.md"
                onChange={(c) => {
                  let y = Array.from(c.target.files);
                  ((c.target.value = ""), Ca(() => on(y)));
                }}
              />
            </div>
            {transfer && <TransferProgress transfer={transfer} />}
            <details className="paste">
              <summary>{"텍스트로 입력하기"}</summary>
              <textarea
                aria-label="회의록 내용"
                placeholder="회의 내용을 붙여 넣으세요."
                value={paste}
                onChange={(c) => setPaste(c.target.value)}
              />
              <Button
                disabled={working || paste.trim().length < 10}
                onClick={() => Ca(() => on([], paste))}
              >
                {"내용 불러오기"}
              </Button>
            </details>
            <div className="section-head">
              <h2>
                {"파일 "}
                {queue.length}
                {"개 "}
                {queue.some((c) => !c.selected) && (
                  <small className="warning">{"· 프로젝트 확인 필요"}</small>
                )}
              </h2>
              <div className="actions">
                {queue.length > 0 && (
                  <button
                    type="button"
                    className="button up-clear"
                    disabled={working}
                    title="불러온 파일을 목록에서 모두 뺍니다. 이미 등록된 회의록은 지워지지 않습니다."
                    onClick={() => {
                      setQueue(() => []);
                      setUploadErrors([]);
                    }}
                  >
                    {"전체 비우기"}
                  </button>
                )}
                {D.can_create_project && (
                  <Button
                    icon={Plus}
                    onClick={() =>
                      setModal({
                        type: "project",
                        name: "",
                      })
                    }
                  >
                    {"새 프로젝트"}
                  </Button>
                )}
              </div>
            </div>
            {uploadErrors.map((c, y) => (
              <p role="alert" className="error-box" key={y}>
                {c.filename}
                {": "}
                {c.error}
              </p>
            ))}
            {queue.map((c) => (
              <div
                className={"upload-row " + (c.selected ? "" : "needs-check")}
                key={c.id}
              >
                <div>
                  <b>{c.filename}</b>
                  <details>
                    <summary>{"제목·날짜"}</summary>
                    <input
                      aria-label={c.filename + " 제목"}
                      value={c.title}
                      onChange={(y) =>
                        fn(c.id, {
                          title: y.target.value,
                        })
                      }
                    />
                    <input
                      aria-label={c.filename + " 회의일"}
                      type="date"
                      value={c.meeting_date || ""}
                      onChange={(y) =>
                        fn(c.id, {
                          meeting_date: y.target.value,
                        })
                      }
                    />
                  </details>
                  {c.warnings?.map((y, I) => (
                    <small className="warning" key={I}>
                      {y}
                    </small>
                  ))}
                </div>
                <div>
                  <select
                    aria-label={c.filename + " 프로젝트"}
                    value={c.selected}
                    onChange={(y) =>
                      fn(c.id, {
                        selected: y.target.value,
                        confirmed: !!y.target.value,
                        reason: "직접 선택",
                      })
                    }
                  >
                    <option value="">{"프로젝트 확인 필요"}</option>
                    {D.projects.map((y) => (
                      <option key={y.id} value={y.id}>
                        {y.name}
                      </option>
                    ))}
                  </select>
                  <small>{c.reason}</small>
                  {(() => {
                    if (
                      c.selected ||
                      !c.declared_project ||
                      c.declared_project.length < 2
                    )
                      return null;
                    const nz = (t) =>
                        String(t || "")
                          .toLowerCase()
                          .replace(/[^0-9a-z\uAC00-\uD7A3]/g, ""),
                      bg = (t) => {
                        const m = new Map();
                        for (let q = 0; q < t.length - 1; q++) {
                          const g = t.slice(q, q + 2);
                          m.set(g, (m.get(g) || 0) + 1);
                        }
                        return m;
                      },
                      sim = (a, d) => {
                        a = nz(a);
                        d = nz(d);
                        if (!a || !d) return 0;
                        if (a === d) return 1;
                        const A = bg(a),
                          B = bg(d);
                        let s = 0;
                        A.forEach((v, g) => {
                          s += Math.min(v, B.get(g) || 0);
                        });
                        return (
                          (2 * s) /
                          (Math.max(a.length - 1, 1) +
                            Math.max(d.length - 1, 1))
                        );
                      },
                      near = D.projects
                        .map((P) => ({
                          P,
                          s: sim(P.name, c.declared_project),
                        }))
                        .filter((z) => z.s >= 0.7)
                        .sort((a, d) => d.s - a.s)
                        .slice(0, 3),
                      mk = D.can_create_project ? (
                        <button
                          type="button"
                          className="up-suggest"
                          title="회의록의 프로젝트명 칸에 적힌 이름입니다. 만들기 전에 이름을 고칠 수 있습니다."
                          onClick={() =>
                            setModal({
                              type: "project",
                              name: c.declared_project,
                              declared: c.declared_project,
                            })
                          }
                        >
                          <span>{"추천"}</span>
                          {"새 프로젝트로 만들기: "}
                          <b>{c.declared_project}</b>
                          {(() => {
                            const k = queue.filter(
                              (E) =>
                                !E.selected &&
                                E.declared_project === c.declared_project,
                            ).length;
                            return k > 1 ? (
                              <em>
                                {" · 같은 프로젝트명 " +
                                  k +
                                  "개 파일에 함께 적용"}
                              </em>
                            ) : null;
                          })()}
                        </button>
                      ) : null;
                    if (!near.length) return mk;
                    return (
                      <div
                        className="up-near"
                        role="group"
                        aria-label="유사한 이름의 프로젝트 확인"
                      >
                        <b>{"유사한 이름의 프로젝트가 있습니다"}</b>
                        <div className="up-near-doc">
                          <em>{"문서"}</em>
                          <span>{c.declared_project}</span>
                        </div>
                        {near.map((z) => (
                          <div className="up-near-row" key={z.P.id}>
                            <em>{"기존"}</em>
                            <span>{z.P.name}</span>
                            <button
                              type="button"
                              className="up-near-yes"
                              onClick={() =>
                                setQueue((y) =>
                                  y.map((I) =>
                                    !I.selected &&
                                    I.declared_project === c.declared_project
                                      ? {
                                          ...I,
                                          selected: z.P.id,
                                          confirmed: !0,
                                          reason: "유사한 이름 확인 후 선택",
                                        }
                                      : I,
                                  ),
                                )
                              }
                            >
                              {"이 프로젝트로 등록"}
                            </button>
                          </div>
                        ))}
                        {D.can_create_project ? (
                          <button
                            type="button"
                            className="up-near-new"
                            onClick={() =>
                              setModal({
                                type: "project",
                                name: c.declared_project,
                                declared: c.declared_project,
                              })
                            }
                          >
                            {"새 프로젝트로 만들기"}
                          </button>
                        ) : null}
                      </div>
                    );
                  })()}
                </div>
                <button
                  className="icon-button"
                  aria-label={c.filename + " 제외"}
                  onClick={() =>
                    setQueue((y) => y.filter((I) => I.id !== c.id))
                  }
                >
                  <X size={16} />
                </button>
              </div>
            ))}
            <div className="register-footer">
              <p>
                {queue.length
                  ? "저장 후 AI 분석이 진행됩니다. 다른 화면으로 이동해도 계속됩니다."
                  : "등록할 파일을 선택해 주세요."}
              </p>
              <Button
                primary={!0}
                disabled={
                  working || !queue.length || queue.some((c) => !c.selected)
                }
                onClick={() => Ca(Og)}
              >
                {working ? "처리 중…" : queue.length + "개 등록"}
              </Button>
            </div>
          </React.Fragment>
        )}
        {page === "detail" && meeting && (
          <React.Fragment>
            <button className="back" onClick={Bg}>
              <ArrowLeft size={16} />
              {"돌아가기"}
            </button>
            <div className="page-heading">
              <div>
                <h1>{meeting.title}</h1>
                <p className="meeting-meta">
                  <span>{et(meeting.project_id)}</span>
                  <span>
                    {"회의일 "}
                    {day(meeting.date)}
                  </span>
                  <span>
                    {"등록일 "}
                    {meeting.created_at
                      ? day(meeting.created_at.slice(0, 10))
                      : "기록 없음"}
                  </span>
                  <span>
                    {"등록자 "}
                    {Xu(meeting.author)}
                  </span>
                </p>
              </div>
              {nf && (
                <div className="actions">
                  {D.projects.find((c) => c.id === meeting.project_id)?.pm ===
                    D.user.id && (
                    <Button
                      disabled={!!workflow.pend(D)[meeting.id]}
                      title={
                        workflow.pend(D)[meeting.id]
                          ? "검수를 마쳐 회의록을 등록한 뒤 보낼 수 있습니다."
                          : ""
                      }
                      onClick={() =>
                        setModal({
                          type: "approval",
                        })
                      }
                    >
                      {D.meetings.find((c) => c.id === meeting.id)?.approval
                        ? "합의 메일 다시 보내기"
                        : "합의 메일 보내기"}
                    </Button>
                  )}
                  <Button
                    icon={Pencil}
                    disabled={at(meeting)}
                    onClick={() =>
                      setModal({
                        type: "source",
                        title: meeting.title,
                        date: meeting.date || "",
                        source: meeting.source,
                      })
                    }
                  >
                    {"본문 수정"}
                  </Button>
                  <Button
                    icon={Trash2}
                    onClick={() =>
                      setModal({
                        type: "trash",
                      })
                    }
                  >
                    {"삭제"}
                  </Button>
                </div>
              )}
            </div>
            {React.createElement(
              approval.ApprovalLine,
              (() => {
                const ap = D.meetings.find(
                    (c) => c.id === meeting.id,
                  )?.approval,
                  ids =
                    ap && ap.status === "approved" && !ap.applied_at
                      ? ap.item_ids || []
                      : [],
                  cnt =
                    D.projects.find((c) => c.id === meeting.project_id)?.pm ===
                    D.user.id
                      ? D.changes.filter(
                          (c) =>
                            ids.includes(c.id) &&
                            c.review_state === "확인됨" &&
                            ["요청", "보류"].includes(c.business_state),
                        ).length
                      : 0;
                return {
                  approval: ap,
                  meetingId: meeting.id,
                  applyCount: cnt,
                  onApply: () =>
                    Ca(async () => {
                      const r = await api(
                        "/v3/meetings/" + meeting.id + "/approval-apply",
                        "POST",
                        {},
                      );
                      await he();
                      setToast(r.applied + "건을 합의로 반영했습니다.");
                    }),
                };
              })(),
            )}
            <div className="tabs">
              <button
                className={tab === "ai" ? "active" : ""}
                onClick={() => setTab("ai")}
              >
                {"AI 정리"}
              </button>
              <button
                className={tab === "source" ? "active" : ""}
                onClick={() => setTab("source")}
              >
                {"원본"}
              </button>
              <span>{Br(meeting)}</span>
            </div>
            {tab === "ai" ? (
              <React.Fragment>
                <div className="analysis-status" aria-live="polite">
                  {at(meeting) ? (
                    <MeetingProgress
                      meeting={{
                        ...meeting,
                        progress: D.meetings.find((c) => c.id === meeting.id)
                          ?.progress,
                      }}
                    />
                  ) : meeting.analysis_state === "failed" ? (
                    <React.Fragment>
                      <CircleAlert size={18} />
                      <span>{meeting.error}</span>
                      {nf && (
                        <Button onClick={() => Ca(Dr)}>{"다시 분석"}</Button>
                      )}
                    </React.Fragment>
                  ) : null}
                </div>
                <article className="reading">
                  {dn.map((c, y) => (
                    <section className="point" key={c.id}>
                      {(y === 0 || dn[y - 1].kind !== c.kind) && (
                        <h2>{c.kind}</h2>
                      )}
                      {edit?.id === c.id ? (
                        <React.Fragment>
                          <textarea
                            value={edit.value}
                            aria-label="정리 문장 수정"
                            onChange={(I) =>
                              setEdit({
                                ...edit,
                                value: I.target.value,
                              })
                            }
                          />
                          <div className="actions">
                            <Button onClick={() => setEdit(null)}>
                              {"취소"}
                            </Button>
                            <Button
                              primary={!0}
                              disabled={working || !edit.value.trim()}
                              onClick={() => Ca(Eg)}
                            >
                              {"저장"}
                            </Button>
                          </div>
                        </React.Fragment>
                      ) : (
                        <button
                          className={
                            "sentence " +
                            (activePoint === c.id ? "selected" : "")
                          }
                          onClick={() => {
                            (setActivePoint(activePoint === c.id ? null : c.id),
                              setEvidence(!1));
                          }}
                        >
                          {c.text}
                        </button>
                      )}
                      {activePoint === c.id && !edit && (
                        <div className="point-tools">
                          {nf && !at(meeting) && (
                            <button
                              onClick={() =>
                                setEdit({
                                  id: c.id,
                                  value: c.text,
                                })
                              }
                            >
                              <Pencil size={14} />
                              {"수정"}
                            </button>
                          )}
                          <button onClick={() => setEvidence(!evidence)}>
                            <Quote size={14} />
                            {"원문 근거"}
                          </button>
                        </div>
                      )}
                      {activePoint === c.id && evidence && (
                        <div className="evidence">
                          {c.evidence.map((I) => (
                            <p key={I}>{wg[I]}</p>
                          ))}
                          <button
                            onClick={() => {
                              (setFocus(c.evidence),
                                setSourceText(!0),
                                setTab("source"));
                            }}
                          >
                            {"원문에서 보기 "}
                            <ArrowUpRight size={14} />
                          </button>
                        </div>
                      )}
                    </section>
                  ))}
                  {!dn.length && !at(meeting) && (
                    <Empty>
                      {"아직 AI 정리 내용이 없습니다."}
                      {nf && (
                        <Button onClick={() => Ca(Dr)}>{"AI 분석하기"}</Button>
                      )}
                    </Empty>
                  )}
                </article>
              </React.Fragment>
            ) : (
              <React.Fragment>
                <div className="source-toolbar">
                  <div className="actions">
                    <Button
                      onClick={() => {
                        (setSourceText(!sourceText), workflow.scroll());
                      }}
                    >
                      {sourceText
                        ? "업로드한 원본"
                        : meeting.revision > 1
                          ? "수정 본문"
                          : "원문 텍스트"}
                    </Button>
                    {!sourceText && meeting.has_pdf && (
                      <select
                        aria-label="원본 확대 비율"
                        value={sourceZoom}
                        onChange={(c) => setSourceZoom(Number(c.target.value))}
                      >
                        {[60, 80, 100].map((c) => (
                          <option key={c} value={c}>
                            {c}
                            {"%"}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <a
                    className="button"
                    href={"/api/v3/meetings/" + meeting.id + "/download"}
                  >
                    <Download size={16} />
                    {"원본 다운로드"}
                  </a>
                </div>
                <div className="ai-layout">
                  {sourceText || !meeting.has_pdf ? (
                    <article className="paper source-lines">
                      {meeting.revision > 1 && (
                        <p className="muted">
                          {
                            "웹에서 수정한 본문입니다. 업로드한 원본 파일은 별도로 보관됩니다."
                          }
                        </p>
                      )}
                      {!sourceText && (
                        <p className="muted">
                          {meeting.source_type === "docx" &&
                          !meeting.preview_finished
                            ? "원본 미리보기를 준비 중입니다. 원문 텍스트를 먼저 확인할 수 있습니다."
                            : "원문에서 읽어 온 텍스트입니다."}
                        </p>
                      )}
                      {(meeting.lines || []).map((c) => (
                        <p
                          id={"source-" + c.id}
                          className={focus.includes(c.id) ? "highlight" : ""}
                          key={c.id}
                        >
                          {focus.includes(c.id)
                            ? workflow.mark(React, meeting, api, setD, c)
                            : c.text}
                        </p>
                      ))}
                    </article>
                  ) : (
                    <div className="pdf-pages">
                      {Array.from(
                        {
                          length: meeting.preview_pages || 1,
                        },
                        (c, y) => (
                          <div
                            key={y}
                            className="pdf-page"
                            style={{
                              width: sourceZoom + "%",
                            }}
                          >
                            <img
                              src={
                                "/api/meetings/" +
                                meeting.id +
                                "/preview/" +
                                (y + 1)
                              }
                              alt={"원본 " + (y + 1) + "페이지"}
                            />
                            {workflow
                              .rects(meeting, api, setD, y + 1)
                              .map((q, k) => (
                                <span
                                  key={k}
                                  className={
                                    q[4] === 0 ? "pdf-hl sub" : "pdf-hl"
                                  }
                                  style={{
                                    left: q[0] * 100 + "%",
                                    top: q[1] * 100 + "%",
                                    width: q[2] * 100 + "%",
                                    height: q[3] * 100 + "%",
                                  }}
                                />
                              ))}
                          </div>
                        ),
                      )}
                    </div>
                  )}
                  {(() => {
                    const _ev = (D.changes || []).filter(
                      (x) => x.meeting_id === meeting.id,
                    );
                    workflow.watch(meeting, at(meeting), he);
                    const _P = D.projects.find(
                        (x) => x.id === meeting.project_id,
                      ),
                      _PM = _P?.pm === D.user.id,
                      // 2026-11-23: 프로젝트 참여자도 검수가 끝나기 전까지 확인·제외·수정할 수 있다(끝난 뒤에는 PM만).
                      _open = _ev.some((x) => x.review_state !== "확인됨" && x.review_state !== "제외"),
                      _CR = _PM || ((_P?.members || []).includes(D.user.id) && _open),
                      _busy = working || at(meeting),
                      _send = (e, a, l) =>
                        Ca(async () => {
                          const q = await api(
                            "/v3/changes/" + e.id + "/review",
                            "POST",
                            {
                              version: e.version,
                              action: a,
                              link_to: l || "",
                            },
                          );
                          setD((y) => ({
                            ...y,
                            changes: y.changes.map((x) =>
                              x.id === q.id
                                ? {
                                    ...x,
                                    ...q,
                                  }
                                : x,
                            ),
                          }));
                          setToast(
                            a === "확인"
                              ? "확인했습니다. 변경이력에 남습니다."
                              : a === "제외"
                                ? "제외했습니다."
                                : "되돌렸습니다.",
                          );
                          he().catch(() => {});
                        }),
                      _show = (e) => {
                        workflow.sel = e.id;
                        setFocus((e.evidence || []).slice());
                        setTab("source");
                        workflow.scroll();
                      },
                      _left = _ev.filter(
                        (x) =>
                          x.review_state !== "확인됨" &&
                          x.review_state !== "제외",
                      ).length,
                      _nt = (t) =>
                        String(t || "")
                          .replace(/\s+/g, "")
                          .toLowerCase(),
                      _dur = (x) => {
                        x = Math.max(0, Math.round(x));
                        return x < 60
                          ? x + "초"
                          : Math.floor(x / 60) + "분 " + (x % 60) + "초";
                      },
                      _el = () => {
                        const t = Date.parse(
                          meeting.analysis_started_at ||
                            meeting.analysis_queued_at ||
                            "",
                        );
                        return isNaN(t)
                          ? ""
                          : _dur((Date.now() - t) / 1000) + " 경과";
                      },
                      _seen = new Set(
                        D.changes
                          .filter(
                            (x) =>
                              x.project_id === meeting.project_id &&
                              x.meeting_id !== meeting.id &&
                              x.review_state !== "제외" &&
                              (x.meeting_date || "") < (meeting.date || "9999"),
                          )
                          .map((x) => _nt(x.title)),
                      ),
                      _base = (e) =>
                        !e.before &&
                        e.business_state === "확정" &&
                        !_seen.has(_nt(e.title)),
                      _CN = [
                        [
                          "요청·보류",
                          "고객이 요청했거나 아직 결론이 나지 않은 항목입니다.",
                        ],
                        [
                          "합의·변경",
                          "이 회의에서 합의했거나 값이 바뀐 항목입니다.",
                        ],
                        ["기준 사양", "이전 회의에 없던 최초 사양입니다."],
                      ],
                      _cat = (e) =>
                        ["요청", "보류"].includes(e.business_state)
                          ? 0
                          : _base(e)
                            ? 2
                            : 1,
                      _grp = (e) => _ev.filter((x) => _cat(x) === _cat(e)),
                      _sorted = _ev.slice().sort((a, d) => _cat(a) - _cat(d));
                    const _all = (list) =>
                        Ca(async () => {
                          const done = [];
                          for (const e of list) {
                            done.push(
                              await api(
                                "/v3/changes/" + e.id + "/review",
                                "POST",
                                {
                                  version: e.version,
                                  action: "확인",
                                  link_to: "",
                                },
                              ),
                            );
                          }
                          setD((y) => ({
                            ...y,
                            changes: y.changes.map((x) => {
                              const q = done.find((d) => d.id === x.id);
                              return q
                                ? {
                                    ...x,
                                    ...q,
                                  }
                                : x;
                            }),
                          }));
                          setToast(
                            done.length +
                              "건을 확인했습니다. 변경이력에 남습니다.",
                          );
                          he().catch(() => {});
                        }),
                      _gh = (e) => {
                        const g = _grp(e);
                        if (!g || g[0].id !== e.id) return null;
                        const wait = g.filter(
                          (x) =>
                            x.review_state !== "확인됨" &&
                            x.review_state !== "제외",
                        );
                        return (
                          <div className="rv-group">
                            <div>
                              <b>{_CN[_cat(e)][0] + " " + g.length + "건"}</b>
                              <small>{_CN[_cat(e)][1]}</small>
                            </div>
                            <span className="rv-grouptools">
                              {_CR && wait.length ? (
                                <button
                                  type="button"
                                  className="rv-btn rv-yes"
                                  disabled={_busy}
                                  onClick={(ev) => {
                                    ev.stopPropagation();
                                    _all(wait);
                                  }}
                                >
                                  {"남은 " + wait.length + "건 확인"}
                                </button>
                              ) : (
                                <small className="rv-state rv-ok">
                                  {wait.length ? "" : "모두 처리됨"}
                                </small>
                              )}
                              {(() => {
                                const oks = g.filter(
                                  (x) => x.review_state === "확인됨",
                                );
                                return _CR && oks.length ? (
                                  <button
                                    type="button"
                                    className="rv-btn rv-allundo"
                                    disabled={_busy}
                                    title="이 범주에서 확인한 항목을 모두 검토 전으로 되돌립니다. 제외한 항목은 그대로 둡니다."
                                    onClick={(ev) => {
                                      ev.stopPropagation();
                                      Ca(async () => {
                                        const done = [];
                                        for (const e of oks) {
                                          done.push(
                                            await api(
                                              "/v3/changes/" + e.id + "/review",
                                              "POST",
                                              {
                                                version: e.version,
                                                action: "검토 전",
                                                link_to: "",
                                              },
                                            ),
                                          );
                                        }
                                        setD((y) => ({
                                          ...y,
                                          changes: y.changes.map((x) => {
                                            const q = done.find(
                                              (d) => d.id === x.id,
                                            );
                                            return q
                                              ? {
                                                  ...x,
                                                  ...q,
                                                }
                                              : x;
                                          }),
                                        }));
                                        setToast(
                                          done.length +
                                            "건의 확인을 취소했습니다.",
                                        );
                                        he().catch(() => {});
                                      });
                                    }}
                                  >
                                    {"전체 되돌리기"}
                                  </button>
                                ) : null;
                              })()}
                            </span>
                          </div>
                        );
                      };
                    return (
                      <section className="rv-panel">
                        <div className="section-head">
                          <h2>{"요구·변경 검수"}</h2>
                          <span className="rv-headtools">
                            <span
                              className={
                                at(meeting) || _left
                                  ? "status warning"
                                  : "status"
                              }
                            >
                              {at(meeting)
                                ? "분석 중… " + _el()
                                : !_ev.length
                                  ? "항목 없음"
                                  : _left
                                    ? _left + "건 확인 필요"
                                    : "모두 확인함"}
                            </span>
                            {!at(meeting) && meeting.metrics?.seconds && !meeting.metrics?.cache_hit ? (
                              <small
                                className="rv-took"
                                title={meeting.metrics.model || ""}
                              >
                                {"분석 " + _dur(meeting.metrics.seconds)}
                              </small>
                            ) : null}
                            {nf && (
                              <button
                                type="button"
                                className="rv-btn"
                                disabled={_busy}
                                title="확인·제외한 항목은 그대로 두고 나머지만 다시 뽑습니다"
                                onClick={() => Ca(Dr)}
                              >
                                {"다시 분석"}
                              </button>
                            )}
                          </span>
                        </div>
                        <p className="muted">
                          {(_left
                            ? "모든 항목을 확인하거나 제외해야 이 회의록이 등록됩니다. 그 전에는 흐름·변경이력에 나오지 않습니다. "
                            : "") +
                            "항목을 누르면 왼쪽 원문에서 근거 문장이 형광펜으로 표시됩니다."}
                        </p>
                        {(() => {
                          if (!_CR || at(meeting) || !_ev.length) return null;
                          const wait = _ev.filter(
                              (x) =>
                                x.review_state !== "확인됨" &&
                                x.review_state !== "제외",
                            ),
                            oks = _ev.filter(
                              (x) => x.review_state === "확인됨",
                            ),
                            undo = () =>
                              Ca(async () => {
                                const done = [];
                                for (const e of oks) {
                                  done.push(
                                    await api(
                                      "/v3/changes/" + e.id + "/review",
                                      "POST",
                                      {
                                        version: e.version,
                                        action: "검토 전",
                                        link_to: "",
                                      },
                                    ),
                                  );
                                }
                                setD((y) => ({
                                  ...y,
                                  changes: y.changes.map((x) => {
                                    const q = done.find((d) => d.id === x.id);
                                    return q
                                      ? {
                                          ...x,
                                          ...q,
                                        }
                                      : x;
                                  }),
                                }));
                                setToast(
                                  done.length + "건의 확인을 취소했습니다.",
                                );
                                he().catch(() => {});
                              });
                          return (
                            <div className="rv-bulk">
                              <button
                                type="button"
                                className="rv-btn rv-allok"
                                disabled={_busy || !wait.length}
                                title="아직 확인하지 않은 항목을 모두 확인 처리합니다. 제외한 항목은 그대로 둡니다."
                                onClick={() => _all(wait)}
                              >
                                {wait.length
                                  ? "남은 " + wait.length + "건 전체 확인"
                                  : "전체 확인"}
                              </button>
                              <button
                                type="button"
                                className="rv-btn rv-allundo"
                                disabled={_busy || !oks.length}
                                title="확인한 항목을 모두 검토 전으로 되돌립니다. 제외한 항목은 그대로 둡니다."
                                onClick={undo}
                              >
                                {"전체 확인 취소"}
                              </button>
                            </div>
                          );
                        })()}
                        {(() => {
                          const k = _ev.filter(
                            (x) =>
                              x.review_state !== "제외" &&
                              x.review_state !== "확인됨" &&
                              (x.checks || []).length,
                          ).length;
                          return k ? (
                            <p className="rv-warn">
                              {"⚠ 자동 점검에서 " +
                                k +
                                "건이 의심 항목으로 표시됐습니다. 이 항목들은 원문을 꼭 대조해 주세요."}
                            </p>
                          ) : null;
                        })()}
                        {(meeting.metrics?.screened_items || []).length > 0 && (
                          <details className="rv-screened">
                            <summary>
                              {"AI가 요구·사양·납기가 아니라고 보고 뺀 문장 " +
                                meeting.metrics.screened_items.length +
                                "건"}
                            </summary>
                            {meeting.metrics.screened_items.map((x, i) => (
                              <p key={i}>
                                <b>{x.title}</b> {x.after}
                                <small>{" · " + x.kind}</small>
                              </p>
                            ))}
                            <small>
                              {
                                "필요한 내용이 빠졌다면 원문을 확인해 직접 기록해 주세요."
                              }
                            </small>
                          </details>
                        )}
                        {(meeting.metrics?.dropped_changes || 0) +
                          (meeting.metrics?.dropped_notes || 0) >
                          0 && (
                          <p className="rv-hint">
                            {"원문에 항목이 많아 " +
                              ((meeting.metrics.dropped_changes || 0) +
                                (meeting.metrics.dropped_notes || 0)) +
                              "건은 자동 추출에서 빠졌습니다. 원문을 직접 확인해 주세요."}
                          </p>
                        )}
                        {_sorted.map((e) => {
                          const ok = e.review_state === "확인됨",
                            no = e.review_state === "제외",
                            ev = e.evidence || [],
                            sel = workflow.sel === e.id,
                            mates = _ev.filter(
                              (x) =>
                                x.id !== e.id &&
                                x.category === e.category &&
                                x.review_state !== "제외",
                            );
                          return (
                            <React.Fragment key={e.id}>
                              {_gh(e)}
                              <article
                                className={
                                  "rv-item" +
                                  (ok ? " done" : "") +
                                  (no ? " out" : "") +
                                  (sel ? " sel" : "") +
                                  (_grp(e) ? " ingrp" : "")
                                }
                                onClick={() => _show(e)}
                              >
                                <div className="rv-item-head">
                                  <button
                                    type="button"
                                    className="rv-title"
                                    onClick={() => _show(e)}
                                  >
                                    {e.title}
                                    <small>{" · " + e.category}</small>
                                  </button>
                                  <span
                                    className={
                                      ["요청", "보류"].includes(
                                        e.business_state,
                                      )
                                        ? "status warning"
                                        : _base(e)
                                          ? "status base"
                                          : "status"
                                    }
                                  >
                                    {_base(e)
                                      ? "기준 사양"
                                      : e.business_state === "확정"
                                        ? "합의"
                                        : e.business_state}
                                  </span>
                                  <small
                                    className={
                                      ok
                                        ? "rv-state rv-ok"
                                        : no
                                          ? "rv-state rv-out"
                                          : "rv-state rv-wait"
                                    }
                                    title={
                                      ok
                                        ? Xu(e.confirmed_by) +
                                          " · " +
                                          (e.confirmed_at || "")
                                        : ""
                                    }
                                  >
                                    {ok ? "확인됨" : no ? "제외" : "검토 전"}
                                  </small>
                                </div>
                                <p className="rv-delta">
                                  {e.before ? <del>{e.before}</del> : null}
                                  {e.before ? " → " : ""}
                                  <b>{e.after}</b>
                                </p>
                                {e.original_title && (
                                  <p className="rv-orig">
                                    {"회의록 표기: " + e.original_title}
                                  </p>
                                )}
                                {e.retitled_from && (
                                  <p className="rv-orig">
                                    {"AI가 항목명을 다시 지었습니다: " +
                                      e.retitled_from +
                                      " → " +
                                      e.title}
                                  </p>
                                )}
                                {!no &&
                                  (e.checks || []).map((k, i) => (
                                    <p key={i} className="rv-warn">
                                      {"⚠ " + k.text}
                                    </p>
                                  ))}
                                {!ok && e.suggested_topic_title && (
                                  <p className="rv-hint">
                                    {"같은 건으로 보입니다: " +
                                      e.suggested_topic_title}
                                  </p>
                                )}
                                <div className="rv-actions">
                                  <button
                                    type="button"
                                    className="rv-link-btn"
                                    onClick={() => _show(e)}
                                  >
                                    {"원문에서 보기"}
                                  </button>
                                  {_CR && !no && (
                                    <button
                                      type="button"
                                      className="rv-link-btn"
                                      disabled={_busy}
                                      title="항목명이나 값을 고칩니다. 고친 뒤에는 다시 확인해야 합니다."
                                      onClick={(ev) => {
                                        ev.stopPropagation();
                                        setModal({
                                          type: "changeEdit",
                                          event: e,
                                          meeting: meeting,
                                        });
                                      }}
                                    >
                                      {"수정"}
                                    </button>
                                  )}
                                  {!_CR && !ok && !no && (
                                    <small className="rv-pmonly">
                                      {"검수가 끝난 회의록은 PM(" +
                                        Xu(_P?.pm) +
                                        ")만 고칠 수 있습니다"}
                                    </small>
                                  )}
                                  {_CR && !ok && !no && (
                                    <button
                                      type="button"
                                      className="rv-btn rv-yes"
                                      disabled={_busy}
                                      onClick={() => _send(e, "확인", "")}
                                    >
                                      {"확인"}
                                    </button>
                                  )}
                                  {_CR && !ok && !no && (
                                    <button
                                      type="button"
                                      className="rv-btn rv-no"
                                      disabled={_busy}
                                      onClick={() => _send(e, "제외", "")}
                                    >
                                      {"제외"}
                                    </button>
                                  )}
                                  {_CR && (ok || no) && (
                                    <button
                                      type="button"
                                      className="rv-btn rv-undo"
                                      disabled={_busy}
                                      onClick={() => _send(e, "검토 전", "")}
                                    >
                                      {"되돌리기"}
                                    </button>
                                  )}
                                </div>
                              </article>
                            </React.Fragment>
                          );
                        })}
                        {(() => {
                          const W = workflow,
                            prev = W.lastLeft;
                          W.lastLeft = {
                            id: meeting.id,
                            left: _left,
                          };
                          if (at(meeting)) return null;
                          const done = _ev.length > 0 && !_left,
                            re2 = () =>
                              setD((y) => ({
                                ...y,
                              }));
                          if (
                            done &&
                            prev &&
                            prev.id === meeting.id &&
                            prev.left > 0
                          )
                            W.rvPop = {
                              mid: meeting.id,
                              kind: "done",
                            };
                          const cnt = {};
                          D.changes.forEach((x) => {
                            if (
                              x.meeting_id !== meeting.id &&
                              x.review_state !== "확인됨" &&
                              x.review_state !== "제외"
                            )
                              cnt[x.meeting_id] = (cnt[x.meeting_id] || 0) + 1;
                          });
                          const next = D.meetings
                              .filter((m) => cnt[m.id])
                              .sort((a, b) =>
                                (a.date || "").localeCompare(b.date || ""),
                              )[0],
                            okN = _ev.filter(
                              (x) => x.review_state === "확인됨",
                            ).length,
                            pop =
                              W.rvPop && W.rvPop.mid === meeting.id
                                ? W.rvPop.kind
                                : null,
                            close = () => {
                              W.rvPop = null;
                              re2();
                            };
                          return (
                            <React.Fragment>
                              {_ev.length > 0 && (
                                <div className="rv-regbar">
                                  <span>
                                    {done
                                      ? "모든 항목을 검수했습니다."
                                      : "검수 " +
                                        (_ev.length - _left) +
                                        " / " +
                                        _ev.length +
                                        "건 · 남은 " +
                                        _left +
                                        "건"}
                                  </span>
                                  <button
                                    type="button"
                                    className={
                                      "rv-btn rv-reg" + (done ? " ok" : "")
                                    }
                                    onClick={() => {
                                      W.rvPop = {
                                        mid: meeting.id,
                                        kind: done ? "done" : "need",
                                      };
                                      re2();
                                    }}
                                  >
                                    {done ? "등록 완료" : "등록하기"}
                                  </button>
                                </div>
                              )}
                              {pop && (
                                <div className="overlay" onClick={close}>
                                  <div
                                    className={"modal rv-pop " + pop}
                                    role="dialog"
                                    aria-modal="true"
                                    onClick={(ev) => ev.stopPropagation()}
                                  >
                                    {pop === "need" ? (
                                      <React.Fragment>
                                        <div className="modal-body">
                                          <i
                                            className="rv-pop-ic"
                                            aria-hidden="true"
                                          >
                                            {"!"}
                                          </i>
                                          <h2>{"아직 등록할 수 없습니다"}</h2>
                                          <p>
                                            {"확인하지 않은 항목이 "}
                                            <b>{_left + "건"}</b>
                                            {" 남았습니다."}
                                            <br />
                                            {
                                              "모든 항목을 확인하거나 제외해야 회의록이 등록됩니다."
                                            }
                                          </p>
                                          <div className="rv-pop-prog">
                                            <div className="rv-pop-bar">
                                              <span
                                                style={{
                                                  width:
                                                    (_ev.length
                                                      ? Math.round(
                                                          ((_ev.length -
                                                            _left) /
                                                            _ev.length) *
                                                            100,
                                                        )
                                                      : 0) + "%",
                                                }}
                                              />
                                            </div>
                                            <small>
                                              {"검수 " +
                                                (_ev.length - _left) +
                                                " / " +
                                                _ev.length +
                                                "건"}
                                            </small>
                                          </div>
                                        </div>
                                        <footer>
                                          <button
                                            type="button"
                                            className="rv-btn"
                                            onClick={close}
                                          >
                                            {"닫기"}
                                          </button>
                                          <button
                                            type="button"
                                            className="rv-btn rv-pri"
                                            onClick={() => {
                                              close();
                                              setTimeout(() => {
                                                const el = [
                                                  ...document.querySelectorAll(
                                                    ".rv-item",
                                                  ),
                                                ].find(
                                                  (x) =>
                                                    !x.classList.contains(
                                                      "done",
                                                    ) &&
                                                    !x.classList.contains(
                                                      "out",
                                                    ),
                                                );
                                                el &&
                                                  el.scrollIntoView({
                                                    block: "center",
                                                    behavior: "smooth",
                                                  });
                                              }, 50);
                                            }}
                                          >
                                            {"남은 항목으로 가기"}
                                          </button>
                                        </footer>
                                      </React.Fragment>
                                    ) : (
                                      <React.Fragment>
                                        <div className="modal-body">
                                          <i
                                            className="rv-pop-ic"
                                            aria-hidden="true"
                                          >
                                            {"✓"}
                                          </i>
                                          <h2>
                                            {
                                              "검수를 마쳐 회의록이 등록됐습니다"
                                            }
                                          </h2>
                                          <p>
                                            {"확인 " +
                                              okN +
                                              "건" +
                                              (_ev.length - okN
                                                ? " · 제외 " +
                                                  (_ev.length - okN) +
                                                  "건"
                                                : "") +
                                              ". 이제 흐름과 변경이력에 반영됩니다."}
                                          </p>
                                          {next && (
                                            <p className="muted">
                                              {"검수가 남은 회의록: " +
                                                (next.date || "").replace(
                                                  /-/g,
                                                  ".",
                                                ) +
                                                " " +
                                                next.title +
                                                " · " +
                                                cnt[next.id] +
                                                "건"}
                                            </p>
                                          )}
                                        </div>
                                        <footer>
                                          <button
                                            type="button"
                                            className="rv-btn"
                                            onClick={close}
                                          >
                                            {"닫기"}
                                          </button>
                                          <button
                                            type="button"
                                            className="rv-btn"
                                            onClick={() => {
                                              W.rvPop = null;
                                              Be("minutes");
                                            }}
                                          >
                                            {"회의록 목록"}
                                          </button>
                                          <button
                                            type="button"
                                            className={
                                              "rv-btn" + (next ? "" : " rv-pri")
                                            }
                                            onClick={() => {
                                              W.rvPop = null;
                                              W.hist.tab = "flow";
                                              setPid(meeting.project_id);
                                              setTopic("");
                                              Be("changes");
                                            }}
                                          >
                                            {"흐름에서 보기"}
                                          </button>
                                          {next && (
                                            <button
                                              type="button"
                                              className="rv-btn rv-pri"
                                              onClick={() => {
                                                W.rvPop = null;
                                                Ca(() => ff(next.id, []));
                                              }}
                                            >
                                              {"다음 회의록 검수 →"}
                                            </button>
                                          )}
                                        </footer>
                                      </React.Fragment>
                                    )}
                                  </div>
                                </div>
                              )}
                            </React.Fragment>
                          );
                        })()}
                      </section>
                    );
                  })()}
                </div>
              </React.Fragment>
            )}
          </React.Fragment>
        )}
        {page === "weekly" && (
          <WeeklyReport toast={setToast} openMeeting={ff} />
        )}
        {page === "changes" && (
          <React.Fragment>
            <button className="back" onClick={() => Be("home")}>
              <ArrowLeft size={16} />
              {"홈으로"}
            </button>
            <div className="page-heading">
              <div>
                <span className="eyebrow">{pid || "PROJECT HISTORY"}</span>
                <h1>{pid ? et(pid) : "프로젝트 변경이력"}</h1>
                {pid && (
                  <p>
                    {"PM "}
                    {Xu(D.projects.find((c) => c.id === pid)?.pm)}
                    {" · 참여자 "}
                    {D.projects.find((c) => c.id === pid)?.members?.length || 0}
                    {"명"}
                  </p>
                )}
              </div>
              <div className="actions">
                {pid &&
                  D.projects.find((c) => c.id === pid)?.pm === D.user.id && (
                    <Button
                      icon={Users}
                      onClick={() => setModal({ type: "members", pid, add: [] })}
                    >
                      {"참여자"}
                    </Button>
                  )}
                {pid &&
                  D.projects.find((c) => c.id === pid)?.pm === D.user.id && (
                    <Button
                      icon={Trash2}
                      onClick={() =>
                        Ca(async () =>
                          setModal({
                            type: "deleteProject",
                            project: D.projects.find((c) => c.id === pid),
                            preview: await api(
                              "/projects/" + pid + "/trash-preview",
                            ),
                          }),
                        )
                      }
                    >
                      {"프로젝트 삭제"}
                    </Button>
                  )}
              </div>
            </div>
            {(() => {
              const __X = {
                  R: React,
                  u: D,
                  p: pid,
                  o: setD,
                  Q: api,
                  Ca,
                  ff,
                  at,
                  vt: day,
                  et,
                  Xu,
                  Ig: ChangeValue,
                  df,
                  he,
                },
                __H = workflow.hist,
                __fl = __H.tab === "flow";
              return (
                <React.Fragment>
                  <div className="tabs pf-tabs" role="group" aria-label="프로젝트 보기 방식">
                    <button
                      type="button"
                      className={__fl ? "active" : ""}
                      aria-pressed={__fl}
                      onClick={() => {
                        __H.tab = "flow";
                        setD((y) => ({
                          ...y,
                        }));
                      }}
                    >
                      <Route size={18} aria-hidden="true" />
                      {"흐름"}
                    </button>
                    <button
                      type="button"
                      className={__fl ? "" : "active"}
                      aria-pressed={!__fl}
                      onClick={() => {
                        __H.tab = "hist";
                        setD((y) => ({
                          ...y,
                        }));
                      }}
                    >
                      <History size={18} aria-hidden="true" />
                      {"변경이력"}
                    </button>
                  </div>
                  {__fl ? (
                    pid ? (
                      workflow.Flow(__X)
                    ) : (
                      <div className="pf-pick">
                        <p className="muted">
                          {"흐름을 볼 프로젝트를 고르세요."}
                        </p>
                        <div className="pf-pickgrid">
                          {D.projects.map((c) => (
                            <button
                              type="button"
                              key={c.id}
                              className="pf-pickbtn"
                              onClick={() => {
                                changeProject(c.id);
                                setTopic("");
                                setD((y) => ({
                                  ...y,
                                }));
                              }}
                            >
                              <small>{c.id}</small>
                              <b>{c.name}</b>
                              <span>
                                {"회의록 " +
                                  D.meetings.filter(
                                    (m) => m.project_id === c.id,
                                  ).length +
                                  "건"}
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  ) : (
                    (() => {
                      const H =
                          workflow.hist ||
                          (workflow.hist = {
                            open: {},
                            filter: "all",
                          }),
                        re = () =>
                          setD((y) => ({
                            ...y,
                          })),
                        stateFilter = HISTORY_STATES.includes(H.filter) ? H.filter : (H.filter = H.filter === "done" ? "확정" : "all"),
                        last = (g) => g.events[g.events.length - 1],
                        pend = (g) =>
                          ["요청", "보류"].includes(last(g).business_state),
                        done = (g) => last(g).business_state === "확정",
                        mts = [
                          ...new Map(
                            df
                              .flatMap((g) => g.events)
                              .map((e) => [
                                e.meeting_id,
                                {
                                  id: e.meeting_id,
                                  t: e.meeting_title,
                                  d: e.meeting_date || "",
                                },
                              ]),
                          ).values(),
                        ].sort((x, y) => y.d.localeCompare(x.d)),
                        qq = (H.q || "").trim().toLowerCase(),
                        base = df.filter(
                          (g) =>
                            (!H.cat || g.category === H.cat) &&
                            (!H.mt ||
                              g.events.some((e) => e.meeting_id === H.mt)) &&
                            (!qq ||
                              (
                                g.title + " " + categoryLabel(g.category) +
                                " " +
                                g.events
                                  .map(
                                    (e) =>
                                      (e.original_title || "") +
                                      " " +
                                      e.before +
                                      " " +
                                      e.after,
                                  )
                                  .join(" ")
                              )
                                .toLowerCase()
                                .includes(qq)),
                        ),
                        list = base.filter((g) => matchesHistoryState(g, stateFilter)),
                        PG = 10,
                        pages = Math.max(1, Math.ceil(list.length / PG)),
                        pg = Math.min(H.page || 0, pages - 1),
                        shown = list.slice(pg * PG, pg * PG + PG),
                        isOpen = (g) => !!H.open[g.key],
                        cur = shown.find((g) => g.key === H.sel) || shown[0],
                        st = (e) => (
                          <span
                            className={
                              "status " +
                              (["요청", "보류"].includes(e.business_state)
                                ? "warning"
                                : "")
                            }
                          >
                            {e.business_state === "확정"
                              ? "합의"
                              : e.business_state}
                          </span>
                        ),
                        info = (g) => {
                          const lab = workflow.revs(g.events),
                            B = lab.__cur;
                          return {
                            lab,
                            B,
                            L: last(g),
                            un: g.events.filter(
                              (x) => x.review_state !== "확인됨",
                            ).length,
                            after: B
                              ? g.events
                                  .slice(g.events.indexOf(B) + 1)
                                  .some((x) => x.business_state !== "확정")
                              : !1,
                          };
                        },
                        now = (I, big) => (
                          <React.Fragment>
                            <ChangeValue event={I.B || I.L} compact={!big} />
                            {(I.B || I.L).after_source && (
                              <small className="hx-src">
                                {"원문: " + (I.B || I.L).after_source}
                              </small>
                            )}
                            {!I.B && (
                              <small className="hx-sub">
                                {"합의된 기준 없음"}
                              </small>
                            )}
                            {I.after && (
                              <small className="hx-sub warn">
                                {"이후 변경 요청 있음"}
                              </small>
                            )}
                          </React.Fragment>
                        ),
                        categoryControl = (g) => {
                          const project = D.projects.find(p => p.id === g.project_id);
                          return <HistoryCategoryEditor group={g} project={project} records={D.changes}
                            canEdit={project?.pm === D.user.id} api={api}
                            onSaved={async result => {
                              const key = groupKey(g.project_id, result.category, g.title);
                              H.sel = key; H.open[key] = true;
                              if (H.cat === g.category) H.cat = result.category;
                              setTopic(key);
                              await he();
                            }} />;
                        },
                        body = (g, placement = "inline") => {
                          const { lab } = info(g),
                            desc = H.evSort === "desc",
                            flowId = "history-flow-" + placement + "-" + encodeURIComponent(g.key),
                            order = g.events.map((e, k) => ({
                              e,
                              n: k + 1,
                            })),
                            evs = desc ? order.slice().reverse() : order,
                            isOpenE = (e) => !!(H.evOpen && H.evOpen[e.id]),
                            tagOf = (e, R) =>
                              e.business_state === "확정"
                                ? R.t === "재확인"
                                  ? "재확인 (값 변동 없음)"
                                  : (R.t || "합의") + " 합의"
                                : e.business_state === "요청"
                                  ? "변경 요청 (미합의)"
                                  : e.business_state === "보류"
                                    ? "보류 (미합의)"
                                    : e.business_state;
                          return (
                            <div
                              className={"tl " + (desc ? "tl-desc" : "tl-asc")}
                            >
                              {placement === "inline" && <div className="history-inline-category">{categoryControl(g)}</div>}
                              <div className="tl-tools">
                                <b>
                                  {"변경 흐름 · " +
                                    (desc ? "최신 순" : "오래된 순")}
                                </b>
                                <button
                                  type="button"
                                  onClick={() => {
                                    H.evSort = desc ? "asc" : "desc";
                                    re();
                                  }}
                                >
                                  {desc ? "⇅ 오래된 순으로" : "⇅ 최신 순으로"}
                                </button>
                              </div>
                              <div id={flowId} className="tl-records">
                              {evs.map((x, idx) => {
                                const e = x.e,
                                  R = lab[e.id] || {
                                    t: "",
                                    c: "",
                                  },
                                  isCur = lab.__cur === e,
                                  pendS =
                                    e.business_state === "요청" ||
                                    e.business_state === "보류",
                                  rev = ((e.quotes || [])
                                    .join(" ")
                                    .match(/(?:Spec\.?\s*)?Rev\.?\s*\d+/i) ||
                                    [])[0],
                                  open = isOpenE(e),
                                  long = String(e.after || "").length > 36,
                                  tog = () => {
                                    H.evOpen = H.evOpen || {};
                                    H.evOpen[e.id] = !open;
                                    re();
                                  };
                                return (
                                  <div
                                    key={e.id}
                                    className={
                                      "tl-item" +
                                      (isCur ? " cur" : "") +
                                      (pendS ? " req" : "")
                                    }
                                  >
                                    <div className="tl-rail">
                                      <span className="tl-num">{x.n}</span>
                                      {idx < evs.length - 1 && (
                                        <span className="tl-conn" />
                                      )}
                                    </div>
                                    <div className="tl-card">
                                      <div className="tl-head">
                                        <time>
                                          {day(
                                            e.meeting_date || e.effective_date,
                                          )}
                                        </time>
                                        <span className="tl-tag">
                                          {tagOf(e, R)}
                                        </span>
                                        {(() => {
                                          const a = (
                                            D.meetings.find(
                                              (q) => q.id === e.meeting_id,
                                            ) || {}
                                          ).approval;
                                          if (
                                            !a ||
                                            !(a.item_ids || []).includes(
                                              e.id,
                                            ) ||
                                            ![
                                              "approved",
                                              "rejected",
                                              "sent",
                                            ].includes(a.status)
                                          )
                                            return null;
                                          const d = a.responded_at
                                            ? " " +
                                              a.responded_at
                                                .slice(5, 10)
                                                .replace("-", ".")
                                            : "";
                                          return (
                                            <span
                                              className={"tl-agree " + a.status}
                                              title={
                                                a.email +
                                                (a.comment
                                                  ? " · 의견: " + a.comment
                                                  : "")
                                              }
                                            >
                                              {a.status === "approved"
                                                ? "합의" + d
                                                : a.status === "rejected"
                                                  ? "반려" + d
                                                  : "회신 대기"}
                                            </span>
                                          );
                                        })()}
                                        {isCur && (
                                          <span className="tl-curflag">
                                            {"현재 합의"}
                                          </span>
                                        )}
                                        {rev && (
                                          <span
                                            className="tl-rev"
                                            title="회의록에 적힌 공식 리비전 표기"
                                          >
                                            {rev}
                                          </span>
                                        )}
                                        {D.projects.find(
                                          (q) => q.id === e.project_id,
                                        )?.pm === D.user.id && (
                                          <button
                                            type="button"
                                            className="tl-edit"
                                            disabled={
                                              working ||
                                              at(
                                                D.meetings.find(
                                                  (q) => q.id === e.meeting_id,
                                                ) || {},
                                              )
                                            }
                                            onClick={() =>
                                              Ca(async () =>
                                                setModal({
                                                  type: "changeEdit",
                                                  event: e,
                                                  meeting: await api(
                                                    "/meetings/" + e.meeting_id,
                                                  ),
                                                }),
                                              )
                                            }
                                          >
                                            {"✎ 수정"}
                                          </button>
                                        )}
                                      </div>
                                      <div
                                        className={
                                          "tl-val" + (long ? " long" : "")
                                        }
                                      >
                                        {e.before ? (
                                          <del>{e.before + " → "}</del>
                                        ) : null}
                                        {e.after}
                                      </div>
                                      {(e.checks || []).map((k, i) => (
                                        <p key={"w" + i} className="rv-warn">
                                          {"⚠ " + k.text}
                                        </p>
                                      ))}
                                      {(e.checks || []).length > 0 &&
                                        D.projects.find(
                                          (q) => q.id === e.project_id,
                                        )?.pm === D.user.id && (
                                          <div className="tl-fix">
                                            <span>
                                              {"이 항목의 기록이 아니라면"}
                                            </span>
                                            <button
                                              type="button"
                                              className="rv-btn rv-no"
                                              disabled={working}
                                              onClick={() =>
                                                Ca(async () => {
                                                  const q = await api(
                                                    "/v3/changes/" +
                                                      e.id +
                                                      "/review",
                                                    "POST",
                                                    {
                                                      version: e.version,
                                                      action: "제외",
                                                      link_to: "",
                                                    },
                                                  );
                                                  setD((y) => ({
                                                    ...y,
                                                    changes: y.changes.map(
                                                      (z) =>
                                                        z.id === q.id
                                                          ? {
                                                              ...z,
                                                              ...q,
                                                            }
                                                          : z,
                                                    ),
                                                  }));
                                                  setToast(
                                                    "이 기록을 변경이력에서 제외했습니다. 회의록 검수 화면에서 되돌릴 수 있습니다.",
                                                  );
                                                  he().catch(() => {});
                                                })
                                              }
                                            >
                                              {"이 기록 제외"}
                                            </button>
                                          </div>
                                        )}
                                      <button
                                        type="button"
                                        className="tl-more"
                                        aria-expanded={open}
                                        onClick={tog}
                                      >
                                        {open
                                          ? "▾ 원문 근거 접기"
                                          : "▸ 원문 근거 보기"}
                                      </button>
                                      {open && (
                                        <React.Fragment>
                                          {e.original_title && (
                                            <p className="rv-orig">
                                              {"회의록 표기: " +
                                                e.original_title}
                                            </p>
                                          )}
                                          <div className="tl-quotes">
                                            {(e.quotes || []).map((q, z) => (
                                              <p key={z}>
                                                {String(q)
                                                  .split(
                                                    /(?<=[가-힣)][.!?])\s+/,
                                                  )
                                                  .map((t, k) => (
                                                    <span key={k}>{t}</span>
                                                  ))}
                                              </p>
                                            ))}
                                          </div>
                                          <button
                                            type="button"
                                            className="tl-link"
                                            onClick={() => {
                                              workflow.sel = e.id;
                                              Ca(() =>
                                                ff(e.meeting_id, e.evidence),
                                              );
                                            }}
                                          >
                                            {e.meeting_title + " 에서 보기 ↗"}
                                          </button>
                                        </React.Fragment>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                              </div>
                            </div>
                          );
                        },
                        pick = (g) => {
                          H.sel = g.key;
                          H.open[g.key] = !H.open[g.key];
                          re();
                        };
                      return (
                        <div className="hx history-items-layout">
                          <HistoryToolbar
                            projectId={pid}
                            history={H}
                            meetings={mts}
                            counts={Object.fromEntries(HISTORY_STATES.map(state => [state, base.filter(g => matchesHistoryState(g, state)).length]))}
                            categories={usedCategories(df)}
                            resultCount={list.length}
                            canExpand={shown.length > 0}
                            allExpanded={shown.length > 0 && shown.every(isOpen)}
                            onChange={re}
                            onToggleAll={() => {
                              const all = shown.every(isOpen);
                              shown.forEach((g) => {
                                H.open[g.key] = !all;
                              });
                              re();
                            }}
                          />
                          <div className="hx-split">
                            <div className="hx-list">
                              {shown.map((g) => {
                                const I = info(g),
                                  on = cur && cur.key === g.key;
                                return (
                                  <section
                                    key={g.key}
                                    className={
                                      "hx-row" +
                                      (on ? " on" : "") +
                                      (isOpen(g) ? " open" : "")
                                    }
                                  >
                                    <button
                                      type="button"
                                      className="hx-tr"
                                      aria-pressed={!!on}
                                      aria-label={g.title + " · " + (I.L.business_state === "확정" ? "합의" : I.L.business_state)}
                                      onClick={() => pick(g)}
                                    >
                                      <span className="hx-c-name">
                                        <b>{g.title}</b>
                                      </span>
                                      <span className="hx-c-st">{st(I.L)}</span>
                                      <span className="hx-c-now">
                                        <ChangeValue event={I.L} compact />
                                      </span>
                                      <span className="hx-c-cat">
                                        {categoryLabel(g.category)}
                                        {!pid && " · " + et(g.project_id)}
                                      </span>
                                    </button>
                                    {isOpen(g) && (
                                      <div className="hx-inline">{body(g)}</div>
                                    )}
                                  </section>
                                );
                              })}
                              {!list.length && (
                                <p className="empty">
                                  {df.length
                                    ? "해당하는 항목이 없습니다."
                                    : D.meetings.some(
                                          (c) =>
                                            (!pid || c.project_id === pid) &&
                                            at(c),
                                        )
                                      ? "회의록을 분석하고 있습니다. 완료되면 변경 기록이 표시됩니다."
                                      : "아직 변경 기록이 없습니다."}
                                </p>
                              )}
                              {list.length > PG && (
                                <div className="pager hx-pager">
                                  <span>
                                    {pg * PG +
                                      1 +
                                      "–" +
                                      Math.min(pg * PG + PG, list.length) +
                                      " / " +
                                      list.length}
                                  </span>
                                  <button
                                    type="button"
                                    aria-label="이전"
                                    disabled={pg === 0}
                                    onClick={() => {
                                      H.page = pg - 1;
                                      re();
                                    }}
                                  >
                                    {"‹"}
                                  </button>
                                  {Array.from(
                                    {
                                      length: pages,
                                    },
                                    (_, i) => (
                                      <button
                                        type="button"
                                        key={i}
                                        className={i === pg ? "on" : ""}
                                        onClick={() => {
                                          H.page = i;
                                          re();
                                        }}
                                      >
                                        {i + 1}
                                      </button>
                                    ),
                                  )}
                                  <button
                                    type="button"
                                    aria-label="다음"
                                    disabled={pg >= pages - 1}
                                    onClick={() => {
                                      H.page = pg + 1;
                                      re();
                                    }}
                                  >
                                    {"›"}
                                  </button>
                                </div>
                              )}
                            </div>
                            {cur && (
                              <aside className="hx-detail">
                                {(() => {
                                  const I = info(cur);
                                  return (
                                    <React.Fragment>
                                      <div className="hx-dhead">
                                        <div className="history-meta-row">
                                        <small>
                                          {(pid
                                            ? ""
                                            : et(cur.project_id) + " · ") +
                                            categoryLabel(cur.category) +
                                            " · " +
                                            day(
                                              cur.events[0].meeting_date ||
                                                cur.events[0].effective_date,
                                            ) +
                                            " 시작 · 기록 " +
                                            cur.events.length +
                                            "건" +
                                            (I.un
                                              ? " · 미확인 " + I.un + "건"
                                              : "")}
                                        </small>
                                        <h2>{cur.title}</h2>
                                        {categoryControl(cur)}
                                        </div>
                                        {(() => {
                                          const B = I.B,
                                            rest = B
                                              ? cur.events
                                                  .slice(
                                                    cur.events.indexOf(B) + 1,
                                                  )
                                                  .filter(
                                                    (x) =>
                                                      x.business_state !==
                                                      "확정",
                                                  ).length
                                              : 0;
                                          return (
                                            <React.Fragment>
                                              {B ? (
                                                <div className="rv-now">
                                                  <span className="k">
                                                    {"현재 합의 내용"}
                                                  </span>
                                                  <span className="v">
                                                    {B.before ? (
                                                      <del>
                                                        {B.before + " → "}
                                                      </del>
                                                    ) : null}
                                                    {B.after}
                                                  </span>
                                                  <span className="t">
                                                    {(I.lab.__label || "") +
                                                      " · " +
                                                      day(
                                                        B.meeting_date ||
                                                          B.effective_date,
                                                      )}
                                                  </span>
                                                </div>
                                              ) : (
                                                <div className="rv-now none">
                                                  <span className="k">
                                                    {"현재 합의 내용"}
                                                  </span>
                                                  <span className="v">
                                                    {
                                                      "아직 합의된 값이 없습니다"
                                                    }
                                                  </span>
                                                </div>
                                              )}
                                              {rest ? (
                                                <p className="rv-after">
                                                  {"이후 합의되지 않은 변경 요청·보류가 " +
                                                    rest +
                                                    "건 있습니다."}
                                                </p>
                                              ) : null}
                                            </React.Fragment>
                                          );
                                        })()}
                                      </div>
                                      {body(cur, "detail")}
                                    </React.Fragment>
                                  );
                                })()}
                              </aside>
                            )}
                          </div>
                          <p className="muted hx-note">
                            {
                              "같은 이름의 기록을 날짜순으로 이은 것입니다. 사람이 확인한 합의 값이 바뀔 때만 최초·변경 N차로 세고, 확인 전 기록은 미확인으로 흐리게 표시합니다."
                            }
                          </p>
                        </div>
                      );
                    })()
                  )}
                </React.Fragment>
              );
            })()}
          </React.Fragment>
        )}
      </main>
      <QuestionPanel
        key={D.user.id}
        D={D}
        open={questionOpen}
        close={() => setQuestionOpen(!1)}
        onOpenProject={(c) => {
          (setQuestionOpen(!1), setPid(c), setTopic(""), Be("changes"));
        }}
      />
      {modal?.type === "changeEdit" && (
        <HistoryEditor
          event={modal.event}
          meeting={modal.meeting}
          close={() => setModal(null)}
          onSaved={(c) => {
            (setD((y) => ({
              ...y,
              changes: y.changes.map((I) =>
                I.id === c.id
                  ? {
                      ...I,
                      ...c,
                    }
                  : I,
              ),
            })),
              setTopic(c.project_id + "|" + c.category + "|" + norm(c.title)),
              setModal(null),
              setToast("변경 기록을 저장했습니다."),
              he().catch((y) =>
                setToast("저장했습니다. 화면 갱신을 위해 다시 열어 주세요."),
              ));
          }}
        />
      )}
      {modal?.type === "unifiedTrash" && (
        <TrashPanel close={() => setModal(null)} onChanged={he} />
      )}
      {modal?.type === "deleteProject" && (
        <Modal
          title="프로젝트를 휴지통으로 이동할까요?"
          close={() => setModal(null)}
          footer={
            <React.Fragment>
              <Button onClick={() => setModal(null)}>{"취소"}</Button>
              <Button
                primary={!0}
                disabled={working}
                onClick={() =>
                  Ca(async () => {
                    (await api(
                      "/projects/" + modal.project.id + "/trash",
                      "POST",
                      {
                        version: modal.preview.version,
                      },
                    ),
                      setPid(""),
                      setTopic(""),
                      setCardsPage(0),
                      Be("home"),
                      await he(),
                      setToast("프로젝트를 휴지통으로 이동했습니다."));
                  })
                }
              >
                {"휴지통으로 이동"}
              </Button>
            </React.Fragment>
          }
        >
          <h3>{modal.project.name}</h3>
          <p>
            {"회의록 "}
            {modal.preview.meetings}
            {
              "개와 연결된 일정·변경이력이 함께 숨겨집니다. 상단 휴지통에서 복원할 수 있습니다."
            }
          </p>
        </Modal>
      )}
      {modal?.type === "account" && (
        <Modal title="내 계정" close={() => setModal(null)}>
          <h3>{D.user.name}</h3>
          <p>
            {D.user.department}
            {" · "}
            {D.user.position}
          </p>
          <Button
            icon={LogOut}
            onClick={() =>
              Ca(async () => {
                (await api("/logout", "POST"),
                  setD(null),
                  setModal(null),
                  setPage("home"),
                  setPid(""),
                  setQueue([]),
                  setMemos({}));
              })
            }
          >
            {authMode === "supabase" ? "로그아웃" : "사용자 바꾸기"}
          </Button>
        </Modal>
      )}
      {modal?.type === "approval" &&
        meeting &&
        React.createElement(approval.SendApprovalDialog, {
          meeting: meeting,
          items: D.changes
            .filter(
              (c) => c.meeting_id === meeting.id && c.review_state === "확인됨",
            )
            .map((c) => ({
              id: c.id,
              title: c.title,
              before: c.before || "",
              after: c.after || "",
            })),
          blocked: Math.max(0, workflow.pend(D)[meeting.id] || 0),
          approval: D.meetings.find((c) => c.id === meeting.id)?.approval,
          close: () => setModal(null),
          onSent: () => he().catch((c) => setToast(c.message)),
        })}
      {modal?.type === "project" && (
        <Modal
          title="새 프로젝트"
          close={() => setModal(null)}
          footer={
            <Button
              primary={!0}
              disabled={working || modal.name.trim().length < 2}
              onClick={() =>
                Ca(async () => {
                  let c = await api("/projects", "POST", {
                    name: modal.name,
                    members:
                      modal.members ??
                      D.people
                        .filter(
                          (y) =>
                            (y.account_status || "active") === "active" &&
                            y.id !== D.user.id,
                        )
                        .map((y) => y.id),
                  });
                  modal.declared &&
                    setQueue((l) =>
                      l.map((E) =>
                        E.declared_project === modal.declared && !E.selected
                          ? {
                              ...E,
                              selected: c.id,
                              confirmed: !0,
                              reason: "문서의 프로젝트명으로 만든 새 프로젝트",
                            }
                          : E,
                      ),
                    );
                  (await he(),
                    setCardsPage(0),
                    setPid(c.id),
                    setModal(null),
                    setToast("프로젝트를 등록했습니다."));
                })
              }
            >
              {"프로젝트 만들기"}
            </Button>
          }
        >
          <label>
            {"프로젝트명"}
            <input
              autoFocus={!0}
              value={modal.name}
              onChange={(c) =>
                setModal({
                  ...modal,
                  name: c.target.value,
                })
              }
            />
          </label>
          {(() => {
            // 참여자 선택: 처음에는 사용 중인 사람을 모두 고른 상태, PM(나)은 항상 포함
            const others = D.people.filter(
                (y) =>
                  (y.account_status || "active") === "active" &&
                  y.id !== D.user.id,
              ),
              chosen = modal.members ?? others.map((y) => y.id);
            return (
              <fieldset className="member-pick">
                <legend>{"참여자"}</legend>
                {others.map((y) => (
                  <label key={y.id}>
                    <input
                      type="checkbox"
                      checked={chosen.includes(y.id)}
                      onChange={(ev) =>
                        setModal({
                          ...modal,
                          members: ev.target.checked
                            ? [...chosen, y.id]
                            : chosen.filter((x) => x !== y.id),
                        })
                      }
                    />
                    {y.name}
                    <small>{y.position || ""}</small>
                  </label>
                ))}
                <p className="muted">
                  {"PM "}
                  {D.user.name}
                  {" · 참여자 "}
                  {chosen.length + 1}
                  {"명 · 참여자만 이 프로젝트를 볼 수 있습니다."}
                </p>
              </fieldset>
            );
          })()}
        </Modal>
      )}
      {modal?.type === "notices" && (
        <Modal
          title="알림"
          close={() => setModal(null)}
          footer={
            notices.unread ? (
              <Button
                disabled={working}
                onClick={() =>
                  Ca(async () => {
                    (await api("/notifications/read", "POST", { all: !0 }),
                      await loadNotices());
                  })
                }
              >
                {"모두 읽음"}
              </Button>
            ) : null
          }
        >
          {notices.items.length === 0 ? (
            <p className="muted">{"새 알림이 없습니다."}</p>
          ) : (
            <ul className="notice-list">
              {notices.items.map((n) => (
                <li key={n.id} className={n.read_at ? "" : "unread"}>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() =>
                      Ca(async () => {
                        (n.read_at ||
                          (await api("/notifications/read", "POST", {
                            ids: [n.id],
                          })),
                          await loadNotices(),
                          n.target_type === "meeting" &&
                          D.meetings.some((x) => x.id === n.target_id)
                            ? await ff(n.target_id)
                            : setModal(null));
                      })
                    }
                  >
                    <span>{n.title}</span>
                    <small>
                      {Xu(n.actor)}
                      {" · "}
                      {new Date(n.created_at).toLocaleString("ko-KR", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
      {modal?.type === "members" &&
        (() => {
          const proj = D.projects.find((c) => c.id === modal.pid);
          if (!proj) return null;
          const inProject = D.people.filter((y) => proj.members.includes(y.id)),
            addable = D.people.filter(
              (y) =>
                !proj.members.includes(y.id) &&
                (y.account_status || "active") === "active",
            ),
            picked = modal.add || [];
          return (
            <Modal title="참여자 관리" close={() => setModal(null)}>
              <p className="muted">
                {proj.name}
                {" · 참여자는 이 프로젝트의 회의록·변경이력을 볼 수 있습니다."}
              </p>
              <ul className="member-list">
                {inProject.map((y) => (
                  <li key={y.id}>
                    <span>
                      {y.name}
                      <small>
                        {y.position || ""}
                        {y.id === proj.pm ? " · PM" : ""}
                        {(y.account_status || "active") !== "active"
                          ? " · 사용 중지"
                          : ""}
                      </small>
                    </span>
                    {y.id !== proj.pm &&
                      (modal.confirm?.id === y.id ? (
                        <span className="member-confirm">
                          <small>
                            {modal.confirm.meetings
                              ? `작성한 회의록 ${modal.confirm.meetings}건은 그대로 남지만, 이 프로젝트를 볼 수 없게 됩니다.`
                              : "이 프로젝트를 더 이상 볼 수 없게 됩니다."}
                          </small>
                          <Button
                            primary={!0}
                            disabled={working}
                            onClick={() =>
                              Ca(async () => {
                                (await api(
                                  "/projects/" + proj.id + "/members/" + y.id,
                                  "DELETE",
                                ),
                                  await he(),
                                  setModal({ ...modal, confirm: null }),
                                  setToast(y.name + "님을 참여자에서 뺐습니다."));
                              })
                            }
                          >
                            {"빼기 확인"}
                          </Button>
                          <Button onClick={() => setModal({ ...modal, confirm: null })}>
                            {"취소"}
                          </Button>
                        </span>
                      ) : (
                        <Button
                          disabled={working}
                          onClick={() =>
                            Ca(async () => {
                              let impact = await api(
                                "/projects/" + proj.id + "/members/" + y.id + "/impact",
                              );
                              impact.open_tasks
                                ? setToast(
                                    impact.name +
                                      "님이 담당·검토 중인 업무가 " +
                                      impact.open_tasks +
                                      "건 있어 뺄 수 없습니다. 업무 담당자를 먼저 바꿔 주세요.",
                                  )
                                : setModal({ ...modal, confirm: impact });
                            })
                          }
                        >
                          {"빼기"}
                        </Button>
                      ))}
                  </li>
                ))}
              </ul>
              <h3 className="member-add-title">{"추가하기"}</h3>
              {addable.length === 0 ? (
                <p className="muted">{"추가할 수 있는 사람이 없습니다."}</p>
              ) : (
                <div className="member-pick">
                  {addable.map((y) => (
                    <label key={y.id}>
                      <input
                        type="checkbox"
                        checked={picked.includes(y.id)}
                        onChange={(ev) =>
                          setModal({
                            ...modal,
                            add: ev.target.checked
                              ? [...picked, y.id]
                              : picked.filter((x) => x !== y.id),
                          })
                        }
                      />
                      {y.name}
                      <small>{y.position || ""}</small>
                    </label>
                  ))}
                  <Button
                    primary={!0}
                    disabled={working || !picked.length}
                    onClick={() =>
                      Ca(async () => {
                        (await api("/projects/" + proj.id + "/members", "PATCH", {
                          ids: picked,
                        }),
                          await he(),
                          setModal({ ...modal, add: [] }),
                          setToast(picked.length + "명을 참여자로 추가했습니다."));
                      })
                    }
                  >
                    {"선택한 사람 추가"}
                  </Button>
                </div>
              )}
            </Modal>
          );
        })()}
      {modal?.type === "event" && (
        <Modal
          title={modal.event.kind}
          close={() => setModal(null)}
          footer={
            <Button
              primary={!0}
              onClick={() =>
                Ca(() => ff(modal.event.meeting_id, modal.event.evidence))
              }
            >
              {"근거 회의록 보기"}
            </Button>
          }
        >
          <span className="muted">{et(modal.event.project_id)}</span>
          <h3>{modal.event.title}</h3>
          <p>
            {day(modal.event.start)}
            {modal.event.start !== modal.event.end
              ? " – " + day(modal.event.end)
              : ""}
          </p>
        </Modal>
      )}
      {modal?.type === "source" && (
        <Modal
          title="회의록 본문 수정"
          close={() => setModal(null)}
          footer={
            <Button
              primary={!0}
              disabled={working || modal.source.length < 10}
              onClick={() =>
                Ca(async () => {
                  (await api(
                    "/v3/meetings/" + meeting.id + "/source",
                    "PATCH",
                    {
                      version: meeting.version,
                      title: modal.title,
                      date: modal.date,
                      source: modal.source,
                    },
                  ),
                    setModal(null),
                    setMeeting(await api("/meetings/" + meeting.id)),
                    await he(),
                    setToast("새 버전으로 저장하고 다시 분석합니다."));
                })
              }
            >
              {"저장하고 다시 분석"}
            </Button>
          }
        >
          <label>
            {"회의 제목"}
            <input
              value={modal.title}
              onChange={(c) =>
                setModal({
                  ...modal,
                  title: c.target.value,
                })
              }
            />
          </label>
          <label>
            {"회의일"}
            <input
              type="date"
              value={modal.date}
              onChange={(c) =>
                setModal({
                  ...modal,
                  date: c.target.value,
                })
              }
            />
          </label>
          <label>
            {"본문"}
            <textarea
              className="body-editor"
              value={modal.source}
              onChange={(c) =>
                setModal({
                  ...modal,
                  source: c.target.value,
                })
              }
            />
          </label>
        </Modal>
      )}
      {modal?.type === "trash" && (
        <Modal
          title="회의록을 휴지통으로 이동할까요?"
          close={() => setModal(null)}
          footer={
            <React.Fragment>
              <Button onClick={() => setModal(null)}>{"취소"}</Button>
              <Button
                primary={!0}
                disabled={working}
                onClick={() =>
                  Ca(async () => {
                    (await api("/v3/meetings/" + meeting.id, "DELETE"),
                      setModal(null),
                      Be("minutes"),
                      await he(),
                      setToast("회의록을 휴지통으로 이동했습니다."));
                  })
                }
              >
                {"휴지통으로 이동"}
              </Button>
            </React.Fragment>
          }
        >
          <p>{meeting.title}</p>
          <p className="muted">
            {"이 회의록에서 나온 일정과 변경 기록도 목록에서 제외됩니다."}
          </p>
        </Modal>
      )}
      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button aria-label="메시지 닫기" onClick={() => setToast("")}>
            <X size={17} />
          </button>
        </div>
      )}
    </React.Fragment>
  ) : (
    <div className="login">
      <div>
        <span className="brand">
          <img src={logo} alt="PNT" />
        </span>
        <h1>
          {"회의에서 나온 정보,"}
          <br />
          {"프로젝트의 흐름으로."}
        </h1>
        <p>{"회의록 · AI 정리 · 변경이력"}</p>
      </div>
      <section>
        <h2>{"업무 공간에 들어가기"}</h2>
        {authMode === "supabase" ? (
          <form
            className="login-form"
            onSubmit={(ev) => {
              (ev.preventDefault(),
                Ca(async () => {
                  let r = await api("/auth/login", "POST", {
                    user_id: loginId.trim(),
                    password: loginPw,
                  });
                  (setLoginPw(""),
                    setToast(""),
                    r.user.role === "admin" ? setAdminUser(r.user) : await he());
                }));
            }}
          >
            <p>{"아이디와 비밀번호를 입력하세요."}</p>
            <label>
              {"아이디"}
              <input
                autoFocus={!0}
                autoComplete="username"
                value={loginId}
                onChange={(c) => setLoginId(c.target.value)}
              />
            </label>
            <label>
              {"비밀번호"}
              <input
                type="password"
                autoComplete="current-password"
                value={loginPw}
                onChange={(c) => setLoginPw(c.target.value)}
              />
            </label>
            <button
              type="submit"
              className="primary"
              disabled={working || !loginId.trim() || !loginPw}
            >
              {"로그인"}
              <ArrowRight size={18} />
            </button>
          </form>
        ) : (
          <p>{"사용자를 선택해 시작하세요."}</p>
        )}
        {authMode !== "supabase" && accounts.map((c) => (
          <button
            disabled={working}
            key={c.id}
            onClick={() =>
              Ca(async () => {
                (await api("/demo-login", "POST", {
                  username: c.id,
                }),
                  await he());
              })
            }
          >
            <span>
              {c.name}
              <small>{c.position}</small>
            </span>
            <ArrowRight size={18} />
          </button>
        ))}
        {toast && <p role="alert">{toast}</p>}
      </section>
    </div>
  );
}
export { api, Button, Modal, Empty, App };
const approval = createApproval(React, api, Button, Modal, logo);
export { approval };
