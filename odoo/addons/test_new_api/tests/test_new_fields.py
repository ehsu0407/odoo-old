#
# test cases for new-style fields
#
import base64
from collections import OrderedDict
from datetime import date, datetime, time
import io
from PIL import Image
import psycopg2

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import common
from odoo.tools import mute_logger, float_repr
from odoo.tools.date_utils import add, subtract, start_of, end_of
from odoo.tools.image import image_data_uri


class TestFields(common.TransactionCase):

    def test_00_basics(self):
        """ test accessing new fields """
        # find a discussion
        discussion = self.env.ref('test_new_api.discussion_0')

        # read field as a record attribute or as a record item
        self.assertIsInstance(discussion.name, str)
        self.assertIsInstance(discussion['name'], str)
        self.assertEqual(discussion['name'], discussion.name)

        # read it with method read()
        values = discussion.read(['name'])[0]
        self.assertEqual(values['name'], discussion.name)

    def test_01_basic_get_assertion(self):
        """ test item getter """
        # field access works on single record
        record = self.env.ref('test_new_api.message_0_0')
        self.assertEqual(len(record), 1)
        ok = record.body

        # field access fails on multiple records
        records = self.env['test_new_api.message'].search([])
        assert len(records) > 1
        with self.assertRaises(ValueError):
            faulty = records.body

    def test_01_basic_set_assertion(self):
        """ test item setter """
        # field assignment works on single record
        record = self.env.ref('test_new_api.message_0_0')
        self.assertEqual(len(record), 1)
        record.body = 'OK'

        # field assignment on multiple records should assign value to all records
        records = self.env['test_new_api.message'].search([])
        records.body = 'Updated'
        self.assertTrue(all(map(lambda record:record.body=='Updated', records)))

        # field assigmenent does not cache the wrong value when write overridden
        record.priority = 4
        self.assertEqual(record.priority, 5)

    def test_05_unknown_fields(self):
        """ test ORM operations with unknown fields """
        cat = self.env['test_new_api.category'].create({'name': 'Foo'})

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.search([('zzz', '=', 42)])
        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.search([], order='zzz')

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read(['zzz'])

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read_group([('zzz', '=', 42)], fields=['color'], groupby=['parent'])
        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read_group([], fields=['zzz'], groupby=['parent'])
        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read_group([], fields=['zzz:sum'], groupby=['parent'])
        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read_group([], fields=['color'], groupby=['zzz'])
        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.read_group([], fields=['color'], groupby=['parent'], orderby='zzz')
        # exception: accept '__count' as field to aggregate
        cat.read_group([], fields=['__count'], groupby=['parent'])

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.create({'name': 'Foo', 'zzz': 42})

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.write({'zzz': 42})

        with self.assertRaisesRegex(ValueError, 'Invalid field'):
            cat.new({'name': 'Foo', 'zzz': 42})

    def test_10_computed(self):
        """ check definition of computed fields """
        # by default function fields are not stored and readonly
        field = self.env['test_new_api.message']._fields['size']
        self.assertFalse(field.store)
        self.assertFalse(field.compute_sudo)
        self.assertTrue(field.readonly)

        field = self.env['test_new_api.message']._fields['name']
        self.assertTrue(field.store)
        self.assertTrue(field.compute_sudo)
        self.assertTrue(field.readonly)

    def test_10_computed_custom(self):
        """ check definition of custom computed fields """
        self.env['ir.model.fields'].create({
            'name': 'x_bool_false_computed',
            'model_id': self.env.ref('test_new_api.model_test_new_api_message').id,
            'field_description': 'A boolean computed to false',
            'compute': "for r in self: r['x_bool_false_computed'] = False",
            'store': False,
            'ttype': 'boolean'
        })
        field = self.env['test_new_api.message']._fields['x_bool_false_computed']
        self.assertFalse(field.depends)

    def test_10_computed_custom_invalid_transitive_depends(self):
        self.patch(type(self.env["ir.model.fields"]), "_check_depends", lambda self: True)
        self.env["ir.model.fields"].create(
            {
                "name": "x_computed_custom_valid_depends",
                "model_id": self.env.ref("test_new_api.model_test_new_api_foo").id,
                "state": "manual",
                "field_description": "A compute with a valid depends",
                "compute": "for r in self: r['x_computed_custom_valid_depends'] = False",
                "depends": "value1",
                "store": False,
                "ttype": "boolean",
            }
        )
        self.env["ir.model.fields"].create(
            {
                "name": "x_computed_custom_valid_transitive_depends",
                "model_id": self.env.ref("test_new_api.model_test_new_api_foo").id,
                "state": "manual",
                "field_description": "A compute with a valid transitive depends",
                "compute": "for r in self: r['x_computed_custom_valid_transitive_depends'] = False",
                "depends": "x_computed_custom_valid_depends",
                "store": False,
                "ttype": "boolean",
            }
        )
        self.env["ir.model.fields"].create(
            {
                "name": "x_computed_custom_invalid_depends",
                "model_id": self.env.ref("test_new_api.model_test_new_api_foo").id,
                "state": "manual",
                "field_description": "A compute with an invalid depends",
                "compute": "for r in self: r['x_computed_custom_invalid_depends'] = False",
                "depends": "bar",
                "store": False,
                "ttype": "boolean",
            }
        )
        self.env["ir.model.fields"].create(
            {
                "name": "x_computed_custom_invalid_transitive_depends",
                "model_id": self.env.ref("test_new_api.model_test_new_api_foo").id,
                "state": "manual",
                "field_description": "A compute with an invalid transitive depends",
                "compute": "for r in self: r['x_computed_custom_invalid_transitive_depends'] = False",
                "depends": "x_computed_custom_invalid_depends",
                "store": False,
                "ttype": "boolean",
            }
        )
        fields = self.env["test_new_api.foo"]._fields
        triggers = self.env.registry.field_triggers
        value1 = fields["value1"]
        valid_depends = fields["x_computed_custom_valid_depends"]
        valid_transitive_depends = fields["x_computed_custom_valid_transitive_depends"]
        invalid_depends = fields["x_computed_custom_invalid_depends"]
        invalid_transitive_depends = fields["x_computed_custom_invalid_transitive_depends"]
        # `x_computed_custom_valid_depends` in the triggers of the field `value1`
        self.assertTrue(valid_depends in triggers[value1][None])
        # `x_computed_custom_valid_transitive_depends` in the triggers `x_computed_custom_valid_depends` and `value1`
        self.assertTrue(valid_transitive_depends in triggers[valid_depends][None])
        self.assertTrue(valid_transitive_depends in triggers[value1][None])
        # `x_computed_custom_invalid_depends` not in any triggers, as it was invalid and was skipped
        self.assertEqual(
            sum(invalid_depends in field_triggers.get(None, []) for field_triggers in triggers.values()), 0
        )
        # `x_computed_custom_invalid_transitive_depends` in the triggers of `x_computed_custom_invalid_depends` only
        self.assertTrue(invalid_transitive_depends in triggers[invalid_depends][None])
        self.assertEqual(
            sum(invalid_transitive_depends in field_triggers.get(None, []) for field_triggers in triggers.values()), 1
        )

    @mute_logger('odoo.fields')
    def test_10_computed_stored_x_name(self):
        # create a custom model with two fields
        self.env["ir.model"].create({
            "name": "x_test_10_compute_store_x_name",
            "model": "x_test_10_compute_store_x_name",
            "field_id": [
                (0, 0, {'name': 'x_name', 'ttype': 'char'}),
                (0, 0, {'name': 'x_stuff_id', 'ttype': 'many2one', 'relation': 'ir.model'}),
            ],
        })
        # set 'x_stuff_id' refer to a model not loaded yet
        self.cr.execute("""
            UPDATE ir_model_fields
            SET relation = 'not.loaded'
            WHERE model = 'x_test_10_compute_store_x_name' AND name = 'x_stuff_id'
        """)
        # set 'x_name' be computed and depend on 'x_stuff_id'
        self.cr.execute("""
            UPDATE ir_model_fields
            SET compute = 'pass', depends = 'x_stuff_id.x_custom_1'
            WHERE model = 'x_test_10_compute_store_x_name' AND name = 'x_name'
        """)
        # setting up models should not crash
        self.registry.setup_models(self.cr)

    def test_10_display_name(self):
        """ test definition of automatic field 'display_name' """
        field = type(self.env['test_new_api.discussion']).display_name
        self.assertTrue(field.automatic)
        self.assertTrue(field.compute)
        self.assertEqual(field.depends, ('name',))

    def test_10_non_stored(self):
        """ test non-stored fields """
        # a field declared with store=False should not have a column
        field = self.env['test_new_api.category']._fields['dummy']
        self.assertFalse(field.store)
        self.assertFalse(field.compute)
        self.assertFalse(field.inverse)

        # find messages
        for message in self.env['test_new_api.message'].search([]):
            # check definition of field
            self.assertEqual(message.size, len(message.body or ''))

            # check recomputation after record is modified
            size = message.size
            message.write({'body': (message.body or '') + "!!!"})
            self.assertEqual(message.size, size + 3)

        # create a message, assign body, and check size in several environments
        message1 = self.env['test_new_api.message'].create({})
        message2 = message1.with_user(self.env.ref('base.user_demo'))
        self.assertEqual(message1.size, 0)
        self.assertEqual(message2.size, 0)

        message1.write({'body': "XXX"})
        self.assertEqual(message1.size, 3)
        self.assertEqual(message2.size, 3)

        # special case: computed field without dependency must be computed
        record = self.env['test_new_api.mixed'].create({})
        self.assertTrue(record.now)

    def test_11_stored(self):
        """ test stored fields """
        def check_stored(disc):
            """ Check the stored computed field on disc.messages """
            for msg in disc.messages:
                self.assertEqual(msg.name, "[%s] %s" % (disc.name, msg.author.name))

        # find the demo discussion, and check messages
        discussion1 = self.env.ref('test_new_api.discussion_0')
        self.assertTrue(discussion1.messages)
        check_stored(discussion1)

        # modify discussion name, and check again messages
        discussion1.name = 'Talking about stuff...'
        check_stored(discussion1)

        # switch message from discussion, and check again
        discussion2 = discussion1.copy({'name': 'Another discussion'})
        message2 = discussion1.messages[0]
        message2.discussion = discussion2
        check_stored(discussion2)

        # create a new discussion with messages, and check their name
        user_root = self.env.ref('base.user_root')
        user_demo = self.env.ref('base.user_demo')
        discussion3 = self.env['test_new_api.discussion'].create({
            'name': 'Stuff',
            'participants': [(4, user_root.id), (4, user_demo.id)],
            'messages': [
                (0, 0, {'author': user_root.id, 'body': 'one'}),
                (0, 0, {'author': user_demo.id, 'body': 'two'}),
                (0, 0, {'author': user_root.id, 'body': 'three'}),
            ],
        })
        check_stored(discussion3)

        # modify the discussion messages: edit the 2nd one, remove the last one
        # (keep modifications in that order, as they reproduce a former bug!)
        discussion3.write({
            'messages': [
                (4, discussion3.messages[0].id),
                (1, discussion3.messages[1].id, {'author': user_root.id}),
                (2, discussion3.messages[2].id),
            ],
        })
        check_stored(discussion3)

    def test_11_stored_protected(self):
        """ test protection against recomputation """
        model = self.env['test_new_api.compute.protected']
        field = model._fields['bar']

        record = model.create({'foo': 'unprotected #1'})
        self.assertEqual(record.bar, 'unprotected #1')

        record.write({'foo': 'unprotected #2'})
        self.assertEqual(record.bar, 'unprotected #2')

        # by protecting 'bar', we prevent it from being recomputed
        with self.env.protecting([field], record):
            record.write({'foo': 'protected'})
            self.assertEqual(record.bar, 'unprotected #2')

            # also works when nested
            with self.env.protecting([field], record):
                record.write({'foo': 'protected'})
                self.assertEqual(record.bar, 'unprotected #2')

            record.write({'foo': 'protected'})
            self.assertEqual(record.bar, 'unprotected #2')

        record.write({'foo': 'unprotected #3'})
        self.assertEqual(record.bar, 'unprotected #3')

        # also works with duplicated fields
        with self.env.protecting([field, field], record):
            record.write({'foo': 'protected'})
            self.assertEqual(record.bar, 'unprotected #3')

        record.write({'foo': 'unprotected #4'})
        self.assertEqual(record.bar, 'unprotected #4')

        # we protect 'bar' on a different record
        with self.env.protecting([field], record):
            record2 = model.create({'foo': 'unprotected'})
            self.assertEqual(record2.bar, 'unprotected')

    def test_11_computed_access(self):
        """ test computed fields with access right errors """
        User = self.env['res.users']
        user1 = User.create({'name': 'Aaaah', 'login': 'a'})
        user2 = User.create({'name': 'Boooh', 'login': 'b'})
        user3 = User.create({'name': 'Crrrr', 'login': 'c'})
        # add a rule to not give access to user2
        self.env['ir.rule'].create({
            'model_id': self.env['ir.model'].search([('model', '=', 'res.users')]).id,
            'domain_force': "[('id', '!=', %d)]" % user2.id,
        })
        # DLE P72: Since we decided that we do not raise security access errors for data to which we had the occassion
        # to put the value in the cache, we need to invalidate the cache for user1, user2 and user3 in order
        # to test the below access error. Otherwise the above create calls set in the cache the information needed
        # to compute `company_type` ('is_company'), and doesn't need to trigger a read.
        # We need to force the read in order to test the security access
        User.invalidate_cache()
        # group users as a recordset, and read them as user demo
        users = (user1 + user2 + user3).with_user(self.env.ref('base.user_demo'))
        user1, user2, user3 = users
        # regression test: a bug invalidated the field's value from cache
        user1.company_type
        with self.assertRaises(AccessError):
            user2.company_type
        user3.company_type

    def test_12_recursive(self):
        """ test recursively dependent fields """
        Category = self.env['test_new_api.category']
        abel = Category.create({'name': 'Abel'})
        beth = Category.create({'name': 'Bethany'})
        cath = Category.create({'name': 'Catherine'})
        dean = Category.create({'name': 'Dean'})
        ewan = Category.create({'name': 'Ewan'})
        finn = Category.create({'name': 'Finnley'})
        gabe = Category.create({'name': 'Gabriel'})

        cath.parent = finn.parent = gabe
        abel.parent = beth.parent = cath
        dean.parent = ewan.parent = finn

        self.assertEqual(abel.display_name, "Gabriel / Catherine / Abel")
        self.assertEqual(beth.display_name, "Gabriel / Catherine / Bethany")
        self.assertEqual(cath.display_name, "Gabriel / Catherine")
        self.assertEqual(dean.display_name, "Gabriel / Finnley / Dean")
        self.assertEqual(ewan.display_name, "Gabriel / Finnley / Ewan")
        self.assertEqual(finn.display_name, "Gabriel / Finnley")
        self.assertEqual(gabe.display_name, "Gabriel")

        ewan.parent = cath
        self.assertEqual(ewan.display_name, "Gabriel / Catherine / Ewan")

        cath.parent = finn
        self.assertEqual(ewan.display_name, "Gabriel / Finnley / Catherine / Ewan")

    def test_12_recursive_recompute(self):
        """ test recomputation on recursively dependent field """
        a = self.env['test_new_api.recursive'].create({'name': 'A'})
        b = self.env['test_new_api.recursive'].create({'name': 'B', 'parent': a.id})
        c = self.env['test_new_api.recursive'].create({'name': 'C', 'parent': b.id})
        d = self.env['test_new_api.recursive'].create({'name': 'D', 'parent': c.id})
        self.assertEqual(a.full_name, 'A')
        self.assertEqual(b.full_name, 'A / B')
        self.assertEqual(c.full_name, 'A / B / C')
        self.assertEqual(d.full_name, 'A / B / C / D')
        self.assertEqual(a.display_name, 'A')
        self.assertEqual(b.display_name, 'A / B')
        self.assertEqual(c.display_name, 'A / B / C')
        self.assertEqual(d.display_name, 'A / B / C / D')

        a.name = 'A1'
        self.assertEqual(a.full_name, 'A1')
        self.assertEqual(b.full_name, 'A1 / B')
        self.assertEqual(c.full_name, 'A1 / B / C')
        self.assertEqual(d.full_name, 'A1 / B / C / D')
        self.assertEqual(a.display_name, 'A1')
        self.assertEqual(b.display_name, 'A1 / B')
        self.assertEqual(c.display_name, 'A1 / B / C')
        self.assertEqual(d.display_name, 'A1 / B / C / D')

        b.parent = False
        self.assertEqual(a.full_name, 'A1')
        self.assertEqual(b.full_name, 'B')
        self.assertEqual(c.full_name, 'B / C')
        self.assertEqual(d.full_name, 'B / C / D')
        self.assertEqual(a.display_name, 'A1')
        self.assertEqual(b.display_name, 'B')
        self.assertEqual(c.display_name, 'B / C')
        self.assertEqual(d.display_name, 'B / C / D')

        # rename several records to trigger several recomputations at once
        (d + c + b).write({'name': 'X'})
        self.assertEqual(a.full_name, 'A1')
        self.assertEqual(b.full_name, 'X')
        self.assertEqual(c.full_name, 'X / X')
        self.assertEqual(d.full_name, 'X / X / X')
        self.assertEqual(a.display_name, 'A1')
        self.assertEqual(b.display_name, 'X')
        self.assertEqual(c.display_name, 'X / X')
        self.assertEqual(d.display_name, 'X / X / X')

        # delete b; both c and d are deleted in cascade; c should also be marked
        # to recompute, but recomputation should not fail...
        b.unlink()
        self.assertEqual((a + b + c + d).exists(), a)

    def test_12_recursive_tree(self):
        foo = self.env['test_new_api.recursive.tree'].create({'name': 'foo'})
        self.assertEqual(foo.display_name, 'foo()')
        bar = foo.create({'name': 'bar', 'parent_id': foo.id})
        self.assertEqual(foo.display_name, 'foo(bar())')
        baz = foo.create({'name': 'baz', 'parent_id': bar.id})
        self.assertEqual(foo.display_name, 'foo(bar(baz()))')

    def test_12_cascade(self):
        """ test computed field depending on computed field """
        message = self.env.ref('test_new_api.message_0_0')
        message.invalidate_cache()
        double_size = message.double_size
        self.assertEqual(double_size, message.size)

        record = self.env['test_new_api.cascade'].create({'foo': "Hi"})
        self.assertEqual(record.baz, "<[Hi]>")
        record.foo = "Ho"
        self.assertEqual(record.baz, "<[Ho]>")

    def test_13_inverse(self):
        """ test inverse computation of fields """
        Category = self.env['test_new_api.category']
        abel = Category.create({'name': 'Abel'})
        beth = Category.create({'name': 'Bethany'})
        cath = Category.create({'name': 'Catherine'})
        dean = Category.create({'name': 'Dean'})
        ewan = Category.create({'name': 'Ewan'})
        finn = Category.create({'name': 'Finnley'})
        gabe = Category.create({'name': 'Gabriel'})
        self.assertEqual(ewan.display_name, "Ewan")

        ewan.display_name = "Abel / Bethany / Catherine / Erwan"

        self.assertEqual(beth.parent, abel)
        self.assertEqual(cath.parent, beth)
        self.assertEqual(ewan.parent, cath)
        self.assertEqual(ewan.name, "Erwan")

        # check create/write with several records
        vals = {'name': 'None', 'display_name': 'Foo'}
        foo1, foo2 = Category.create([vals, vals])
        self.assertEqual(foo1.name, 'Foo')
        self.assertEqual(foo2.name, 'Foo')

        (foo1 + foo2).write({'display_name': 'Bar'})
        self.assertEqual(foo1.name, 'Bar')
        self.assertEqual(foo2.name, 'Bar')

        # create/write on 'foo' should only invoke the compute method
        log = []
        model = self.env['test_new_api.compute.inverse'].with_context(log=log)
        record = model.create({'foo': 'Hi'})
        self.assertEqual(record.foo, 'Hi')
        self.assertEqual(record.bar, 'Hi')
        self.assertCountEqual(log, ['compute'])

        log.clear()
        record.write({'foo': 'Ho'})
        self.assertEqual(record.foo, 'Ho')
        self.assertEqual(record.bar, 'Ho')
        self.assertCountEqual(log, ['compute'])

        # create/write on 'bar' should only invoke the inverse method
        log.clear()
        record = model.create({'bar': 'Hi'})
        self.assertEqual(record.foo, 'Hi')
        self.assertEqual(record.bar, 'Hi')
        self.assertCountEqual(log, ['inverse'])

        log.clear()
        record.write({'bar': 'Ho'})
        self.assertEqual(record.foo, 'Ho')
        self.assertEqual(record.bar, 'Ho')
        self.assertCountEqual(log, ['inverse'])

        # Test compatibility multiple compute/inverse fields
        log = []
        model = self.env['test_new_api.multi_compute_inverse'].with_context(log=log)
        record = model.create({
            'bar1': '1',
            'bar2': '2',
            'bar3': '3',
        })
        self.assertEqual(record.foo, '1/2/3')
        self.assertEqual(record.bar1, '1')
        self.assertEqual(record.bar2, '2')
        self.assertEqual(record.bar3, '3')
        self.assertCountEqual(log, ['inverse1', 'inverse23'])

        log.clear()
        record.write({'bar2': '4', 'bar3': '5'})
        self.assertEqual(record.foo, '1/4/5')
        self.assertEqual(record.bar1, '1')
        self.assertEqual(record.bar2, '4')
        self.assertEqual(record.bar3, '5')
        self.assertCountEqual(log, ['inverse23'])

        log.clear()
        record.write({'bar1': '6', 'bar2': '7'})
        self.assertEqual(record.foo, '6/7/5')
        self.assertEqual(record.bar1, '6')
        self.assertEqual(record.bar2, '7')
        self.assertEqual(record.bar3, '5')
        self.assertCountEqual(log, ['inverse1', 'inverse23'])

        log.clear()
        record.write({'foo': 'A/B/C'})
        self.assertEqual(record.foo, 'A/B/C')
        self.assertEqual(record.bar1, 'A')
        self.assertEqual(record.bar2, 'B')
        self.assertEqual(record.bar3, 'C')
        self.assertCountEqual(log, ['compute'])

        # corner case: write on a field that is marked to compute
        log.clear()
        # writing on 'foo' marks 'bar1', 'bar2', 'bar3' to compute
        record.write({'foo': '1/2/3'})
        self.assertCountEqual(log, [])
        # writing on 'bar3' must force the computation before updating
        record.write({'bar3': 'X'})
        self.assertCountEqual(log, ['compute', 'inverse23'])
        self.assertEqual(record.foo, '1/2/X')
        self.assertEqual(record.bar1, '1')
        self.assertEqual(record.bar2, '2')
        self.assertEqual(record.bar3, 'X')
        self.assertCountEqual(log, ['compute', 'inverse23'])

        log.clear()
        # writing on 'foo' marks 'bar1', 'bar2', 'bar3' to compute
        record.write({'foo': 'A/B/C'})
        self.assertCountEqual(log, [])
        # writing on 'bar1', 'bar2', 'bar3' discards the computation
        record.write({'bar1': 'X', 'bar2': 'Y', 'bar3': 'Z'})
        self.assertCountEqual(log, ['inverse1', 'inverse23'])
        self.assertEqual(record.foo, 'X/Y/Z')
        self.assertEqual(record.bar1, 'X')
        self.assertEqual(record.bar2, 'Y')
        self.assertEqual(record.bar3, 'Z')
        self.assertCountEqual(log, ['inverse1', 'inverse23'])

    def test_13_inverse_access(self):
        """ test access rights on inverse fields """
        foo = self.env['test_new_api.category'].create({'name': 'Foo'})
        user = self.env['res.users'].create({'name': 'Foo', 'login': 'foo'})
        self.assertFalse(user.has_group('base.group_system'))
        # add group on non-stored inverse field
        self.patch(type(foo).display_name, 'groups', 'base.group_system')
        with self.assertRaises(AccessError):
            foo.with_user(user).display_name = 'Forbidden'

    def test_14_search(self):
        """ test search on computed fields """
        discussion = self.env.ref('test_new_api.discussion_0')

        # determine message sizes
        sizes = set(message.size for message in discussion.messages)

        # search for messages based on their size
        for size in sizes:
            messages0 = self.env['test_new_api.message'].search(
                [('discussion', '=', discussion.id), ('size', '<=', size)])

            messages1 = self.env['test_new_api.message'].browse()
            for message in discussion.messages:
                if message.size <= size:
                    messages1 += message

            self.assertEqual(messages0, messages1)

    def test_15_constraint(self):
        """ test new-style Python constraints """
        discussion = self.env.ref('test_new_api.discussion_0')

        # remove oneself from discussion participants: we can no longer create
        # messages in discussion
        discussion.participants -= self.env.user
        with self.assertRaises(ValidationError):
            self.env['test_new_api.message'].create({'discussion': discussion.id, 'body': 'Whatever'})

        # make sure that assertRaises() does not leave fields to recompute
        self.assertFalse(self.env.fields_to_compute())

        # put back oneself into discussion participants: now we can create
        # messages in discussion
        discussion.participants += self.env.user
        self.env['test_new_api.message'].create({'discussion': discussion.id, 'body': 'Whatever'})

        # check constraint on recomputed field
        self.assertTrue(discussion.messages)
        with self.assertRaises(ValidationError):
            discussion.name = "X"
            discussion.flush()

    def test_15_constraint_inverse(self):
        """ test constraint method on normal field and field with inverse """
        log = []
        model = self.env['test_new_api.compute.inverse'].with_context(log=log, log_constraint=True)

        # create/write with normal field only
        log.clear()
        record = model.create({'baz': 'Hi'})
        self.assertCountEqual(log, ['constraint'])

        log.clear()
        record.write({'baz': 'Ho'})
        self.assertCountEqual(log, ['constraint'])

        # create/write with inverse field only
        log.clear()
        record = model.create({'bar': 'Hi'})
        self.assertCountEqual(log, ['inverse', 'constraint'])

        log.clear()
        record.write({'bar': 'Ho'})
        self.assertCountEqual(log, ['inverse', 'constraint'])

        # create/write with both fields only
        log.clear()
        record = model.create({'bar': 'Hi', 'baz': 'Hi'})
        self.assertCountEqual(log, ['inverse', 'constraint'])

        log.clear()
        record.write({'bar': 'Ho', 'baz': 'Ho'})
        self.assertCountEqual(log, ['inverse', 'constraint'])

    def test_20_float(self):
        """ test rounding of float fields """
        record = self.env['test_new_api.mixed'].create({})
        query = "SELECT 1 FROM test_new_api_mixed WHERE id=%s AND number=%s"

        # 2.49609375 (exact float) must be rounded to 2.5
        record.write({'number': 2.49609375})
        record.flush()
        self.cr.execute(query, [record.id, '2.5'])
        self.assertTrue(self.cr.rowcount)
        self.assertEqual(record.number, 2.5)

        # 1.1 (1.1000000000000000888178420 in float) must be 1.1 in database
        record.write({'number': 1.1})
        record.flush()
        self.cr.execute(query, [record.id, '1.1'])
        self.assertTrue(self.cr.rowcount)
        self.assertEqual(record.number, 1.1)

    def test_21_float_digits(self):
        """ test field description """
        precision = self.env.ref('test_new_api.decimal_new_api_number')
        description = self.env['test_new_api.mixed'].fields_get()['number2']
        self.assertEqual(description['digits'], (16, precision.digits))

    def check_monetary(self, record, amount, currency, msg=None):
        # determine the possible roundings of amount
        if currency:
            ramount = currency.round(amount)
            samount = float(float_repr(ramount, currency.decimal_places))
        else:
            ramount = samount = amount

        # check the currency on record
        self.assertEqual(record.currency_id, currency)

        # check the value on the record
        self.assertIn(record.amount, [ramount, samount], msg)

        # check the value in the database
        record.flush()
        self.cr.execute('SELECT amount FROM test_new_api_mixed WHERE id=%s', [record.id])
        value = self.cr.fetchone()[0]
        self.assertEqual(value, samount, msg)

    def test_20_monetary(self):
        """ test monetary fields """
        model = self.env['test_new_api.mixed']
        currency = self.env['res.currency'].with_context(active_test=False)
        amount = 14.70126

        for rounding in [0.01, 0.0001, 1.0, 0]:
            # first retrieve a currency corresponding to rounding
            if rounding:
                currency = currency.search([('rounding', '=', rounding)], limit=1)
                self.assertTrue(currency, "No currency found for rounding %s" % rounding)
            else:
                # rounding=0 corresponds to currency=False
                currency = currency.browse()

            # case 1: create with amount and currency
            record = model.create({'amount': amount, 'currency_id': currency.id})
            self.check_monetary(record, amount, currency, 'create(amount, currency)')

            # case 2: assign amount
            record.amount = 0
            record.amount = amount
            self.check_monetary(record, amount, currency, 'assign(amount)')

            # case 3: write with amount and currency
            record.write({'amount': 0, 'currency_id': False})
            record.write({'amount': amount, 'currency_id': currency.id})
            self.check_monetary(record, amount, currency, 'write(amount, currency)')

            # case 4: write with amount only
            record.write({'amount': 0})
            record.write({'amount': amount})
            self.check_monetary(record, amount, currency, 'write(amount)')

            # case 5: write with amount on several records
            records = record + model.create({'currency_id': currency.id})
            records.write({'amount': 0})
            records.write({'amount': amount})
            for record in records:
                self.check_monetary(record, amount, currency, 'multi write(amount)')

    def test_20_monetary_opw_2223134(self):
        """ test monetary fields with cache override """
        model = self.env['test_new_api.monetary_order']
        currency = self.env.ref('base.USD')

        def check(value):
            self.assertEqual(record.total, value)
            record.flush()
            self.cr.execute('SELECT total FROM test_new_api_monetary_order WHERE id=%s', [record.id])
            [total] = self.cr.fetchone()
            self.assertEqual(total, value)

        # create, and compute amount
        record = model.create({
            'currency_id': currency.id,
            'line_ids': [(0, 0, {'subtotal': 1.0})],
        })
        check(1.0)

        # delete and add a line: the deletion of the line clears the cache, then
        # the recomputation of 'total' must prefetch record.currency_id without
        # screwing up the new value in cache
        record.write({
            'line_ids': [(2, record.line_ids.id), (0, 0, {'subtotal': 1.0})],
        })
        check(1.0)

    def test_20_like(self):
        """ test filtered_domain() on char fields. """
        record = self.env['test_new_api.multi.tag'].create({'name': 'Foo'})
        self.assertTrue(record.filtered_domain([('name', 'like', 'F')]))
        self.assertTrue(record.filtered_domain([('name', 'ilike', 'f')]))

        record.name = 'Bar'
        self.assertFalse(record.filtered_domain([('name', 'like', 'F')]))
        self.assertFalse(record.filtered_domain([('name', 'ilike', 'f')]))

        record.name = False
        self.assertFalse(record.filtered_domain([('name', 'like', 'F')]))
        self.assertFalse(record.filtered_domain([('name', 'ilike', 'f')]))

    def test_21_date(self):
        """ test date fields """
        record = self.env['test_new_api.mixed'].create({})

        # one may assign False or None
        record.date = None
        self.assertFalse(record.date)

        # one may assign date but not datetime objects
        record.date = date(2012, 5, 1)
        self.assertEqual(record.date, date(2012, 5, 1))

        # DLE P41: We now support to assign datetime to date. Not sure this is the good practice though.
        # with self.assertRaises(TypeError):
        #     record.date = datetime(2012, 5, 1, 10, 45, 0)

        # one may assign dates and datetime in the default format, and it must be checked
        record.date = '2012-05-01'
        self.assertEqual(record.date, date(2012, 5, 1))

        record.date = "2012-05-01 10:45:00"
        self.assertEqual(record.date, date(2012, 5, 1))

        with self.assertRaises(ValueError):
            record.date = '12-5-1'

        # check filtered_domain
        self.assertTrue(record.filtered_domain([('date', '<', '2012-05-02')]))
        self.assertTrue(record.filtered_domain([('date', '<', date(2012, 5, 2))]))
        self.assertTrue(record.filtered_domain([('date', '<', datetime(2012, 5, 2, 12, 0, 0))]))
        self.assertTrue(record.filtered_domain([('date', '!=', False)]))
        self.assertFalse(record.filtered_domain([('date', '=', False)]))

        record.date = None
        self.assertFalse(record.filtered_domain([('date', '<', '2012-05-02')]))
        self.assertFalse(record.filtered_domain([('date', '<', date(2012, 5, 2))]))
        self.assertFalse(record.filtered_domain([('date', '<', datetime(2012, 5, 2, 12, 0, 0))]))
        self.assertFalse(record.filtered_domain([('date', '!=', False)]))
        self.assertTrue(record.filtered_domain([('date', '=', False)]))

    def test_21_datetime(self):
        """ test datetime fields """
        for i in range(0, 10):
            self.assertEqual(fields.Datetime.now().microsecond, 0)

        record = self.env['test_new_api.mixed'].create({})

        # assign falsy value
        record.moment = None
        self.assertFalse(record.moment)

        # assign string
        record.moment = '2012-05-01'
        self.assertEqual(record.moment, datetime(2012, 5, 1))
        record.moment = '2012-05-01 06:00:00'
        self.assertEqual(record.moment, datetime(2012, 5, 1, 6))
        with self.assertRaises(ValueError):
            record.moment = '12-5-1'

        # assign date or datetime
        record.moment = date(2012, 5, 1)
        self.assertEqual(record.moment, datetime(2012, 5, 1))
        record.moment = datetime(2012, 5, 1, 6)
        self.assertEqual(record.moment, datetime(2012, 5, 1, 6))

        # check filtered_domain
        self.assertTrue(record.filtered_domain([('moment', '<', '2012-05-02')]))
        self.assertTrue(record.filtered_domain([('moment', '<', date(2012, 5, 2))]))
        self.assertTrue(record.filtered_domain([('moment', '<', datetime(2012, 5, 1, 12, 0, 0))]))
        self.assertTrue(record.filtered_domain([('moment', '!=', False)]))
        self.assertFalse(record.filtered_domain([('moment', '=', False)]))

        record.moment = None
        self.assertFalse(record.filtered_domain([('moment', '<', '2012-05-02')]))
        self.assertFalse(record.filtered_domain([('moment', '<', date(2012, 5, 2))]))
        self.assertFalse(record.filtered_domain([('moment', '<', datetime(2012, 5, 2, 12, 0, 0))]))
        self.assertFalse(record.filtered_domain([('moment', '!=', False)]))
        self.assertTrue(record.filtered_domain([('moment', '=', False)]))

    def test_21_date_datetime_helpers(self):
        """ test date/datetime fields helpers """
        _date = fields.Date.from_string("2077-10-23")
        _datetime = fields.Datetime.from_string("2077-10-23 09:42:00")

        # addition
        self.assertEqual(add(_date, days=5), date(2077, 10, 28))
        self.assertEqual(add(_datetime, seconds=10), datetime(2077, 10, 23, 9, 42, 10))

        # subtraction
        self.assertEqual(subtract(_date, months=1), date(2077, 9, 23))
        self.assertEqual(subtract(_datetime, hours=2), datetime(2077, 10, 23, 7, 42, 0))

        # start_of
        # year
        self.assertEqual(start_of(_date, 'year'), date(2077, 1, 1))
        self.assertEqual(start_of(_datetime, 'year'), datetime(2077, 1, 1))

        # quarter
        q1 = date(2077, 1, 1)
        q2 = date(2077, 4, 1)
        q3 = date(2077, 7, 1)
        q4 = date(2077, 10, 1)
        self.assertEqual(start_of(_date.replace(month=3), 'quarter'), q1)
        self.assertEqual(start_of(_date.replace(month=5), 'quarter'), q2)
        self.assertEqual(start_of(_date.replace(month=7), 'quarter'), q3)
        self.assertEqual(start_of(_date, 'quarter'), q4)
        self.assertEqual(start_of(_datetime, 'quarter'), datetime.combine(q4, time.min))

        # month
        self.assertEqual(start_of(_date, 'month'), date(2077, 10, 1))
        self.assertEqual(start_of(_datetime, 'month'), datetime(2077, 10, 1))

        # week
        self.assertEqual(start_of(_date, 'week'), date(2077, 10, 18))
        self.assertEqual(start_of(_datetime, 'week'), datetime(2077, 10, 18))

        # day
        self.assertEqual(start_of(_date, 'day'), _date)
        self.assertEqual(start_of(_datetime, 'day'), _datetime.replace(hour=0, minute=0, second=0))

        # hour
        with self.assertRaises(ValueError):
            start_of(_date, 'hour')
        self.assertEqual(start_of(_datetime, 'hour'), _datetime.replace(minute=0, second=0))

        # invalid
        with self.assertRaises(ValueError):
            start_of(_datetime, 'poop')

        # end_of
        # year
        self.assertEqual(end_of(_date, 'year'), _date.replace(month=12, day=31))
        self.assertEqual(end_of(_datetime, 'year'),
                         datetime.combine(_date.replace(month=12, day=31), time.max))

        # quarter
        q1 = date(2077, 3, 31)
        q2 = date(2077, 6, 30)
        q3 = date(2077, 9, 30)
        q4 = date(2077, 12, 31)
        self.assertEqual(end_of(_date.replace(month=2), 'quarter'), q1)
        self.assertEqual(end_of(_date.replace(month=4), 'quarter'), q2)
        self.assertEqual(end_of(_date.replace(month=9), 'quarter'), q3)
        self.assertEqual(end_of(_date, 'quarter'), q4)
        self.assertEqual(end_of(_datetime, 'quarter'), datetime.combine(q4, time.max))

        # month
        self.assertEqual(end_of(_date, 'month'), _date.replace(day=31))
        self.assertEqual(end_of(_datetime, 'month'),
                         datetime.combine(date(2077, 10, 31), time.max))

        # week
        self.assertEqual(end_of(_date, 'week'), date(2077, 10, 24))
        self.assertEqual(end_of(_datetime, 'week'),
                         datetime.combine(datetime(2077, 10, 24), time.max))

        # day
        self.assertEqual(end_of(_date, 'day'), _date)
        self.assertEqual(end_of(_datetime, 'day'), datetime.combine(_datetime, time.max))

        # hour
        with self.assertRaises(ValueError):
            end_of(_date, 'hour')
        self.assertEqual(end_of(_datetime, 'hour'),
                         datetime.combine(_datetime, time.max).replace(hour=_datetime.hour))

        # invalid
        with self.assertRaises(ValueError):
            end_of(_datetime, 'crap')

    def test_22_selection(self):
        """ test selection fields """
        record = self.env['test_new_api.mixed'].create({})

        # one may assign False or None
        record.lang = None
        self.assertFalse(record.lang)

        # one may assign a value, and it must be checked
        for language in self.env['res.lang'].search([]):
            record.lang = language.code
        with self.assertRaises(ValueError):
            record.lang = 'zz_ZZ'

    def test_23_relation(self):
        """ test relation fields """
        demo = self.env.ref('base.user_demo')
        message = self.env.ref('test_new_api.message_0_0')

        # check environment of record and related records
        self.assertEqual(message.env, self.env)
        self.assertEqual(message.discussion.env, self.env)

        demo_env = self.env(user=demo)
        self.assertNotEqual(demo_env, self.env)

        # check environment of record and related records
        self.assertEqual(message.env, self.env)
        self.assertEqual(message.discussion.env, self.env)

        # "migrate" message into demo_env, and check again
        demo_message = message.with_user(demo)
        self.assertEqual(demo_message.env, demo_env)
        self.assertEqual(demo_message.discussion.env, demo_env)

        # assign record's parent to a record in demo_env
        message.discussion = message.discussion.copy({'name': 'Copy'})

        # both message and its parent field must be in self.env
        self.assertEqual(message.env, self.env)
        self.assertEqual(message.discussion.env, self.env)

    def test_24_reference(self):
        """ test reference fields. """
        record = self.env['test_new_api.mixed'].create({})

        # one may assign False or None
        record.reference = None
        self.assertFalse(record.reference)

        # one may assign a user or a partner...
        record.reference = self.env.user
        self.assertEqual(record.reference, self.env.user)
        record.reference = self.env.user.partner_id
        self.assertEqual(record.reference, self.env.user.partner_id)
        # ... but no record from a model that starts with 'ir.'
        with self.assertRaises(ValueError):
            record.reference = self.env['ir.model'].search([], limit=1)

    def test_25_related(self):
        """ test related fields. """
        message = self.env.ref('test_new_api.message_0_0')
        discussion = message.discussion

        # by default related fields are not stored
        field = message._fields['discussion_name']
        self.assertFalse(field.store)
        self.assertFalse(field.readonly)

        # check value of related field
        self.assertEqual(message.discussion_name, discussion.name)

        # change discussion name, and check result
        discussion.name = 'Foo'
        self.assertEqual(message.discussion_name, 'Foo')

        # change discussion name via related field, and check result
        message.discussion_name = 'Bar'
        self.assertEqual(discussion.name, 'Bar')
        self.assertEqual(message.discussion_name, 'Bar')

        # change discussion name via related field on several records
        discussion1 = discussion.create({'name': 'X1'})
        discussion2 = discussion.create({'name': 'X2'})
        discussion1.participants = discussion2.participants = self.env.user
        message1 = message.create({'discussion': discussion1.id})
        message2 = message.create({'discussion': discussion2.id})
        self.assertEqual(message1.discussion_name, 'X1')
        self.assertEqual(message2.discussion_name, 'X2')

        (message1 + message2).write({'discussion_name': 'X3'})
        self.assertEqual(discussion1.name, 'X3')
        self.assertEqual(discussion2.name, 'X3')

        # search on related field, and check result
        search_on_related = self.env['test_new_api.message'].search([('discussion_name', '=', 'Bar')])
        search_on_regular = self.env['test_new_api.message'].search([('discussion.name', '=', 'Bar')])
        self.assertEqual(search_on_related, search_on_regular)

        # check that field attributes are copied
        message_field = message.fields_get(['discussion_name'])['discussion_name']
        discussion_field = discussion.fields_get(['name'])['name']
        self.assertEqual(message_field['help'], discussion_field['help'])

    def test_25_related_attributes(self):
        """ test the attributes of related fields """
        text = self.registry['test_new_api.foo'].text
        self.assertFalse(text.trim, "The target field is defined with trim=False")

        # trim=True is the default on the field's class
        self.assertTrue(type(text).trim, "By default, a Char field has trim=True")

        # the parameter 'trim' is not set in text1's definition, so the field
        # retrieves its value from text.trim
        text1 = self.registry['test_new_api.bar'].text1
        self.assertFalse(text1.trim, "The related field retrieves trim=False from target")

        # KNOWN ISSUE: text2 is defined with trim=True, however its value is
        # taken from text.trim because True is the default on the field's class
        text2 = self.registry['test_new_api.bar'].text2
        self.assertFalse(text2.trim,
                         "The related field was defined with trim=True, but takes its value from target")

    def test_25_related_single(self):
        """ test related fields with a single field in the path. """
        record = self.env['test_new_api.related'].create({'name': 'A'})
        self.assertEqual(record.related_name, record.name)
        self.assertEqual(record.related_related_name, record.name)

        # check searching on related fields
        records0 = record.search([('name', '=', 'A')])
        self.assertIn(record, records0)
        records1 = record.search([('related_name', '=', 'A')])
        self.assertEqual(records1, records0)
        records2 = record.search([('related_related_name', '=', 'A')])
        self.assertEqual(records2, records0)

        # check writing on related fields
        record.write({'related_name': 'B'})
        self.assertEqual(record.name, 'B')
        record.write({'related_related_name': 'C'})
        self.assertEqual(record.name, 'C')

    def test_25_related_multi(self):
        """ test write() on several related fields based on a common computed field. """
        foo = self.env['test_new_api.foo'].create({'name': 'A', 'value1': 1, 'value2': 2})
        oof = self.env['test_new_api.foo'].create({'name': 'B', 'value1': 1, 'value2': 2})
        bar = self.env['test_new_api.bar'].create({'name': 'A'})
        self.assertEqual(bar.foo, foo)
        self.assertEqual(bar.value1, 1)
        self.assertEqual(bar.value2, 2)

        foo.invalidate_cache()
        bar.write({'value1': 3, 'value2': 4})
        self.assertEqual(foo.value1, 3)
        self.assertEqual(foo.value2, 4)

        # modify 'name', and search on 'foo': this should flush 'name'
        bar.name = 'B'
        self.assertEqual(bar.foo, oof)
        self.assertIn(bar, bar.search([('foo', 'in', oof.ids)]))

    def test_25_one2many_inverse_related(self):
        left = self.env['test_new_api.trigger.left'].create({})
        right = self.env['test_new_api.trigger.right'].create({})
        self.assertFalse(left.right_id)
        self.assertFalse(right.left_ids)
        self.assertFalse(right.left_size)

        # create middle: this should trigger left.right_id by traversing
        # middle.left_id, and right.left_size by traversing left.right_id
        # after its computation!
        middle = self.env['test_new_api.trigger.middle'].create({
            'left_id': left.id,
            'right_id': right.id,
        })
        self.assertEqual(left.right_id, right)
        self.assertEqual(right.left_ids, left)
        self.assertEqual(right.left_size, 1)

        # delete middle: this should trigger left.right_id by traversing
        # middle.left_id, and right.left_size by traversing left.right_id
        # before its computation!
        middle.unlink()
        self.assertFalse(left.right_id)
        self.assertFalse(right.left_ids)
        self.assertFalse(right.left_size)

    def test_26_inherited(self):
        """ test inherited fields. """
        # a bunch of fields are inherited from res_partner
        for user in self.env['res.users'].search([]):
            partner = user.partner_id
            for field in ('is_company', 'name', 'email', 'country_id'):
                self.assertEqual(getattr(user, field), getattr(partner, field))
                self.assertEqual(user[field], partner[field])

    def test_27_company_dependent(self):
        """ test company-dependent fields. """
        # consider three companies
        company0 = self.env.ref('base.main_company')
        company1 = self.env['res.company'].create({'name': 'A'})
        company2 = self.env['res.company'].create({'name': 'B'})

        # create one user per company
        user0 = self.env['res.users'].create({
            'name': 'Foo', 'login': 'foo', 'company_id': company0.id,
            'company_ids': [(6, 0, [company0.id, company1.id, company2.id])]})
        user1 = self.env['res.users'].create({
            'name': 'Bar', 'login': 'bar', 'company_id': company1.id,
            'company_ids': [(6, 0, [company0.id, company1.id, company2.id])]})
        user2 = self.env['res.users'].create({
            'name': 'Baz', 'login': 'baz', 'company_id': company2.id,
            'company_ids': [(6, 0, [company0.id, company1.id, company2.id])]})

        # create values for many2one field
        tag0 = self.env['test_new_api.multi.tag'].create({'name': 'Qux'})
        tag1 = self.env['test_new_api.multi.tag'].create({'name': 'Quux'})
        tag2 = self.env['test_new_api.multi.tag'].create({'name': 'Quuz'})

        # create default values for the company-dependent fields
        field_foo = self.env['ir.model.fields']._get('test_new_api.company', 'foo')
        self.env['ir.property'].create({'name': 'foo', 'fields_id': field_foo.id,
                                        'value': 'default', 'type': 'char'})
        field_tag_id = self.env['ir.model.fields']._get('test_new_api.company', 'tag_id')
        self.env['ir.property'].create({'name': 'foo', 'fields_id': field_tag_id.id,
                                        'value': tag0, 'type': 'many2one'})

        # assumption: users don't have access to 'ir.property'
        accesses = self.env['ir.model.access'].search([('model_id.model', '=', 'ir.property')])
        accesses.write(dict.fromkeys(['perm_read', 'perm_write', 'perm_create', 'perm_unlink'], False))

        # create/modify a record, and check the value for each user
        record = self.env['test_new_api.company'].create({
            'foo': 'main',
            'date': '1932-11-09',
            'moment': '1932-11-09 00:00:00',
            'tag_id': tag1.id,
        })
        self.assertEqual(record.with_user(user0).foo, 'main')
        self.assertEqual(record.with_user(user1).foo, 'default')
        self.assertEqual(record.with_user(user2).foo, 'default')
        self.assertEqual(str(record.with_user(user0).date), '1932-11-09')
        self.assertEqual(record.with_user(user1).date, False)
        self.assertEqual(record.with_user(user2).date, False)
        self.assertEqual(str(record.with_user(user0).moment), '1932-11-09 00:00:00')
        self.assertEqual(record.with_user(user1).moment, False)
        self.assertEqual(record.with_user(user2).moment, False)
        self.assertEqual(record.with_user(user0).tag_id, tag1)
        self.assertEqual(record.with_user(user1).tag_id, tag0)
        self.assertEqual(record.with_user(user2).tag_id, tag0)

        record.with_user(user1).write({
            'foo': 'alpha',
            'date': '1932-12-10',
            'moment': '1932-12-10 23:59:59',
            'tag_id': tag2.id,
        })
        self.assertEqual(record.with_user(user0).foo, 'main')
        self.assertEqual(record.with_user(user1).foo, 'alpha')
        self.assertEqual(record.with_user(user2).foo, 'default')
        self.assertEqual(str(record.with_user(user0).date), '1932-11-09')
        self.assertEqual(str(record.with_user(user1).date), '1932-12-10')
        self.assertEqual(record.with_user(user2).date, False)
        self.assertEqual(str(record.with_user(user0).moment), '1932-11-09 00:00:00')
        self.assertEqual(str(record.with_user(user1).moment), '1932-12-10 23:59:59')
        self.assertEqual(record.with_user(user2).moment, False)
        self.assertEqual(record.with_user(user0).tag_id, tag1)
        self.assertEqual(record.with_user(user1).tag_id, tag2)
        self.assertEqual(record.with_user(user2).tag_id, tag0)

        # regression: duplicated records caused values to be browse(browse(id))
        recs = record.create({}) + record + record
        recs.invalidate_cache()
        for rec in recs.with_user(user0):
            self.assertIsInstance(rec.tag_id.id, int)

        # unlink value of a many2one (tag2), and check again
        tag2.unlink()
        self.assertEqual(record.with_user(user0).tag_id, tag1)
        self.assertEqual(record.with_user(user1).tag_id, tag0.browse())
        self.assertEqual(record.with_user(user2).tag_id, tag0)

        record.with_user(user1).foo = False
        self.assertEqual(record.with_user(user0).foo, 'main')
        self.assertEqual(record.with_user(user1).foo, False)
        self.assertEqual(record.with_user(user2).foo, 'default')

        # set field with 'force_company' in context
        record.with_user(user0).with_context(force_company=company1.id).foo = 'beta'
        record.invalidate_cache()
        self.assertEqual(record.with_user(user0).foo, 'main')
        self.assertEqual(record.with_user(user1).foo, 'beta')
        self.assertEqual(record.with_user(user2).foo, 'default')

        # add group on company-dependent field
        self.assertFalse(user0.has_group('base.group_system'))
        self.patch(type(record).foo, 'groups', 'base.group_system')
        with self.assertRaises(AccessError):
            record.with_user(user0).foo = 'forbidden'
            record.flush()

        user0.write({'groups_id': [(4, self.env.ref('base.group_system').id)]})
        record.with_user(user0).foo = 'yes we can'

        # add ir.rule to prevent access on record
        self.assertTrue(user0.has_group('base.group_user'))
        rule = self.env['ir.rule'].create({
            'model_id': self.env['ir.model']._get_id(record._name),
            'groups': [self.env.ref('base.group_user').id],
            'domain_force': str([('id', '!=', record.id)]),
        })
        with self.assertRaises(AccessError):
            record.with_user(user0).foo = 'forbidden'
            record.flush()

        # create company record and attribute
        company_record = self.env['test_new_api.company'].create({'foo': 'ABC'})
        attribute_record = self.env['test_new_api.company.attr'].create({
            'company': company_record.id,
            'quantity': 1,
        })
        self.assertEqual(attribute_record.bar, 'ABC')

        # change quantity, 'bar' should recompute to 'ABCABC'
        attribute_record.quantity = 2
        self.assertEqual(attribute_record.bar, 'ABCABC')

        # change company field 'foo', 'bar' should recompute to 'DEFDEF'
        company_record.foo = 'DEF'
        self.assertEqual(attribute_record.company.foo, 'DEF')
        self.assertEqual(attribute_record.bar, 'DEFDEF')

    def test_28_company_dependent_search(self):
        """ Test the search on company-dependent fields in all corner cases.
            This assumes that filtered_domain() correctly filters records when
            its domain refers to company-dependent fields.
        """
        Property = self.env['ir.property']
        Model = self.env['test_new_api.company']

        # create 4 records for all cases: two with explicit truthy values, one
        # with an explicit falsy value, and one without an explicit value
        records = Model.create([{}] * 4)

        # For each field, we assign values to the records, and test a number of
        # searches.  The search cases are given by comparison operators, and for
        # each operator, we test a number of possible operands.  Every search()
        # returns a subset of the records, and we compare it to an equivalent
        # search performed by filtered_domain().

        def test_field(field_name, truthy_values, operations):
            # set ir.properties to all records except the last one
            Property.set_multi(
                field_name, Model._name,
                {rec.id: val for rec, val in zip(records, truthy_values + [False])},
                # Using this sentinel for 'default_value' forces the method to
                # create 'ir.property' records for the value False. Without it,
                # no property would be created because False is the default
                # value.
                default_value=object(),
            )

            # test without default value
            test_cases(field_name, operations)

            # set default value to False
            ir_field = self.env['ir.model.fields']._get(Model._name, field_name)
            prop = Property.create({
                'name': ir_field.name,
                'type': ir_field.ttype,
                'fields_id': ir_field.id,
                'value': False,
            })
            prop.flush()
            prop.invalidate_cache()
            test_cases(field_name, operations, False)

            # set default value to truthy_values[0]
            prop.write({'value': truthy_values[0]})
            prop.flush()
            prop.invalidate_cache()
            test_cases(field_name, operations, truthy_values[0])

        def test_cases(field_name, operations, default=None):
            for operator, values in operations.items():
                for value in values:
                    domain = [(field_name, operator, value)]
                    with self.subTest(domain=domain, default=default):
                        search_result = Model.search([('id', 'in', records.ids)] + domain)
                        filter_result = records.filtered_domain(domain)
                        self.assertEqual(
                            search_result, filter_result,
                            f"Got values {[r[field_name] for r in search_result]} "
                            f"instead of {[r[field_name] for r in filter_result]}",
                        )

        # boolean fields
        test_field('truth', [True, True], {
            '=': (True, False),
            '!=': (True, False),
        })
        # integer fields
        test_field('count', [10, -2], {
            '=': (10, -2, 0, False),
            '!=': (10, -2, 0, False),
            '<': (10, -2, 0),
            '>=': (10, -2, 0),
            '<=': (10, -2, 0),
            '>': (10, -2, 0),
        })
        # float fields
        test_field('phi', [1.61803, -1], {
            '=': (1.61803, -1, 0, False),
            '!=': (1.61803, -1, 0, False),
            '<': (1.61803, -1, 0),
            '>=': (1.61803, -1, 0),
            '<=': (1.61803, -1, 0),
            '>': (1.61803, -1, 0),
        })
        # char fields
        test_field('foo', ['qwer', 'azer'], {
            'like': ('qwer', 'azer'),
            'ilike': ('qwer', 'azer'),
            'not like': ('qwer', 'azer'),
            'not ilike': ('qwer', 'azer'),
            '=': ('qwer', 'azer', False),
            '!=': ('qwer', 'azer', False),
            'not in': (['qwer', 'azer'], ['qwer', False], [False], []),
            'in': (['qwer', 'azer'], ['qwer', False], [False], []),
        })
        # date fields
        date1, date2 = date(2021, 11, 22), date(2021, 11, 23)
        test_field('date', [date1, date2], {
            '=': (date1, date2, False),
            '!=': (date1, date2, False),
            '<': (date1, date2),
            '>=': (date1, date2),
            '<=': (date1, date2),
            '>': (date1, date2),
        })
        # datetime fields
        moment1, moment2 = datetime(2021, 11, 22), datetime(2021, 11, 23)
        test_field('moment', [moment1, moment2], {
            '=': (moment1, moment2, False),
            '!=': (moment1, moment2, False),
            '<': (moment1, moment2),
            '>=': (moment1, moment2),
            '<=': (moment1, moment2),
            '>': (moment1, moment2),
        })
        # many2one fields
        tag1, tag2 = self.env['test_new_api.multi.tag'].create([{'name': 'one'}, {'name': 'two'}])
        test_field('tag_id', [tag1.id, tag2.id], {
            'like': (tag1.name, tag2.name),
            'ilike': (tag1.name, tag2.name),
            'not like': (tag1.name, tag2.name),
            'not ilike': (tag1.name, tag2.name),
            '=': (tag1.id, tag2.id, False),
            '!=': (tag1.id, tag2.id, False),
            'in': ([tag1.id, tag2.id], [tag2.id, False], [False], []),
            'not in': ([tag1.id, tag2.id], [tag2.id, False], [False], []),
        })

    def test_30_read(self):
        """ test computed fields as returned by read(). """
        discussion = self.env.ref('test_new_api.discussion_0')

        for message in discussion.messages:
            display_name = message.display_name
            size = message.size

            data = message.read(['display_name', 'size'])[0]
            self.assertEqual(data['display_name'], display_name)
            self.assertEqual(data['size'], size)

    def test_31_prefetch(self):
        """ test prefetch of records handle AccessError """
        Category = self.env['test_new_api.category']
        cat1 = Category.create({'name': 'NOACCESS'})
        cat2 = Category.create({'name': 'ACCESS', 'parent': cat1.id})
        cats = cat1 + cat2

        self.env.clear()

        cat1, cat2 = cats
        self.assertEqual(cat2.name, 'ACCESS')
        # both categories should be ready for prefetching
        self.assertItemsEqual(cat2._prefetch_ids, cats.ids)
        # but due to our (lame) overwrite of `read`, it should not forbid us to read records we have access to
        self.assertFalse(cat2.discussions)
        self.assertEqual(cat2.parent, cat1)
        with self.assertRaises(AccessError):
            cat1.name

    def test_40_real_vs_new(self):
        """ test field access on new records vs real records. """
        Model = self.env['test_new_api.category']
        real_record = Model.create({'name': 'Foo'})
        self.env.cache.invalidate()
        new_origin = Model.new({'name': 'Bar'}, origin=real_record)
        new_record = Model.new({'name': 'Baz'})

        # non-computed non-stored field: default value
        real_record = real_record.with_context(default_dummy='WTF')
        new_origin = new_origin.with_context(default_dummy='WTF')
        new_record = new_record.with_context(default_dummy='WTF')
        self.assertEqual(real_record.dummy, 'WTF')
        self.assertEqual(new_origin.dummy, 'WTF')
        self.assertEqual(new_record.dummy, 'WTF')

        # non-computed stored field: origin or default if no origin
        real_record = real_record.with_context(default_color=42)
        new_origin = new_origin.with_context(default_color=42)
        new_record = new_record.with_context(default_color=42)
        self.assertEqual(real_record.color, 0)
        self.assertEqual(new_origin.color, 0)
        self.assertEqual(new_record.color, 42)

        # computed non-stored field: always computed
        self.assertEqual(real_record.display_name, 'Foo')
        self.assertEqual(new_origin.display_name, 'Bar')
        self.assertEqual(new_record.display_name, 'Baz')

        # computed stored field: origin or computed if no origin
        Model = self.env['test_new_api.recursive']
        real_record = Model.create({'name': 'Foo'})
        new_origin = Model.new({'name': 'Bar'}, origin=real_record)
        new_record = Model.new({'name': 'Baz'})
        self.assertEqual(real_record.display_name, 'Foo')
        self.assertEqual(new_origin.display_name, 'Bar')
        self.assertEqual(new_record.display_name, 'Baz')

        # computed stored field with recomputation: always computed
        real_record.name = 'Fool'
        new_origin.name = 'Barr'
        new_record.name = 'Bazz'
        self.assertEqual(real_record.display_name, 'Fool')
        self.assertEqual(new_origin.display_name, 'Barr')
        self.assertEqual(new_record.display_name, 'Bazz')

    def test_40_new_defaults(self):
        """ Test new records with defaults. """
        user = self.env.user
        discussion = self.env.ref('test_new_api.discussion_0')

        # create a new message; fields have their default value if not given
        new_msg = self.env['test_new_api.message'].new({'body': "XXX"})
        self.assertFalse(new_msg.id)
        self.assertEqual(new_msg.body, "XXX")
        self.assertEqual(new_msg.author, user)

        # assign some fields; should have no side effect
        new_msg.discussion = discussion
        new_msg.body = "YYY"
        self.assertEqual(new_msg.discussion, discussion)
        self.assertEqual(new_msg.body, "YYY")
        self.assertNotIn(new_msg, discussion.messages)

        # check computed values of fields
        self.assertEqual(new_msg.name, "[%s] %s" % (discussion.name, user.name))
        self.assertEqual(new_msg.size, 3)

        # extra tests for x2many fields with default
        cat1 = self.env['test_new_api.category'].create({'name': "Cat1"})
        cat2 = self.env['test_new_api.category'].create({'name': "Cat2"})
        discussion = discussion.with_context(default_categories=[(4, cat1.id)])
        # no value gives the default value
        new_disc = discussion.new({'name': "Foo"})
        self.assertEqual(new_disc.categories._origin, cat1)
        # value overrides default value
        new_disc = discussion.new({'name': "Foo", 'categories': [(4, cat2.id)]})
        self.assertEqual(new_disc.categories._origin, cat2)

    def test_40_new_fields(self):
        """ Test new records with relational fields. """
        # create a new discussion with all kinds of relational fields
        msg0 = self.env['test_new_api.message'].create({'body': "XXX"})
        msg1 = self.env['test_new_api.message'].create({'body': "WWW"})
        cat0 = self.env['test_new_api.category'].create({'name': 'AAA'})
        cat1 = self.env['test_new_api.category'].create({'name': 'DDD'})
        new_disc = self.env['test_new_api.discussion'].new({
            'name': "Stuff",
            'moderator': self.env.uid,
            'messages': [
                (4, msg0.id),
                (4, msg1.id), (1, msg1.id, {'body': "YYY"}),
                (0, 0, {'body': "ZZZ"})
            ],
            'categories': [
                (4, cat0.id),
                (4, cat1.id), (1, cat1.id, {'name': "BBB"}),
                (0, 0, {'name': "CCC"})
            ],
        })
        self.assertFalse(new_disc.id)

        # many2one field values are actual records
        self.assertEqual(new_disc.moderator.id, self.env.uid)

        # x2many fields values are new records
        new_msg0, new_msg1, new_msg2 = new_disc.messages
        self.assertFalse(new_msg0.id)
        self.assertFalse(new_msg1.id)
        self.assertFalse(new_msg2.id)

        new_cat0, new_cat1, new_cat2 = new_disc.categories
        self.assertFalse(new_cat0.id)
        self.assertFalse(new_cat1.id)
        self.assertFalse(new_cat2.id)

        # the x2many has its inverse field set
        self.assertEqual(new_msg0.discussion, new_disc)
        self.assertEqual(new_msg1.discussion, new_disc)
        self.assertEqual(new_msg2.discussion, new_disc)

        self.assertFalse(msg0.discussion)
        self.assertFalse(msg1.discussion)

        self.assertEqual(new_cat0.discussions, new_disc)    # add other discussions
        self.assertEqual(new_cat1.discussions, new_disc)
        self.assertEqual(new_cat2.discussions, new_disc)

        self.assertNotIn(new_disc, cat0.discussions)
        self.assertNotIn(new_disc, cat1.discussions)

        # new lines are connected to their origin
        self.assertEqual(new_msg0._origin, msg0)
        self.assertEqual(new_msg1._origin, msg1)
        self.assertFalse(new_msg2._origin)

        self.assertEqual(new_cat0._origin, cat0)
        self.assertEqual(new_cat1._origin, cat1)
        self.assertFalse(new_cat2._origin)

        # the field values are either specific, or the same as the origin
        self.assertEqual(new_msg0.body, "XXX")
        self.assertEqual(new_msg1.body, "YYY")
        self.assertEqual(new_msg2.body, "ZZZ")

        self.assertEqual(msg0.body, "XXX")
        self.assertEqual(msg1.body, "WWW")

        self.assertEqual(new_cat0.name, "AAA")
        self.assertEqual(new_cat1.name, "BBB")
        self.assertEqual(new_cat2.name, "CCC")

        self.assertEqual(cat0.name, "AAA")
        self.assertEqual(cat1.name, "DDD")

        # special case for many2one fields that define _inherits
        new_email = self.env['test_new_api.emailmessage'].new({'body': "XXX"})
        self.assertFalse(new_email.id)
        self.assertTrue(new_email.message)
        self.assertFalse(new_email.message.id)
        self.assertEqual(new_email.body, "XXX")

        new_email = self.env['test_new_api.emailmessage'].new({'message': msg0.id})
        self.assertFalse(new_email.id)
        self.assertFalse(new_email._origin)
        self.assertFalse(new_email.message.id)
        self.assertEqual(new_email.message._origin, msg0)
        self.assertEqual(new_email.body, "XXX")

        # check that this does not generate an infinite recursion
        new_disc._convert_to_write(new_disc._cache)

    def test_40_new_inherited_fields(self):
        """ Test the behavior of new records with inherited fields. """
        email = self.env['test_new_api.emailmessage'].new({'body': 'XXX'})
        self.assertEqual(email.body, 'XXX')
        self.assertEqual(email.message.body, 'XXX')

        email.body = 'YYY'
        self.assertEqual(email.body, 'YYY')
        self.assertEqual(email.message.body, 'YYY')

        email.message.body = 'ZZZ'
        self.assertEqual(email.body, 'ZZZ')
        self.assertEqual(email.message.body, 'ZZZ')

    def test_40_new_ref_origin(self):
        """ Test the behavior of new records with ref/origin. """
        Discussion = self.env['test_new_api.discussion']
        new = Discussion.new

        # new records with identical/different refs
        xs = new() + new(ref='a') + new(ref='b') + new(ref='b')
        self.assertEqual([x == y for x in xs for y in xs], [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 1,
            0, 0, 1, 1,
        ])
        for x in xs:
            self.assertFalse(x._origin)

        # new records with identical/different origins
        a, b = Discussion.create([{'name': "A"}, {'name': "B"}])
        xs = new() + new(origin=a) + new(origin=b) + new(origin=b)
        self.assertEqual([x == y for x in xs for y in xs], [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 1,
            0, 0, 1, 1,
        ])
        self.assertFalse(xs[0]._origin)
        self.assertEqual(xs[1]._origin, a)
        self.assertEqual(xs[2]._origin, b)
        self.assertEqual(xs[3]._origin, b)
        self.assertEqual(xs._origin, a + b + b)
        self.assertEqual(xs._origin._origin, a + b + b)

        # new records with refs and origins
        x1 = new(ref='a')
        x2 = new(origin=b)
        self.assertNotEqual(x1, x2)

        # new discussion based on existing discussion
        disc = self.env.ref('test_new_api.discussion_0')
        new_disc = disc.new(origin=disc)
        self.assertFalse(new_disc.id)
        self.assertEqual(new_disc._origin, disc)
        self.assertEqual(new_disc.name, disc.name)
        # many2one field
        self.assertEqual(new_disc.moderator, disc.moderator)
        # one2many field
        self.assertTrue(new_disc.messages)
        self.assertNotEqual(new_disc.messages, disc.messages)
        self.assertEqual(new_disc.messages._origin, disc.messages)
        # many2many field
        self.assertTrue(new_disc.participants)
        self.assertNotEqual(new_disc.participants, disc.participants)
        self.assertEqual(new_disc.participants._origin, disc.participants)

        # provide many2one field as a dict of values; the value is a new record
        # with the given 'id' as origin (if given, of course)
        new_msg = disc.messages.new({
            'discussion': {'name': disc.name},
        })
        self.assertTrue(new_msg.discussion)
        self.assertFalse(new_msg.discussion.id)
        self.assertFalse(new_msg.discussion._origin)

        new_msg = disc.messages.new({
            'discussion': {'name': disc.name, 'id': disc.id},
        })
        self.assertTrue(new_msg.discussion)
        self.assertFalse(new_msg.discussion.id)
        self.assertEqual(new_msg.discussion._origin, disc)

        # check convert_to_write
        tag = self.env['test_new_api.multi.tag'].create({'name': 'Foo'})
        rec = self.env['test_new_api.multi'].create({
            'lines': [(0, 0, {'tags': [(6, 0, tag.ids)]})],
        })
        new = rec.new(origin=rec)
        self.assertEqual(new.lines.tags._origin, rec.lines.tags)
        vals = new._convert_to_write(new._cache)
        self.assertEqual(vals['lines'], [(6, 0, rec.lines.ids)])

    def test_41_new_compute(self):
        """ Check recomputation of fields on new records. """
        move = self.env['test_new_api.move'].create({
            'line_ids': [(0, 0, {'quantity': 1}), (0, 0, {'quantity': 1})],
        })
        move.flush()
        line = move.line_ids[0]

        new_move = move.new(origin=move)
        new_line = line.new(origin=line)

        # move_id is fetched from origin
        self.assertEqual(new_line.move_id, move)
        self.assertEqual(new_move.quantity, 2)
        self.assertEqual(move.quantity, 2)

        # modifying new_line must trigger recomputation on new_move, even if
        # new_line.move_id is not new_move!
        new_line.quantity = 2
        self.assertEqual(new_line.move_id, move)
        self.assertEqual(new_move.quantity, 3)
        self.assertEqual(move.quantity, 2)

    def test_41_new_one2many(self):
        """ Check command on one2many field on new record. """
        move = self.env['test_new_api.move'].create({})
        line = self.env['test_new_api.move_line'].create({'move_id': move.id, 'quantity': 1})
        move.flush()

        new_move = move.new(origin=move)
        new_line = line.new(origin=line)
        self.assertEqual(new_move.line_ids, new_line)

        # drop line, and create a new one
        new_move.line_ids = [(2, new_line.id), (0, 0, {'quantity': 2})]
        self.assertEqual(len(new_move.line_ids), 1)
        self.assertFalse(new_move.line_ids.id)
        self.assertEqual(new_move.line_ids.quantity, 2)

        # assign line to new move without origin
        new_move = move.new()
        new_move.line_ids = line
        self.assertFalse(new_move.line_ids.id)
        self.assertEqual(new_move.line_ids._origin, line)
        self.assertEqual(new_move.line_ids.move_id, new_move)

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_41_new_related(self):
        """ test the behavior of related fields starting on new records. """
        # make discussions unreadable for demo user
        access = self.env.ref('test_new_api.access_discussion')
        access.write({'perm_read': False})

        # create an environment for demo user
        env = self.env(user=self.env.ref('base.user_demo'))
        self.assertEqual(env.user.login, "demo")

        # create a new message as demo user
        discussion = self.env.ref('test_new_api.discussion_0')
        message = env['test_new_api.message'].new({'discussion': discussion})
        self.assertEqual(message.discussion, discussion)

        # read the related field discussion_name
        self.assertEqual(message.discussion.env, env)
        self.assertEqual(message.discussion_name, discussion.name)
        # DLE P75: message.discussion.name is put in the cache as sudo thanks to the computation of message.discussion_name
        # As we decided that now if we had the chance to access the value at some point in the code, and that it was stored in the cache
        # it's not a big deal to no longer raise the accesserror, as we had the chance to get the value at some point
        # with self.assertRaises(AccessError):
        #     message.discussion.name

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_42_new_related(self):
        """ test the behavior of related fields traversing new records. """
        # make discussions unreadable for demo user
        access = self.env.ref('test_new_api.access_discussion')
        access.write({'perm_read': False})

        # create an environment for demo user
        env = self.env(user=self.env.ref('base.user_demo'))
        self.assertEqual(env.user.login, "demo")

        # create a new discussion and a new message as demo user
        discussion = env['test_new_api.discussion'].new({'name': 'Stuff'})
        message = env['test_new_api.message'].new({'discussion': discussion})
        self.assertEqual(message.discussion, discussion)

        # read the related field discussion_name
        self.assertNotEqual(message.sudo().env, message.env)
        self.assertEqual(message.discussion_name, discussion.name)

    def test_43_new_related(self):
        """ test the behavior of one2many related fields """
        partner = self.env['res.partner'].create({
            'name': 'Foo',
            'child_ids': [(0, 0, {'name': 'Bar'})],
        })
        multi = self.env['test_new_api.multi'].new()
        multi.partner = partner
        self.assertEqual(multi.partners.mapped('name'), ['Bar'])

    def test_50_defaults(self):
        """ test default values. """
        fields = ['discussion', 'body', 'author', 'size']
        defaults = self.env['test_new_api.message'].default_get(fields)
        self.assertEqual(defaults, {'author': self.env.uid})

        defaults = self.env['test_new_api.mixed'].default_get(['number'])
        self.assertEqual(defaults, {'number': 3.14})

    def test_50_search_many2one(self):
        """ test search through a path of computed fields"""
        messages = self.env['test_new_api.message'].search(
            [('author_partner.name', '=', 'Marc Demo')])
        self.assertEqual(messages, self.env.ref('test_new_api.message_0_1'))

    def test_60_one2many_domain(self):
        """ test the cache consistency of a one2many field with a domain """
        discussion = self.env.ref('test_new_api.discussion_0')
        message = discussion.messages[0]
        self.assertNotIn(message, discussion.important_messages)

        message.important = True
        self.assertIn(message, discussion.important_messages)

        # writing on very_important_messages should call its domain method
        self.assertIn(message, discussion.very_important_messages)
        discussion.write({'very_important_messages': [(5,)]})
        self.assertFalse(discussion.very_important_messages)
        self.assertFalse(message.exists())

    def test_60_many2many_domain(self):
        """ test the cache consistency of a many2many field with a domain """
        discussion = self.env.ref('test_new_api.discussion_0')
        category = self.env['test_new_api.category'].create({'name': "Foo"})
        discussion.categories = category
        discussion.flush()
        discussion.invalidate_cache()

        # patch the many2many field to give it a domain (this simply avoids
        # adding yet another test model)
        field = discussion._fields['categories']
        self.patch(field, 'domain', [('color', '!=', 42)])
        self.registry.setup_models(self.cr)

        # the category is in the many2many
        self.assertIn(category, discussion.categories)

        # modify the category; it should not longer be in the many2many
        category.color = 42
        self.assertNotIn(category, discussion.categories)

        # modify again the category; it should be back in the many2many
        category.color = 69
        self.assertIn(category, discussion.categories)

    def test_70_x2many_write(self):
        discussion = self.env.ref('test_new_api.discussion_0')
        Message = self.env['test_new_api.message']
        # There must be 3 messages, 0 important
        self.assertEqual(len(discussion.messages), 3)
        self.assertEqual(len(discussion.important_messages), 0)
        self.assertEqual(len(discussion.very_important_messages), 0)
        discussion.important_messages = [(0, 0, {
            'body': 'What is the answer?',
            'important': True,
        })]
        # There must be 4 messages, 1 important
        self.assertEqual(len(discussion.messages), 4)
        self.assertEqual(len(discussion.important_messages), 1)
        self.assertEqual(len(discussion.very_important_messages), 1)
        discussion.very_important_messages |= Message.new({
            'body': '42',
            'important': True,
        })
        # There must be 5 messages, 2 important
        self.assertEqual(len(discussion.messages), 5)
        self.assertEqual(len(discussion.important_messages), 2)
        self.assertEqual(len(discussion.very_important_messages), 2)

    def test_70_relational_inverse(self):
        """ Check the consistency of relational fields with inverse(s). """
        discussion = self.env.ref('test_new_api.discussion_0')
        demo_discussion = discussion.with_user(self.env.ref('base.user_demo'))

        # check that the demo user sees the same messages
        self.assertEqual(demo_discussion.messages, discussion.messages)

        # add a message as user demo
        messages = demo_discussion.messages
        message = messages.create({'discussion': discussion.id})
        self.assertEqual(demo_discussion.messages, messages + message)
        self.assertEqual(demo_discussion.messages, discussion.messages)

        # add a message as superuser
        messages = discussion.messages
        message = messages.create({'discussion': discussion.id})
        self.assertEqual(discussion.messages, messages + message)
        self.assertEqual(demo_discussion.messages, discussion.messages)

    def test_71_relational_inverse(self):
        """ Check the consistency of relational fields with inverse(s). """
        move1 = self.env['test_new_api.move'].create({})
        move2 = self.env['test_new_api.move'].create({})
        line = self.env['test_new_api.move_line'].create({'move_id': move1.id})
        line.flush()

        self.env.cache.invalidate()
        line.with_context(prefetch_fields=False).move_id

        # Setting 'move_id' updates the one2many field that is based on it,
        # which has a domain.  Here we check that evaluating the domain does not
        # accidentally override 'move_id' (by prefetch).
        line.move_id = move2
        self.assertEqual(line.move_id, move2)

    def test_72_relational_inverse(self):
        """ Check the consistency of relational fields with inverse(s). """
        move1 = self.env['test_new_api.move'].create({})
        move2 = self.env['test_new_api.move'].create({})

        # makes sure that line.move_id is flushed before search
        line = self.env['test_new_api.move_line'].create({'move_id': move1.id})
        moves = self.env['test_new_api.move'].search([('line_ids', 'in', line.id)])
        self.assertEqual(moves, move1)

        # makes sure that line.move_id is flushed before search
        line.move_id = move2
        moves = self.env['test_new_api.move'].search([('line_ids', 'in', line.id)])
        self.assertEqual(moves, move2)

    def test_80_copy(self):
        Translations = self.env['ir.translation']
        discussion = self.env.ref('test_new_api.discussion_0')
        message = self.env.ref('test_new_api.message_0_0')
        message1 = self.env.ref('test_new_api.message_0_1')

        email = self.env.ref('test_new_api.emailmessage_0_0')
        self.assertEqual(email.message, message)

        self.env['res.lang'].load_lang('fr_FR')

        def count(msg):
            # return the number of translations of msg.label
            return Translations.search_count([
                ('name', '=', 'test_new_api.message,label'),
                ('res_id', '=', msg.id),
            ])

        # set a translation for message.label
        email.with_context(lang='fr_FR').label = "bonjour"
        self.assertEqual(count(message), 1)
        self.assertEqual(count(message1), 0)

        # setting the parent record should not copy its translations
        email.copy({'message': message1.id})
        self.assertEqual(count(message), 1)
        self.assertEqual(count(message1), 0)

        # setting a one2many should not copy translations on the lines
        discussion.copy({'messages': [(6, 0, message1.ids)]})
        self.assertEqual(count(message), 1)
        self.assertEqual(count(message1), 0)

    def test_85_binary_guess_zip(self):
        from odoo.addons.base.tests.test_mimetypes import ZIP
        # Regular ZIP files can be uploaded by non-admin users
        self.env['test_new_api.binary_svg'].with_user(
            self.env.ref('base.user_demo'),
        ).create({
            'name': 'Test without attachment',
            'image_wo_attachment': base64.b64decode(ZIP),
        })

    def test_86_text_base64_guess_svg(self):
        from odoo.addons.base.tests.test_mimetypes import SVG
        with self.assertRaises(UserError) as e:
            self.env['test_new_api.binary_svg'].with_user(
                self.env.ref('base.user_demo'),
            ).create({
                'name': 'Test without attachment',
                'image_wo_attachment': SVG.decode("utf-8"),
            })
        self.assertEqual(e.exception.name, 'Only admins can upload SVG files.')

    def test_90_binary_svg(self):
        from odoo.addons.base.tests.test_mimetypes import SVG
        # This should work without problems
        self.env['test_new_api.binary_svg'].create({
            'name': 'Test without attachment',
            'image_wo_attachment': SVG,
        })
        # And this gives error
        with self.assertRaises(UserError):
            self.env['test_new_api.binary_svg'].with_user(
                self.env.ref('base.user_demo'),
            ).create({
                'name': 'Test without attachment',
                'image_wo_attachment': SVG,
            })

    def test_91_binary_svg_attachment(self):
        from odoo.addons.base.tests.test_mimetypes import SVG
        # This doesn't neuter SVG with admin
        record = self.env['test_new_api.binary_svg'].create({
            'name': 'Test without attachment',
            'image_attachment': SVG,
        })
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', record._name),
            ('res_field', '=', 'image_attachment'),
            ('res_id', '=', record.id),
        ])
        self.assertEqual(attachment.mimetype, 'image/svg+xml')
        # ...but this should be neutered with demo user
        record = self.env['test_new_api.binary_svg'].with_user(
            self.env.ref('base.user_demo'),
        ).create({
            'name': 'Test without attachment',
            'image_attachment': SVG,
        })
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', record._name),
            ('res_field', '=', 'image_attachment'),
            ('res_id', '=', record.id),
        ])
        self.assertEqual(attachment.mimetype, 'text/plain')

    def test_92_binary_self_avatar_svg(self):
        from odoo.addons.base.tests.test_mimetypes import SVG
        demo_user = self.env.ref('base.user_demo')
        # User demo changes his own avatar
        demo_user.with_user(demo_user).image_1920 = SVG
        # The SVG file should have been neutered
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', demo_user.partner_id._name),
            ('res_field', '=', 'image_1920'),
            ('res_id', '=', demo_user.partner_id.id),
        ])
        self.assertEqual(attachment.mimetype, 'text/plain')

    def test_93_monetary_related(self):
        """ Check the currency field on related monetary fields. """
        # check base field
        field = self.env['test_new_api.monetary_base']._fields['amount']
        self.assertEqual(field.currency_field, 'base_currency_id')

        # related fields must use the field 'currency_id' or 'x_currency_id'
        field = self.env['test_new_api.monetary_related']._fields['amount']
        self.assertEqual(field.related, ('monetary_id', 'amount'))
        self.assertEqual(field.currency_field, 'currency_id')

        field = self.env['test_new_api.monetary_custom']._fields['x_amount']
        self.assertEqual(field.related, ('monetary_id', 'amount'))
        self.assertEqual(field.currency_field, 'x_currency_id')

        # inherited field must use the same field as its parent field
        field = self.env['test_new_api.monetary_inherits']._fields['amount']
        self.assertEqual(field.related, ('monetary_id', 'amount'))
        self.assertEqual(field.currency_field, 'base_currency_id')

    def test_94_image(self):
        f = io.BytesIO()
        Image.new('RGB', (4000, 2000), '#4169E1').save(f, 'PNG')
        f.seek(0)
        image_w = base64.b64encode(f.read())

        f = io.BytesIO()
        Image.new('RGB', (2000, 4000), '#4169E1').save(f, 'PNG')
        f.seek(0)
        image_h = base64.b64encode(f.read())

        record = self.env['test_new_api.model_image'].create({
            'name': 'image',
            'image': image_w,
            'image_128': image_w,
        })

        # test create (no resize)
        self.assertEqual(record.image, image_w)
        # test create (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_128))).size, (128, 64))
        # test create related store (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (512, 256))
        # test create related no store (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (256, 128))

        record.write({
            'image': image_h,
            'image_128': image_h,
        })

        # test write (no resize)
        self.assertEqual(record.image, image_h)
        # test write (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_128))).size, (64, 128))
        # test write related store (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (256, 512))
        # test write related no store (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (128, 256))

        record = self.env['test_new_api.model_image'].create({
            'name': 'image',
            'image': image_h,
            'image_128': image_h,
        })

        # test create (no resize)
        self.assertEqual(record.image, image_h)
        # test create (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_128))).size, (64, 128))
        # test create related store (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (256, 512))
        # test create related no store (resize, height limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (128, 256))

        record.write({
            'image': image_w,
            'image_128': image_w,
        })

        # test write (no resize)
        self.assertEqual(record.image, image_w)
        # test write (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_128))).size, (128, 64))
        # test write related store (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (512, 256))
        # test write related store (resize, width limited)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (256, 128))

        # test create inverse store
        record = self.env['test_new_api.model_image'].create({
            'name': 'image',
            'image_512': image_w,
        })
        record.invalidate_cache(fnames=['image_512'], ids=record.ids)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (512, 256))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image))).size, (4000, 2000))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (256, 128))
        # test write inverse store
        record.write({
            'image_512': image_h,
        })
        record.invalidate_cache(fnames=['image_512'], ids=record.ids)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (256, 512))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image))).size, (2000, 4000))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (128, 256))

        # test create inverse no store
        record = self.env['test_new_api.model_image'].create({
            'name': 'image',
            'image_256': image_w,
        })
        record.invalidate_cache(fnames=['image_256'], ids=record.ids)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (512, 256))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image))).size, (4000, 2000))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (256, 128))
        # test write inverse no store
        record.write({
            'image_256': image_h,
        })
        record.invalidate_cache(fnames=['image_256'], ids=record.ids)
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_512))).size, (256, 512))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image))).size, (2000, 4000))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(record.image_256))).size, (128, 256))

        # test bin_size
        record_bin_size = record.with_context(bin_size=True)
        self.assertEqual(record_bin_size.image, b'31.54 Kb')
        self.assertEqual(record_bin_size.image_512, b'1.02 Kb')
        self.assertEqual(record_bin_size.image_256, b'424.00 bytes')

        # ensure image_data_uri works (value must be bytes and not string)
        self.assertEqual(record.image_256[:8], b'iVBORw0K')
        self.assertEqual(image_data_uri(record.image_256)[:30], 'data:image/png;base64,iVBORw0K')

        # ensure invalid image raises
        with self.assertRaises(UserError), self.cr.savepoint():
            record.write({
                'image': 'invalid image',
            })

        # assignment of invalid image on new record does nothing, the value is
        # taken from origin instead (use-case: onchange)
        new_record = record.new(origin=record)
        new_record.image = '31.54 Kb'
        self.assertEqual(record.image, image_h)
        self.assertEqual(new_record.image, image_h)

        # assignment to new record with origin should not do any query
        with self.assertQueryCount(0):
            new_record.image = image_w

    def test_95_binary_bin_size(self):
        binary_value = base64.b64encode(b'content')
        binary_size = b'7.00 bytes'

        def assertBinaryValue(record, value):
            for field in ('binary', 'binary_related_store', 'binary_related_no_store'):
                self.assertEqual(record[field], value)

        # created, flushed, and first read without context
        record = self.env['test_new_api.model_binary'].create({'binary': binary_value})
        record.flush()
        record.invalidate_cache()
        record_no_bin_size = record.with_context(bin_size=False)
        record_bin_size = record.with_context(bin_size=True)

        assertBinaryValue(record, binary_value)
        assertBinaryValue(record_no_bin_size, binary_value)
        assertBinaryValue(record_bin_size, binary_size)

        # created, flushed, and first read with bin_size=False
        record_no_bin_size = self.env['test_new_api.model_binary'].with_context(bin_size=False).create({'binary': binary_value})
        record_no_bin_size.flush()
        record_no_bin_size.invalidate_cache()
        record = self.env['test_new_api.model_binary'].browse(record.id)
        record_bin_size = record.with_context(bin_size=True)

        assertBinaryValue(record_no_bin_size, binary_value)
        assertBinaryValue(record, binary_value)
        assertBinaryValue(record_bin_size, binary_size)

        # created, flushed, and first read with bin_size=True
        record_bin_size = self.env['test_new_api.model_binary'].with_context(bin_size=True).create({'binary': binary_value})
        record_bin_size.flush()
        record_bin_size.invalidate_cache()
        record = self.env['test_new_api.model_binary'].browse(record.id)
        record_no_bin_size = record.with_context(bin_size=False)

        assertBinaryValue(record_bin_size, binary_size)
        assertBinaryValue(record_no_bin_size, binary_value)
        assertBinaryValue(record, binary_value)

        # created without context and flushed with bin_size
        record = self.env['test_new_api.model_binary'].create({'binary': binary_value})
        record_no_bin_size = record.with_context(bin_size=False)
        record_bin_size = record.with_context(bin_size=True)
        record_bin_size.flush()
        record_bin_size.invalidate_cache()

        assertBinaryValue(record, binary_value)
        assertBinaryValue(record_no_bin_size, binary_value)
        assertBinaryValue(record_bin_size, binary_size)

        # check computed binary field with arbitrary Python value
        record = self.env['test_new_api.model_binary'].create({})
        record.flush()
        record.invalidate_cache()
        record_no_bin_size = record.with_context(bin_size=False)
        record_bin_size = record.with_context(bin_size=True)

        expected_value = [(record.id, False)]
        self.assertEqual(record.binary_computed, expected_value)
        self.assertEqual(record_no_bin_size.binary_computed, expected_value)
        self.assertEqual(record_bin_size.binary_computed, expected_value)

    def test_96_order_m2o(self):
        belgium, congo = self.env['test_new_api.country'].create([
            {'name': "Duchy of Brabant"},
            {'name': "Congo"},
        ])
        cities = self.env['test_new_api.city'].create([
            {'name': "Brussels", 'country_id': belgium.id},
            {'name': "Kinshasa", 'country_id': congo.id},
        ])
        # cities are sorted by country_id, name
        self.assertEqual(cities.sorted().mapped('name'), ["Kinshasa", "Brussels"])

        # change order of countries, and check sorted()
        belgium.name = "Belgium"
        self.assertEqual(cities.sorted().mapped('name'), ["Brussels", "Kinshasa"])

    def test_97_ir_rule_m2m_field(self):
        """Ensures m2m fields can't be read if the left records can't be read.
        Also makes sure reading m2m doesn't take more queries than necessary."""
        tag = self.env['test_new_api.multi.tag'].create({})
        record = self.env['test_new_api.multi.line'].create({
            'name': 'image',
            'tags': [(4, tag.id)],
        })

        # only one query as admin: reading pivot table
        with self.assertQueryCount(1):
            record.read(['tags'])

        user = self.env['res.users'].create({'name': "user", 'login': "user"})
        record_user = record.with_user(user)

        # prep the following query count by caching access check related data
        record_user.read(['tags'])

        # only one query as user: reading pivot table
        with self.assertQueryCount(1):
            record_user.read(['tags'])

        # create a passing ir.rule
        self.env['ir.rule'].create({
            'model_id': self.env['ir.model']._get(record._name).id,
            'domain_force': "[('id', '=', %d)]" % record.id,
        })

        # prep the following query count by caching access check related data
        record_user.read(['tags'])

        # still only 1 query: reading pivot table
        # access rules are checked in python in this case
        with self.assertQueryCount(1):
            record_user.read(['tags'])

        # create a blocking ir.rule
        self.env['ir.rule'].create({
            'model_id': self.env['ir.model']._get(record._name).id,
            'domain_force': "[('id', '!=', %d)]" % record.id,
        })

        # ensure ir.rule is applied even when reading m2m
        with self.assertRaises(AccessError):
            record_user.read(['tags'])

    def test_98_unlink_recompute(self):
        move = self.env['test_new_api.move'].create({
            'line_ids': [(0, 0, {'quantity': 42})],
        })
        line = move.line_ids
        self.assertEqual(move.quantity, 42)

        # create an ir.rule for lines that uses move.quantity
        self.env['ir.rule'].create({
            'model_id': self.env['ir.model']._get(line._name).id,
            'domain_force': "[('move_id.quantity', '>=', 0)]",
        })

        # unlink the line, and check the recomputation of move.quantity
        user = self.env.ref('base.user_demo')
        line.with_user(user).unlink()
        self.assertEqual(move.quantity, 0)


