"use strict";
// 팀원(배근우) approval.jsx 를 번들에 붙이기 위한 변환본. React·api·Button·Modal·logo 는 본 앱의 것을 받아 쓴다.
window.__pntApproval = function (React, api, Button, Modal, logo) {
    const { useState, useEffect } = React;
    const labels = { sent: '고객 회신 대기', approved: '고객 합의', rejected: '고객 반려', expired: '합의 링크 만료', canceled: '요청 취소' };
    const md = s => s ? s.slice(5, 10).replace('-', '.') : '';
    const itemText = x => (x.before ? x.before + ' → ' : '') + x.after;
    const when = s => s ? s.slice(0, 16).replace('T', ' ') : '';
    // The mail link is /#/approval/<token>; it opens without the workspace or a login.
    const approvalToken = () => { const m = window.location.hash.match(/^#\/approval\/([\w-]+)$/); return m ? m[1] : ''; };
    function ApprovalBadge({ approval }) {
        if (!approval || !labels[approval.status])
            return null;
        const n = (approval.item_ids || []).length, done = approval.status === 'approved' || approval.status === 'rejected';
        return React.createElement("span", { className: 'status approval-' + approval.status, title: approval.email },
            labels[approval.status],
            done && approval.responded_at ? ' ' + md(approval.responded_at) : '',
            n && approval.status !== 'expired' && approval.status !== 'canceled' ? ' · 항목 ' + n + '건' : '');
    }
    function ApprovalLine({ approval, applyCount, onApply, meetingId }) {
        const [open, setOpen] = useState(false), [showH, setShowH] = useState(false), [hist, setHist] = useState(null);
        useEffect(() => { if (showH && meetingId)
            api('/v3/meetings/' + meetingId + '/approval-requests').then(setHist).catch(() => setHist([])); }, [showH, meetingId, approval?.id, approval?.status, approval?.applied_at]);
        if (!approval || !labels[approval.status])
            return null;
        const items = approval.items || [];
        return React.createElement("div", { className: "approval-line" },
            React.createElement("div", { className: "approval-row" },
                React.createElement(ApprovalBadge, { approval: approval }),
                React.createElement("span", null,
                    approval.email,
                    " \u00B7 ",
                    when(approval.sent_at),
                    " \uBC1C\uC1A1",
                    approval.responded_at ? ' · ' + when(approval.responded_at) + ' 응답' : '',
                    approval.outdated ? ' · 이전 본문 기준' : ''),
                items.length > 0 && React.createElement("button", { type: "button", className: "approval-toggle", "aria-expanded": open, onClick: () => setOpen(!open) }, (open ? '▾ ' : '▸ ') + '합의 요청 항목 ' + items.length + '건'),
                React.createElement("button", { type: "button", className: "approval-toggle", "aria-expanded": showH, onClick: () => setShowH(!showH) }, (showH ? '▾ ' : '▸ ') + '합의 진행 이력'),
                applyCount > 0 && React.createElement("button", { type: "button", className: "button primary approval-apply", title: "\uACE0\uAC1D\uC774 \uD569\uC758\uD55C \uD56D\uBAA9 \uC911 \uC544\uC9C1 \uC694\uCCAD\u00B7\uBCF4\uB958\uC778 \uAC83\uC744 \uD569\uC758\uB85C \uBC14\uAFC9\uB2C8\uB2E4.", onClick: onApply }, '합의로 반영 (' + applyCount + '건)')),
            approval.comment && React.createElement("span", { className: "approval-comment" },
                "\uACE0\uAC1D \uC758\uACAC: ",
                approval.comment),
            open && React.createElement("ul", { className: "approval-items" }, items.map(x => React.createElement("li", { key: x.id },
                React.createElement("b", null, x.title),
                React.createElement("span", null, itemText(x))))),
            showH && React.createElement(ApprovalFlow, { hist: hist }));
    }
    function ApprovalFlow({ hist }) {
        if (!hist)
            return React.createElement("p", { className: "muted ap-flow-empty" }, "\uBD88\uB7EC\uC624\uB294 \uC911\u2026");
        if (!hist.length)
            return React.createElement("p", { className: "muted ap-flow-empty" }, "\uAE30\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.");
        const asc = hist.slice().reverse(), steps = [];
        asc.forEach((h, i) => {
            steps.push({ k: h.id + 's', cls: 'send', label: '발송', when: h.sent_at, text: h.email + (h.item_count ? ' · 항목 ' + h.item_count + '건' : '') });
            if (h.status === 'approved' || h.status === 'rejected')
                steps.push({ k: h.id + 'r', cls: h.status, label: h.status === 'approved' ? '고객 합의' : '고객 반려', when: h.responded_at, text: h.comment ? '의견: ' + h.comment : '' });
            else if (h.status === 'expired')
                steps.push({ k: h.id + 'e', cls: 'muted', label: '링크 만료', when: h.expires_at, text: '회신 없이 기간이 지났습니다.' });
            else if (h.status === 'canceled')
                steps.push({ k: h.id + 'c', cls: 'muted', label: '다시 보냄', when: asc[i + 1]?.sent_at, text: '이전 링크는 쓸 수 없게 됐습니다.' });
            else if (h.status === 'sent')
                steps.push({ k: h.id + 'w', cls: 'wait', label: '회신 대기', when: null, text: when(h.expires_at) + '까지 유효' });
            if (h.applied_at)
                steps.push({ k: h.id + 'a', cls: 'applied', label: 'PM 합의 반영', when: h.applied_at, text: '요청·보류 항목을 합의로 바꿨습니다.' });
        });
        return React.createElement("ol", { className: "ap-flow" }, steps.map(x => React.createElement("li", { key: x.k, className: 'ap-flow-' + x.cls },
            React.createElement("i", { "aria-hidden": "true" }),
            React.createElement("time", null, x.when ? when(x.when).slice(5).replace('-', '.') : ''),
            React.createElement("b", null, x.label),
            x.text && React.createElement("span", null, x.text))));
    }
    function SendApprovalDialog({ meeting, approval, close, onSent, items = [], blocked = 0 }) {
        const [form, setForm] = useState({ email: approval?.email || '', name: '', message: '' }), [history, setHistory] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState(''), [sent, setSent] = useState(null);
        useEffect(() => { api('/v3/meetings/' + meeting.id + '/approval-requests').then(setHistory).catch(() => setHistory([])); }, [meeting.id]);
        const waiting = history.some(h => h.status === 'sent');
        async function submit() {
            setBusy(true);
            setError('');
            try {
                const result = await api('/v3/meetings/' + meeting.id + '/approval-requests', 'POST', form);
                setSent(result);
                onSent(result);
            }
            catch (e) {
                setError(e.message);
            }
            finally {
                setBusy(false);
            }
        }
        if (sent)
            return React.createElement(Modal, { title: "\uD569\uC758 \uC694\uCCAD\uC744 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4", close: close, footer: React.createElement(Button, { primary: true, onClick: close }, "\uB2EB\uAE30") },
                sent.mode === 'smtp' ? React.createElement("p", null,
                    sent.email,
                    " \uC8FC\uC18C\uB85C \uD569\uC758 \uC694\uCCAD \uBA54\uC77C\uC744 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4.") : React.createElement(React.Fragment, null,
                    React.createElement("p", null, "\uD14C\uC2A4\uD2B8 \uBAA8\uB4DC(MAIL_MODE=console)\uB77C \uBA54\uC77C\uC740 \uBCF4\uB0B4\uC9C0 \uC54A\uACE0 \uC11C\uBC84 \uC2E4\uD589 \uCC3D\uC5D0 \uB0B4\uC6A9\uC744 \uCD9C\uB825\uD588\uC2B5\uB2C8\uB2E4."),
                    React.createElement("p", { className: "approval-link" },
                        "\uD569\uC758 \uB9C1\uD06C: ",
                        React.createElement("a", { href: sent.link, target: "_blank", rel: "noreferrer" }, sent.link))),
                React.createElement("p", { className: "muted" },
                    "\uB9C1\uD06C\uB294 ",
                    when(sent.expires_at),
                    "\uAE4C\uC9C0 \uD55C \uBC88\uB9CC \uC0AC\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4."));
        return React.createElement(Modal, { title: "\uD569\uC758 \uBA54\uC77C \uBCF4\uB0B4\uAE30", close: () => { if (!busy)
                close(); }, footer: React.createElement(React.Fragment, null,
                React.createElement(Button, { onClick: close, disabled: busy }, "\uCDE8\uC18C"),
                React.createElement(Button, { primary: true, disabled: busy || !form.email.trim() || blocked > 0, onClick: submit }, busy ? '보내는 중…' : '메일 보내기')) },
            React.createElement("h3", null, meeting.title),
            React.createElement("label", null,
                "\uBC1B\uB294 \uC0AC\uB78C \uC774\uBA54\uC77C",
                React.createElement("input", { autoFocus: true, type: "email", placeholder: "customer@example.com", value: form.email, onChange: e => setForm({ ...form, email: e.target.value }) })),
            React.createElement("label", null,
                "\uBC1B\uB294 \uC0AC\uB78C \uC774\uB984 (\uC120\uD0DD)",
                React.createElement("input", { maxLength: 50, placeholder: "\uC608: \uD64D\uAE38\uB3D9 \uCC45\uC784", value: form.name, onChange: e => setForm({ ...form, name: e.target.value }) })),
            React.createElement("label", null,
                "\uC804\uB2EC \uBA54\uC2DC\uC9C0 (\uC120\uD0DD)",
                React.createElement("textarea", { maxLength: 1000, rows: 3, placeholder: "\uC608: 11/12 \uD68C\uC758 \uB0B4\uC6A9\uC785\uB2C8\uB2E4. \uD655\uC778 \uD6C4 \uD569\uC758 \uBD80\uD0C1\uB4DC\uB9BD\uB2C8\uB2E4.", value: form.message, onChange: e => setForm({ ...form, message: e.target.value }) })),
            blocked > 0 ? React.createElement("p", { className: "error-box" },
                "\uAC80\uC218\uAC00 \uB05D\uB098\uC9C0 \uC54A\uC740 \uD56D\uBAA9\uC774 ",
                blocked,
                "\uAC74 \uC788\uC2B5\uB2C8\uB2E4. \uAC80\uC218\uB97C \uB9C8\uCCD0 \uD68C\uC758\uB85D\uC744 \uB4F1\uB85D\uD55C \uB4A4 \uBCF4\uB0BC \uC218 \uC788\uC2B5\uB2C8\uB2E4.") : React.createElement("div", { className: "approval-preview" },
                React.createElement("b", null, '메일에 담길 합의 요청 항목 ' + items.length + '건'),
                items.length ? React.createElement("ul", { className: "approval-items" }, items.map(x => React.createElement("li", { key: x.id },
                    React.createElement("b", null, x.title),
                    React.createElement("span", null, itemText(x))))) : React.createElement("p", { className: "muted" }, "\uD655\uC778\uB41C \uC694\uAD6C\u00B7\uBCC0\uACBD \uD56D\uBAA9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uD68C\uC758\uB85D \uBCF8\uBB38\uB9CC \uBCF4\uB0C5\uB2C8\uB2E4.")),
            React.createElement("p", { className: "muted" }, "\uBC1B\uB294 \uBD84\uC740 \uBA54\uC77C\uC758 \uB9C1\uD06C\uC5D0\uC11C \uD68C\uC758\uB85D \uBCF8\uBB38\uACFC \uC704 \uD56D\uBAA9\uC744 \uD655\uC778\uD558\uACE0 \uD569\uC758 \uB610\uB294 \uBC18\uB824\uD569\uB2C8\uB2E4."),
            waiting && React.createElement("p", { className: "error-box" }, "\uC751\uB2F5\uC744 \uAE30\uB2E4\uB9AC\uB294 \uC694\uCCAD\uC774 \uC788\uC2B5\uB2C8\uB2E4. \uB2E4\uC2DC \uBCF4\uB0B4\uBA74 \uC774\uC804 \uBA54\uC77C\uC758 \uB9C1\uD06C\uB294 \uC4F8 \uC218 \uC5C6\uAC8C \uB429\uB2C8\uB2E4."),
            error && React.createElement("p", { role: "alert", className: "error-box" }, error),
            history.length > 0 && React.createElement("div", { className: "approval-history" },
                React.createElement("h4", null, "\uC774\uC804 \uC694\uCCAD"),
                history.map(h => React.createElement("p", { key: h.id },
                    React.createElement(ApprovalBadge, { approval: h }),
                    React.createElement("span", null,
                        h.email,
                        " \u00B7 ",
                        when(h.sent_at)),
                    h.comment && React.createElement("small", null,
                        "\uD68C\uC2E0 \uC758\uACAC: ",
                        h.comment)))));
    }
    // Meeting minutes text laid out like the company minutes form: title, info table, sections.
    const SECTIONS = ['회의 안건', '논의 내용', '결정 사항', '추가 확인 사항', '후속 조치', '참고 사항', '기타 사항', '첨부'];
    const cells = t => t.split(/\s*\|\s*/).map(x => x.trim());
    const isHeadRow = row => row.some(x => /^(조치 ?내용|내용|담당|담당자|기한|일정|비고|항목)$/.test(x));
    function minutesLayout(lines) {
        const doc = { title: '', subtitle: '', info: [], sections: [], intro: [] };
        let section = null;
        for (const raw of lines || []) {
            const text = (raw || '').trim();
            if (!text)
                continue;
            const heading = text.replace(/^[■□▶●◆#\d.\s]+(?=\D)/, '').trim();
            if (SECTIONS.includes(heading)) {
                section = { title: heading, items: [] };
                doc.sections.push(section);
                continue;
            }
            if (!section) {
                if (!doc.title && !doc.info.length && /^회의록$/.test(text)) {
                    doc.title = text;
                    continue;
                }
                if (/^MEETING MINUTES/i.test(text)) {
                    doc.subtitle = text.replace(/\s*\|\s*/g, '  |  ');
                    continue;
                }
                if (text.includes('|')) {
                    const c = cells(text), pairs = [];
                    for (let i = 0; i < c.length; i += 2)
                        pairs.push([c[i], c[i + 1] ?? '']);
                    doc.info.push(pairs);
                    continue;
                }
                doc.intro.push(text);
                continue;
            }
            const last = section.items[section.items.length - 1];
            if (text.includes('|')) {
                const row = cells(text);
                if (last?.type === 'table')
                    last.rows.push(row);
                else
                    section.items.push({ type: 'table', head: isHeadRow(row) ? row : null, rows: isHeadRow(row) ? [] : [row] });
                continue;
            }
            section.items.push({ type: 'p', text, strong: section.title === '논의 내용' && /^\d+\.\s/.test(text) });
        }
        return doc;
    }
    function MinutesDocument({ lines }) {
        const doc = minutesLayout(lines), wide = Math.max(1, ...doc.info.map(r => r.length));
        return React.createElement("article", { className: "minutes-doc" },
            React.createElement("header", null,
                React.createElement("h1", null, doc.title || '회의록'),
                React.createElement("p", { className: "minutes-sub" }, doc.subtitle || 'MEETING MINUTES')),
            doc.info.length > 0 && React.createElement("table", { className: "minutes-info" },
                React.createElement("tbody", null, doc.info.map((pairs, i) => React.createElement("tr", { key: i }, pairs.map(([k, v], j) => React.createElement(React.Fragment, { key: j },
                    React.createElement("th", null, k),
                    React.createElement("td", { colSpan: j === pairs.length - 1 ? (wide - pairs.length) * 2 + 1 : 1 }, v))))))),
            doc.intro.map((t, i) => React.createElement("p", { key: 'i' + i }, t)),
            doc.sections.map((sec, i) => React.createElement("section", { key: i },
                React.createElement("h2", null, sec.title),
                sec.items.map((item, j) => item.type === 'table' ? React.createElement("table", { key: j, className: "minutes-table" },
                    item.head && React.createElement("thead", null,
                        React.createElement("tr", null, item.head.map((x, k) => React.createElement("th", { key: k }, x)))),
                    React.createElement("tbody", null, item.rows.map((row, k) => React.createElement("tr", { key: k }, row.map((x, l) => React.createElement("td", { key: l }, x)))))) : React.createElement("p", { key: j, className: item.strong ? 'minutes-strong' : '' }, item.text)))));
    }
    const closedText = { expired: '링크의 유효 기간이 지났습니다. 담당자에게 다시 요청해 주세요.', canceled: '더 이상 사용할 수 없는 링크입니다. 새로 받은 메일의 링크를 사용해 주세요.' };
    function ApprovalPage({ token }) {
        const [view, setView] = useState(null), [loadError, setLoadError] = useState(''), [comment, setComment] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
        const load = () => api('/v3/approvals/' + token).then(setView).catch(e => setLoadError(e.message));
        useEffect(() => { load(); }, [token]);
        async function respond(decision) {
            if (decision === 'rejected' && !comment.trim() && !window.confirm('의견 없이 반려할까요? 반려 사유를 적어 주시면 담당자가 확인하기 쉽습니다.'))
                return;
            setBusy(true);
            setError('');
            try {
                await api('/v3/approvals/' + token, 'POST', { decision, comment });
            }
            catch (e) {
                setError(e.message);
            }
            // Reload either way: another click or an expiry may already have settled it.
            finally {
                await load();
                setBusy(false);
            }
        }
        const head = React.createElement("span", { className: "brand" },
            React.createElement("img", { src: logo, alt: "PNT" }));
        if (loadError)
            return React.createElement("div", { className: "approval-page" },
                React.createElement("section", { className: "approval-card" },
                    head,
                    React.createElement("h1", null, "\uD68C\uC758\uB85D \uD569\uC758 \uC694\uCCAD"),
                    React.createElement("p", { role: "alert", className: "error-box" }, loadError)));
        if (!view)
            return React.createElement("div", { className: "approval-page" },
                React.createElement("section", { className: "approval-card" },
                    head,
                    React.createElement("p", { className: "muted" }, "\uBD88\uB7EC\uC624\uB294 \uC911\u2026")));
        const done = view.status === 'approved' || view.status === 'rejected';
        return React.createElement("div", { className: "approval-page" },
            React.createElement("section", { className: "approval-card" },
                head,
                React.createElement("h1", null, "\uD68C\uC758\uB85D \uD569\uC758 \uC694\uCCAD"),
                React.createElement("dl", null,
                    React.createElement("dt", null, "\uD504\uB85C\uC81D\uD2B8"),
                    React.createElement("dd", null, view.project_name),
                    React.createElement("dt", null, "\uD68C\uC758\uB85D"),
                    React.createElement("dd", null,
                        view.title,
                        view.date ? ' (' + view.date + ')' : ''),
                    view.requested_by_name && React.createElement(React.Fragment, null,
                        React.createElement("dt", null, "\uC694\uCCAD\uC790"),
                        React.createElement("dd", null,
                            view.requested_by_name,
                            " \u00B7 ",
                            when(view.sent_at)))),
                view.message && React.createElement("p", { className: "approval-message" }, view.message),
                (view.items || []).length > 0 && React.createElement("div", { className: "approval-preview" },
                    React.createElement("b", null, '합의 요청 항목 ' + view.items.length + '건'),
                    React.createElement("ul", { className: "approval-items" }, view.items.map(x => React.createElement("li", { key: x.id },
                        React.createElement("b", null, x.title),
                        React.createElement("span", null, itemText(x)))))),
                closedText[view.status] && React.createElement("p", { className: "error-box" }, closedText[view.status]),
                done && React.createElement("div", { className: 'approval-result ' + view.status },
                    view.status === 'approved' ? React.createElement("b", { "aria-hidden": "true" }, "\u2713") : React.createElement("b", { "aria-hidden": "true" }, "!"),
                    React.createElement("div", null,
                        React.createElement("b", null, view.status === 'approved' ? '합의 처리되었습니다.' : '반려 처리되었습니다.'),
                        " ",
                        React.createElement("small", null, when(view.responded_at)),
                        view.comment && React.createElement("p", null,
                            "\uB0A8\uAE30\uC2E0 \uC758\uACAC: ",
                            view.comment),
                        React.createElement("p", { className: "muted" }, "\uC774 \uCC3D\uC740 \uB2EB\uC73C\uC154\uB3C4 \uB429\uB2C8\uB2E4."))),
                view.status === 'sent' && React.createElement("div", { className: "approval-form" },
                    React.createElement("p", { className: "muted" },
                        "\uC704 \uD56D\uBAA9\uACFC \uC544\uB798 \uD68C\uC758\uB85D \uB0B4\uC6A9\uC744 \uD655\uC778\uD55C \uB4A4 \uD569\uC758 \uB610\uB294 \uBC18\uB824\uB97C \uC120\uD0DD\uD574 \uC8FC\uC138\uC694. ",
                        when(view.expires_at),
                        "\uAE4C\uC9C0 \uD55C \uBC88\uB9CC \uCC98\uB9AC\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4."),
                    React.createElement("label", null,
                        "\uC758\uACAC (\uC120\uD0DD, \uBC18\uB824 \uC2DC \uC0AC\uC720\uB97C \uC801\uC5B4 \uC8FC\uC138\uC694)",
                        React.createElement("textarea", { rows: 3, maxLength: 1000, value: comment, onChange: e => setComment(e.target.value) })),
                    error && React.createElement("p", { role: "alert", className: "error-box" }, error),
                    React.createElement("div", { className: "actions" },
                        React.createElement(Button, { primary: true, disabled: busy, onClick: () => respond('approved') }, "\uD569\uC758"),
                        React.createElement(Button, { className: "reject", disabled: busy, onClick: () => respond('rejected') }, "\uBC18\uB824")))),
            view.pages > 0 ? React.createElement("div", { className: "pdf-pages approval-pages" }, Array.from({ length: view.pages }, (_, i) => React.createElement("img", { key: i, src: '/api/v3/approvals/' + token + '/pages/' + (i + 1), alt: '회의록 ' + (i + 1) + '페이지' }))) : view.lines && React.createElement(MinutesDocument, { lines: view.lines }));
    }
    return { ApprovalBadge, ApprovalLine, SendApprovalDialog, ApprovalPage, approvalToken, MinutesDocument };
};
