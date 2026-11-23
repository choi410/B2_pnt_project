// 관리자 설정 화면: 사용자 관리(역할·사용 중지) + 프로젝트 PM 교체.
// 업무 데이터(회의록·변경이력)는 다루지 않는다. 실제 권한 검사는 서버(/api/admin)가 한다.
import React from "react";
import { LogOut, RefreshCw, Users, FolderKanban } from "lucide-react";

const fmt = (value) => (value ? new Date(value).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" }) : "-");

export function AdminConsole({ api, user, logo, onLogout }) {
  const [tab, setTab] = React.useState("users");
  const [users, setUsers] = React.useState(null);
  const [projects, setProjects] = React.useState(null);
  const [candidates, setCandidates] = React.useState([]);
  const [choice, setChoice] = React.useState({});
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const load = React.useCallback(async () => {
    const [u, p] = await Promise.all([api("/admin/users"), api("/admin/projects")]);
    setUsers(u.users);
    setProjects(p.projects);
    setCandidates(p.pm_candidates);
  }, [api]);

  React.useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, [load]);

  const run = async (work, done) => {
    setBusy(true);
    setMessage("");
    try {
      await work();
      await load();
      if (done) setMessage(done);
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const changeUser = (u, change, done) =>
    run(() => api(`/admin/users/${u.id}`, "PATCH", change), done);

  const changePm = (p) => {
    const pm = choice[p.id];
    if (!pm || pm === p.pm) return;
    const name = candidates.find((c) => c.id === pm)?.name || pm;
    run(
      () => api(`/admin/projects/${encodeURIComponent(p.id)}/pm`, "PATCH", { pm_id: pm, version: p.version }),
      `${p.name}의 PM을 ${name}(으)로 바꿨습니다.`,
    ).then(() => setChoice((c) => ({ ...c, [p.id]: "" })));
  };

  return (
    <div className="admin-console">
      <header className="admin-head">
        <span className="brand">
          <img src={logo} alt="PNT" />
        </span>
        <div>
          <h1>{"관리자 설정"}</h1>
          <p className="muted">
            {user.name}
            {" · 관리자"}
          </p>
        </div>
        <button type="button" className="admin-logout" disabled={busy} onClick={onLogout}>
          <LogOut size={17} />
          {"로그아웃"}
        </button>
      </header>

      <nav className="tabs" aria-label="관리자 메뉴">
        <button type="button" className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
          <Users size={16} /> {"사용자 관리"}
        </button>
        <button type="button" className={tab === "projects" ? "active" : ""} onClick={() => setTab("projects")}>
          <FolderKanban size={16} /> {"프로젝트 PM"}
        </button>
        <button type="button" className="admin-refresh" disabled={busy} onClick={() => run(async () => {})} aria-label="새로 고침">
          <RefreshCw size={16} />
        </button>
      </nav>

      {message && (
        <p className="admin-message" role="status">
          {message}
        </p>
      )}

      {tab === "users" && (
        <section className="admin-panel">
          <p className="muted">
            {"역할을 바꾸거나 사용을 중지하면 그 사람은 바로 로그아웃되고, 다시 로그인할 때 새 권한이 적용됩니다. "}
            {"계정 추가·비밀번호 변경·관리자 지정은 Supabase 대시보드에서 합니다."}
          </p>
          {!users ? (
            <p className="muted">{"불러오는 중…"}</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{"이름"}</th>
                  <th>{"아이디"}</th>
                  <th>{"사번 · 부서"}</th>
                  <th>{"역할"}</th>
                  <th>{"상태"}</th>
                  <th>{"맡은 PM"}</th>
                  <th>{"최근 로그인"}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const locked = u.is_me || u.role === "admin";
                  const active = u.account_status === "active";
                  return (
                    <tr key={u.id} className={active ? "" : "inactive"}>
                      <td>
                        {u.name}
                        {u.is_me && <small>{" (나)"}</small>}
                      </td>
                      <td>{u.app_user_id || "-"}</td>
                      <td>
                        {u.emp_no || "-"}
                        <small>{u.department || ""}</small>
                      </td>
                      <td>
                        {locked ? (
                          u.role_label
                        ) : (
                          <select
                            aria-label={`${u.name} 역할`}
                            value={u.role}
                            disabled={busy}
                            onChange={(e) =>
                              changeUser(u, { role: e.target.value }, `${u.name}님의 역할을 ${e.target.value === "pm" ? "PM" : "팀원"}(으)로 바꿨습니다.`)
                            }
                          >
                            <option value="pm">{"PM"}</option>
                            <option value="member">{"팀원"}</option>
                          </select>
                        )}
                      </td>
                      <td>
                        {locked ? (
                          active ? "사용 중" : "사용 중지"
                        ) : (
                          <button
                            type="button"
                            className={active ? "admin-danger" : "primary"}
                            disabled={busy}
                            onClick={() =>
                              changeUser(
                                u,
                                { account_status: active ? "inactive" : "active" },
                                active ? `${u.name}님의 계정 사용을 중지했습니다.` : `${u.name}님의 계정을 다시 사용합니다.`,
                              )
                            }
                          >
                            {active ? "사용 중지" : "다시 사용"}
                          </button>
                        )}
                      </td>
                      <td>{u.pm_projects ? `${u.pm_projects}개` : "-"}</td>
                      <td>{fmt(u.last_sign_in_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}

      {tab === "projects" && (
        <section className="admin-panel">
          <p className="muted">
            {"프로젝트 PM만 바꿀 수 있습니다. 새 PM은 참여자에 자동으로 추가되며, 회의록·변경이력 내용은 이 화면에서 보이지 않습니다."}
          </p>
          {!projects ? (
            <p className="muted">{"불러오는 중…"}</p>
          ) : projects.length === 0 ? (
            <p className="muted">{"프로젝트가 없습니다."}</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{"프로젝트"}</th>
                  <th>{"현재 PM"}</th>
                  <th>{"참여자"}</th>
                  <th>{"PM 바꾸기"}</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {p.name}
                      <small>{p.id}</small>
                    </td>
                    <td>{p.pm_name || "-"}</td>
                    <td>{`${p.member_count}명`}</td>
                    <td className="admin-pm">
                      <select
                        aria-label={`${p.name} 새 PM`}
                        value={choice[p.id] || ""}
                        disabled={busy}
                        onChange={(e) => setChoice((c) => ({ ...c, [p.id]: e.target.value }))}
                      >
                        <option value="">{"PM 계정 선택"}</option>
                        {candidates
                          .filter((c) => c.id !== p.pm)
                          .map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                      <button type="button" className="primary" disabled={busy || !choice[p.id]} onClick={() => changePm(p)}>
                        {"저장"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
