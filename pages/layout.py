from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import app, ui

from services import auth_service
from core.i18n import t


APP_NAME = t("app.name")

_IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
app.add_static_files("/images", str(_IMAGES_DIR))

LOGO_URL = "/images/logo_without_company_name.png"

NAV_ITEMS = [
    {"label_key": "nav.dashboard", "path": "/dashboard", "icon": "space_dashboard"},
    {"label_key": "nav.inventory", "path": "/inventory", "icon": "inventory_2"},
    {"label_key": "nav.products", "path": "/products", "icon": "category"},
    {"label_key": "nav.suppliers", "path": "/suppliers", "icon": "local_shipping"},
    {"label_key": "nav.purchases", "path": "/purchases", "icon": "shopping_cart"},
    {"label_key": "nav.sales", "path": "/sales", "icon": "point_of_sale"},
    {"label_key": "nav.debtors", "path": "/debtors", "icon": "payments"},
    {"label_key": "nav.reports", "path": "/reports", "icon": "assessment"},
    {"label_key": "nav.settings", "path": "/settings", "icon": "settings"},
]

MOBILE_BREAKPOINT = 768

_THEME_CSS = """
:root {
    --fc-primary: #007979;
    --fc-primary-hover: #24B1B1;
    --fc-bg: #FFF0E4;
    --fc-surface-2: #FFE0C5;
    --fc-surface: #FFFFFF;
    --fc-text: #0F172A;
    --fc-muted: #64748B;
    --fc-success: #22C55E;
    --fc-warning: #F59E0B;
    --fc-danger: #EF4444;
    --fc-header-height: 72px;
    --fc-sidebar-width: 260px;
    --fc-sidebar-width-collapsed: 80px;
}

html, body {
    background: var(--fc-bg);
    color: var(--fc-text);
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ---------- app shell ---------- */
.fc-app {
    height: 100vh;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--fc-bg);
}

.fc-body {
    flex: 1 1 auto;
    display: flex;
    min-height: 0;
    width: 100%;
}

/* ---------- header ---------- */
.fc-header {
    height: var(--fc-header-height);
    min-height: var(--fc-header-height);
    position: sticky;
    top: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 0 24px;
    background: var(--fc-surface);
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.fc-header-logo {
    height: 46px;
    width: 46px;
    display: block;
    flex: 0 0 auto;
}

.fc-header-title {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1;
    color: var(--fc-text);
    user-select: none;
}

/* ---------- sidebar ---------- */
.fc-sidebar {
    position: relative;
    flex: 0 0 auto;
    width: var(--fc-sidebar-width);
    height: 100%;
    background: var(--fc-surface);
    border-radius: 0 24px 24px 0;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
    transition: width 300ms ease, transform 300ms ease;
    z-index: 90;
}

.fc-sidebar.fc-collapsed {
    width: var(--fc-sidebar-width-collapsed);
}

.fc-sidebar-inner {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 32px 16px 20px;
    overflow: hidden;
}

/* ---------- navigation ---------- */
.fc-nav {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.fc-nav-item {
    display: flex;
    align-items: center;
    gap: 14px;
    min-height: 48px;
    padding: 0 14px;
    border-radius: 16px;
    color: var(--fc-muted);
    font-weight: 600;
    font-size: 14.5px;
    white-space: nowrap;
    cursor: pointer;
    transition: background-color 200ms ease, color 200ms ease, padding 300ms ease;
}

.fc-nav-item .q-icon {
    font-size: 22px;
    flex: 0 0 auto;
}

.fc-nav-item:hover {
    background: rgba(255, 224, 197, 0.55);
    color: var(--fc-primary);
}

.fc-nav-item.fc-active {
    background: var(--fc-surface-2);
    color: var(--fc-primary);
}

.fc-nav-label {
    transition: opacity 200ms ease;
}

.fc-sidebar.fc-collapsed .fc-nav-item {
    justify-content: center;
    gap: 0;
    padding: 0;
}

.fc-sidebar.fc-collapsed .fc-nav-label {
    opacity: 0;
    width: 0;
    overflow: hidden;
    pointer-events: none;
}

/* ---------- collapse button ---------- */
.fc-collapse-btn {
    position: absolute;
    top: 30px;
    right: -16px;
    width: 32px;
    height: 32px;
    min-height: 32px;
    border-radius: 9999px;
    background: var(--fc-surface) !important;
    color: var(--fc-primary) !important;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.18);
    z-index: 95;
}

.fc-collapse-btn:hover {
    color: var(--fc-primary-hover) !important;
}

.fc-collapse-btn .q-icon {
    font-size: 18px;
}

/* ---------- profile ---------- */
.fc-profile-wrap {
    margin-top: auto;
    border-top: 1px solid rgba(15, 23, 42, 0.08);
    padding-top: 14px;
}

.fc-profile {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 8px;
    white-space: nowrap;
    overflow: hidden;
}

.fc-avatar {
    width: 40px;
    height: 40px;
    flex: 0 0 auto;
    border-radius: 9999px;
    background: linear-gradient(135deg, var(--fc-primary), var(--fc-primary-hover));
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 16px;
}

.fc-profile-text {
    display: flex;
    flex-direction: column;
    line-height: 1.25;
    transition: opacity 200ms ease;
}

.fc-profile-name {
    font-weight: 700;
    font-size: 14px;
    color: var(--fc-text);
}

.fc-profile-role {
    font-size: 12px;
    color: var(--fc-muted);
}

.fc-sidebar.fc-collapsed .fc-profile {
    justify-content: center;
    gap: 0;
    padding-left: 0;
    padding-right: 0;
}

.fc-sidebar.fc-collapsed .fc-profile-text {
    opacity: 0;
    width: 0;
    overflow: hidden;
}

.fc-profile-logout {
    margin-left: auto;
    color: var(--fc-muted) !important;
}

.fc-profile-logout:hover {
    color: #EF4444 !important;
}

.fc-sidebar.fc-collapsed .fc-profile-logout {
    display: none;
}

/* ---------- content ---------- */
.fc-content {
    flex: 1 1 auto;
    min-width: 0;
    height: 100%;
    overflow-y: auto;
    padding: 24px;
    background: var(--fc-bg);
}

/* ---------- responsive: mobile drawer ---------- */
@media (max-width: 767px) {
    .fc-sidebar {
        position: fixed;
        left: 0;
        top: var(--fc-header-height);
        bottom: 0;
        height: auto;
        width: var(--fc-sidebar-width);
    }

    .fc-sidebar.fc-collapsed {
        width: var(--fc-sidebar-width);
        transform: translateX(-100%);
    }

    .fc-sidebar.fc-collapsed .fc-nav-item {
        justify-content: flex-start;
        gap: 14px;
        padding: 0 14px;
    }

    .fc-sidebar.fc-collapsed .fc-nav-label,
    .fc-sidebar.fc-collapsed .fc-profile-text {
        opacity: 1;
        width: auto;
    }

    .fc-sidebar.fc-collapsed .fc-profile {
        justify-content: flex-start;
        gap: 12px;
        padding: 6px 8px;
    }

    .fc-collapse-btn {
        right: -16px;
    }
}
"""


