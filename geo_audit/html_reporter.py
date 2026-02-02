from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _bool_cell(v: Any) -> int:
    return 1 if bool(v) else 0


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure row is JSON-serializable and has expected types.
    """
    out: Dict[str, Any] = {}

    out["url"] = _safe_str(row.get("url")).strip()
    out["title"] = _safe_str(row.get("title")).strip()
    out["score"] = _safe_int(row.get("score"), 0)

    for k in [
        "direct_answer",
        "definition",
        "headings",
        "facts",
        "sources",
        "faq",
        "lists",
        "tables",
        "word_count_ok",
        "meta_ok",
    ]:
        out[k] = _safe_int(row.get(k), _bool_cell(row.get(k)))

    out["word_count"] = _safe_int(row.get("word_count"), 0)
    out["h2_count"] = _safe_int(row.get("h2_count"), 0)
    out["list_count"] = _safe_int(row.get("list_count"), 0)
    out["table_count"] = _safe_int(row.get("table_count"), 0)
    out["meta_len"] = _safe_int(row.get("meta_len"), 0)

    out["recommendations"] = _safe_str(row.get("recommendations")).replace("\n", " ").replace("\r", " ").strip()

    return out


def write_html_report(output_path: Path, rows: Iterable[Dict[str, Any]], *, page_size: int = 10) -> None:
    """
    Single HTML report:
      - client-side pagination
      - sticky header for column labels
      - renders only the visible page (fast for 1000+)
      - truncated recommendations with modal "more" view
      - score color bands: 0–4 red, 5–7 orange, 8–10 green
      - average score of currently displayed rows (after filtering), color-coded
    """
    ensure_parent_dir(output_path)

    page_size = max(1, int(page_size))
    data: List[Dict[str, Any]] = [_sanitize_row(r) for r in list(rows)]

    # Default sort: highest score first, then title
    data.sort(key=lambda x: (-_safe_int(x.get("score"), 0), (x.get("title") or "").lower()))

    columns = [
        ("score", "Skóre"),
        ("direct_answer", "Priama odpoveď v úvode"),
        ("definition", "Obsahuje definíciu"),
        ("headings", "Štruktúrované nadpisy"),
        ("facts", "Obsahuje fakty a čísla"),
        ("sources", "Citácie zdrojov"),
        ("faq", "FAQ sekcia"),
        ("lists", "Obsahuje zoznamy"),
        ("tables", "Obsahuje tabuľku"),
        ("word_count_ok", "Dostatočná dĺžka"),
        ("meta_ok", "Meta description"),
        ("word_count", "Slová"),
        ("h2_count", "H2 #"),
        ("list_count", "Listy #"),
        ("table_count", "Tabuľky #"),
        ("meta_len", "Meta dĺžka"),
        ("recommendations", "Odporúčania"),
    ]


    payload = {
        "pageSize": page_size,
        "rows": data,
        "columns": columns,
        "generatedCount": len(data),
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    html_doc = f"""<!doctype html>
<html lang="sk">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>GEO Audit Report</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --card: #101824;
      --text: #e6edf3;
      --muted: #9fb0c0;
      --border: #203041;
      --pill: #152232;
      --link: #7dd3fc;
      --shadow: 0 10px 30px rgba(0,0,0,.35);

      --good: #1f6f43;
      --warn: #b26a00;
      --bad:  #7a2323;

      --goodBg: rgba(31,111,67,.25);
      --warnBg: rgba(178,106,0,.25);
      --badBg:  rgba(122,35,35,.25);
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: var(--bg);
      color: var(--text);
    }}

    .wrap {{
      max-width: 1400px;
      margin: 24px auto;
      padding: 0 16px 24px 16px;
    }}

    .header {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }}

    .title {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .title h1 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.2px;
    }}

    .sub {{
      color: var(--muted);
      font-size: 13px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}

    .avg {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid rgba(32,48,65,.8);
      background: rgba(255,255,255,.03);
    }}
    .avg .label {{ color: var(--muted); }}
    .avg .value {{
      font-weight: 700;
      letter-spacing: .2px;
    }}
    .avg .value.good {{ color: #5ee7a8; }}
    .avg .value.warn {{ color: #ffbe5c; }}
    .avg .value.bad  {{ color: #ff8b8b; }}

    .controls {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
    }}

    .input {{
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 10px;
      outline: none;
      min-width: 320px;
    }}
    .input:focus {{
      border-color: #2a4056;
    }}

    .btn {{
      background: var(--pill);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 10px;
      border-radius: 10px;
      cursor: pointer;
      user-select: none;
      display: inline-flex;
      gap: 8px;
      align-items: center;
      justify-content: center;
    }}
    .btn:hover {{
      border-color: #2a4056;
    }}
    .btn:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}

    .iconBtn {{
      padding: 6px 8px;
      border-radius: 10px;
      border: 1px solid rgba(32,48,65,.9);
      background: rgba(255,255,255,.03);
      color: var(--text);
      cursor: pointer;
    }}
    .iconBtn:hover {{
      border-color: #2a4056;
    }}

    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .table-wrap {{
      overflow: auto;
      max-height: calc(100vh - 220px);
    }}

    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      min-width: 1200px;
    }}

    thead th {{
      position: sticky;
      top: 0;
      z-index: 5;
      background: #0f1a27;
      border-bottom: 1px solid var(--border);
      padding: 10px 10px;
      font-size: 12px;
      text-align: left;
      color: #cfe2f3;
      white-space: nowrap;
    }}

    tbody td {{
      border-bottom: 1px solid rgba(32,48,65,.55);
      padding: 10px 10px;
      font-size: 13px;
      vertical-align: top;
    }}

    tbody tr:hover td {{
      background: rgba(255,255,255,.02);
    }}

    .col-url {{ max-width: 360px; }}
    .col-title {{ max-width: 320px; }}

    a {{
      color: var(--link);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}

    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 2px 10px;
      border-radius: 999px;
      background: var(--pill);
      border: 1px solid rgba(32,48,65,.8);
      font-size: 12px;
      min-width: 42px;
    }}
    .pill.good {{
      background: var(--goodBg);
      border-color: rgba(31,111,67,.55);
    }}
    .pill.bad {{
      background: var(--badBg);
      border-color: rgba(122,35,35,.55);
    }}

    /* Score pills: 0-4 bad, 5-7 warn, 8-10 good */
    .scorePill {{
      font-weight: 800;
      min-width: 46px;
    }}
    .scorePill.good {{
      background: var(--goodBg);
      border-color: rgba(31,111,67,.55);
      color: #5ee7a8;
    }}
    .scorePill.warn {{
      background: var(--warnBg);
      border-color: rgba(178,106,0,.55);
      color: #ffbe5c;
    }}
    .scorePill.bad {{
      background: var(--badBg);
      border-color: rgba(122,35,35,.55);
      color: #ff8b8b;
    }}

    .muted {{
      color: var(--muted);
      font-size: 12px;
    }}

    .pager {{
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-top: 1px solid var(--border);
      background: rgba(255,255,255,.01);
    }}
    .pager .left, .pager .right {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}

    .select {{
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 10px;
      outline: none;
    }}

    .note {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}

    .recCell {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      justify-content: space-between;
    }}
    .recPreview {{
      color: #d7e3ee;
      max-width: 520px;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;          /* show 2 lines max */
      -webkit-box-orient: vertical;
      line-height: 1.35;
    }}
    .recMeta {{
      display: inline-flex;
      gap: 6px;
      align-items: center;
      flex-shrink: 0;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 26px;
      padding: 2px 8px;
      font-size: 12px;
      border-radius: 999px;
      border: 1px solid rgba(32,48,65,.85);
      background: rgba(255,255,255,.03);
      color: var(--text);
      font-weight: 700;
    }}

    /* Modal */
    .modalOverlay {{
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.55);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 18px;
      z-index: 50;
    }}
    .modalOverlay.open {{
      display: flex;
    }}
    .modal {{
      width: min(980px, 100%);
      max-height: min(80vh, 900px);
      overflow: auto;
      background: #0f1a27;
      border: 1px solid rgba(32,48,65,.9);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }}
    .modalHeader {{
      position: sticky;
      top: 0;
      background: #0f1a27;
      border-bottom: 1px solid rgba(32,48,65,.9);
      padding: 14px 16px;
      display: flex;
      gap: 12px;
      align-items: flex-start;
      justify-content: space-between;
      z-index: 1;
    }}
    .modalTitle {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .modalTitle .h {{
      font-size: 16px;
      font-weight: 800;
      margin: 0;
      line-height: 1.25;
    }}
    .modalTitle .u {{
      font-size: 12px;
      color: var(--muted);
      word-break: break-all;
    }}
    .modalBody {{
      padding: 14px 16px 18px 16px;
      line-height: 1.5;
    }}
    .recList {{
      margin: 10px 0 0 18px;
      padding: 0;
    }}
    .recList li {{
      margin: 6px 0;
    }}
    .metaRow {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div class="title">
        <h1>GEO Audit Report</h1>
        <div class="sub">
          <span>Počet článkov: <span id="count"></span></span>
          <span>Stránka: <span id="pageInfo"></span></span>
          <span class="avg">
            <span class="label">Priemer (zobrazené):</span>
            <span id="avgScore" class="value">0.0</span>
          </span>
        </div>
      </div>

      <div class="controls">
        <input id="q" class="input" placeholder="Filtrovať (URL, title, odporúčania)..." />
        <select id="sort" class="select" title="Sort">
          <option value="score_desc">Skóre (desc)</option>
          <option value="score_asc">Skóre (asc)</option>
          <option value="title_asc">Title (A→Z)</option>
          <option value="title_desc">Title (Z→A)</option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="col-url">URL</th>
              <th class="col-title">Title</th>
              {''.join([f"<th>{label}</th>" for _, label in columns])}
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>

      <div class="pager">
        <div class="left">
          <button id="prev" class="btn">← Predchádzajúca</button>
          <button id="next" class="btn">Ďalšia →</button>
          <span class="muted">Zobrazené: <span id="shown"></span></span>
        </div>
        <div class="right">
          <span class="muted">Stránka</span>
          <select id="pageSelect" class="select" title="Page select"></select>
          <span class="muted">Page size:</span>
          <select id="pageSize" class="select" title="Page size">
            <option value="10" selected>10</option>
            <option value="20">20</option>
            <option value="50">50</option>
          </select>
        </div>
      </div>
    </div>

    <div class="note">
      Tip: „Odporúčania“ sú skrátené – klikni na <code>▸</code> pre celý detail. Hlavička stĺpcov je sticky (pri scrollovaní zostáva hore).
      Pre veľké vstupy (napr. 1000 článkov) sa renderuje vždy len aktuálna stránka.
    </div>
  </div>

  <!-- Modal -->
  <div id="modalOverlay" class="modalOverlay" role="dialog" aria-modal="true" aria-hidden="true">
    <div class="modal">
      <div class="modalHeader">
        <div class="modalTitle">
          <div id="modalTitle" class="h">Detail odporúčaní</div>
          <div class="u"><a id="modalUrl" href="#" target="_blank" rel="noopener noreferrer"></a></div>
          <div class="metaRow">
            <span>Skóre:</span>
            <span id="modalScore"></span>
          </div>
        </div>
        <button id="modalClose" class="btn">Zavrieť</button>
      </div>
      <div class="modalBody">
        <div class="muted">Odporúčania:</div>
        <ul id="modalRecs" class="recList"></ul>
      </div>
    </div>
  </div>

  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    (function() {{
      const payload = JSON.parse(document.getElementById("payload").textContent);
      let rows = payload.rows || [];
      const columns = payload.columns || [];
      let pageSize = payload.pageSize || 10;
      let pageIndex = 0;

      const elCount = document.getElementById("count");
      const elPageInfo = document.getElementById("pageInfo");
      const elShown = document.getElementById("shown");
      const elBody = document.getElementById("tbody");
      const elAvgScore = document.getElementById("avgScore");

      const elQ = document.getElementById("q");
      const elSort = document.getElementById("sort");
      const elPrev = document.getElementById("prev");
      const elNext = document.getElementById("next");
      const elPageSelect = document.getElementById("pageSelect");
      const elPageSize = document.getElementById("pageSize");

      // Modal elements
      const modalOverlay = document.getElementById("modalOverlay");
      const modalClose = document.getElementById("modalClose");
      const modalTitle = document.getElementById("modalTitle");
      const modalUrl = document.getElementById("modalUrl");
      const modalScore = document.getElementById("modalScore");
      const modalRecs = document.getElementById("modalRecs");

      // Working set after filter/sort
      let view = rows.slice();

      function esc(s) {{
        return (s ?? "").toString()
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }}

      function scoreBand(score) {{
        const s = parseInt(score, 10) || 0;
        if (s <= 4) return "bad";
        if (s <= 7) return "warn";
        return "good";
      }}

      function scorePill(score) {{
        const s = parseInt(score, 10) || 0;
        const band = scoreBand(s);
        return `<span class="pill scorePill ${{band}}">${{s}}</span>`;
      }}

      function avgBand(avg) {{
        const a = Number(avg) || 0;
        if (a <= 4.999) return "bad";
        if (a <= 7.999) return "warn";
        return "good";
      }}

      function pill01(v) {{
        const ok = (parseInt(v, 10) || 0) === 1;
        const cls = ok ? "pill good" : "pill bad";
        const txt = ok ? "1" : "0";
        return `<span class="${{cls}}">${{txt}}</span>`;
      }}

      function sortView(mode) {{
        if (mode === "score_desc") {{
          view.sort((a,b) => (b.score||0) - (a.score||0) || (a.title||"").localeCompare(b.title||""));
        }} else if (mode === "score_asc") {{
          view.sort((a,b) => (a.score||0) - (b.score||0) || (a.title||"").localeCompare(b.title||""));
        }} else if (mode === "title_asc") {{
          view.sort((a,b) => (a.title||"").localeCompare(b.title||""));
        }} else if (mode === "title_desc") {{
          view.sort((a,b) => (b.title||"").localeCompare(a.title||""));
        }}
      }}

      function recCount(recs) {{
        const s = (recs || "").toString().trim();
        if (!s) return 0;
        // recommendations are joined with " | "
        return s.split("|").map(x => x.trim()).filter(Boolean).length;
      }}

      function recPreview(recs, maxChars = 120) {{
        const s = (recs || "").toString().trim();
        if (!s) return "";
        if (s.length <= maxChars) return s;
        return s.slice(0, maxChars).trim() + "…";
      }}

      function computeAverage() {{
        if (!view.length) return 0;
        let sum = 0;
        for (const r of view) sum += (parseInt(r.score, 10) || 0);
        return sum / view.length;
      }}

      function renderAverage() {{
        const avg = computeAverage();
        const txt = avg.toFixed(1).replace(".", ",");
        elAvgScore.textContent = txt;
        elAvgScore.classList.remove("good","warn","bad");
        elAvgScore.classList.add(avgBand(avg));
      }}

      function applyFilter() {{
        const q = (elQ.value || "").trim().toLowerCase();
        if (!q) {{
          view = rows.slice();
        }} else {{
          view = rows.filter(r => {{
            const hay = `${{r.url||""}} ${{r.title||""}} ${{r.recommendations||""}}`.toLowerCase();
            return hay.includes(q);
          }});
        }}
        sortView(elSort.value);
        pageIndex = 0;
        render();
      }}

      function pageCount() {{
        return Math.max(1, Math.ceil(view.length / pageSize));
      }}

      function clampPage() {{
        const pc = pageCount();
        if (pageIndex < 0) pageIndex = 0;
        if (pageIndex >= pc) pageIndex = pc - 1;
      }}

      function renderPageSelect() {{
        const pc = pageCount();
        elPageSelect.innerHTML = "";
        for (let i=0; i<pc; i++) {{
          const opt = document.createElement("option");
          opt.value = String(i);
          opt.textContent = String(i + 1);
          elPageSelect.appendChild(opt);
        }}
        elPageSelect.value = String(pageIndex);
      }}

      function openModal(row) {{
        const title = (row.title || "").toString();
        const url = (row.url || "").toString();
        const score = parseInt(row.score, 10) || 0;
        const recs = (row.recommendations || "").toString().trim();

        modalTitle.textContent = title || "Detail odporúčaní";
        modalUrl.textContent = url || "";
        modalUrl.href = url || "#";

        modalScore.innerHTML = scorePill(score);

        // Build list items from " | " separated recs
        modalRecs.innerHTML = "";
        const items = recs
          ? recs.split("|").map(x => x.trim()).filter(Boolean)
          : [];

        if (!items.length) {{
          const li = document.createElement("li");
          li.textContent = "Žiadne odporúčania.";
          modalRecs.appendChild(li);
        }} else {{
          for (const it of items) {{
            const li = document.createElement("li");
            li.textContent = it;
            modalRecs.appendChild(li);
          }}
        }}

        modalOverlay.classList.add("open");
        modalOverlay.setAttribute("aria-hidden", "false");
      }}

      function closeModal() {{
        modalOverlay.classList.remove("open");
        modalOverlay.setAttribute("aria-hidden", "true");
      }}

      function render() {{
        clampPage();
        renderPageSelect();
        renderAverage();

        const start = pageIndex * pageSize;
        const end = Math.min(view.length, start + pageSize);
        const slice = view.slice(start, end);

        elBody.innerHTML = slice.map((r, idx) => {{
          const url = esc(r.url || "");
          const title = esc(r.title || "");
          const urlCell = url ? `<a href="${{url}}" target="_blank" rel="noopener noreferrer">${{url}}</a>` : "";
          const titleCell = title || "";

          const colsHtml = columns.map(([key, _label]) => {{
            const v = r[key];

            const isCriterion = [
              "direct_answer","definition","headings","facts","sources","faq","lists","tables","word_count_ok","meta_ok"
            ].includes(key);

            if (key === "score") return `<td>${{scorePill(v)}}</td>`;
            if (isCriterion) return `<td>${{pill01(v)}}</td>`;

            if (key === "recommendations") {{
              const recs = (r.recommendations || "").toString();
              const cnt = recCount(recs);
              const preview = esc(recPreview(recs, 140));
              const btn = cnt > 0
                ? `<button class="iconBtn" data-action="more" data-idx="${{start + idx}}" title="Zobraziť celé odporúčania">▸</button>`
                : `<button class="iconBtn" disabled title="Žiadne odporúčania">▸</button>`;
              const badge = `<span class="badge" title="Počet odporúčaní">${{cnt}}</span>`;
              return `<td>
                <div class="recCell">
                  <div class="recPreview">${{preview}}</div>
                  <div class="recMeta">${{badge}}${{btn}}</div>
                </div>
              </td>`;
            }}

            return `<td>${{esc(v ?? "")}}</td>`;
          }}).join("");

          return `<tr>
            <td class="col-url">${{urlCell}}</td>
            <td class="col-title">${{titleCell}}</td>
            ${{colsHtml}}
          </tr>`;
        }}).join("");

        const pc = pageCount();
        elCount.textContent = view.length.toString();
        elPageInfo.textContent = `${{pageIndex + 1}} / ${{pc}}`;
        elShown.textContent = view.length ? `${{start + 1}}–${{end}} z ${{view.length}}` : `0–0 z 0`;

        elPrev.disabled = pageIndex <= 0;
        elNext.disabled = pageIndex >= pc - 1;
      }}

      // Delegate click for "more" buttons
      document.addEventListener("click", (ev) => {{
        const t = ev.target;
        if (!(t instanceof HTMLElement)) return;

        const action = t.getAttribute("data-action");
        if (action === "more") {{
          const idx = parseInt(t.getAttribute("data-idx") || "0", 10) || 0;
          const row = view[idx];
          if (row) openModal(row);
        }}
      }});

      // Modal close behaviors
      modalClose.addEventListener("click", closeModal);
      modalOverlay.addEventListener("click", (ev) => {{
        if (ev.target === modalOverlay) closeModal();
      }});
      document.addEventListener("keydown", (ev) => {{
        if (ev.key === "Escape") closeModal();
      }});

      // Events
      elQ.addEventListener("input", () => applyFilter());
      elSort.addEventListener("change", () => {{
        sortView(elSort.value);
        pageIndex = 0;
        render();
      }});
      elPrev.addEventListener("click", () => {{
        pageIndex--;
        render();
      }});
      elNext.addEventListener("click", () => {{
        pageIndex++;
        render();
      }});
      elPageSelect.addEventListener("change", () => {{
        pageIndex = parseInt(elPageSelect.value, 10) || 0;
        render();
      }});
      elPageSize.addEventListener("change", () => {{
        pageSize = parseInt(elPageSize.value, 10) || 10;
        pageIndex = 0;
        render();
      }});

      // Initial render
      sortView(elSort.value);
      render();
    }})();
  </script>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")
