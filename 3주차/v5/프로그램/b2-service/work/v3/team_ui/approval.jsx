// 팀원(배근우)의 고객 합의 화면.
export default (function createApproval(React, api, Button, Modal, logo) {
  const { useState, useEffect } = React;
  const labels = {
    sent: "회신 대기",
    approved: "합의",
    rejected: "반려",
    expired: "합의 링크 만료",
    canceled: "요청 취소",
  };
  const md = (s) => (s ? s.slice(5, 10).replace("-", ".") : "");
  const itemText = (x) => (x.before ? x.before + " → " : "") + x.after;
  const when = (s) => (s ? s.slice(0, 16).replace("T", " ") : "");
  // The mail link is /#/approval/<token>; it opens without the workspace or a login.
  const approvalToken = () => {
    const m = window.location.hash.match(/^#\/approval\/([\w-]+)$/);
    return m ? m[1] : "";
  };
  function ApprovalBadge({ approval }) {
    if (!approval || !labels[approval.status]) return null;
    const n = (approval.item_ids || []).length,
      done = approval.status === "approved" || approval.status === "rejected";
    return (
      <span
        className={"status approval-" + approval.status}
        title={approval.email}
      >
        {labels[approval.status]}
        {done && approval.responded_at ? " " + md(approval.responded_at) : ""}
        {n && approval.status !== "expired" && approval.status !== "canceled"
          ? " · 항목 " + n + "건"
          : ""}
      </span>
    );
  }
  function ApprovalLine({ approval, applyCount, onApply, meetingId }) {
    const [open, setOpen] = useState(false),
      [showH, setShowH] = useState(false),
      [hist, setHist] = useState(null);
    useEffect(() => {
      if (showH && meetingId)
        api("/v3/meetings/" + meetingId + "/approval-requests")
          .then(setHist)
          .catch(() => setHist([]));
    }, [
      showH,
      meetingId,
      approval?.id,
      approval?.status,
      approval?.applied_at,
    ]);
    if (!approval || !labels[approval.status]) return null;
    const items = approval.items || [];
    return (
      <div className="approval-line">
        <div className="approval-row">
          <ApprovalBadge approval={approval} />
          <span>
            {approval.email}
            {" · "}
            {when(approval.sent_at)}
            {" 발송"}
            {approval.responded_at
              ? " · " + when(approval.responded_at) + " 응답"
              : ""}
            {approval.outdated ? " · 이전 본문 기준" : ""}
          </span>
          {items.length > 0 && (
            <button
              type="button"
              className="approval-toggle"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {(open ? "▾ " : "▸ ") + "합의 요청 항목 " + items.length + "건"}
            </button>
          )}
          <button
            type="button"
            className="approval-toggle"
            aria-expanded={showH}
            onClick={() => setShowH(!showH)}
          >
            {(showH ? "▾ " : "▸ ") + "합의 진행 이력"}
          </button>
          {applyCount > 0 && (
            <button
              type="button"
              className="button primary approval-apply"
              title="합의된 항목 중 아직 요청·보류인 것을 합의로 바꿉니다."
              onClick={onApply}
            >
              {"합의로 반영 (" + applyCount + "건)"}
            </button>
          )}
        </div>
        {approval.comment && (
          <span className="approval-comment">
            {"의견: "}
            {approval.comment}
          </span>
        )}
        {open && (
          <ul className="approval-items">
            {items.map((x) => (
              <li key={x.id}>
                <b>{x.title}</b>
                <span>{itemText(x)}</span>
              </li>
            ))}
          </ul>
        )}
        {showH && <ApprovalFlow hist={hist} />}
      </div>
    );
  }
  function ApprovalFlow({ hist }) {
    if (!hist) return <p className="muted ap-flow-empty">{"불러오는 중…"}</p>;
    if (!hist.length)
      return <p className="muted ap-flow-empty">{"기록이 없습니다."}</p>;
    const asc = hist.slice().reverse(),
      steps = [];
    asc.forEach((h, i) => {
      steps.push({
        k: h.id + "s",
        cls: "send",
        label: "발송",
        when: h.sent_at,
        text: h.email + (h.item_count ? " · 항목 " + h.item_count + "건" : ""),
      });
      if (h.status === "approved" || h.status === "rejected")
        steps.push({
          k: h.id + "r",
          cls: h.status,
          label: h.status === "approved" ? "합의" : "반려",
          when: h.responded_at,
          text: h.comment ? "의견: " + h.comment : "",
        });
      else if (h.status === "expired")
        steps.push({
          k: h.id + "e",
          cls: "muted",
          label: "링크 만료",
          when: h.expires_at,
          text: "회신 없이 기간이 지났습니다.",
        });
      else if (h.status === "canceled")
        steps.push({
          k: h.id + "c",
          cls: "muted",
          label: "다시 보냄",
          when: asc[i + 1]?.sent_at,
          text: "이전 링크는 쓸 수 없게 됐습니다.",
        });
      else if (h.status === "sent")
        steps.push({
          k: h.id + "w",
          cls: "wait",
          label: "회신 대기",
          when: null,
          text: when(h.expires_at) + "까지 유효",
        });
      if (h.applied_at)
        steps.push({
          k: h.id + "a",
          cls: "applied",
          label: "PM 합의 반영",
          when: h.applied_at,
          text: "요청·보류 항목을 합의로 바꿨습니다.",
        });
    });
    return (
      <ol className="ap-flow">
        {steps.map((x) => (
          <li key={x.k} className={"ap-flow-" + x.cls}>
            <i aria-hidden="true" />
            <time>{x.when ? when(x.when).slice(5).replace("-", ".") : ""}</time>
            <b>{x.label}</b>
            {x.text && <span>{x.text}</span>}
          </li>
        ))}
      </ol>
    );
  }
  function SendApprovalDialog({
    meeting,
    approval,
    close,
    onSent,
    items = [],
    blocked = 0,
  }) {
    const [form, setForm] = useState({
        email: approval?.email || "",
        name: "",
        message: "",
      }),
      [history, setHistory] = useState([]),
      [busy, setBusy] = useState(false),
      [error, setError] = useState(""),
      [sent, setSent] = useState(null);
    useEffect(() => {
      api("/v3/meetings/" + meeting.id + "/approval-requests")
        .then(setHistory)
        .catch(() => setHistory([]));
    }, [meeting.id]);
    const waiting = history.some((h) => h.status === "sent");
    async function submit() {
      setBusy(true);
      setError("");
      try {
        const result = await api(
          "/v3/meetings/" + meeting.id + "/approval-requests",
          "POST",
          form,
        );
        setSent(result);
        onSent(result);
      } catch (e) {
        setError(e.message);
      } finally {
        setBusy(false);
      }
    }
    if (sent)
      return (
        <Modal
          title="합의 요청을 보냈습니다"
          close={close}
          footer={
            <Button primary={true} onClick={close}>
              {"닫기"}
            </Button>
          }
        >
          {sent.mode === "smtp" ? (
            <p>
              {sent.email}
              {" 주소로 합의 요청 메일을 보냈습니다."}
            </p>
          ) : (
            <React.Fragment>
              <p>
                {
                  "테스트 모드(MAIL_MODE=console)라 메일은 보내지 않고 서버 실행 창에 내용을 출력했습니다."
                }
              </p>
              <p className="approval-link">
                {"합의 링크: "}
                <a href={sent.link} target="_blank" rel="noreferrer">
                  {sent.link}
                </a>
              </p>
            </React.Fragment>
          )}
          <p className="muted">
            {"링크는 "}
            {when(sent.expires_at)}
            {"까지 한 번만 사용할 수 있습니다."}
          </p>
        </Modal>
      );
    return (
      <Modal
        title="합의 메일 보내기"
        close={() => {
          if (!busy) close();
        }}
        footer={
          <React.Fragment>
            <Button onClick={close} disabled={busy}>
              {"취소"}
            </Button>
            <Button
              primary={true}
              disabled={busy || !form.email.trim() || blocked > 0}
              onClick={submit}
            >
              {busy ? "보내는 중…" : "메일 보내기"}
            </Button>
          </React.Fragment>
        }
      >
        <h3>{meeting.title}</h3>
        <label>
          {"받는 사람 이메일"}
          <input
            autoFocus={true}
            type="email"
            placeholder="customer@example.com"
            value={form.email}
            onChange={(e) =>
              setForm({
                ...form,
                email: e.target.value,
              })
            }
          />
        </label>
        <label>
          {"받는 사람 이름 (선택)"}
          <input
            maxLength={50}
            placeholder="예: 홍길동 책임"
            value={form.name}
            onChange={(e) =>
              setForm({
                ...form,
                name: e.target.value,
              })
            }
          />
        </label>
        <label>
          {"전달 메시지 (선택)"}
          <textarea
            maxLength={1000}
            rows={3}
            placeholder="예: 11/12 회의 내용입니다. 확인 후 합의 부탁드립니다."
            value={form.message}
            onChange={(e) =>
              setForm({
                ...form,
                message: e.target.value,
              })
            }
          />
        </label>
        {blocked > 0 ? (
          <p className="error-box">
            {"검수가 끝나지 않은 항목이 "}
            {blocked}
            {"건 있습니다. 검수를 마쳐 회의록을 등록한 뒤 보낼 수 있습니다."}
          </p>
        ) : (
          <div className="approval-preview">
            <b>{"메일에 담길 합의 요청 항목 " + items.length + "건"}</b>
            {items.length ? (
              <ul className="approval-items">
                {items.map((x) => (
                  <li key={x.id}>
                    <b>{x.title}</b>
                    <span>{itemText(x)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                {"확인된 요구·변경 항목이 없습니다. 회의록 본문만 보냅니다."}
              </p>
            )}
          </div>
        )}
        <p className="muted">
          {
            "받는 분은 메일의 링크에서 회의록 본문과 위 항목을 확인하고 합의 또는 반려합니다."
          }
        </p>
        {waiting && (
          <p className="error-box">
            {
              "응답을 기다리는 요청이 있습니다. 다시 보내면 이전 메일의 링크는 쓸 수 없게 됩니다."
            }
          </p>
        )}
        {error && (
          <p role="alert" className="error-box">
            {error}
          </p>
        )}
        {history.length > 0 && (
          <div className="approval-history">
            <h4>{"이전 요청"}</h4>
            {history.map((h) => (
              <p key={h.id}>
                <ApprovalBadge approval={h} />
                <span>
                  {h.email}
                  {" · "}
                  {when(h.sent_at)}
                </span>
                {h.comment && (
                  <small>
                    {"회신 의견: "}
                    {h.comment}
                  </small>
                )}
              </p>
            ))}
          </div>
        )}
      </Modal>
    );
  }
  // Meeting minutes text laid out like the company minutes form: title, info table, sections.
  const SECTIONS = [
    "회의 안건",
    "논의 내용",
    "결정 사항",
    "추가 확인 사항",
    "후속 조치",
    "참고 사항",
    "기타 사항",
    "첨부",
  ];
  const cells = (t) => t.split(/\s*\|\s*/).map((x) => x.trim());
  const isHeadRow = (row) =>
    row.some((x) =>
      /^(조치 ?내용|내용|담당|담당자|기한|일정|비고|항목)$/.test(x),
    );
  function minutesLayout(lines) {
    const doc = {
      title: "",
      subtitle: "",
      info: [],
      sections: [],
      intro: [],
    };
    let section = null;
    for (const raw of lines || []) {
      const text = (raw || "").trim();
      if (!text) continue;
      const heading = text.replace(/^[■□▶●◆#\d.\s]+(?=\D)/, "").trim();
      if (SECTIONS.includes(heading)) {
        section = {
          title: heading,
          items: [],
        };
        doc.sections.push(section);
        continue;
      }
      if (!section) {
        if (!doc.title && !doc.info.length && /^회의록$/.test(text)) {
          doc.title = text;
          continue;
        }
        if (/^MEETING MINUTES/i.test(text)) {
          doc.subtitle = text.replace(/\s*\|\s*/g, "  |  ");
          continue;
        }
        if (text.includes("|")) {
          const c = cells(text),
            pairs = [];
          for (let i = 0; i < c.length; i += 2)
            pairs.push([c[i], c[i + 1] ?? ""]);
          doc.info.push(pairs);
          continue;
        }
        doc.intro.push(text);
        continue;
      }
      const last = section.items[section.items.length - 1];
      if (text.includes("|")) {
        const row = cells(text);
        if (last?.type === "table") last.rows.push(row);
        else
          section.items.push({
            type: "table",
            head: isHeadRow(row) ? row : null,
            rows: isHeadRow(row) ? [] : [row],
          });
        continue;
      }
      section.items.push({
        type: "p",
        text,
        strong: section.title === "논의 내용" && /^\d+\.\s/.test(text),
      });
    }
    return doc;
  }
  function MinutesDocument({ lines }) {
    const doc = minutesLayout(lines),
      wide = Math.max(1, ...doc.info.map((r) => r.length));
    return (
      <article className="minutes-doc">
        <header>
          <h1>{doc.title || "회의록"}</h1>
          <p className="minutes-sub">{doc.subtitle || "MEETING MINUTES"}</p>
        </header>
        {doc.info.length > 0 && (
          <table className="minutes-info">
            <tbody>
              {doc.info.map((pairs, i) => (
                <tr key={i}>
                  {pairs.map(([k, v], j) => (
                    <React.Fragment key={j}>
                      <th>{k}</th>
                      <td
                        colSpan={
                          j === pairs.length - 1
                            ? (wide - pairs.length) * 2 + 1
                            : 1
                        }
                      >
                        {v}
                      </td>
                    </React.Fragment>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {doc.intro.map((t, i) => (
          <p key={"i" + i}>{t}</p>
        ))}
        {doc.sections.map((sec, i) => (
          <section key={i}>
            <h2>{sec.title}</h2>
            {sec.items.map((item, j) =>
              item.type === "table" ? (
                <table key={j} className="minutes-table">
                  {item.head && (
                    <thead>
                      <tr>
                        {item.head.map((x, k) => (
                          <th key={k}>{x}</th>
                        ))}
                      </tr>
                    </thead>
                  )}
                  <tbody>
                    {item.rows.map((row, k) => (
                      <tr key={k}>
                        {row.map((x, l) => (
                          <td key={l}>{x}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p key={j} className={item.strong ? "minutes-strong" : ""}>
                  {item.text}
                </p>
              ),
            )}
          </section>
        ))}
      </article>
    );
  }
  const closedText = {
    expired: "링크의 유효 기간이 지났습니다. 담당자에게 다시 요청해 주세요.",
    canceled:
      "더 이상 사용할 수 없는 링크입니다. 새로 받은 메일의 링크를 사용해 주세요.",
  };
  function ApprovalPage({ token }) {
    const [view, setView] = useState(null),
      [loadError, setLoadError] = useState(""),
      [comment, setComment] = useState(""),
      [busy, setBusy] = useState(false),
      [error, setError] = useState("");
    const load = () =>
      api("/v3/approvals/" + token)
        .then(setView)
        .catch((e) => setLoadError(e.message));
    useEffect(() => {
      load();
    }, [token]);
    async function respond(decision) {
      if (
        decision === "rejected" &&
        !comment.trim() &&
        !window.confirm(
          "의견 없이 반려할까요? 반려 사유를 적어 주시면 담당자가 확인하기 쉽습니다.",
        )
      )
        return;
      setBusy(true);
      setError("");
      try {
        await api("/v3/approvals/" + token, "POST", {
          decision,
          comment,
        });
      } catch (e) {
        setError(e.message);
      } finally {
        // Reload either way: another click or an expiry may already have settled it.
        await load();
        setBusy(false);
      }
    }
    const head = (
      <span className="brand">
        <img src={logo} alt="PNT" />
      </span>
    );
    if (loadError)
      return (
        <div className="approval-page">
          <section className="approval-card">
            {head}
            <h1>{"회의록 합의 요청"}</h1>
            <p role="alert" className="error-box">
              {loadError}
            </p>
          </section>
        </div>
      );
    if (!view)
      return (
        <div className="approval-page">
          <section className="approval-card">
            {head}
            <p className="muted">{"불러오는 중…"}</p>
          </section>
        </div>
      );
    const done = view.status === "approved" || view.status === "rejected";
    return (
      <div className="approval-page">
        <section className="approval-card">
          {head}
          <h1>{"회의록 합의 요청"}</h1>
          <dl>
            <dt>{"프로젝트"}</dt>
            <dd>{view.project_name}</dd>
            <dt>{"회의록"}</dt>
            <dd>
              {view.title}
              {view.date ? " (" + view.date + ")" : ""}
            </dd>
            {view.requested_by_name && (
              <React.Fragment>
                <dt>{"요청자"}</dt>
                <dd>
                  {view.requested_by_name}
                  {" · "}
                  {when(view.sent_at)}
                </dd>
              </React.Fragment>
            )}
          </dl>
          {view.message && <p className="approval-message">{view.message}</p>}
          {(view.items || []).length > 0 && (
            <div className="approval-preview">
              <b>{"합의 요청 항목 " + view.items.length + "건"}</b>
              <ul className="approval-items">
                {view.items.map((x) => (
                  <li key={x.id}>
                    <b>{x.title}</b>
                    <span>{itemText(x)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {closedText[view.status] && (
            <p className="error-box">{closedText[view.status]}</p>
          )}
          {done && (
            <div className={"approval-result " + view.status}>
              {view.status === "approved" ? (
                <b aria-hidden="true">{"✓"}</b>
              ) : (
                <b aria-hidden="true">{"!"}</b>
              )}
              <div>
                <b>
                  {view.status === "approved"
                    ? "합의 처리되었습니다."
                    : "반려 처리되었습니다."}
                </b>{" "}
                <small>{when(view.responded_at)}</small>
                {view.comment && (
                  <p>
                    {"남기신 의견: "}
                    {view.comment}
                  </p>
                )}
                <p className="muted">{"이 창은 닫으셔도 됩니다."}</p>
              </div>
            </div>
          )}
          {view.status === "sent" && (
            <div className="approval-form">
              <p className="muted">
                {
                  "위 항목과 아래 회의록 내용을 확인한 뒤 합의 또는 반려를 선택해 주세요. "
                }
                {when(view.expires_at)}
                {"까지 한 번만 처리할 수 있습니다."}
              </p>
              <label>
                {"의견 (선택, 반려 시 사유를 적어 주세요)"}
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </label>
              {error && (
                <p role="alert" className="error-box">
                  {error}
                </p>
              )}
              <div className="actions">
                <Button
                  primary={true}
                  disabled={busy}
                  onClick={() => respond("approved")}
                >
                  {"합의"}
                </Button>
                <Button
                  className="reject"
                  disabled={busy}
                  onClick={() => respond("rejected")}
                >
                  {"반려"}
                </Button>
              </div>
            </div>
          )}
        </section>
        {view.pages > 0 ? (
          <div className="pdf-pages approval-pages">
            {Array.from(
              {
                length: view.pages,
              },
              (_, i) => (
                <img
                  key={i}
                  src={"/api/v3/approvals/" + token + "/pages/" + (i + 1)}
                  alt={"회의록 " + (i + 1) + "페이지"}
                />
              ),
            )}
          </div>
        ) : (
          view.lines && <MinutesDocument lines={view.lines} />
        )}
      </div>
    );
  }
  return {
    ApprovalBadge,
    ApprovalLine,
    SendApprovalDialog,
    ApprovalPage,
    approvalToken,
    MinutesDocument,
  };
});
