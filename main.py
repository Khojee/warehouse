from nicegui import ui

from core.i18n import set_locale
from database import initialize_database
from services.auth_service import get_storage_secret

set_locale("uz")
initialize_database()

import pages.login
import pages.dashboard
import pages.debtors
import pages.inventory
import pages.purchases
import pages.products
import pages.sales
import pages.settings
import pages.suppliers

ui.run(storage_secret=get_storage_secret())
