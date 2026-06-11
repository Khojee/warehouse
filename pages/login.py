from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from pages.layout import APP_NAME, LOGO_URL, _apply_theme
from services import auth_service


_LOGIN_CSS = """
.fc-login-wrap {
    min-height: 100vh;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--fc-bg);
    padding: 24px;
}

.fc-login-card {
    width: 100%;
    max-width: 420px;
    background: var(--fc-surface);
    border-radius: 24px;
    padding: 40px 36px 36px;
    box-shadow: 0 2px 4px rgba(15, 23, 42, 0.04), 0 16px 48px rgba(15, 23, 42, 0.10);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
}

.fc-login-logo {
    height: 72px;
    width: 72px;
}

.fc-login-title {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: var(--fc-text);
    line-height: 1.1;
}

.fc-login-subtitle {
    font-size: 14px;
    color: var(--fc-muted);
    margin-bottom: 10px;
}

.fc-login-card .q-field {
    width: 100%;
}

.fc-login-error {
    width: 100%;
    text-align: center;
    font-size: 13.5px;
    font-weight: 500;
    color: var(--fc-danger, #EF4444);
    background: rgba(239, 68, 68, 0.10);
    border-radius: 12px;
    padding: 10px 12px;
}

.fc-login-btn {
    width: 100%;
    margin-top: 6px;
}
"""


@ui.page("/login")
def login_page() -> RedirectResponse | None:
    if auth_service.current_user() is not None:
        return RedirectResponse("/dashboard")

    _apply_theme()
    ui.add_css(_LOGIN_CSS)

    with ui.element("div").classes("fc-login-wrap"):
        with ui.element("div").classes("fc-login-card"):
            ui.image(LOGO_URL).classes("fc-login-logo").props("no-spinner")
            ui.label(APP_NAME).classes("fc-login-title")
            ui.label("Sign in to your warehouse").classes("fc-login-subtitle")

            username_input = ui.input("Username").props("outlined")
            password_input = ui.input(
                "Password", password=True, password_toggle_button=True
            ).props("outlined")

            error_label = ui.label("").classes("fc-login-error")
            error_label.set_visibility(False)

            def do_login() -> None:
                ok, message = auth_service.authenticate(
                    str(username_input.value or ""),
                    str(password_input.value or ""),
                )
                if ok:
                    ui.navigate.to("/dashboard")
                    return
                error_label.text = message
                error_label.set_visibility(True)
                password_input.value = ""
                password_input.update()

            ui.button("Login", on_click=do_login).classes("fc-login-btn")
            username_input.on("keydown.enter", lambda _: do_login())
            password_input.on("keydown.enter", lambda _: do_login())

    return None


@ui.page("/logout")
def logout_page() -> RedirectResponse:
    auth_service.logout_session()
    return RedirectResponse("/login")