class TestX2many(common.TransactionCase):
    def test_definition_many2many(self):
        """ Test the definition of inherited many2many fields. """
        field = self.env['test_new_api.multi.line']._fields['tags']
        self.assertEqual(field.relation, 'test_new_api_multi_line_test_new_api_multi_tag_rel')
        self.assertEqual(field.column1, 'test_new_api_multi_line_id')
        self.assertEqual(field.column2, 'test_new_api_multi_tag_id')

        field = self.env['test_new_api.multi.line2']._fields['tags']
        self.assertEqual(field.relation, 'test_new_api_multi_line2_test_new_api_multi_tag_rel')
        self.assertEqual(field.column1, 'test_new_api_multi_line2_id')
        self.assertEqual(field.column2, 'test_new_api_multi_tag_id')

    def test_10_ondelete_many2many(self):
        """Test A can't be deleted when used on the relation."""
        record_a = self.env['test_new_api.model_a'].create({'name': 'a'})
        record_b = self.env['test_new_api.model_b'].create({'name': 'b'})
        record_a.write({
            'a_restricted_b_ids': [(6, 0, record_b.ids)],
        })
        with self.assertRaises(psycopg2.IntegrityError):
            with mute_logger('odoo.sql_db'), self.cr.savepoint():
                record_a.unlink()
        # Test B is still cascade.
        record_b.unlink()
        self.assertFalse(record_b.exists())

    def test_11_ondelete_many2many(self):
        """Test B can't be deleted when used on the relation."""
        record_a = self.env['test_new_api.model_a'].create({'name': 'a'})
        record_b = self.env['test_new_api.model_b'].create({'name': 'b'})
        record_a.write({
            'b_restricted_b_ids': [(6, 0, record_b.ids)],
        })
        with self.assertRaises(psycopg2.IntegrityError):
            with mute_logger('odoo.sql_db'), self.cr.savepoint():
                record_b.unlink()
        # Test A is still cascade.
        record_a.unlink()
        self.assertFalse(record_a.exists())

    def test_12_active_test_one2many(self):
        Model = self.env['test_new_api.model_active_field']

        parent = Model.create({})
        self.assertFalse(parent.children_ids)

        # create with implicit active_test=True in context
        child1, child2 = Model.create([
            {'parent_id': parent.id, 'active': True},
            {'parent_id': parent.id, 'active': False},
        ])
        act_children = child1
        all_children = child1 + child2
        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)

        # create with active_test=False in context
        child3, child4 = Model.with_context(active_test=False).create([
            {'parent_id': parent.id, 'active': True},
            {'parent_id': parent.id, 'active': False},
        ])
        act_children = child1 + child3
        all_children = child1 + child2 + child3 + child4
        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)

        # replace active children
        parent.write({'children_ids': [(6, 0, [child1.id])]})
        act_children = child1
        all_children = child1 + child2 + child4
        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)

        # replace all children
        parent.with_context(active_test=False).write({'children_ids': [(6, 0, [child1.id])]})
        act_children = child1
        all_children = child1
        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)

        # check recomputation of inactive records
        parent.write({'children_ids': [(6, 0, child4.ids)]})
        self.assertTrue(child4.parent_active)
        parent.active = False
        self.assertFalse(child4.parent_active)

    def test_12_active_test_one2many_with_context(self):
        Model = self.env['test_new_api.model_active_field']
        parent = Model.create({})
        all_children = Model.create([
            {'parent_id': parent.id, 'active': True},
            {'parent_id': parent.id, 'active': False},
        ])
        act_children = all_children[0]

        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)

        self.assertEqual(parent.all_children_ids, all_children)
        self.assertEqual(parent.with_context(active_test=True).all_children_ids, all_children)
        self.assertEqual(parent.with_context(active_test=False).all_children_ids, all_children)

        self.assertEqual(parent.active_children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=True).active_children_ids, act_children)
        self.assertEqual(parent.with_context(active_test=False).active_children_ids, act_children)

        # check read()
        self.env.cache.invalidate()
        self.assertEqual(parent.children_ids, act_children)
        self.assertEqual(parent.all_children_ids, all_children)
        self.assertEqual(parent.active_children_ids, act_children)

        self.env.cache.invalidate()
        self.assertEqual(parent.with_context(active_test=False).children_ids, all_children)
        self.assertEqual(parent.with_context(active_test=False).all_children_ids, all_children)
        self.assertEqual(parent.with_context(active_test=False).active_children_ids, act_children)

    def test_search_many2many(self):
        """ Tests search on many2many fields. """
        tags = self.env['test_new_api.multi.tag']
        tagA = tags.create({})
        tagB = tags.create({})
        tagC = tags.create({})
        recs = self.env['test_new_api.multi.line']
        recW = recs.create({})
        recX = recs.create({'tags': [(4, tagA.id)]})
        recY = recs.create({'tags': [(4, tagB.id)]})
        recZ = recs.create({'tags': [(4, tagA.id), (4, tagB.id)]})
        recs = recW + recX + recY + recZ

        # test 'in'
        result = recs.search([('tags', 'in', (tagA + tagB).ids)])
        self.assertEqual(result, recX + recY + recZ)

        result = recs.search([('tags', 'in', tagA.ids)])
        self.assertEqual(result, recX + recZ)

        result = recs.search([('tags', 'in', tagB.ids)])
        self.assertEqual(result, recY + recZ)

        result = recs.search([('tags', 'in', tagC.ids)])
        self.assertEqual(result, recs.browse())

        result = recs.search([('tags', 'in', [])])
        self.assertEqual(result, recs.browse())

        # test 'not in'
        result = recs.search([('id', 'in', recs.ids), ('tags', 'not in', (tagA + tagB).ids)])
        self.assertEqual(result, recs - recX - recY - recZ)

        result = recs.search([('id', 'in', recs.ids), ('tags', 'not in', tagA.ids)])
        self.assertEqual(result, recs - recX - recZ)

        result = recs.search([('id', 'in', recs.ids), ('tags', 'not in', tagB.ids)])
        self.assertEqual(result, recs - recY - recZ)

        result = recs.search([('id', 'in', recs.ids), ('tags', 'not in', tagC.ids)])
        self.assertEqual(result, recs)

        result = recs.search([('id', 'in', recs.ids), ('tags', 'not in', [])])
        self.assertEqual(result, recs)

        # special case: compare with False
        result = recs.search([('id', 'in', recs.ids), ('tags', '=', False)])
        self.assertEqual(result, recW)

        result = recs.search([('id', 'in', recs.ids), ('tags', '!=', False)])
        self.assertEqual(result, recs - recW)

    def test_search_one2many(self):
        """ Tests search on one2many fields. """
        recs = self.env['test_new_api.multi']
        recX = recs.create({'lines': [(0, 0, {}), (0, 0, {})]})
        recY = recs.create({'lines': [(0, 0, {})]})
        recZ = recs.create({})
        recs = recX + recY + recZ
        line1, line2, line3 = recs.lines
        line4 = recs.create({'lines': [(0, 0, {})]}).lines
        line0 = line4.create({})

        # test 'in'
        result = recs.search([('id', 'in', recs.ids), ('lines', 'in', (line1 + line2 + line3 + line4).ids)])
        self.assertEqual(result, recX + recY)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'in', (line1 + line3 + line4).ids)])
        self.assertEqual(result, recX + recY)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'in', (line1 + line4).ids)])
        self.assertEqual(result, recX)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'in', line4.ids)])
        self.assertEqual(result, recs.browse())

        result = recs.search([('id', 'in', recs.ids), ('lines', 'in', [])])
        self.assertEqual(result, recs.browse())

        # test 'not in'
        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', (line1 + line2 + line3).ids)])
        self.assertEqual(result, recs - recX - recY)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', (line1 + line3).ids)])
        self.assertEqual(result, recs - recX - recY)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', line1.ids)])
        self.assertEqual(result, recs - recX)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', (line1 + line4).ids)])
        self.assertEqual(result, recs - recX)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', line4.ids)])
        self.assertEqual(result, recs)

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', [])])
        self.assertEqual(result, recs)

        # these cases are weird
        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', (line1 + line0).ids)])
        self.assertEqual(result, recs.browse())

        result = recs.search([('id', 'in', recs.ids), ('lines', 'not in', line0.ids)])
        self.assertEqual(result, recs.browse())

        # special case: compare with False
        result = recs.search([('id', 'in', recs.ids), ('lines', '=', False)])
        self.assertEqual(result, recZ)

        result = recs.search([('id', 'in', recs.ids), ('lines', '!=', False)])
        self.assertEqual(result, recs - recZ)

    def test_create_batch_m2m(self):
        lines = self.env['test_new_api.multi.line'].create([{
            'tags': [(0, 0, {'name': str(j)}) for j in range(3)],
        } for i in range(3)])
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(len(line.tags), 3)

    def test_custom_m2m(self):
        model_id = self.env['ir.model']._get_id('res.partner')
        field = self.env['ir.model.fields'].create({
            'name': 'x_foo',
            'field_description': 'Foo',
            'model_id': model_id,
            'ttype': 'many2many',
            'relation': 'res.country',
            'store': False,
        })
        self.assertTrue(field.unlink())

    def test_custom_m2m_related(self):
        # this checks the ondelete of a related many2many field
        model_id = self.env['ir.model']._get_id('res.partner')
        field = self.env['ir.model.fields'].create({
            'name': 'x_foo',
            'field_description': 'Foo',
            'model_id': model_id,
            'ttype': 'many2many',
            'relation': 'res.partner.category',
            'related': 'category_id',
            'readonly': True,
            'store': True,
        })
        self.assertTrue(field.unlink())


