/* Small Markdown reader for library/opspro-showcase-guide.html: headings, paragraphs, lists,
   tables, rules, `code` and **bold**. It covers the walkthrough only, not general Markdown.
   Raw HTML in the source is shown as text (everything is escaped first). */
(function () {
  var esc = HARTOps.esc;

  function slug(s) {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  // Inline: escape, lift code spans out, bold, put the code back.
  function inline(s) {
    var codes = [];
    s = esc(s).replace(/`([^`]+)`/g, function (m, c) {
      codes.push("<code>" + c + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
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
        out.push("<h" + level + ' id="' + id + '">' + inline(t) +
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

  window.HARTMarkdown = { render: render };
})();
