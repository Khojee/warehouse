from nicegui import ui

from pages.layout import with_master_layout


@ui.page("/")
@ui.page("/dashboard")
@with_master_layout("Dashboard")
def dashboard_page() -> None:
    ui.label("Dashboard").classes("text-h4 q-mb-md")
    ui.label("Dashboard content placeholder").classes("text-subtitle2 text-grey-7")

