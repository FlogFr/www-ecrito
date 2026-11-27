/* Ecrito — carte du voyage et visionneuse photo. */
(function () {
  "use strict";

  var data = window.ECRITO;
  var FLIGHT_KM = 900; // au-delà, le trajet est dessiné comme un vol (arc pointillé)

  var mapEl = document.getElementById("map");
  if (mapEl && window.L && data) initMap(mapEl);
  initLightbox();

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function km(a, b) {
    var r = Math.PI / 180;
    var h = Math.pow(Math.sin((b.lat - a.lat) * r / 2), 2) +
      Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.pow(Math.sin((b.lon - a.lon) * r / 2), 2);
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  // Courbe de Bézier entre deux étapes, bombée vers le nord, pour les vols.
  function arc(a, b) {
    var dLat = b.lat - a.lat, dLon = b.lon - a.lon, k = 0.22;
    var oLat = dLon * k, oLon = -dLat * k;
    if (oLat < 0) { oLat = -oLat; oLon = -oLon; }
    var cLat = (a.lat + b.lat) / 2 + oLat, cLon = (a.lon + b.lon) / 2 + oLon;
    var pts = [];
    for (var i = 0; i <= 40; i++) {
      var t = i / 40, u = 1 - t;
      pts.push([u * u * a.lat + 2 * u * t * cLat + t * t * b.lat, u * u * a.lon + 2 * u * t * cLon + t * t * b.lon]);
    }
    return pts;
  }

  function initMap(el) {
    var stages = data.stages;
    var isPost = el.dataset.mode === "post";
    var current = isPost ? stages[Number(el.dataset.current) - 1] : null;

    // Sur mobile, la carte de l'article s'insère dans le fil du texte.
    var slot = document.querySelector(".post__map-mobile");
    var aside = el.parentNode;
    var mq = window.matchMedia("(max-width: 959px)");
    var map;
    function place() {
      var target = mq.matches && slot ? slot : aside;
      if (el.parentNode !== target) target.appendChild(el);
      if (map) map.invalidateSize();
    }
    place();
    if (mq.addEventListener) mq.addEventListener("change", place);

    map = L.map(el, {
      zoomControl: true,
      scrollWheelZoom: true,
      dragging: !(isPost && mq.matches && L.Browser.mobile),
      zoomSnap: 0.25
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);

    // Cadrage
    var asia = stages.filter(function (s) { return s.country !== "France"; });
    var allBounds = L.latLngBounds(asia.map(function (s) { return [s.lat, s.lon]; }));
    function showAll() { map.fitBounds(allBounds, { paddingTopLeft: [40, 40], paddingBottomRight: [40, current ? 40 : 110] }); }
    function showCurrent() { map.setView([current.lat, current.lon], 7); }
    var frame = current ? showCurrent : showAll;
    frame();
    // Carte initialisée sans taille (onglet masqué…) : on recadre dès qu'elle en a une.
    if (!map.getSize().x) map.once("resize", frame);

    // Tracé : un segment par trajet, couleur du pays d'arrivée.
    for (var i = 1; i < stages.length; i++) {
      var a = stages[i - 1], b = stages[i];
      var flight = km(a, b) > FLIGHT_KM;
      var near = current && (a === current || b === current);
      var dim = current && !near;
      var line = flight ? arc(a, b) : [[a.lat, a.lon], [b.lat, b.lon]];
      var color = data.colors[b.country];
      if (!flight) {
        L.polyline(line, { color: "#fff", weight: 7, opacity: dim ? 0.4 : 0.8, interactive: false }).addTo(map);
      }
      L.polyline(line, {
        color: color,
        weight: flight ? 2.5 : 4,
        opacity: dim ? 0.45 : 0.95,
        dashArray: flight ? "2 8" : null,
        lineCap: "round",
        interactive: false
      }).addTo(map);
    }

    // Pins cliquables, avec le titre de l'étape.
    var pins = stages.map(function (s) {
      var html = '<a class="pin' + (s === current ? " is-current" : "") + '" href="' + s.url +
        '" style="--c:' + data.colors[s.country] + '" aria-label="' + esc(s.title) + '">' +
        '<span class="pin__dot">' + s.n + '</span><span class="pin__label">' + esc(s.label) + '</span></a>';
      var marker = L.marker([s.lat, s.lon], {
        icon: L.divIcon({ className: "pin-icon", html: html, iconSize: [24, 24], iconAnchor: [12, 12] }),
        keyboard: false,
        riseOnHover: true,
        zIndexOffset: s === current ? 2000 : 0
      }).addTo(map);
      if (s !== current) {
        marker.bindTooltip(
          (s.cover ? '<img src="' + s.cover + '" alt="">' : "") +
          '<span class="pin-tip__body"><span class="pin-tip__date">Étape ' + s.n + " · " + esc(s.date) +
          '</span><span class="pin-tip__title">' + esc(s.title) + "</span></span>",
          { direction: "top", offset: [0, -16], className: "pin-tip", opacity: 1 }
        );
      }
      marker.on("click", function () { window.location.href = s.url; });
      var root = marker.getElement().querySelector(".pin");
      return { stage: s, marker: marker, el: root, label: root.querySelector(".pin__label"), dot: root.querySelector(".pin__dot") };
    });

    if (current) {
      var Toggle = L.Control.extend({
        options: { position: "topright" },
        onAdd: function () {
          var btn = L.DomUtil.create("button", "map-toggle");
          var all = false;
          btn.type = "button";
          btn.textContent = "Tout le voyage";
          L.DomEvent.disableClickPropagation(btn);
          L.DomEvent.on(btn, "click", function () {
            all = !all;
            if (all) showAll(); else showCurrent();
            btn.textContent = all ? "Recentrer sur l'étape" : "Tout le voyage";
          });
          return btn;
        }
      });
      map.addControl(new Toggle());
    }

    // Masque les titres qui se chevauchent ; d'autres apparaissent en zoomant.
    var order = pins.slice();
    if (current) {
      order.sort(function (p, q) { return km(p.stage, current) - km(q.stage, current); });
    }
    function overlaps(r, rects, box) {
      if (r.left < box.left || r.right > box.right || r.top < box.top || r.bottom > box.bottom) return true;
      for (var i = 0; i < rects.length; i++) {
        var o = rects[i];
        if (r.left < o.right + 2 && r.right > o.left - 2 && r.top < o.bottom + 2 && r.bottom > o.top - 2) return true;
      }
      return false;
    }
    function declutter() {
      var box = el.getBoundingClientRect();
      var placed = pins.map(function (p) { return p.dot.getBoundingClientRect(); });
      order.forEach(function (p) {
        p.el.classList.remove("pin--left");
        p.label.classList.remove("is-hidden");
        p.label.style.maxWidth = "";
        if (!overlaps(p.label.getBoundingClientRect(), placed, box)) {
          placed.push(p.label.getBoundingClientRect());
          return;
        }
        p.el.classList.add("pin--left");
        if (!overlaps(p.label.getBoundingClientRect(), placed, box)) {
          placed.push(p.label.getBoundingClientRect());
          return;
        }
        p.el.classList.remove("pin--left");
        if (p.stage !== current) {
          p.label.classList.add("is-hidden");
          return;
        }
        // L'étape en cours garde toujours son titre, raccourci du côté le plus large.
        var dot = p.dot.getBoundingClientRect();
        var right = box.right - dot.right, left = dot.left - box.left;
        p.el.classList.toggle("pin--left", left > right);
        p.label.style.maxWidth = Math.max(48, Math.max(left, right) - 22) + "px";
        placed.push(p.label.getBoundingClientRect());
      });
    }
    var queued = false;
    function schedule() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { queued = false; declutter(); });
    }
    map.on("zoomend moveend resize", schedule);
    map.whenReady(schedule);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);

    // Accueil : survoler une étape de la liste la met en avant sur la carte.
    var active = null;
    function setActive(n) {
      if (active) {
        active.el.classList.remove("is-active");
        active.marker.setZIndexOffset(0);
      }
      active = n ? pins[n - 1] : null;
      if (!active) return;
      active.el.classList.add("is-active");
      active.marker.setZIndexOffset(1000);
      var ll = active.marker.getLatLng();
      if (!map.getBounds().pad(-0.1).contains(ll)) map.panTo(ll);
    }
    document.querySelectorAll("[data-stage]").forEach(function (card) {
      var n = Number(card.dataset.stage);
      card.addEventListener("mouseenter", function () { setActive(n); });
      card.addEventListener("focus", function () { setActive(n); });
      card.addEventListener("mouseleave", function () { setActive(null); });
      card.addEventListener("blur", function () { setActive(null); });
    });
    pins.forEach(function (p) {
      p.marker.on("mouseover", function () {
        var card = document.querySelector('[data-stage="' + p.stage.n + '"]');
        if (card) card.classList.add("is-active");
      });
      p.marker.on("mouseout", function () {
        var card = document.querySelector('[data-stage="' + p.stage.n + '"]');
        if (card) card.classList.remove("is-active");
      });
    });
  }

  function initLightbox() {
    var links = Array.prototype.slice.call(document.querySelectorAll("a[data-lightbox]"));
    if (!links.length) return;

    var box = document.createElement("div");
    box.className = "lightbox";
    box.hidden = true;
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Photos");
    box.innerHTML =
      '<img class="lightbox__img" alt="">' +
      '<button class="lightbox__close" type="button" aria-label="Fermer">&times;</button>' +
      '<button class="lightbox__prev" type="button" aria-label="Photo précédente">&#8249;</button>' +
      '<button class="lightbox__next" type="button" aria-label="Photo suivante">&#8250;</button>' +
      '<p class="lightbox__count"></p>';
    document.body.appendChild(box);

    var img = box.querySelector(".lightbox__img");
    var count = box.querySelector(".lightbox__count");
    var index = 0, opener = null;

    function show(i) {
      index = (i + links.length) % links.length;
      img.src = links[index].href;
      count.textContent = (index + 1) + " / " + links.length;
      [index - 1, index + 1].forEach(function (j) {
        new Image().src = links[(j + links.length) % links.length].href;
      });
    }
    function open(i) {
      opener = document.activeElement;
      box.hidden = false;
      document.documentElement.style.overflow = "hidden";
      show(i);
      box.querySelector(".lightbox__close").focus();
    }
    function close() {
      box.hidden = true;
      img.removeAttribute("src");
      document.documentElement.style.overflow = "";
      if (opener) opener.focus();
    }

    links.forEach(function (link, i) {
      link.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey) return;
        e.preventDefault();
        open(i);
      });
    });
    box.querySelector(".lightbox__close").addEventListener("click", close);
    box.querySelector(".lightbox__prev").addEventListener("click", function () { show(index - 1); });
    box.querySelector(".lightbox__next").addEventListener("click", function () { show(index + 1); });
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", function (e) {
      if (box.hidden) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") show(index - 1);
      else if (e.key === "ArrowRight") show(index + 1);
    });

    var startX = null;
    box.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", function (e) {
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
      else if (e.target === img) show(index + 1);
    });
  }
})();
