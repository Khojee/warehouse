from nicegui import ui

from core.i18n import set_locale
from services.auth_service import ensure_users_table, get_storage_secret

set_locale("uz")

import pages.login
import pages.dashboard
import pages.debtors
import pages.inventory
import pages.purchases
import pages.products
import pages.sales
import pages.settings
import pages.suppliers

ensure_users_table()

ui.run(storage_secret=get_storage_secret())