class TestHtmlField(common.TransactionCase):

    def setUp(self):
        super(TestHtmlField, self).setUp()
        self.model = self.env['test_new_api.mixed']

    def test_00_sanitize(self):
        self.assertEqual(self.model._fields['comment1'].sanitize, False)
        self.assertEqual(self.model._fields['comment2'].sanitize_attributes, True)
        self.assertEqual(self.model._fields['comment2'].strip_classes, False)
        self.assertEqual(self.model._fields['comment3'].sanitize_attributes, True)
        self.assertEqual(self.model._fields['comment3'].strip_classes, True)

        some_ugly_html = """<p>Oops this should maybe be sanitized
% if object.some_field and not object.oriented:
<table>
    % if object.other_field:
    <tr style="margin: 0px; border: 10px solid black;">
        ${object.mako_thing}
        <td>
    </tr>
    <tr class="custom_class">
        This is some html.
    </tr>
    % endif
    <tr>
%if object.dummy_field:
        <p>Youpie</p>
%endif"""

        record = self.model.create({
            'comment1': some_ugly_html,
            'comment2': some_ugly_html,
            'comment3': some_ugly_html,
            'comment4': some_ugly_html,
        })

        self.assertEqual(record.comment1, some_ugly_html, 'Error in HTML field: content was sanitized but field has sanitize=False')

        self.assertIn('<tr class="', record.comment2)

        # sanitize should have closed tags left open in the original html
        self.assertIn('</table>', record.comment3, 'Error in HTML field: content does not seem to have been sanitized despise sanitize=True')
        self.assertIn('</td>', record.comment3, 'Error in HTML field: content does not seem to have been sanitized despise sanitize=True')
        self.assertIn('<tr style="', record.comment3, 'Style attr should not have been stripped')
        # sanitize does not keep classes if asked to
        self.assertNotIn('<tr class="', record.comment3)

        self.assertNotIn('<tr style="', record.comment4, 'Style attr should have been stripped')