def _apply_theme() -> None:
    ui.colors(
        primary="#007979",
        secondary="#24B1B1",
        accent="#FFE0C5",
        positive="#22C55E",
        negative="#EF4444",
        warning="#F59E0B",
    )
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800'
        '&display=swap" rel="stylesheet">'
    )
    ui.add_css(_THEME_CSS)
    ui.query(".nicegui-content").classes("p-0 gap-0")


def _build_header() -> None:
    with ui.element("header").classes("fc-header"):
        ui.image(LOGO_URL).classes("fc-header-logo").props("no-spinner fit=contain")
        ui.label(APP_NAME).classes("fc-header-title")


def _build_sidebar(current_path: str, user: dict[str, Any]) -> None:
    state = {"collapsed": False}

    sidebar = ui.element("aside").classes("fc-sidebar")

    def apply_state() -> None:
        if state["collapsed"]:
            sidebar.classes(add="fc-collapsed")
            collapse_btn.props("icon=chevron_right")
        else:
            sidebar.classes(remove="fc-collapsed")
            collapse_btn.props("icon=chevron_left")

    def toggle() -> None:
        state["collapsed"] = not state["collapsed"]
        apply_state()

    with sidebar:
        collapse_btn = (
            ui.button(on_click=toggle)
            .props("flat round dense icon=chevron_left")
            .classes("fc-collapse-btn")
        )
        with ui.element("div").classes("fc-sidebar-inner"):
            with ui.element("nav").classes("fc-nav"):
                for item in NAV_ITEMS:
                    is_active = current_path == item["path"]
                    nav_item = ui.element("div").classes(
                        "fc-nav-item" + (" fc-active" if is_active else "")
                    )
                    nav_item.on(
                        "click",
                        lambda path=item["path"]: ui.navigate.to(path),
                    )
                    with nav_item:
                        ui.icon(item["icon"])
                        nav_label = t(item["label_key"])
                        ui.label(nav_label).classes("fc-nav-label")
                        ui.tooltip(nav_label).props("anchor='center right' self='center left'")
            full_name = str(user.get("full_name") or t("app.user_fallback"))
            username = str(user.get("username") or "")
            initial = (full_name.strip()[:1] or "U").upper()
            with ui.element("div").classes("fc-profile-wrap"):
                with ui.element("div").classes("fc-profile"):
                    with ui.element("div").classes("fc-avatar"):
                        ui.label(initial)
                    with ui.element("div").classes("fc-profile-text"):
                        ui.label(full_name).classes("fc-profile-name")
                        ui.label(username).classes("fc-profile-role")
                    with ui.button(
                        on_click=lambda: ui.navigate.to("/logout")
                    ).props("flat round dense icon=logout").classes("fc-profile-logout"):
                        ui.tooltip(t("nav.logout"))

    initialized = {"done": False}

    async def init_responsive() -> None:
        # on_connect also fires on reconnects; only initialize once per page.
        if initialized["done"]:
            return
        initialized["done"] = True
        try:
            width = await ui.run_javascript("window.innerWidth", timeout=5.0)
        except TimeoutError:
            return
        if isinstance(width, (int, float)) and width < MOBILE_BREAKPOINT and not state["collapsed"]:
            state["collapsed"] = True
            apply_state()

    # Run after the websocket handshake instead of a detached timer: connect
    # handlers never fire for clients that are discarded before connecting,
    # which previously caused "parent slot has been deleted" errors.
    ui.context.client.on_connect(init_responsive)


