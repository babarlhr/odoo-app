###################################################################################
# 
#    Copyright (C) 2017 MuK IT GmbH
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

import logging

from odoo import _, SUPERUSER_ID
from odoo import models, api, fields
from odoo.exceptions import AccessError

from odoo.addons.muk_security.tools.security import NoSecurityUid

_logger = logging.getLogger(__name__)

class AccessGroupsModel(models.AbstractModel):
    
    _name = 'muk_security.mixins.access_groups'
    _description = "Group Access Mixin"
    _inherit = 'muk_security.mixins.access'
    
    # Set it to True to enforced security even if no group has been set
    _strict_security = False
    
    # If set the group fields are restricted by the access group
    _field_groups = None 
    
    # If set to True the model is extended by fields to suspend the checks
    _active_suspend = False 
    
    # If set the suspend fields are restricted by the access group
    _suspend_groups = None 
    
    #----------------------------------------------------------
    # Datebase
    #----------------------------------------------------------

    @api.model
    def _add_magic_fields(self):
        super(AccessGroupsModel, self)._add_magic_fields()
        def add(name, field):
            if name not in self._fields:
                self._add_field(name, field)
        if self._active_suspend:
            add('suspend_security_read', fields.Boolean(
                _module=self._module,
                string="Suspend Security for Read",
                automatic=True,
                default=False,
                groups=self._suspend_groups))
            add('suspend_security_create', fields.Boolean(
                _module=self._module,
                string="Suspend Security for Create",
                automatic=True,
                default=False,
                groups=self._suspend_groups))
            add('suspend_security_write', fields.Boolean(
                _module=self._module,
                string="Suspend Security for Write",
                automatic=True,
                default=False,
                groups=self._suspend_groups))
            add('suspend_security_unlink', fields.Boolean(
                _module=self._module,
                string="Suspend Security for Unlink",
                automatic=True,
                default=False,
                groups=self._suspend_groups))
        add('groups', fields.Many2many(
            _module=self._module,
            comodel_name='muk_security.access_groups',
            relation='%s_groups_rel' % (self._table),
            column1='aid',
            column2='gid',
            string="Groups",
            automatic=True,
            groups=self._field_groups))
        add('complete_groups', fields.Many2many(
            _module=self._module,
            comodel_name='muk_security.access_groups',
            relation='%s_complete_groups_rel' % (self._table),
            column1='aid',
            column2='gid',
            string="Complete Groups", 
            compute='_compute_groups', 
            store=True,
            automatic=True,
            groups=self._field_groups))
    
    #----------------------------------------------------------
    # Function
    #----------------------------------------------------------
    
    @api.model
    def _get_no_access_ids(self):
        if not self._strict_security:
            sql = '''
                SELECT id
                FROM %s a
                WHERE NOT EXISTS (
                    SELECT *
                    FROM %s_complete_groups_rel r
                    WHERE r.aid = a.id
                );         
            ''' % (self._table, self._table)
            self.env.cr.execute(sql)
            fetch = self.env.cr.fetchall()
            return len(fetch) > 0 and list(map(lambda x: x[0], fetch)) or []
        else:
            return []
    
    @api.model
    def _get_suspended_access_ids(self, operation):
        if self._active_suspend:
            sql = '''
                SELECT id
                FROM %s a
                WHERE a.suspend_security_%s = true
            ''' % (self._table, operation)
            self.env.cr.execute(sql)
            fetch = self.env.cr.fetchall()
            return len(fetch) > 0 and list(map(lambda x: x[0], fetch)) or []
        else:
            return []
        
    @api.model
    def _get_access_ids(self):
        model = self._name.split(".")[-1]
        sql = '''
            SELECT r.aid
            FROM %s_complete_groups_rel r
            JOIN muk_security_access_groups g ON r.gid = g.id
            JOIN muk_security_access_groups_users_rel u ON r.gid = u.gid
            WHERE u.uid = %s AND g.perm_read = true
        ''' % (self._table, self.env.user.id)
        self.env.cr.execute(sql)
        fetch = self.env.cr.fetchall()
        access_ids = len(fetch) > 0 and list(map(lambda x: x[0], fetch)) or []
        return access_ids
    
    @api.model
    def _get_ids_without_security(self, operation):
        no_access_ids = self._get_no_access_ids()
        suspended_access_ids = self._get_suspended_access_ids(operation)
        return list(set(no_access_ids).union(suspended_access_ids))
    
    @api.model
    def _get_complete_access_ids(self, operation):
        access_ids = self._get_access_ids()
        no_access_ids = self._get_no_access_ids()
        suspended_access_ids = self._get_suspended_access_ids(operation)
        return list(set(access_ids).union(no_access_ids, suspended_access_ids))
    
    @api.multi
    def _eval_access_skip(self, operation):
        if isinstance(self.env.uid, NoSecurityUid):
            return True
        return False
    
    @api.multi
    def check_access_groups(self, operation):
        if self.env.user.id == SUPERUSER_ID or self._eval_access_skip(operation):
            return None
        filter_ids = self._get_ids_without_security(operation)
        for record in self.filtered(lambda rec: rec.id not in filter_ids):
            sql = '''
                SELECT perm_%s                
                FROM %s_complete_groups_rel r
                JOIN muk_security_access_groups g ON r.gid = g.id
                JOIN muk_security_access_groups_users_rel u ON r.gid = u.gid
                WHERE r.aid = %s AND u.uid = %s
            ''' % (operation, self._table, record.id, self.env.user.id)
            self.env.cr.execute(sql)
            fetch = self.env.cr.fetchall()
            if not any(list(map(lambda x: x[0], fetch))):
                raise AccessError(_("This operation is forbidden!"))
    
    @api.multi
    def check_access(self, operation, raise_exception=False):
        res = super(BaseModelAccessGroups, self).check_access(operation, raise_exception)
        try:
            access_groups = self.check_access_groups(operation) == None
            return res and access_groups
        except AccessError:
            if raise_exception:
                raise
            return False
        
    #----------------------------------------------------------
    # Read
    #----------------------------------------------------------
    
    @api.multi
    def _after_read(self, result, *largs, **kwargs):
        result = super(BaseModelAccessGroups, self)._after_read(result)
        if self.env.user.id == SUPERUSER_ID or self._eval_access_skip("read"):
            return result
        access_ids = self._get_complete_access_ids("read")
        result = [result] if not isinstance(result, list) else result
        if len(access_ids) > 0:
            access_result = []
            for record in result:
                if record['id'] in access_ids:
                    access_result.append(record)
            return access_result
        return []
    
    @api.model
    def _after_search(self, result, *largs, **kwargs):
        result = super(BaseModelAccessGroups, self)._after_search(result)
        if self.env.user.id == SUPERUSER_ID or self._eval_access_skip("read"):
            return result
        access_ids = self._get_complete_access_ids("read")
        if len(access_ids) > 0:
            access_result = self.env[self._name]
            if isinstance(result, int):
                if result in access_ids:
                    return result
            else:
                for record in result:
                    if record.id in access_ids:
                        access_result += record
                return access_result
        return self.env[self._name]
    
    @api.model
    def _after_name_search(self, result, *largs, **kwargs):
        result = super(BaseModelAccessGroups, self)._after_name_search(result)
        if self.env.user.id == SUPERUSER_ID or self._eval_access_skip("read"):
            return result
        access_ids = self._get_complete_access_ids("read")
        if len(access_ids) > 0:
            access_result = []
            for tuple in result:
                if tuple[0] in access_ids:
                    access_result.append(tuple)
            return access_result
        return []
    
    #----------------------------------------------------------
    # Read, View 
    #----------------------------------------------------------
    
    @api.depends('groups')
    def _compute_groups(self):
        for record in self:
            record.complete_groups = record.groups
        
    #----------------------------------------------------------
    # Create, Update, Delete 
    #----------------------------------------------------------
    
    @api.multi
    def _before_write(self, vals, *largs, **kwargs):
        self.check_access_groups('write')
        return super(BaseModelAccessGroups, self)._before_write(vals, *largs, **kwargs)

    @api.multi
    def _before_unlink(self, *largs, **kwargs):
        self.check_access_groups('unlink')
        return super(BaseModelAccessGroups, self)._before_unlink(*largs, **kwargs)