# -*- coding: utf-8 -*-
# Copyright 2018 Ivan Yelizariev <https://it-projects.info/team/yelizariev>
# Copyright 2018 Ildar Nasyrov <https://it-projects.info/team/iledarn>
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# views, that has to be force to be multi-company
MULTI_VIEWS = [
    'website.footer_custom',
    'website.footer_default',
    'website.layout_logo_show',
    'website.show_sign_in',
]


class WebsiteTheme(models.Model):
    _inherit = 'website.theme'

    name = fields.Char(string="Theme")
    converted_theme_addon = fields.Char(
        string="Theme's technical name",
        help="")

    dependency_ids = fields.Many2many(
        'ir.module.module',
        string="Dependencies",
        help='Theme-like dependencies. Add modules here if you got error "The style compilation failed".')

    @api.model
    def _get_multi_views_refs(self):
        refs = self.env["ir.model.data"]
        for xmlid in MULTI_VIEWS:
            module, name = xmlid.split('.', 1)
            new_ref = self.env["ir.model.data"].search([
                ('module', '=', module),
                ('name', '=', name)
            ])
            refs += new_ref
        return refs

    def _convert_assets(self):
        """Generate assets for converted themes"""
        Asset = self.env["website.theme.asset"]

        common_refs = self.env["ir.model.data"]

        # add views with customize_show menu, so we can activate them per
        # website independently
        common_refs |= self.env['ir.ui.view']\
                           .with_context(active_test=False)\
                           .search([
                               ('website_id', '=', False),
                               ('customize_show', '=', True),
                           ]).mapped('model_data_id')
        _logger.debug('common_refs: %s', common_refs.mapped('complete_name'))

        for one in self:
            refs = self.env["ir.model.data"]

            if one.converted_theme_addon:
                # Get all views owned by the converted theme addon
                refs |= self.env["ir.model.data"].search([
                    ("module", "in", [one.converted_theme_addon] + one.dependency_ids.mapped('name')),
                    ("model", "=", "ir.ui.view"),
                ])

            if refs or one.asset_ids:
                # add common_refs only for installed themes
                refs |= common_refs

                # Force to make some base views multi-company. E.g. multi-footer
                refs |= self._get_multi_views_refs()

            # Skip views without inherit_id, because those have new
            # template definition only and after appliying multi-theme
            # for several websites it will be copied and then it leads
            # to error on compilation when any template with <t
            # t-call="..."/> -- expected singleton
            views = self.env["ir.ui.view"].with_context(active_test=False) \
                .search([
                    ("id", "in", refs.mapped("res_id")),
                    ("type", "=", "qweb"),
                    ("inherit_id", "!=", False),
                ])
            existing = frozenset(
                one
                .mapped("asset_ids")
                .filtered("auto")
                .mapped("name")
            )
            expected = frozenset(views.mapped("xml_id"))

            dangling = tuple(existing - expected)
            # Create a new asset for each theme view
            for ref in expected - existing:
                _logger.debug("Creating asset %s for theme %s", ref, one.name)

                # we set priority equal to view id to apply copied views in a
                # right order
                one.asset_ids |= Asset.new({
                    "name": ref,
                    "auto": True,
                    'priority': view.id,
                })
            # Delete all dangling assets
            if dangling:
                _logger.debug(
                    "Removing dangling assets for theme %s: %s",
                    one.name, dangling)
                Asset.search([("name", "in", dangling)]).unlink()
        # Turn all assets multiwebsite-only
        Asset._find_and_deactivate_views()


class WebsiteThemeAsset(models.Model):
    _inherit = "website.theme.asset"
    _order = 'priority,id'

    priority = fields.Integer()
