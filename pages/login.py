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

.fc-login-link {
    color: var(--fc-primary) !important;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0.01em;
}

.fc-login-link:hover {
    color: var(--fc-primary-hover) !important;
}

.q-dialog .q-card {
    border-radius: 20px;
    padding: 8px;
}

.fc-credentials-card {
    width: 460px;
    max-width: 100%;
}

.fc-credentials-title {
    font-size: 19px;
    font-weight: 700;
    color: var(--fc-text);
}

.fc-credentials-subtitle {
    font-size: 13px;
    color: var(--fc-muted);
    margin-bottom: 4px;
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

            with ui.dialog() as credentials_dialog, ui.card().classes("fc-credentials-card"):
                ui.label("Change Username / Password").classes("fc-credentials-title")
                ui.label("Verify your current credentials to set new ones.").classes(
                    "fc-credentials-subtitle"
                )

                current_username_input = ui.input("Current Username").props("outlined").classes("w-full")
                current_password_input = ui.input(
                    "Current Password", password=True, password_toggle_button=True
                ).props("outlined").classes("w-full")
                new_username_input = ui.input("New Username").props("outlined").classes("w-full")
                new_password_input = ui.input(
                    "New Password", password=True, password_toggle_button=True
                ).props("outlined").classes("w-full")
                confirm_password_input = ui.input(
                    "Confirm New Password", password=True, password_toggle_button=True
                ).props("outlined").classes("w-full")

                dialog_error_label = ui.label("").classes("fc-login-error")
                dialog_error_label.set_visibility(False)

                def submit_change() -> None:
                    ok, message = auth_service.change_credentials(
                        str(current_username_input.value or ""),
                        str(current_password_input.value or ""),
                        str(new_username_input.value or ""),
                        str(new_password_input.value or ""),
                        str(confirm_password_input.value or ""),
                    )
                    if ok:
                        credentials_dialog.close()
                        ui.notify(message, color="positive")
                        username_input.value = str(new_username_input.value or "").strip()
                        username_input.update()
                        password_input.value = ""
                        password_input.update()
                        return
                    dialog_error_label.text = message
                    dialog_error_label.set_visibility(True)

                with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                    ui.button("Cancel", on_click=credentials_dialog.close, color="grey-6")
                    ui.button("Save Changes", on_click=submit_change, color="primary")

            def open_credentials_dialog() -> None:
                for field in (
                    current_username_input,
                    current_password_input,
                    new_username_input,
                    new_password_input,
                    confirm_password_input,
                ):
                    field.value = ""
                    field.update()
                dialog_error_label.set_visibility(False)
                credentials_dialog.open()

            ui.button(
                "Change Username / Password", on_click=open_credentials_dialog
            ).props("flat no-caps dense").classes("fc-login-link")

    return None


@ui.page("/logout")
def logout_page() -> RedirectResponse:
    auth_service.logout_session()
    return RedirectResponse("/login")
