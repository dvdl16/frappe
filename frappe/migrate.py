# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals

import json
import os
import sys
import frappe
import frappe.translate
import frappe.modules.patch_handler
import frappe.model.sync
from frappe.utils.fixtures import sync_fixtures
from frappe.utils.connections import check_connection
from frappe.utils.dashboard import sync_dashboards
from frappe.cache_manager import clear_global_cache
from frappe.desk.notifications import clear_notifications
from frappe.website import render
from frappe.core.doctype.language.language import sync_languages
from frappe.modules.utils import sync_customizations
from frappe.core.doctype.scheduled_job_type.scheduled_job_type import sync_jobs
from frappe.modules import full_text_search
from frappe.utils import global_search


def migrate(verbose=True, rebuild_website=False, skip_failing=False, skip_search_index=False):
	'''Migrate all apps to the latest version, will:
	- run before migrate hooks
	- run patches
	- sync doctypes (schema)
	- sync dashboards
	- sync fixtures
	- sync desktop icons
	- sync web pages (from /www)
	- sync web pages (from /www)
	- run after migrate hooks
	'''

	service_status = check_connection(redis_services=["redis_cache"])
	if False in service_status.values():
		for service in service_status:
			if not service_status.get(service, True):
				print("{} service is not running.".format(service))
		print("""Cannot run bench migrate without the services running.
If you are running bench in development mode, make sure that bench is running:

$ bench start

Otherwise, check the server logs and ensure that all the required services are running.""")
		sys.exit(1)

	touched_tables_file = frappe.get_site_path('touched_tables.json')
	if os.path.exists(touched_tables_file):
		os.remove(touched_tables_file)

	try:
		frappe.flags.touched_tables = set()
		frappe.flags.in_migrate = True

		clear_global_cache()

		#run before_migrate hooks
		for app in frappe.get_installed_apps():
			for fn in frappe.get_hooks('before_migrate', app_name=app):
				frappe.get_attr(fn)()

		# run patches
		frappe.modules.patch_handler.run_all(skip_failing)

		# sync
		frappe.model.sync.sync_all(verbose=verbose)
		frappe.translate.clear_cache()
		sync_jobs()
		sync_fixtures()
		sync_dashboards()
		sync_customizations()
		sync_languages()

		frappe.get_doc('Portal Settings', 'Portal Settings').sync_menu()

		# syncs statics
		render.clear_cache()

		# add static pages to global search
		if not skip_search_index:
			# global_search.update_global_search_for_all_web_pages()
			full_text_search.build_index_for_all_routes("web_routes")

		# updating installed applications data
		frappe.get_single('Installed Applications').update_versions()

		#run after_migrate hooks
		for app in frappe.get_installed_apps():
			for fn in frappe.get_hooks('after_migrate', app_name=app):
				frappe.get_attr(fn)()

		frappe.db.commit()

		clear_notifications()

		frappe.publish_realtime("version-update")
		frappe.flags.in_migrate = False
	finally:
		with open(touched_tables_file, 'w') as f:
			json.dump(list(frappe.flags.touched_tables), f, sort_keys=True, indent=4)
		frappe.flags.touched_tables.clear()
