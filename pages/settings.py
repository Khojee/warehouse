from nicegui import ui

from pages.layout import with_master_layout


@ui.page("/settings")
@with_master_layout("Settings")
def settings_page() -> None:
    ui.label("Settings").classes("text-h4 q-mb-md")
    ui.label("Settings content placeholder").classes("text-subtitle2 text-grey-7")

