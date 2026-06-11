from nicegui import ui

from services.auth_service import ensure_users_table, get_storage_secret

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