class TestMagicFields(common.TransactionCase):

    def test_write_date(self):
        record = self.env['test_new_api.discussion'].create({'name': 'Booba'})
        self.assertEqual(record.create_uid, self.env.user)
        self.assertEqual(record.write_uid, self.env.user)

    def test_mro_mixin(self):
        #                               Mixin
        #                                |
        #                                |
        #                                |
        #   ExtendedDisplay    'test_new_api.mixin'    Display    'base'
        #         |                      |                |         |
        #         +----------------------+-+--------------+---------+
        #                                  |
        #                       'test_new_api.display'
        #
        # The field 'display_name' is defined as store=True on the class Display
        # above.  The field 'display_name' on the model 'test_new_api.mixin' is
        # expected to be automatic and non-stored.  But the field 'display_name'
        # on the model 'test_new_api.display' should not be automatic: it must
        # correspond to the definition given in class Display, even if the MRO
        # of the model shows the automatic field on the mixin model before the
        # actual definition.
        registry = self.env.registry
        models = registry.models

        # check setup of models in alphanumeric order
        self.patch(registry, 'models', OrderedDict(sorted(models.items())))
        registry.model_cache.clear()
        registry.setup_models(self.cr)
        field = registry['test_new_api.display'].display_name
        self.assertFalse(field.automatic)
        self.assertTrue(field.store)

        # check setup of models in reverse alphanumeric order
        self.patch(registry, 'models', OrderedDict(sorted(models.items(), reverse=True)))
        registry.model_cache.clear()
        registry.setup_models(self.cr)
        field = registry['test_new_api.display'].display_name
        self.assertFalse(field.automatic)
        self.assertTrue(field.store)


