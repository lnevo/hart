// Click-to-play YouTube videos.
// Markup: <div class="video" data-video="<youtube id>"><a href="https://www.youtube.com/watch?v=<id>">Title</a></div>
// The plain link is the no-JavaScript fallback. This script fills in the thumbnail and caption from
// data/videos.json, and loads the YouTube player only when the visitor presses play.
(function () {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  function monthYear(iso) {
    var m = /^(\d{4})-(\d{2})/.exec(iso || "");
    return m ? MONTHS[parseInt(m[2], 10) - 1] + " " + m[1] : "";
  }

  function watchUrl(id) {
    return "https://www.youtube.com/watch?v=" + encodeURIComponent(id);
  }

  function render(el, v) {
    var id = v.id;
    var meta = [monthYear(v.date), v.duration].filter(Boolean).join(" · ");
    el.innerHTML =
      '<a class="video-frame" href="' + esc(watchUrl(id)) + '" aria-label="Play video: ' + esc(v.title) + '">' +
      '<img src="https://i.ytimg.com/vi/' + esc(id) + '/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">' +
      '<span class="video-play" aria-hidden="true"></span>' +
      (v.duration ? '<span class="video-len" aria-hidden="true">' + esc(v.duration) + "</span>" : "") +
      "</a>" +
      '<div class="video-cap">' +
      '<p class="video-title">' + esc(v.title) + "</p>" +
      (v.blurb ? "<p>" + esc(v.blurb) + "</p>" : "") +
      '<p class="video-meta">' + esc(meta) + (meta ? " · " : "") +
      '<a href="' + esc(watchUrl(id)) + '">YouTube</a></p>' +
      "</div>";
    el.classList.add("is-ready");
    var frame = el.querySelector(".video-frame");
    frame.addEventListener("click", function (ev) {
      // Let ctrl/cmd/shift/middle clicks open YouTube as a normal link.
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      var iframe = document.createElement("iframe");
      iframe.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?autoplay=1&rel=0";
      iframe.title = v.title;
      iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
      iframe.allowFullscreen = true;
      iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      var box = document.createElement("div");
      box.className = "video-frame is-playing";
      box.appendChild(iframe);
      frame.replaceWith(box);
      iframe.focus();
    });
  }

  async function mount(root) {
    var slots = (root || document).querySelectorAll("[data-video]");
    if (!slots.length) return;
    var url = (window.HARTOps ? window.HARTOps.base() : "") + "data/videos.json";
    var res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error("videos.json " + res.status);
    var byId = {};
    ((await res.json()).videos || []).forEach(function (v) {
      byId[v.id] = v;
    });
    for (var i = 0; i < slots.length; i++) {
      var v = byId[slots[i].getAttribute("data-video")];
      if (v) render(slots[i], v); // unknown id: leave the plain YouTube link
    }
  }

  window.HARTVideo = { mount: mount };
})();
