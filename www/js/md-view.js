/* Small Markdown reader for library/opspro-showcase-guide.html: headings, paragraphs, lists,
   tables, rules, `code` and **bold**. It covers the walkthrough only, not general Markdown.
   Raw HTML in the source is shown as text (everything is escaped first). render() is the general
   reader; renderCases() is the walkthrough pass that splits the guide into cases and sections. */
(function () {
  var esc = HARTOps.esc;

  function slug(s) {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  // Case codes (set only while renderCases runs) that bare U05 / R12 in prose link to.
  var linkSet = null;

  // Inline: escape, lift code spans out, link case codes, bold, put the code back.
  function inline(s, noLink) {
    var codes = [];
    s = esc(s).replace(/`([^`]+)`/g, function (m, c) {
      codes.push("<code>" + c + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    if (linkSet && !noLink) {
      s = s.replace(/\b([UR]\d\d)\b/g, function (m, c) {
        return linkSet[c] ? '<a href="#' + c.toLowerCase() + '">' + c + "</a>" : m;
      });
    }
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return s.replace(/\u0000(\d+)\u0000/g, function (m, i) { return codes[+i]; });
  }

  function cells(line) {
    return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); });
  }

  function isRow(l) { return /^\s*\|.*\|\s*$/.test(l); }
  function isSep(l) { return /^\s*\|[\s:|-]+\|\s*$/.test(l); }

  // Returns {html, headings:[{level,id,text}]}.
  function render(text) {
    var lines = text.replace(/\r\n?/g, "\n").split("\n");
    var out = [], heads = [], i = 0, ids = {};

    function uniq(id) {
      if (!ids[id]) { ids[id] = 1; return id; }
      return id + "-" + (++ids[id]);
    }

    while (i < lines.length) {
      var l = lines[i], m;
      if (!l.trim()) { i++; continue; }

      if ((m = /^(#{1,3})\s+(.*)$/.exec(l))) {
        var level = m[1].length, t = m[2].trim();
        // "U01. Title" gets the id u01, so a case can be linked as #u01.
        var code = /^([UR]\d{2})\.\s/.exec(t);
        var id = uniq(code ? code[1].toLowerCase() : slug(t.replace(/`/g, "")));
        heads.push({ level: level, id: id, text: t });
        out.push("<h" + level + ' id="' + id + '">' + inline(t, true) +
          ' <a class="anchor" href="#' + id + '" aria-label="Link to this heading">#</a></h' + level + ">");
        i++;
      } else if (/^-{3,}\s*$/.test(l)) {
        out.push("<hr>"); i++;
      } else if (isRow(l) && i + 1 < lines.length && isSep(lines[i + 1])) {
        var head = cells(l), rows = [];
        i += 2;
        while (i < lines.length && isRow(lines[i])) { rows.push(cells(lines[i])); i++; }
        out.push('<div class="table-wrap"><table class="roster"><thead><tr>' +
          head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") +
          "</tr></thead><tbody>" +
          rows.map(function (r) {
            return "<tr>" + r.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
          }).join("") + "</tbody></table></div>");
      } else if (/^\s*(\d+\.|-)\s+/.test(l)) {
        var ordered = /^\s*\d+\./.test(l), items = [];
        while (i < lines.length && /^\s*(\d+\.|-)\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*(\d+\.|-)\s+/, ""));
          i++;
          // wrapped continuation lines
          while (i < lines.length && lines[i].trim() && /^\s{2,}\S/.test(lines[i]) && !/^\s*(\d+\.|-)\s+/.test(lines[i])) {
            items[items.length - 1] += " " + lines[i].trim(); i++;
          }
        }
        out.push((ordered ? "<ol>" : "<ul>") + items.map(function (x) { return "<li>" + inline(x) + "</li>"; }).join("") + (ordered ? "</ol>" : "</ul>"));
      } else {
        // A paragraph runs to the next blank line. In the guide each "**Label:** text" line
        // stands alone, so those lines stay separate instead of running together.
        var para = [];
        while (i < lines.length && lines[i].trim() && !/^(#{1,3})\s/.test(lines[i]) && !/^-{3,}\s*$/.test(lines[i]) &&
               !/^\s*(\d+\.|-)\s+/.test(lines[i]) && !(isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1]))) {
          para.push(lines[i].trim()); i++;
        }
        var cur = [];
        para.forEach(function (p) {
          if (/^\*\*[^*]+\*\*/.test(p) && cur.length) { out.push("<p>" + inline(cur.join(" ")) + "</p>"); cur = []; }
          cur.push(p);
        });
        if (cur.length) out.push("<p>" + inline(cur.join(" ")) + "</p>");
      }
    }
    return { html: out.join("\n"), headings: heads };
  }

  // —— Case-aware pass for the walkthrough ——
  // The guide is a run of "### U01. Title" cases, each with labelled lines. This pass splits
  // it into cases and the other sections, and leaves render() above as it was.
  var LABELS = { "What you can build": "what", "How it works": "how", "Find it": "find",
                 "See it work": "see", "Try this": "tryit" };

  // "Find it" names become tags; prose between them stays as text.
  function findHtml(s) {
    var out = [], re = /`([^`]+)`/g, last = 0, m;
    function prose(t) {
      t = t.trim();
      if (!t.replace(/[\s,;.\u00b7]+/g, "").replace(/^(and|or)$/i, "")) return;
      out.push('<span class="find-note">' + inline(t.replace(/^[,;\s]+|[,;\s]+$/g, ""), true) + "</span>");
    }
    while ((m = re.exec(s))) {
      prose(s.slice(last, m.index));
      out.push('<code class="tag">' + esc(m[1]) + "</code>");
      last = re.lastIndex;
    }
    prose(s.slice(last));
    return out.join(" ");
  }

  // Drops the guide's "Heading | What it gives you" table (the page's key replaces it)
  // and the sentence that introduces it. Every other table stays.
  function dropKeyTable(lines) {
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      if (isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1]) && /^heading$/i.test(cells(lines[i])[0])) {
        while (i < lines.length && isRow(lines[i])) i++;
        i--;
        for (var j = out.length - 1; j >= 0; j--) {
          if (!out[j].trim()) continue;
          if (/:\s*$/.test(out[j])) out.length = j;
          break;
        }
        continue;
      }
      out.push(lines[i]);
    }
    return out;
  }

  function parseCase(c) {
    var r = { code: c.code, id: c.code.toLowerCase(), title: inline(c.title, true), titleText: c.title,
              what: "", how: "", find: "", see: "", tryit: "", other: "", fallback: "" };
    var raw = {}, other = [], target = null, m;
    c.lines.forEach(function (l) {
      if (!l.trim()) { target = null; return; }
      if ((m = /^\*\*([^*:]+):\*\*\s*(.*)$/.exec(l))) {
        var key = LABELS[m[1].trim()];
        if (key && raw[key] === undefined) { raw[key] = m[2].trim(); target = key; }
        else { other.push(l); target = null; }
      } else if (target && !/^\s*(\d+\.|-|#)\s*/.test(l)) {
        raw[target] += " " + l.trim();
      } else {
        other.push(l); target = null;
      }
    });
    r.what = raw.what === undefined ? "" : inline(raw.what, true);
    r.how = raw.how === undefined ? "" : inline(raw.how);
    r.find = raw.find === undefined ? "" : findHtml(raw.find);
    r.see = raw.see === undefined ? "" : inline(raw.see);
    r.tryit = raw.tryit === undefined ? "" : inline(raw.tryit);
    r.other = other.length ? render(other.join("\n")).html : "";
    r.fallback = render(c.lines.join("\n")).html;
    return r;
  }

  // Returns {cases:[{code,id,title,what,how,find,see,tryit,other,fallback}], sections:[{id,title,html}]}.
  // Sections are the guide's "##" parts other than "Part N"; text before the first one is
  // the "intro" section. Nothing in the guide is dropped except the key table, rules and Part headings.
  function renderCases(text) {
    var lines = text.replace(/\r\n?/g, "\n").split("\n");
    var cases = [], secs = [], cur = null, sec = { title: "", lines: [] }, m;
    secs.push(sec);
    lines.forEach(function (l) {
      if ((m = /^###\s+([UR]\d\d)\.\s*(.*)$/.exec(l))) {
        cur = { code: m[1], title: m[2].trim(), lines: [] };
        cases.push(cur);
      } else if ((m = /^##\s+(.*)$/.exec(l))) {
        cur = null;
        sec = { title: m[1].trim(), lines: [] };
        secs.push(sec);
      } else if (cur) {
        if (!/^#\s/.test(l) && !/^-{3,}\s*$/.test(l)) cur.lines.push(l);
      } else if (!/^#\s/.test(l) && !/^-{3,}\s*$/.test(l)) {
        sec.lines.push(l);
      }
    });
    linkSet = {};
    cases.forEach(function (c) { linkSet[c.code] = 1; });
    try {
      return {
        cases: cases.map(parseCase),
        sections: secs.filter(function (x) { return !/^Part \d/.test(x.title) && x.lines.join("").trim(); })
          .map(function (x) {
            return { id: x.title ? slug(x.title) : "intro", title: x.title,
                     html: render(dropKeyTable(x.lines).join("\n")).html };
          })
      };
    } finally { linkSet = null; }
  }

  window.HARTMarkdown = { render: render, renderCases: renderCases };
})();
