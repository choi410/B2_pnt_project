// Project flow, review queue and evidence rendering from the team interface.
const workflow = {
  boxes: {},
  sel: null,
  state: {},
  revs: function (evs) {
    var key = function (t) {
        var n = (t || "").match(/\d+(?:[.,]\d+)*/g);
        return n && n.length
          ? n.join("|")
          : (t || "").replace(/\s+/g, "").toLowerCase();
      },
      base = null,
      n = 0,
      cur = null,
      out = {};
    evs.forEach(function (e) {
      if (e.review_state !== "확인됨") {
        out[e.id] = {
          t: "미확인",
          c: "un",
        };
        return;
      }
      if (e.business_state !== "확정") {
        out[e.id] = {
          t: e.business_state === "요청" ? "변경 요청" : e.business_state,
          c: "req",
        };
        return;
      }
      var v = key(e.after);
      if (base === null) {
        base = v;
        out[e.id] = {
          t: "최초",
          c: "rev",
        };
        cur = e;
      } else if (v !== base) {
        base = v;
        n++;
        out[e.id] = {
          t: "변경 " + n + "차",
          c: "rev",
        };
        cur = e;
      } else
        out[e.id] = {
          t: "재확인",
          c: "same",
        };
    });
    out.__cur = cur;
    out.__label = cur ? (n ? "변경 " + n + "차" : "최초") : "";
    return out;
  },
  load: function (s, Q, o) {
    var k = s.id + ":" + s.revision + ":" + s.version,
      c = this.boxes;
    if (c[k] !== undefined) return c[k];
    c[k] = null;
    Q("/v3/meetings/" + s.id + "/change-boxes")
      .then(function (x) {
        c[k] = x || {};
        o(function (y) {
          return Object.assign({}, y);
        });
        workflow.scroll();
      })
      .catch(function () {
        c[k] = {};
      });
    return null;
  },
  scroll: function () {
    setTimeout(function () {
      var e =
        document.querySelector(".pdf-hl:not(.sub)") ||
        document.querySelector(".pdf-hl") ||
        document.querySelector(".source-lines mark") ||
        document.querySelector(".source-lines .highlight");
      e &&
        e.scrollIntoView({
          block: "center",
          behavior: "smooth",
        });
    }, 160);
  },
  rects: function (s, Q, o, page) {
    var v = this.load(s, Q, o),
      e = v && this.sel && v[this.sel],
      out = [];
    if (!e) return out;
    e.boxes.forEach(function (g) {
      if (g.page === page)
        g.rects.forEach(function (x) {
          out.push(x.concat(g.main === false ? 0 : 1));
        });
    });
    return out;
  },
  mark: function (R, s, Q, o, line) {
    var v = this.load(s, Q, o),
      e = v && this.sel && v[this.sel],
      c =
        e && e.clauses && (!e.main || e.main === line.id) && e.clauses[line.id];
    if (!c || c === line.text) return line.text;
    var i = line.text.indexOf(c);
    if (i < 0) return line.text;
    return [
      line.text.slice(0, i),
      R.createElement(
        "mark",
        {
          key: "m",
        },
        c,
      ),
      line.text.slice(i + c.length),
    ];
  },
  watch: function (s, busy, refresh) {
    var was = this.state[s.id];
    this.state[s.id] = busy;
    if (was && !busy) {
      this.boxes = {};
      setTimeout(function () {
        refresh().catch(function () {});
      }, 50);
    }
  },
};
workflow.STAGES = [
  "수주/사양협의",
  "설계(기구/전장)",
  "구매/제작",
  "조립/사내시운전(FAT)",
  "현장셋업(SAT)",
  "양산/CS",
];
workflow.flows = {};
workflow.hist = workflow.hist || {
  open: {},
  filter: "all",
};
workflow.KW = {
  "수주/사양협의": [
    "수주",
    "계약",
    "견적",
    "입찰",
    "제안서",
    "킥오프",
    "착수",
    "PO",
    "URS",
  ],
  "설계(기구/전장)": [
    "승인도",
    "설계",
    "도면",
    "사양",
    "규격",
    "공차",
    "배치도",
    "레이아웃",
    "변경 요청",
    "설계 변경",
    "Rev.",
    "검토 의견",
    "DR",
  ],
  "구매/제작": [
    "구매",
    "발주",
    "자재",
    "부품",
    "구성품",
    "업체 선정",
    "외주",
    "제작",
    "가공",
    "용접",
    "도장",
    "제관",
  ],
  "조립/사내시운전(FAT)": [
    "조립",
    "배선",
    "FAT",
    "사내 시운전",
    "공장 시운전",
    "출하 검사",
    "성능 시험",
    "성능 확인",
    "검수",
  ],
  "현장셋업(SAT)": [
    "현장 설치",
    "설치",
    "SAT",
    "셋업",
    "Hook-up",
    "반입",
    "시운전",
    "현장",
  ],
  "양산/CS": [
    "양산",
    "안정화",
    "CS",
    "하자 보수",
    "하자 처리",
    "정산",
    "인수인계",
    "최종 승인",
    "클로징",
  ],
};
workflow.HEADS = {
  결정사항: 2,
  합의사항: 2,
  후속조치: 2,
  향후조치: 2,
  actionitem: 2,
  actionitems: 2,
  회의안건: 1.5,
  안건: 1.5,
  논의내용: 1,
  논의사항: 1,
  추가확인사항: 1,
  확인사항: 1,
  확인필요사항: 1,
  참고사항: 0.5,
};
workflow.infer = function (m) {
  var S = this.STAGES,
    KW = this.KW,
    words = [];
  S.forEach(function (s) {
    KW[s].forEach(function (w) {
      words.push([s, w]);
    });
  });
  words.sort(function (a, b) {
    return b[1].length - a[1].length;
  });
  var score = {},
    hits = {},
    best = {};
  S.forEach(function (s) {
    score[s] = 0;
    hits[s] = [];
  });
  var add = function (text, weight, line) {
    var t = String(text || "").replace(/\s*\/\s*[^/]*$/, function (x) {
        return /\d{4}-\d{2}-\d{2}|까지|차주|중$/.test(x) ? "" : x;
      }),
      used = new Array(t.length).fill(!1),
      found = {};
    words.forEach(function (sw) {
      var s = sw[0],
        w = sw[1],
        from = 0;
      while (true) {
        var i = t.indexOf(w, from);
        if (i < 0) break;
        from = i + w.length;
        if (used.slice(i, i + w.length).some(Boolean)) continue;
        for (var k = i; k < i + w.length; k++) used[k] = !0;
        if (
          /^\s?(일|일정|일자|날짜|예정일|투입일|기한|시점)/.test(
            t.slice(i + w.length),
          )
        )
          continue;
        (found[s] = found[s] || []).push(w);
      }
    });
    Object.keys(found).forEach(function (s) {
      score[s] += found[s].length * weight;
      hits[s] = hits[s].concat(found[s]);
      if (line && (!best[s] || found[s].length * weight > best[s][0]))
        best[s] = [found[s].length * weight, line];
    });
  };
  add(m.title, 1.5);
  var weight = 1,
    H = this.HEADS;
  (m.lines || []).forEach(function (l) {
    var t = String(l.text || "").trim();
    if (!t) return;
    var key = t.replace(/[\s:：\[\]]/g, "").toLowerCase();
    if (key in H) {
      weight = H[key];
      return;
    }
    if (
      /^(회의록|meetingminutes|회의명|프로젝트명|일시|참석자|작성자)/i.test(
        key.replace(/\|.*/, ""),
      )
    )
      return;
    add(t, weight, l);
  });
  var r = S.slice().sort(function (a, b) {
      return score[b] - score[a];
    }),
    top = r[0],
    sec = r[1],
    ok = score[top] >= 3 && score[top] >= score[sec] * 1.5,
    ln = best[top] && best[top][1];
  return {
    stage: ok ? top : null,
    top: top,
    score: Math.round(score[top] * 10) / 10,
    hits: hits[top]
      .filter(function (x, i, a) {
        return a.indexOf(x) === i;
      })
      .slice(0, 6),
    meeting_id: m.id,
    meeting_title: m.title,
    meeting_date: m.date || "",
    line: ln
      ? {
          id: ln.id,
          text: ln.text,
        }
      : null,
  };
};
workflow.flowFor = function (X, pid) {
  var ms = X.u.meetings.filter(function (m) {
      return m.project_id === pid;
    }),
    key =
      pid +
      ":" +
      ms
        .map(function (m) {
          return m.id + "." + m.version;
        })
        .join(","),
    c = this.flows[pid],
    self = this;
  if (c && c.key === key) return c.data || null;
  this.flows[pid] = {
    key: key,
    data: c ? c.data : null,
  };
  var done = function (d) {
    self.flows[pid] = {
      key: key,
      data: d,
    };
    X.o(function (y) {
      return Object.assign({}, y);
    });
  };
  X.Q("/v3/projects/" + pid + "/flow")
    .then(done)
    .catch(function () {
      // 서버에 단계 기능이 아직 없으면(재시작 전) 화면에서 같은 규칙으로 추정한다
      Promise.all(
        ms.map(function (m) {
          return X.Q("/meetings/" + m.id).catch(function () {
            return null;
          });
        }),
      ).then(function (all) {
        var per = {},
          guess = null;
        all
          .filter(Boolean)
          .sort(function (a, b) {
            return (a.date || "").localeCompare(b.date || "");
          })
          .forEach(function (m) {
            var g = self.infer(m);
            per[m.id] = g.stage;
            if (g.stage) guess = g;
          });
        if (!guess && all.length) {
          var lastM = all
            .filter(Boolean)
            .sort(function (a, b) {
              return (a.date || "").localeCompare(b.date || "");
            })
            .pop();
          guess = lastM ? self.infer(lastM) : null;
        }
        done({
          stages: self.STAGES,
          manual: null,
          guess: guess,
          per_meeting: per,
          local: !0,
        });
      });
    });
  return c ? c.data : null;
};
workflow.pend = function (u) {
  // 검수를 마치지 않은 회의록: 값>0 미확인 항목 수, -1 분석 중, -2 분석 실패. 이런 회의록은 아직 등록 전으로 본다.
  if (this._pu === u) return this._pm;
  var m = {};
  (u.changes || []).forEach(function (e) {
    if (e.review_state !== "확인됨" && e.review_state !== "제외")
      m[e.meeting_id] = (m[e.meeting_id] || 0) + 1;
  });
  (u.meetings || []).forEach(function (x) {
    if (m[x.id]) return;
    if (x.analysis_state === "queued" || x.analysis_state === "running")
      m[x.id] = -1;
    else if (x.analysis_state === "failed") m[x.id] = -2;
  });
  this._pu = u;
  this._pm = m;
  return m;
};
workflow.Queue = function (X) {
  var E = X.R.createElement,
    u = X.u,
    H = this.hist,
    re = function () {
      X.o(function (y) {
        return Object.assign({}, y);
      });
    },
    cnt = {};
  u.changes.forEach(function (e) {
    if (e.review_state !== "확인됨" && e.review_state !== "제외")
      cnt[e.meeting_id] = (cnt[e.meeting_id] || 0) + 1;
  });
  var rows = u.meetings
      .filter(function (m) {
        return cnt[m.id];
      })
      .sort(function (a, b) {
        return (a.date || "").localeCompare(b.date || "");
      }),
    total = rows.reduce(function (t, m) {
      return t + cnt[m.id];
    }, 0);
  if (!rows.length) return null;
  var open = H.qopen,
    show = open ? rows : rows.slice(0, 5),
    pn = function (id) {
      var p = u.projects.find(function (x) {
        return x.id === id;
      });
      return p ? p.name : id;
    };
  return E(
    "section",
    {
      className: "rq",
    },
    E(
      "div",
      {
        className: "section-head",
      },
      E(
        "h2",
        null,
        "검수 대기 ",
        E("small", null, "회의록 " + rows.length + "건 · 항목 " + total + "건"),
      ),
      E(
        "span",
        {
          className: "muted",
        },
        "AI가 뽑은 요구·변경 중 아직 사람이 확인하지 않은 항목입니다. 오래된 회의부터 보입니다.",
      ),
    ),
    E(
      "div",
      {
        className: "rq-list",
      },
      show.map(function (m) {
        return E(
          "button",
          {
            type: "button",
            key: m.id,
            className: "rq-row",
            onClick: function () {
              X.Ca(function () {
                return X.ff(m.id, []);
              });
            },
          },
          E("small", null, (m.date || "").replace(/-/g, ".")),
          E("b", null, m.title),
          E(
            "span",
            {
              className: "muted",
            },
            pn(m.project_id),
          ),
          E(
            "em",
            {
              className: "pf-badge warn",
            },
            "미확인 " + cnt[m.id] + "건",
          ),
          E(
            "span",
            {
              className: "rq-go",
            },
            "검수하기 ›",
          ),
        );
      }),
    ),
    rows.length > 5
      ? E(
          "button",
          {
            type: "button",
            className: "rq-more",
            onClick: function () {
              H.qopen = !open;
              re();
            },
          },
          open ? "접기" : "나머지 " + (rows.length - 5) + "건 더 보기",
        )
      : null,
  );
};
workflow.StageBar = function (X, pid, mini) {
  var E = X.R.createElement,
    S = this.STAGES,
    f = this.flowFor(X, pid),
    cur = f ? f.manual || (f.guess && f.guess.stage) || null : null,
    ci = S.indexOf(cur),
    cls = function (i) {
      return (
        "pf-st st" +
        i +
        (ci < 0 ? "" : i < ci ? " done" : i === ci ? " cur" : "")
      );
    };
  if (mini)
    return E(
      "div",
      {
        className: "pf-mini",
      },
      E(
        "div",
        {
          className: "pf-stages mini",
          role: "img",
          "aria-label": ci >= 0 ? "현재 " + cur + " · " + (ci + 1) + "/" + S.length + "단계" : "현재 단계 미정",
        },
        S.map(function (s, i) {
          return E("span", {
            key: s,
            title: (i + 1) + ". " + s + (i === ci ? " · 현재 단계" : ""),
            className: "pf-st" + (i === ci ? " cur" : ""),
            "aria-hidden": true,
          });
        }),
      ),
      E(
        "div",
        { className: "home-stage-caption" },
        E("small", { className: "home-stage-name" },
          !f ? "단계 확인 중" : cur ? cur + (f.manual ? "" : " · 추정") : "단계 판단 보류"),
        ci >= 0 ? E("span", { className: "home-stage-number", "aria-hidden": true }, (ci + 1) + " / " + S.length + "단계") : null,
      ),
    );
  var g = f && f.guess;
  return E(
    "section",
    {
      className: "pf-stagebox",
    },
    E(
      "div",
      {
        className: "pf-chev",
      },
      S.map(function (s, i) {
        return E(
          "span",
          {
            key: s,
            className: cls(i),
          },
          E("small", null, i + 1),
          s,
        );
      }),
    ),
    E(
      "div",
      {
        className: "pf-stagenote",
      },
      E(
        "span",
        {
          className: "pf-now",
        },
        "현재 단계",
        E("b", null, cur || (f ? "판단 보류" : "확인 중")),
        f && f.manual
          ? E(
              "em",
              {
                className: "pf-tag",
              },
              "담당자 지정",
            )
          : cur
            ? E(
                "em",
                {
                  className: "pf-tag warn",
                },
                "규칙 추정",
              )
            : null,
      ),
      f && !f.manual && g && g.line
        ? E(
            "button",
            {
              type: "button",
              className: "pf-why",
              onClick: function () {
                X.Ca(function () {
                  return X.ff(g.meeting_id, [g.line.id]);
                });
              },
            },
            E("span", null, "근거"),
            E("b", null, "『" + g.meeting_title + "』"),
            E("small", null, (g.hits || []).slice(0, 4).join(" · ")),
            E("i", null, "↗"),
          )
        : null,
      f && !f.manual && g && !g.stage
        ? E(
            "small",
            {
              className: "muted",
            },
            "최근 회의록에 단계를 가르는 표현이 뚜렷하지 않아 판단을 보류했습니다.",
          )
        : null,
      f && f.local
        ? E(
            "small",
            {
              className: "muted pf-stagesel",
            },
            "진행 단계 변경은 서버 재시작 후 사용할 수 있습니다.",
          )
        : null,
    ),
  );
};
workflow.split = function (t) {
  return String(t || "")
    .split(/\s+(?=\d+\.\s)/)
    .map(function (x) {
      return x.trim().replace(/^\d+\.\s*/, "");
    })
    .filter(Boolean);
};
workflow.Flow = function (X) {
  var self = this,
    E = X.R.createElement,
    u = X.u,
    pid = X.p,
    H = this.hist,
    re = function () {
      X.o(function (y) {
        return Object.assign({}, y);
      });
    },
    S = this.STAGES,
    f = this.flowFor(X, pid) || {},
    per = f.per_meeting || {};
  var PD = this.pend(u),
    nPend = u.meetings.filter(function (m) {
      return m.project_id === pid && PD[m.id];
    }).length;
  var ms = u.meetings
    .filter(function (m) {
      return m.project_id === pid && !PD[m.id];
    })
    .concat(this.fakeMeetings || [])
    .slice()
    .sort(function (a, b) {
      return (
        (a.date || "").localeCompare(b.date || "") ||
        (a.created_at || "").localeCompare(b.created_at || "")
      );
    });
  var chgAll = u.changes
      .filter(function (e) {
        return e.project_id === pid && e.review_state !== "제외";
      })
      .concat(this.fakeChanges || []),
    chg = chgAll.filter(function (e) {
      return e.review_state === "확인됨";
    }),
    byM = {},
    unM = {};
  chgAll.forEach(function (e) {
    if (e.review_state !== "확인됨")
      unM[e.meeting_id] = (unM[e.meeting_id] || 0) + 1;
  });
  chg.forEach(function (e) {
    (byM[e.meeting_id] = byM[e.meeting_id] || []).push(e);
  });
  var nChg = function (m) {
      return (byM[m.id] || []).length;
    },
    nUn = function (m) {
      return unM[m.id] || 0;
    };
  var ym = function (m) {
      return (m.date || m.created_at || "").slice(0, 7);
    },
    months = [];
  if (ms.length) {
    var a = ym(ms[0]),
      z = ym(ms[ms.length - 1]),
      y = +a.slice(0, 4),
      mo = +a.slice(5, 7);
    for (var gd = 0; gd < 240; gd++) {
      var k = y + "-" + String(mo).padStart(2, "0");
      months.push(k);
      if (k >= z) break;
      mo++;
      if (mo > 12) {
        mo = 1;
        y++;
      }
    }
  }
  var quarter = months.length > 30,
    bucket = function (k) {
      return quarter
        ? k.slice(0, 4) + "-Q" + (Math.floor((+k.slice(5, 7) - 1) / 3) + 1)
        : k;
    },
    cells = [],
    idx = {};
  months.forEach(function (k) {
    var b = bucket(k);
    if (!idx[b]) {
      idx[b] = {
        key: b,
        ms: [],
      };
      cells.push(idx[b]);
    }
  });
  ms.forEach(function (m) {
    var c = idx[bucket(ym(m))];
    c && c.ms.push(m);
  });
  var lastSt = null;
  cells.forEach(function (c) {
    var cnt = {},
      best = null;
    c.ms.forEach(function (m) {
      var s = per[m.id];
      if (s) cnt[s] = (cnt[s] || 0) + 1;
    });
    Object.keys(cnt).forEach(function (s) {
      if (!best || cnt[s] > cnt[best]) best = s;
    });
    c.stage = best || lastSt;
    if (best) lastSt = best;
    c.n = c.ms.length;
    c.chg = c.ms.some(function (m) {
      return nChg(m) > 0;
    });
    c.un = c.ms.reduce(function (t, m) {
      return t + nUn(m);
    }, 0);
  });
  var filled = cells.filter(function (c) {
    return c.n;
  });
  if (!H.fm || !idx[H.fm] || !idx[H.fm].n)
    H.fm = filled.length ? filled[filled.length - 1].key : null;
  var q = (H.fq || "").trim().toLowerCase(),
    pool = q
      ? ms.filter(function (m) {
          return (m.title + " " + (m.date || "")).toLowerCase().indexOf(q) >= 0;
        })
      : idx[H.fm]
        ? idx[H.fm].ms
        : [];
  if (H.fonly)
    pool = pool.filter(function (m) {
      return nChg(m) > 0;
    });
  pool = pool.slice().reverse();
  var sel =
    ms.find(function (m) {
      return m.id === H.fmid;
    }) ||
    pool[0] ||
    ms[ms.length - 1];
  var sIdx = function (s) {
      return S.indexOf(s);
    },
    fmt = function (k) {
      return quarter
        ? k.slice(0, 4) + "년 " + k.slice(6) + "분기"
        : k.slice(0, 4) + "." + k.slice(5);
    };
  // 단계 구간(같은 단계가 이어지는 달을 한 칸으로)
  var spans = [];
  cells.forEach(function (c) {
    var l = spans[spans.length - 1];
    if (l && l.stage === c.stage) l.n++;
    else
      spans.push({
        stage: c.stage,
        n: 1,
      });
  });
  var pcur =
      f.manual ||
      (f.guess && f.guess.stage) ||
      (spans.length ? spans[spans.length - 1].stage : null),
    pd = f.per_detail || {},
    sd = sel
      ? pd[sel.id] ||
        (per[sel.id]
          ? {
              stage: per[sel.id],
              source: "rule",
            }
          : null)
      : null,
    cur = (sd && sd.stage) || pcur,
    ci = sIdx(cur),
    pci = sIdx(pcur),
    runJudge = function (url, reason) {
      H.judging = pid;
      re();
      X.Q(url, "POST", reason ? {reason: reason} : undefined)
        .then(function () {
          H.judging = null;
          self.flows[pid] = null;
          re();
        })
        .catch(function (e) {
          H.judging = null;
          H.judgeErr = (e && e.message) || "단계 판단에 실패했습니다.";
          self.flows[pid] = null;
          re();
        });
    },
    auto = (function () {
      H.autoJ = H.autoJ || {};
      if (
        u.user.level === "leader" && f.ai_ready &&
        f.ai_missing > 0 &&
        !H.judging &&
        H.autoJ[pid] !== f.ai_missing
      ) {
        H.autoJ[pid] = f.ai_missing;
        setTimeout(function () {
          runJudge("/v3/projects/" + pid + "/stage-ai");
        }, 0);
      }
      return null;
    })(),
    reBtn =
      u.user.level === "leader" && f.rejudge && f.ai_ready && sel && H.judging !== pid
        ? E(
            "button",
            {
              type: "button",
              className: "rv-btn pf-aibtn",
              disabled: !!H.stageSaving,
              title:
                "이 회의의 단계를 AI로 다시 판단합니다. 팀장이 직접 지정한 단계는 풀립니다.",
              onClick: function () {
                var reason = window.prompt("회의 진행 단계를 다시 판단하는 사유를 입력해 주세요.");
                if (!reason || !reason.trim()) return;
                H.judgeErr = "";
                runJudge("/v3/meetings/" + sel.id + "/stage-ai", reason.trim());
              },
            },
            "다시 판단",
          )
        : null,
    aiBtn =
      H.judging === pid
        ? E(
            "span",
            {
              className: "pf-judging",
            },
            E("i", {
              className: "pf-spin",
            }),
            "AI가 단계를 판단하는 중… 회의 1건에 3~4초 걸립니다",
          )
        : u.user.level === "leader" && f.ai_ready && f.ai_missing > 0
          ? E(
              "button",
              {
                type: "button",
                className: "rv-btn pf-aibtn",
                disabled: !!H.stageSaving,
                onClick: function () {
                  H.judgeErr = "";
                  runJudge("/v3/projects/" + pid + "/stage-ai");
                },
              },
              "AI로 단계 판단 (" + f.ai_missing + "건)",
            )
          : null,
    stLab =
      sel && sd && sd.stage
        ? E(
            "small",
            {
              className: "pf-stsrc",
              title: sd.reason || "",
            },
            (sel.date || "").replace(/-/g, ".") + " 회의 기준 · ",
            E(
              "b",
              {
                className: sd.source === "rule" ? "rule" : "ai",
              },
              sd.source === "ai"
                ? "AI 판단"
                : sd.source === "pm"
                  ? "담당자 지정"
                  : "키워드 추정",
            ),
            pcur && pcur !== sd.stage ? " · 프로젝트 최근 단계: " + pcur : "",
          )
        : E(
            "small",
            {
              className: "muted",
            },
            sel ? "이 회의는 단계를 판단하지 못했습니다" : "단계 판단 보류",
          ),
    canEditStage = X.requestStage && sel && f.per_detail && !f.local,
    stageEdit =
      canEditStage && H.stageEdit &&
      H.stageEdit.pid === pid && H.stageEdit.mid === sel.id
        ? H.stageEdit
        : null,
    chooseStage = function (stage) {
      if (!canEditStage || H.stageSaving || H.judging === pid) return;
      H.stageEdit = stageEdit && stageEdit.stage === stage
        ? null
        : { pid: pid, mid: sel.id, stage: stage };
      re();
    },
    saveStage = function () {
      var edit = stageEdit;
      if (!edit || H.stageSaving || H.judging === pid) return;
      H.stageEdit = null;
      X.requestStage(sel, S, sd && sd.stage, edit.stage);
      re();
    },
    fix =
      canEditStage
        ? E(
            "select",
            {
              className: "pf-fix",
              title: "이 회의의 단계를 직접 고칩니다",
              disabled: !!H.stageSaving || H.judging === pid,
              value: stageEdit ? stageEdit.stage : sd && sd.source === "pm" ? sd.stage : "",
              onChange: function (ev) {
                chooseStage(ev.target.value);
              },
            },
            E(
              "option",
              {
                value: "",
              },
              sd && sd.source === "pm"
                ? "자동 판단으로 되돌리기"
                : "단계 직접 수정",
            ),
            S.map(function (s) {
              return E(
                "option",
                {
                  key: s,
                  value: s,
                },
                s,
              );
            }),
          )
        : null;
  var time = E(
    "section",
    {
      className: "pf-box pf-time",
    },
    E(
      "div",
      {
        className: "pf-head",
      },
      E("h2", null, "진행 타임라인"),
      E(
        "small",
        {
          className: "muted",
        },
        "회의 " +
          ms.length +
          "건 · " +
          (cells.length
            ? fmt(cells[0].key) + " ~ " + fmt(cells[cells.length - 1].key)
            : "") +
          (quarter ? " · 분기 단위" : ""),
      ),
    ),
    E(
      "div",
      {
        className: "pf-steps",
      },
      E(
        "span",
        {
          className: "pf-stepl",
        },
        "진행 단계",
      ),
      E(
        "ol",
        null,
        S.map(function (s, i) {
          return E(
            "li",
            {
              key: s,
              className:
                (ci < 0 ? "" : i < ci ? "done" : i === ci ? "cur" : "") +
                (i === pci && pci !== ci ? " proj" : ""),
            },
            canEditStage
              ? E(
                  "button",
                  {
                    type: "button",
                    className: "pf-step-edit" + (stageEdit && stageEdit.stage === s ? " pending" : ""),
                    "aria-label": s + " 단계로 수정",
                    "aria-pressed": stageEdit ? stageEdit.stage === s : i === ci,
                    title: stageEdit && stageEdit.stage === s
                      ? "다시 누르면 수정 선택 취소"
                      : (sel.date || "") + " 회의의 단계 수정",
                    disabled: !!H.stageSaving || H.judging === pid,
                    onClick: function () { chooseStage(s); },
                  },
                  E("i", { "aria-hidden": true }),
                  E("span", null, s),
                )
              : E(X.R.Fragment, null, E("i", null), E("span", null, s)),
          );
        }),
      ),
    ),
    stageEdit
      ? E(
          "div",
          {
            className: "pf-stage-editor",
            role: "group",
            "aria-label": "회의 진행 단계 수정",
          },
          E("div", { className: "pf-stage-edit-info" },
            E("small", null, (sel.date || "") + " · " + sel.title),
            E("span", { "aria-live": "polite" },
              "회의 단계: ", cur || "미지정", " → ",
              E("b", null, stageEdit.stage || "자동 판단"),
            ),
          ),
          E("div", { className: "pf-stage-edit-actions" },
            E("button", {
              type: "button", className: "pf-stage-cancel", disabled: !!H.stageSaving,
              onClick: function () { H.stageEdit = null; re(); },
            }, "취소"),
            E("button", {
              type: "button", className: "pf-stage-save", disabled: !!H.stageSaving || H.judging === pid,
              onClick: saveStage,
            }, u.user.level === "leader" ? "단계 변경" : "단계 변경 요청"),
          ),
        )
      : null,
    E(
      "div",
      {
        className: "pf-stmeta",
      },
      stLab,
      sd && sd.reason
        ? E(
            "button",
            {
              type: "button",
              className: "pf-whybtn",
              "aria-expanded": !!H.whyOpen,
              onClick: function () {
                H.whyOpen = !H.whyOpen;
                re();
              },
            },
            (H.whyOpen ? "▾ " : "▸ ") + "판단 근거",
          )
        : null,
      E("span", {
        className: "pf-stsp",
      }),
      fix,
      reBtn,
      aiBtn,
    ),
    H.judgeErr
      ? E(
          "p",
          {
            className: "pf-streason warning",
          },
          H.judgeErr,
        )
      : null,
    H.whyOpen && sd && sd.reason
      ? E(
          "p",
          {
            className: "pf-streason",
          },
          sd.reason,
          sd.evidence ? E("q", null, sd.evidence) : null,
        )
      : null,
    (function () {
      var MP = 6,
        pages = Math.ceil(cells.length / MP) || 1,
        ci0 = Math.max(
          0,
          cells.findIndex(function (c) {
            return c.key === H.fm;
          }),
        ),
        mp =
          H.mpage && H.mpage.pid === pid
            ? Math.min(H.mpage.pg, pages - 1)
            : Math.floor(ci0 / MP),
        sl = cells.slice(mp * MP, mp * MP + MP),
        go = function (d) {
          H.mpage = {
            pid: pid,
            pg: mp + d,
          };
          re();
        };
      while (sl.length < MP) sl.push(null);
      return E(
        "div",
        {
          className: "pf-mwrap" + (pages > 1 ? " nav" : ""),
        },
        pages > 1
          ? E(
              "button",
              {
                type: "button",
                className: "pf-mnav",
                "aria-label": "이전 6개월",
                disabled: mp === 0,
                onClick: function () {
                  go(-1);
                },
              },
              "‹",
            )
          : null,
        E(
          "div",
          {
            className: "pf-months",
          },
          sl.map(function (c, i) {
            if (!c)
              return E("span", {
                key: "b" + i,
                className: "pf-mon blank",
                "aria-hidden": "true",
              });
            var on = !q && c.key === H.fm;
            return E(
              "button",
              {
                type: "button",
                key: c.key,
                disabled: !c.n,
                className: "pf-mon" + (on ? " on" : "") + (c.n ? "" : " empty"),
                title:
                  fmt(c.key) +
                  " · 회의 " +
                  c.n +
                  "건" +
                  (c.un ? " · 미확인 " + c.un + "건" : ""),
                onClick: function () {
                  H.fm = c.key;
                  H.fq = "";
                  H.fmid = null;
                  H.fpage = null;
                  re();
                },
              },
              E(
                "small",
                null,
                quarter
                  ? c.key.slice(0, 4) + " " + c.key.slice(5)
                  : c.key.slice(0, 4) + "." + c.key.slice(5),
              ),
              E("b", null, c.n ? "회의 " + c.n + "건" : "–"),
              E(
                "span",
                {
                  className: "pf-marks",
                },
                c.chg
                  ? E("i", {
                      className: "pf-dot chg",
                      title: "요구·변경 있음",
                    })
                  : null,
                c.un
                  ? E("i", {
                      className: "pf-dot un",
                      title: "미확인 검수 남음",
                    })
                  : null,
              ),
            );
          }),
        ),
        pages > 1
          ? E(
              "button",
              {
                type: "button",
                className: "pf-mnav",
                "aria-label": "다음 6개월",
                disabled: mp >= pages - 1,
                onClick: function () {
                  go(1);
                },
              },
              "›",
            )
          : null,
        pages > 1
          ? E(
              "span",
              {
                className: "pf-mpg",
              },
              Array.from(
                {
                  length: pages,
                },
                function (_, i) {
                  return E("button", {
                    type: "button",
                    key: i,
                    className: i === mp ? "on" : "",
                    "aria-label": i + 1 + "쪽",
                    onClick: function () {
                      H.mpage = {
                        pid: pid,
                        pg: i,
                      };
                      re();
                    },
                  });
                },
              ),
            )
          : null,
      );
    })(),
    E(
      "div",
      {
        className: "pf-legend",
      },
      E(
        "span",
        null,
        E("i", {
          className: "pf-dot chg",
        }),
        "요구·변경 있음",
      ),
      E(
        "span",
        null,
        E("i", {
          className: "pf-dot un",
        }),
        "미확인 검수 남음",
      ),
    ),
    E(
      "div",
      {
        className: "pf-strip",
      },
      E(
        "div",
        {
          className: "pf-striphead",
        },
        E(
          "b",
          null,
          q
            ? "검색 결과 " + pool.length + "건"
            : (H.fm ? fmt(H.fm) : "") + " 회의 " + pool.length + "건",
        ),
        E(
          "label",
          {
            className: "pf-check",
          },
          E("input", {
            type: "checkbox",
            checked: !!H.fonly,
            onChange: function (ev) {
              H.fonly = ev.target.checked;
              H.fmid = null;
              H.fpage = null;
              re();
            },
          }),
          "요구·변경 있는 회의만",
        ),
        E("input", {
          className: "hx-search",
          placeholder: "전체 회의 검색",
          value: H.fq || "",
          onChange: function (ev) {
            H.fq = ev.target.value;
            H.fmid = null;
            H.fpage = null;
            re();
          },
        }),
      ),
      pool.length
        ? E(
            "div",
            {
              className: "pf-chips",
            },
            (function () {
              var all = pool.slice().reverse(),
                PG = 8,
                pages = Math.max(1, Math.ceil(all.length / PG)),
                ix = sel
                  ? all.findIndex(function (m) {
                      return m.id === sel.id;
                    })
                  : -1;
              if (H.fpage == null) H.fpage = ix >= 0 ? Math.floor(ix / PG) : 0;
              if (H.fpage > pages - 1) H.fpage = pages - 1;
              self._fp = {
                pages: pages,
                total: all.length,
                PG: PG,
              };
              return all.slice(H.fpage * PG, H.fpage * PG + PG);
            })().map(function (m) {
              var on = sel && sel.id === m.id,
                un = nUn(m),
                n = nChg(m),
                st = per[m.id];
              return E(
                "button",
                {
                  type: "button",
                  key: m.id,
                  className: "pf-chip" + (on ? " on" : ""),
                  onClick: function () {
                    H.fmid = m.id;
                    re();
                  },
                },
                E(
                  "small",
                  null,
                  (m.date || "").replace(/-/g, ".") + (st ? " · " + st : ""),
                ),
                E("b", null, m.title),
                E(
                  "span",
                  {
                    className: "pf-chipb",
                  },
                  n
                    ? E(
                        "em",
                        {
                          className: "pf-badge",
                        },
                        "요구·변경 " + n,
                      )
                    : null,
                  un
                    ? E(
                        "em",
                        {
                          className: "pf-badge warn",
                        },
                        "미확인 " + un,
                      )
                    : null,
                  X.at(m)
                    ? E(
                        "em",
                        {
                          className: "pf-badge",
                        },
                        "분석 중",
                      )
                    : null,
                ),
              );
            }),
          )
        : E(
            "p",
            {
              className: "muted",
            },
            "해당하는 회의가 없습니다.",
          ),
      (function () {
        var fp = self._fp || {
          pages: 1,
        };
        if (!pool.length || fp.pages < 2) return null;
        var pg = H.fpage || 0;
        return E(
          "div",
          {
            className: "pager pf-pager",
          },
          E(
            "span",
            null,
            pg * fp.PG +
              1 +
              "–" +
              Math.min(pg * fp.PG + fp.PG, fp.total) +
              " / " +
              fp.total +
              "건",
          ),
          E(
            "button",
            {
              type: "button",
              "aria-label": "이전 회의",
              disabled: pg === 0,
              onClick: function () {
                H.fpage = pg - 1;
                re();
              },
            },
            "‹",
          ),
          Array.from(
            {
              length: fp.pages,
            },
            function (_, i) {
              return E(
                "button",
                {
                  type: "button",
                  key: i,
                  className: i === pg ? "on" : "",
                  onClick: function () {
                    H.fpage = i;
                    re();
                  },
                },
                i + 1,
              );
            },
          ),
          E(
            "button",
            {
              type: "button",
              "aria-label": "다음 회의",
              disabled: pg >= fp.pages - 1,
              onClick: function () {
                H.fpage = pg + 1;
                re();
              },
            },
            "›",
          ),
        );
      })(),
    ),
  );
  var detail = E(
    "section",
    {
      className: "pf-box pf-detail",
    },
    sel
      ? (function () {
          var pts = sel.points || [],
            of = function (kind) {
              return pts.filter(function (x) {
                return x.kind === kind;
              });
            },
            sum = of("핵심 내용")
              .map(function (x) {
                return x.text;
              })
              .join(" "),
            dec0 = [].concat.apply(
              [],
              of("결정사항").map(function (x) {
                var ps = self.split(x.text),
                  ev = x.evidence || [];
                return ps.map(function (t, i) {
                  return {
                    t: t,
                    line: ps.length === ev.length ? ev[i] : null,
                  };
                });
              }),
            ),
            fol = [].concat.apply(
              [],
              of("후속 확인")
                .concat(of("추가 확인"))
                .map(function (x) {
                  return self.split(x.text);
                }),
            ),
            ch = byM[sel.id] || [],
            un = nUn(sel),
            sq = function (t) {
              return String(t || "").replace(/\s+/g, "");
            },
            stop = {
              변경: 1,
              요청: 1,
              유지: 1,
              검토: 1,
              여부: 1,
              희망: 1,
              문의: 1,
              반영: 1,
            },
            toks = function (t) {
              return String(t || "")
                .split(/[\s→+,/()·]+/)
                .map(function (w) {
                  return w.replace(
                    /(으로|로|을|를|이|가|은|는|에|의|함|됨)$/,
                    "",
                  );
                })
                .filter(function (w) {
                  return w.length >= 2 && !stop[w];
                });
            },
            dup = function (d) {
              var D = sq(d);
              return ch.some(function (e) {
                if (D.indexOf(sq(e.title)) < 0) return false;
                var w = toks(e.after);
                if (!w.length) return false;
                var hit = w.filter(function (x) {
                  return D.indexOf(sq(x)) >= 0;
                }).length;
                return hit / w.length >= 0.6;
              });
            },
            cov = (function () {
              var m = {};
              ch.forEach(function (e) {
                (e.evidence || []).forEach(function (l) {
                  m[l] = 1;
                });
              });
              return m;
            })(),
            dec = dec0
              .filter(function (d) {
                return !(d.line && cov[d.line]) && !dup(d.t);
              })
              .map(function (d) {
                return d.t;
              }),
            hid = dec0.length - dec.length,
            grp = (function () {
              var m = {},
                o = [];
              ch.forEach(function (e) {
                var k = sq(e.title);
                if (!m[k]) {
                  m[k] = {
                    key: k,
                    title: e.title,
                    items: [],
                  };
                  o.push(m[k]);
                }
                m[k].items.push(e);
              });
              return o;
            })(),
            stc = function (e) {
              var b = e.business_state;
              return b === "확정"
                ? "ok"
                : b === "보류"
                  ? "hold"
                  : b === "요청"
                    ? "req"
                    : "etc";
            },
            part = function (key, title, items, render, note, cnt) {
              var open = H["fc_" + key] === true;
              return E(
                "div",
                {
                  className: "pf-part",
                },
                E(
                  "button",
                  {
                    type: "button",
                    className: "pf-parthead",
                    onClick: function () {
                      H["fc_" + key] = !open;
                      re();
                    },
                  },
                  E("b", null, (open ? "▾ " : "▸ ") + title),
                  E("small", null, (cnt == null ? items.length : cnt) + "건"),
                ),
                open
                  ? items.length
                    ? E(
                        "ul",
                        {
                          className: "pf-ul-" + key,
                        },
                        items.map(render),
                      )
                    : note
                      ? null
                      : E(
                          "p",
                          {
                            className: "muted",
                          },
                          "없음",
                        )
                  : null,
                open && note
                  ? E(
                      "p",
                      {
                        className: "pf-note",
                      },
                      note,
                    )
                  : null,
              );
            };
          return E(
            X.R.Fragment,
            null,
            E(
              "div",
              {
                className: "pf-head",
              },
              E(
                "div",
                null,
                E(
                  "small",
                  {
                    className: "muted",
                  },
                  (sel.date || "").replace(/-/g, ".") +
                    (per[sel.id] ? " · " + per[sel.id] : ""),
                ),
                E("h2", null, sel.title),
              ),
              E(
                "div",
                {
                  className: "actions",
                },
                canEditStage
                  ? E(
                      "button",
                      {
                        type: "button",
                        className: "button",
                        onClick: function () {
                          var stage = (sd && sd.stage) || "";
                          X.requestStage(sel, S, stage, stage);
                        },
                      },
                      u.user.level === "leader" ? "회의 단계 변경" : "회의 단계 변경 요청",
                    )
                  : null,
                E(
                  "button",
                  {
                    type: "button",
                    className: "rv-btn",
                    onClick: function () {
                      X.Ca(function () {
                        return X.ff(sel.id, []);
                      });
                    },
                  },
                  "원본 보기",
                ),
                un
                  ? E(
                      "button",
                      {
                        type: "button",
                        className: "rv-btn rv-yes",
                        onClick: function () {
                          X.Ca(function () {
                            return X.ff(sel.id, []);
                          });
                        },
                      },
                      "검수 " + un + "건 남음",
                    )
                  : null,
              ),
            ),
            sum
              ? E(
                  "div",
                  {
                    className: "pf-sum2",
                  },
                  E("b", null, "핵심 요약"),
                  E(
                    "p",
                    null,
                    sum
                      .split(/(?<=[.다])\s+/)
                      .slice(0, 3)
                      .join(" "),
                  ),
                )
              : X.at(sel)
                ? E(
                    "p",
                    {
                      className: "muted",
                    },
                    "분석 중입니다.",
                  )
                : null,
            (function () {
              var rx =
                  /^(?:\d+[.)]\s*)?([^:：]{1,24})[:：]\s*(.+?)(?:\s*\/\s*([0-9]{4}[-.][0-9]{1,2}[-.][0-9]{1,2}))?\s*$/,
                fl = fol.map(function (t) {
                  var m = String(t).match(rx);
                  return m
                    ? {
                        who: m[1].trim(),
                        what: m[2],
                        due: m[3] || "",
                      }
                    : {
                        what: String(t).replace(/^\d+[.)]\s*/, ""),
                        who: "",
                        due: "",
                      };
                }),
                order = ["확정", "요청", "보류", "철회"],
                lab = {
                  확정: "합의",
                  요청: "요청",
                  보류: "보류",
                  철회: "철회",
                },
                cls = {
                  확정: "ok",
                  요청: "req",
                  보류: "hold",
                  철회: "etc",
                },
                shut = function (k) {
                  return H["f3_" + k] !== false;
                },
                head = function (t, n, k) {
                  return E(
                    "button",
                    {
                      type: "button",
                      className: "pf3-h" + (shut(k) ? " shut" : ""),
                      "aria-expanded": !shut(k),
                      onClick: function () {
                        H["f3_" + k] = !shut(k);
                        re();
                      },
                    },
                    E(
                      "i",
                      {
                        className: "pf3-tw",
                      },
                      shut(k) ? "▸" : "▾",
                    ),
                    E("b", null, t),
                    E("em", null, n),
                    E("small", null, shut(k) ? "펼치기" : "접기"),
                  );
                };
              return E(
                "div",
                {
                  className: "pf3",
                },
                E(
                  "section",
                  null,
                  head("결정", dec0.length, "dec"),
                  shut("dec")
                    ? null
                    : dec0.length
                      ? E(
                          "ol",
                          {
                            className: "pf3-dec",
                          },
                          dec0.map(function (d, i) {
                            return E(
                              "li",
                              {
                                key: i,
                              },
                              String(d.t).replace(/^\d+[.)]\s*/, ""),
                            );
                          }),
                        )
                      : E(
                          "p",
                          {
                            className: "muted",
                          },
                          "없음",
                        ),
                ),
                E(
                  "section",
                  null,
                  head("요구·변경", ch.length, "chg"),
                  shut("chg")
                    ? null
                    : E(
                        X.R.Fragment,
                        null,
                        ch.length
                          ? order.map(function (st) {
                              var xs = ch.filter(function (e) {
                                return e.business_state === st;
                              });
                              return xs.length
                                ? E(
                                    "div",
                                    {
                                      key: st,
                                      className: "pf3-grp",
                                    },
                                    E(
                                      "div",
                                      {
                                        className: "pf3-gh",
                                      },
                                      E("b", null, lab[st]),
                                      E("span", null, xs.length + "건"),
                                    ),
                                    xs.map(function (e) {
                                      var so = H.srcOpen === e.id;
                                      return E(
                                        "p",
                                        {
                                          key: e.id,
                                          className:
                                            "pf3-chg" +
                                            (e.after_source ? " has" : ""),
                                          title: e.after_source
                                            ? "누르면 원문 문장을 봅니다"
                                            : "",
                                          onClick: function () {
                                            if (e.after_source) {
                                              H.srcOpen = so ? null : e.id;
                                              re();
                                            }
                                          },
                                        },
                                        E("b", null, e.title),
                                        E(
                                          "span",
                                          null,
                                          (e.before ? e.before + " → " : "") +
                                            e.after,
                                          e.after_source
                                            ? E(
                                                "i",
                                                {
                                                  className: "pf-srcmark",
                                                },
                                                so ? " 원문 접기" : " 원문",
                                              )
                                            : null,
                                        ),
                                        so
                                          ? E(
                                              "small",
                                              {
                                                className: "pf-src",
                                              },
                                              e.after_source,
                                            )
                                          : null,
                                      );
                                    }),
                                  )
                                : null;
                            })
                          : E(
                              "p",
                              {
                                className: "muted",
                              },
                              "없음",
                            ),
                        un
                          ? E(
                              "p",
                              {
                                className: "pf-note",
                              },
                              "검수 전 항목 " +
                                un +
                                "건은 확인한 뒤 표시됩니다.",
                            )
                          : null,
                      ),
                ),
                E(
                  "section",
                  null,
                  head("후속 사항", fl.length, "fol"),
                  shut("fol")
                    ? null
                    : fl.length
                      ? E(
                          "table",
                          {
                            className: "pf3-tab",
                          },
                          E(
                            "thead",
                            null,
                            E(
                              "tr",
                              null,
                              E("th", null, "할 일"),
                              E("th", null, "담당"),
                              E("th", null, "기한"),
                            ),
                          ),
                          E(
                            "tbody",
                            null,
                            fl.map(function (r, i) {
                              return E(
                                "tr",
                                {
                                  key: i,
                                },
                                E("td", null, r.what),
                                E(
                                  "td",
                                  {
                                    className: "who",
                                  },
                                  r.who || "미정",
                                ),
                                E(
                                  "td",
                                  {
                                    className: "due",
                                  },
                                  r.due ? r.due.replace(/-/g, ".") : "미정",
                                ),
                              );
                            }),
                          ),
                        )
                      : E(
                          "p",
                          {
                            className: "muted",
                          },
                          "없음",
                        ),
                ),
              );
            })(),
          );
        })()
      : E(
          "p",
          {
            className: "muted",
          },
          "회의를 선택하세요.",
        ),
  );
  var go = function (g) {
    H.tab = "hist";
    H.filter = "all";
    H.cat = H.mt = H.rv = H.q = "";
    H.sel = g.key;
    var i = X.df.indexOf(g);
    H.page = i < 0 ? 0 : Math.floor(i / 10);
    H.open[g.key] = !0;
    re();
    window.scrollTo(0, 0);
  };
  var rows = X.df
    .map(function (g) {
      var lab = self.revs(g.events),
        B = lab.__cur,
        agreed = g.events.filter(function (e) {
          return e.business_state === "확정";
        }),
        shown = B || agreed[agreed.length - 1];
      if (!shown) return null;
      return {
        g: g,
        e: shown,
        ok: !!B,
        label: B ? lab.__label : "미확인",
        after: g.events.slice(g.events.indexOf(shown) + 1).some(function (e) {
          return e.business_state !== "확정";
        }),
      };
    })
    .filter(Boolean)
    .sort(function (a, b) {
      return (
        b.ok - a.ok ||
        a.g.category.localeCompare(b.g.category) ||
        a.g.title.localeCompare(b.g.title)
      );
    });
  var open = X.df.filter(function (g) {
    var l = g.events[g.events.length - 1];
    return l.business_state === "요청" || l.business_state === "보류";
  });
  var side = E(
    "div",
    {
      className: "pf-side",
    },
    E(
      "section",
      {
        className: "pf-box",
      },
      E(
        "div",
        {
          className: "pf-head pf-ohead",
        },
        E(
          "h2",
          null,
          "미결 사항 ",
          E(
            "span",
            {
              className: "pf-scope",
            },
            "프로젝트 전체",
          ),
        ),
        E(
          "small",
          {
            className: "muted",
          },
          open.length + "건",
        ),
        E(
          "p",
          {
            className: "pf-onote",
          },
          "모든 회의를 통틀어 마지막 상태가 요청·보류인 항목입니다. 이후 회의에서 합의되면 빠집니다.",
        ),
      ),
      open.length
        ? E(
            "ul",
            {
              className: "pf-open",
            },
            open.map(function (g) {
              var l = g.events[g.events.length - 1];
              var here =
                sel &&
                g.events.some(function (e) {
                  return e.meeting_id === sel.id;
                });
              return E(
                "li",
                {
                  key: g.key,
                  className: here ? "here" : "",
                },
                E(
                  "button",
                  {
                    type: "button",
                    onClick: function () {
                      go(g);
                    },
                  },
                  E(
                    "em",
                    {
                      className:
                        "pf-st " +
                        (l.business_state === "보류" ? "hold" : "req"),
                    },
                    l.business_state,
                  ),
                  E("b", null, g.title),
                  E(
                    "small",
                    null,
                    (here ? "이 회의 · " : "") +
                      X.vt(l.meeting_date || l.effective_date) +
                      " · " +
                      l.after.slice(0, 70),
                  ),
                ),
              );
            }),
          )
        : E(
            "p",
            {
              className: "muted",
            },
            "미결 사항이 없습니다.",
          ),
    ),
  );
  var pendNote = nPend
    ? E(
        "p",
        {
          className: "pf-pendnote",
        },
        "검수를 마치지 않은 회의록 " +
          nPend +
          "건은 아직 등록 전이라 여기에 나오지 않습니다. 회의록 메뉴에서 검수를 마쳐 주세요.",
      )
    : null;
  if (!ms.length)
    return E(
      "div",
      null,
      pendNote,
      E(
        "p",
        {
          className: "empty",
        },
        "이 프로젝트에 등록된 회의록이 없습니다.",
      ),
    );
  return E(
    "div",
    {
      className: "pf-wrap",
    },
    pendNote,
    time,
    E(
      "div",
      {
        className: "pf pf1",
      },
      detail,
    ),
  );
};
export default workflow;
