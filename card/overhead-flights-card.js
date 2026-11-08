/*
 * Overhead Flights card — shows the Overhead Flights add-on's live map inside any Home Assistant dashboard.
 *
 *   type: custom:overhead-flights-card
 *   title: Flights overhead      # optional; "" hides the header
 *   height: 460                  # px, or any CSS height such as "calc(100vh - 140px)" to fill the screen
 *   tour: true                   # cycle a flight card through each aircraft
 *   labels: compact              # full | compact | off
 *   paths: true                  # also draw every plane's recent track (the touring plane always shows its own)
 *   alerts: true                 # overhead countdown, emergency-squawk banner, unusual aircraft jump the tour (default on)
 *   summary: true                # "Today" strip: flights, overhead, busiest hour, lowest pass, notable visitors (default on)
 *   zoom: 8                      # optional fixed zoom (default: fit the add-on's range)
 *   radius: 60                   # optional: fit this many km around home instead
 *   slug: local_overhead_flights # optional; found automatically
 *   margin: "0 12px 12px"        # optional CSS margin around the card (e.g. to line up with a custom board)
 *
 * The add-on sits behind Home Assistant's Ingress, so the card opens an Ingress session the same way
 * Home Assistant's own add-on panels do. That needs an administrator account.
 */
const OFC_VERSION = "1.3.0";
const ofcHeight = (h) => (typeof h === "number" || /^\d+$/.test(String(h ?? ""))) ? `${Number(h) || 460}px` : String(h);
const ofcPx = (h) => (typeof h === "number" ? h : parseInt(h, 10)) || 460;

class OverheadFlightsCard extends HTMLElement {
  setConfig(config) {
    this._config = { title: "Flights overhead", height: 460, tour: true, labels: "compact", ...config };
    this._built = false;
    if (this._hass) this._build();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built && this._config) this._build();
  }

  getCardSize() { return Math.ceil(ofcPx(this._config?.height) / 50) + 1; }
  getGridOptions() { return { columns: "full", rows: Math.ceil(ofcPx(this._config?.height) / 56) + 1 }; }
  static getStubConfig() { return { title: "Flights overhead", height: 460 }; }

  async _build() {
    this._built = true;
    const c = this._config;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; margin: ${c.margin || 0}; }
        ha-card { overflow: hidden; border-radius: var(--ofc-radius, 16px);
          background: var(--ofc-background, linear-gradient(165deg, rgba(16,38,56,.94) 0%, rgba(7,18,30,.95) 100%));
          border: var(--ofc-border, 1px solid rgba(79,182,255,.22)); box-shadow: 0 10px 30px rgba(0,0,0,.45); color: #e6f1f8; }
        .head { display: flex; align-items: center; gap: 10px; padding: 14px 16px 12px; }
        .head h3 { margin: 0; font-size: 15px; letter-spacing: 1.2px; text-transform: uppercase; font-weight: 700; }
        .head a { margin-left: auto; font-size: 12px; color: #4fb6ff; text-decoration: none; border: 1px solid rgba(79,182,255,.5);
          border-radius: 999px; padding: 3px 10px; }
        .frame { position: relative; height: ${ofcHeight(c.height)}; margin: 0 ${c.title === "" ? 0 : "12px 12px"};
          border-radius: ${c.title === "" ? 0 : "12px"}; overflow: hidden; background: #0b1016; }
        iframe { border: 0; width: 100%; height: 100%; display: block; }
        .msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; text-align: center;
          padding: 24px; color: #7fa3b8; font-size: 14px; }
      </style>
      <ha-card>
        ${c.title === "" ? "" : `<div class="head"><ha-icon icon="mdi:airplane"></ha-icon><h3>${c.title}</h3><a id="open" href="#">Open ↗</a></div>`}
        <div class="frame"><div class="msg" id="msg">Connecting to Overhead Flights…</div></div>
      </ha-card>`;
    try {
      const addon = await this._findAddon();
      if (addon.state !== "started") throw new Error("The Overhead Flights add-on isn't running. Start it from Settings → Add-ons.");
      await this._newSession();
      clearInterval(this._timer);
      this._timer = setInterval(() => this._keepSession(), 5 * 60 * 1000);
      const qs = new URLSearchParams({ tour: c.tour === false ? "0" : "1", labels: c.labels || "compact" });
      if (c.zoom) qs.set("zoom", c.zoom);
      if (c.radius) qs.set("radius", c.radius);
      if (c.card === false) qs.set("card", "0");
      if (c.paths) qs.set("paths", "1");
      if (c.alerts === false) qs.set("alerts", "0");
      if (c.summary === false) qs.set("summary", "0");
      const iframe = document.createElement("iframe");
      iframe.src = `${addon.ingress_entry}/embed?${qs}`;
      iframe.title = "Overhead Flights";
      iframe.onload = () => this.shadowRoot.getElementById("msg")?.remove();
      this.shadowRoot.querySelector(".frame").appendChild(iframe);
      const open = this.shadowRoot.getElementById("open");
      if (open) open.onclick = e => {
        e.preventDefault();
        history.pushState(null, "", "/" + addon.slug);
        window.dispatchEvent(new CustomEvent("location-changed"));
      };
    } catch (e) {
      this.shadowRoot.getElementById("msg").textContent = e.message || String(e);
    }
  }

  _sup(endpoint, method = "get", data) {
    const msg = { type: "supervisor/api", endpoint, method };
    if (data) msg.data = data;
    return this._hass.callWS(msg);
  }

  async _findAddon() {
    if (!this._hass.user?.is_admin) throw new Error("The flights map needs an administrator account (Home Assistant only lets admins open add-on pages).");
    let slug = this._config.slug;
    if (!slug) {
      const list = await this._sup("/addons");
      const hit = (list.addons || []).find(a => /(^|_)overhead_flights$/.test(a.slug) && a.installed !== false);
      if (!hit) throw new Error("Overhead Flights add-on not found. Install it first.");
      slug = hit.slug;
    }
    const info = await this._sup(`/addons/${slug}/info`);
    return { slug, state: info.state, ingress_entry: info.ingress_entry };
  }

  async _newSession() {
    const r = await this._sup("/ingress/session", "post");
    this._session = r.session;
    document.cookie = `ingress_session=${r.session};path=/api/hassio_ingress/;SameSite=Strict` + (location.protocol === "https:" ? ";Secure" : "");
  }

  async _keepSession() {
    try { await this._sup("/ingress/validate_session", "post", { session: this._session }); }
    catch { try { await this._newSession(); } catch { /* try again next time */ } }
  }

  disconnectedCallback() { clearInterval(this._timer); this._built = false; }
  connectedCallback() { if (this._hass && this._config && !this._built) this._build(); }
}

customElements.define("overhead-flights-card", OverheadFlightsCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "overhead-flights-card", name: "Overhead Flights", description: "Live map of aircraft over your home (needs the Overhead Flights add-on)", preview: false });
console.info(`%c OVERHEAD-FLIGHTS-CARD %c ${OFC_VERSION} `, "background:#38bdf8;color:#0b1016;font-weight:700", "");