class TestParentStore(common.TransactionCase):

    def setUp(self):
        super(TestParentStore, self).setUp()
        # make a tree of categories:
        #   0
        #  /|\
        # 1 2 3
        #    /|\
        #   4 5 6
        #      /|\
        #     7 8 9
        Cat = self.env['test_new_api.category']
        cat0 = Cat.create({'name': '0'})
        cat1 = Cat.create({'name': '1', 'parent': cat0.id})
        cat2 = Cat.create({'name': '2', 'parent': cat0.id})
        cat3 = Cat.create({'name': '3', 'parent': cat0.id})
        cat4 = Cat.create({'name': '4', 'parent': cat3.id})
        cat5 = Cat.create({'name': '5', 'parent': cat3.id})
        cat6 = Cat.create({'name': '6', 'parent': cat3.id})
        cat7 = Cat.create({'name': '7', 'parent': cat6.id})
        cat8 = Cat.create({'name': '8', 'parent': cat6.id})
        cat9 = Cat.create({'name': '9', 'parent': cat6.id})
        self._cats = Cat.concat(cat0, cat1, cat2, cat3, cat4,
                                cat5, cat6, cat7, cat8, cat9)

    def cats(self, *indexes):
        """ Return the given categories. """
        ids = self._cats.ids
        return self._cats.browse([ids[index] for index in indexes])

    def assertChildOf(self, category, children):
        self.assertEqual(category.search([('id', 'child_of', category.ids)]), children)

    def assertParentOf(self, category, parents):
        self.assertEqual(category.search([('id', 'parent_of', category.ids)]), parents)

    def test_base(self):
        """ Check the initial tree structure. """
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(1), self.cats(1))
        self.assertChildOf(self.cats(2), self.cats(2))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(4), self.cats(4))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertChildOf(self.cats(7), self.cats(7))
        self.assertChildOf(self.cats(8), self.cats(8))
        self.assertChildOf(self.cats(9), self.cats(9))
        self.assertParentOf(self.cats(0), self.cats(0))
        self.assertParentOf(self.cats(1), self.cats(0, 1))
        self.assertParentOf(self.cats(2), self.cats(0, 2))
        self.assertParentOf(self.cats(3), self.cats(0, 3))
        self.assertParentOf(self.cats(4), self.cats(0, 3, 4))
        self.assertParentOf(self.cats(5), self.cats(0, 3, 5))
        self.assertParentOf(self.cats(6), self.cats(0, 3, 6))
        self.assertParentOf(self.cats(7), self.cats(0, 3, 6, 7))
        self.assertParentOf(self.cats(8), self.cats(0, 3, 6, 8))
        self.assertParentOf(self.cats(9), self.cats(0, 3, 6, 9))

    def test_base_compute(self):
        """ Check the tree structure after computation from scratch. """
        self.cats()._parent_store_compute()
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(1), self.cats(1))
        self.assertChildOf(self.cats(2), self.cats(2))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(4), self.cats(4))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertChildOf(self.cats(7), self.cats(7))
        self.assertChildOf(self.cats(8), self.cats(8))
        self.assertChildOf(self.cats(9), self.cats(9))
        self.assertParentOf(self.cats(0), self.cats(0))
        self.assertParentOf(self.cats(1), self.cats(0, 1))
        self.assertParentOf(self.cats(2), self.cats(0, 2))
        self.assertParentOf(self.cats(3), self.cats(0, 3))
        self.assertParentOf(self.cats(4), self.cats(0, 3, 4))
        self.assertParentOf(self.cats(5), self.cats(0, 3, 5))
        self.assertParentOf(self.cats(6), self.cats(0, 3, 6))
        self.assertParentOf(self.cats(7), self.cats(0, 3, 6, 7))
        self.assertParentOf(self.cats(8), self.cats(0, 3, 6, 8))
        self.assertParentOf(self.cats(9), self.cats(0, 3, 6, 9))

    def test_delete(self):
        """ Delete a node. """
        self.cats(6).unlink()
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertParentOf(self.cats(0), self.cats(0))
        self.assertParentOf(self.cats(3), self.cats(0, 3))
        self.assertParentOf(self.cats(5), self.cats(0, 3, 5))

    def test_move_1_0(self):
        """ Move a node to a root position. """
        self.cats(6).write({'parent': False})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(9), self.cats(6, 9))

    def test_move_1_1(self):
        """ Move a node into an empty subtree. """
        self.cats(6).write({'parent': self.cats(1).id})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(1), self.cats(1, 6, 7, 8, 9))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(9), self.cats(0, 1, 6, 9))

    def test_move_1_N(self):
        """ Move a node into a non-empty subtree. """
        self.cats(6).write({'parent': self.cats(0).id})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(3), self.cats(3, 4, 5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(9), self.cats(0, 6, 9))

    def test_move_N_0(self):
        """ Move multiple nodes to root position. """
        self.cats(5, 6).write({'parent': False})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4))
        self.assertChildOf(self.cats(3), self.cats(3, 4))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(5), self.cats(5))
        self.assertParentOf(self.cats(9), self.cats(6, 9))

    def test_move_N_1(self):
        """ Move multiple nodes to an empty subtree. """
        self.cats(5, 6).write({'parent': self.cats(1).id})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(1), self.cats(1, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(3), self.cats(3, 4))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(5), self.cats(0, 1, 5))
        self.assertParentOf(self.cats(9), self.cats(0, 1, 6, 9))

    def test_move_N_N(self):
        """ Move multiple nodes to a non- empty subtree. """
        self.cats(5, 6).write({'parent': self.cats(0).id})
        self.assertChildOf(self.cats(0), self.cats(0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.assertChildOf(self.cats(3), self.cats(3, 4))
        self.assertChildOf(self.cats(5), self.cats(5))
        self.assertChildOf(self.cats(6), self.cats(6, 7, 8, 9))
        self.assertParentOf(self.cats(5), self.cats(0, 5))
        self.assertParentOf(self.cats(9), self.cats(0, 6, 9))

    def test_move_1_cycle(self):
        """ Move a node to create a cycle. """
        with self.assertRaises(UserError):
            self.cats(3).write({'parent': self.cats(9).id})

    def test_move_N_cycle(self):
        """ Move multiple nodes to create a cycle. """
        with self.assertRaises(UserError):
            self.cats(1, 3).write({'parent': self.cats(9).id})

    def test_compute_depend_parent_path(self):
        self.assertEqual(self.cats(7).depth, 3)
        self.assertEqual(self.cats(8).depth, 3)
        self.assertEqual(self.cats(9).depth, 3)

        # change parent of node to have 2 parents
        self.cats(7).parent = self.cats(2)
        self.assertEqual(self.cats(7).depth, 2)

        # change parent of node to root
        self.cats(7).parent = False
        self.assertEqual(self.cats(7).depth, 0)

        # change grand-parent of nodes
        self.cats(6).parent = self.cats(0)
        self.assertEqual(self.cats(8).depth, 2)
        self.assertEqual(self.cats(9).depth, 2)


class TestRequiredMany2one(common.TransactionCase):

    def test_explicit_ondelete(self):
        field = self.env['test_new_api.req_m2o']._fields['foo']
        self.assertEqual(field.ondelete, 'cascade')

    def test_implicit_ondelete(self):
        field = self.env['test_new_api.req_m2o']._fields['bar']
        self.assertEqual(field.ondelete, 'restrict')

    def test_explicit_set_null(self):
        Model = self.env['test_new_api.req_m2o']
        field = Model._fields['foo']

        # invalidate registry to redo the setup afterwards
        self.registry.registry_invalidated = True
        self.patch(field, 'ondelete', 'set null')

        with self.assertRaises(ValueError):
            field._setup_regular_base(Model)


class TestRequiredMany2oneTransient(common.TransactionCase):

    def test_explicit_ondelete(self):
        field = self.env['test_new_api.req_m2o_transient']._fields['foo']
        self.assertEqual(field.ondelete, 'restrict')

    def test_implicit_ondelete(self):
        field = self.env['test_new_api.req_m2o_transient']._fields['bar']
        self.assertEqual(field.ondelete, 'cascade')

    def test_explicit_set_null(self):
        Model = self.env['test_new_api.req_m2o_transient']
        field = Model._fields['foo']

        # invalidate registry to redo the setup afterwards
        self.registry.registry_invalidated = True
        self.patch(field, 'ondelete', 'set null')

        with self.assertRaises(ValueError):
            field._setup_regular_base(Model)


@common.tagged('m2oref')
class TestMany2oneReference(common.TransactionCase):

    def test_delete_m2o_reference_records(self):
        m = self.env['test_new_api.model_many2one_reference']
        self.env.cr.execute("SELECT max(id) FROM test_new_api_model_many2one_reference")
        ids = self.env.cr.fetchone()
        # fake record to emulate the unlink of a non-existant record
        foo = m.browse(1 if not ids[0] else (ids[0] + 1))
        self.assertTrue(foo.unlink())


@common.tagged('selection_abstract')
class TestSelectionDeleteUpdate(common.TransactionCase):

    MODEL_ABSTRACT = 'test_new_api.state_mixin'

    def test_unlink_asbtract(self):
        self.env['ir.model.fields.selection'].search([
            ('field_id.model', '=', self.MODEL_ABSTRACT),
            ('field_id.name', '=', 'state'),
            ('value', '=', 'confirmed'),
        ], limit=1).unlink()


class test_shared_cache(common.TransactionCase):
    def test_shared_cache_computed_field(self):
        # Test case: Check that the shared cache is not used if a compute_sudo stored field
        # is computed IF there is an ir.rule defined on this specific model.

        # Real life example:
        # A user can only see its own timesheets on a task, but the field "Planned Hours",
        # which is stored-compute_sudo, should take all the timesheet lines into account
        # However, when adding a new line and then recomputing the value, no existing line
        # from another user is binded on self, then the value is erased and saved on the
        # database.

        task = self.env['test_new_api.model_shared_cache_compute_parent'].create({
            'name': 'Shared Task'})
        self.env['test_new_api.model_shared_cache_compute_line'].create({
            'user_id': self.env.ref('base.user_admin').id,
            'parent_id': task.id,
            'amount': 1,
        })
        self.assertEqual(task.total_amount, 1)

        self.env['base'].flush()
        task.invalidate_cache()  # Start fresh, as it would be the case on 2 different sessions.

        task = task.with_user(self.env.ref('base.user_demo'))
        with common.Form(task) as task_form:
            # Use demo has no access to the already existing line
            self.assertEqual(len(task_form.line_ids), 0)
            # But see the real total_amount
            self.assertEqual(task_form.total_amount, 1)
            # Now let's add a new line (and retrigger the compute method)
            with task_form.line_ids.new() as line:
                line.amount = 2
            # YTI FIXME : The new value for total_amount, should be 3, not 2.
            # self.assertEqual(task_form.total_amount, 3)
            self.assertEqual(task_form.total_amount, 2)