def _install_session_watchdog() -> None:
    """Enforce the inactivity timeout while a page stays open.

    Client side: any interaction bumps an activity timestamp; a JS interval
    redirects to /logout after 15 idle minutes (even if the server is busy).
    Server side: a per-page timer (started only after the websocket connects)
    polls the real idle time to keep the session fresh during activity and to
    destroy it once the timeout is reached.
    """
    timeout_ms = auth_service.SESSION_TIMEOUT_SECONDS * 1000
    ui.add_body_html(
        f"""
        <script>
        (function () {{
            window._fcLastActivity = Date.now();
            const bump = function () {{ window._fcLastActivity = Date.now(); }};
            ['click', 'keydown', 'mousemove', 'wheel', 'scroll', 'touchstart'].forEach(function (ev) {{
                document.addEventListener(ev, bump, {{ passive: true, capture: true }});
            }});
            setInterval(function () {{
                if (Date.now() - window._fcLastActivity > {timeout_ms}) {{
                    window.location.assign('/logout');
                }}
            }}, 15000);
        }})();
        </script>
        """
    )

    # Resolve the session storage now (request context is available during
    # page build); timer callbacks cannot access app.storage.user directly.
    user_storage = app.storage.user
    started = {"done": False}

    def start_watchdog() -> None:
        if started["done"]:
            return
        started["done"] = True

        async def check_activity() -> None:
            try:
                idle_ms = await ui.run_javascript(
                    "Date.now() - (window._fcLastActivity || Date.now())",
                    timeout=5.0,
                )
                idle_seconds = max(float(idle_ms) / 1000.0, 0.0)
            except (TimeoutError, TypeError, ValueError):
                return
            if idle_seconds >= auth_service.SESSION_TIMEOUT_SECONDS:
                auth_service.logout_session(user_storage)
                ui.navigate.to("/login")
            else:
                auth_service.touch_session(idle_seconds, storage=user_storage)

        ui.timer(60.0, check_activity)

    ui.context.client.on_connect(start_watchdog)


def with_master_layout(page_title: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(page_fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(page_fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            user = auth_service.current_user()
            if user is None:
                return RedirectResponse("/login")
            auth_service.touch_session()

            current_path = str(ui.context.client.request.url.path)

            ui.page_title(t("app.page_title", page_title=page_title, app_name=APP_NAME))
            _apply_theme()
            _install_session_watchdog()

            with ui.element("div").classes("fc-app"):
                _build_header()
                with ui.element("div").classes("fc-body"):
                    _build_sidebar(current_path, user)
                    with ui.column().classes("fc-content"):
                        page_fn(*args, **kwargs)
            return None

        return wrapped

    return decorator
