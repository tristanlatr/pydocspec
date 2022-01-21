import unittest
from textwrap import dedent

import astroid.nodes
import astroid.rebuilder
import astroid.builder
import pytest
from pydocspec import astroidutils

from .test_astbuilder import mod_from_text

class InferTypeAnnotationTests(unittest.TestCase):
    def test_literal_infer(self):
        values = [
            ("{'pom': '12'}", 'dict[str, str]'),
            ("{'pom': 12}", 'dict[str, int]'),
            ("{'pom', 12}", 'set'),
            ("{12, 12}", 'set[int]'),
            ("('pom', 12)", 'tuple'),
            ("(12, 12)", 'tuple[int, ...]'), 
            ("['pom', 12]", 'list'),
            ("[12, 12]", 'list[int]'),
            ("[{'pom': 12}, {'foo': 19}]", 'list[dict]'),
            ("[{'pom': ['123']}, {'foo': ['456']}]", 'list[dict]'),
        ]

        for val, expected_ann in values:
            ann = astroidutils.infer_type_annotation(astroid.builder.parse(val).body[0])
            self.assertEqual(ann.as_string(), expected_ann)

class UnstringAnnotationTests(unittest.TestCase):

    def test_unstring(self):
        annotations = [
            ("hey['list']", "hey[list]"),
            ("hey['list[tuple]']", "hey[list[tuple]]"),
            ("List[Tuple[typing.Literal['good', 'bad'], 'Myobj', Status]]", "List[Tuple[typing.Literal['good', 'bad'], Myobj, Status]]"), 
            ("Tuple[Literal['good', 'bad'], Callable[['MyGeneric[str, Any]'], 'ParsedDocstring']]", "Tuple[Literal['good', 'bad'], Callable[[MyGeneric[str, Any]], ParsedDocstring]]")
            ]
        
        for origin_ann, expected_ann in annotations:
            unstringed = astroidutils.unstring_annotation(astroid.builder.parse(origin_ann).body[0])
            self.assertEqual(unstringed.as_string(), expected_ann)
    
    def test_unstring_raises(self):
        with self.assertRaises(SyntaxError):
            astroidutils.unstring_annotation(astroid.builder.parse("hey['List[']").body[0])
        with self.assertRaisesRegex(SyntaxError, "expected expression, found statement"):
            astroidutils.unstring_annotation(astroid.builder.parse("hey['x=2']").body[0])
        with self.assertRaisesRegex(SyntaxError, "expected expression, found multiple statements"):
            astroidutils.unstring_annotation(astroid.builder.parse(r"hey['list[str]\nlist[str]']").body[0])

class NodeVisitorTests(unittest.TestCase):
    def test_visit_nodes(self):
        class Visitor(astroidutils.NodeVisitor):
            def __init__(self, log) -> None:
                self.log = log
            def visit_Const(self, node: astroid.nodes.Const):
                log.append( (node.lineno, node.__class__.__name__, getattr(node, 'value', node.as_string())) )
            visit_Call = visit_Const
            
        mod = astroid.builder.parse(dedent('''\
            i = 42
            f = 4.25
            c = 4.25j
            s = 'string'
            b = b'bytes'
            t = True
            n = None
            e = ...
            k = list()
            @list(123)
            class Node:
                pass
            '''))
        log = []
        visitor = Visitor(log)
        
        visitor.visit(mod)
        self.assertEqual(log, [
            (1, 'Const', 42),
            (2, 'Const', 4.25),
            (3, 'Const', 4.25j),
            (4, 'Const', 'string'),
            (5, 'Const', b'bytes'),
            (6, 'Const', True),
            (7, 'Const', None),
            (8, 'Const', ...),
            (9, 'Call', 'list()'),
            (10, 'Call', 'list(123)'),
        ])
    
    def test_transform_nodes(self):
        class RewriteName(astroidutils.NodeTransformer):
            # rewrites names to data['<name>']
           def visit_Name(self, node:astroid.nodes.Name) -> astroid.nodes.NodeNG:
               return astroidutils.nodefactory.Subscript(
                   value=astroid.nodes.Name(name='data'),
                   slice=astroid.nodes.Const(value=node.name))
        
        mod = astroid.builder.parse(dedent('''\
            range(list(123), 'soleil')
            f = 4.25
            k = list()


            @list(123)
            class Node:
                pass
            '''))
        
        expected = dedent('''\
            data['range'](data['list'](123), 'soleil')
            f = 4.25
            k = data['list']()


            @data['list'](123)
            class Node:
                pass
            ''')
        
        visitor = RewriteName()
        visitor.visit(mod)
        self.assertEqual(mod.as_string().strip(), expected.strip())

class LiteralEvalTests(unittest.TestCase):
    def test_literal_eval(self):
        self.assertEqual(astroidutils.literal_eval('[1, 2, 3]'), [1, 2, 3])
        self.assertEqual(astroidutils.literal_eval('{"foo": 42}'), {"foo": 42})
        self.assertEqual(astroidutils.literal_eval('(True, False, None)'), (True, False, None))
        self.assertEqual(astroidutils.literal_eval('{1, 2, 3}'), {1, 2, 3})
        self.assertEqual(astroidutils.literal_eval('b"hi"'), b"hi")
        self.assertEqual(astroidutils.literal_eval('set()'), set())
        self.assertRaises(ValueError, astroidutils.literal_eval, 'foo()')
        self.assertEqual(astroidutils.literal_eval('6'), 6)
        self.assertEqual(astroidutils.literal_eval('+6'), 6)
        self.assertEqual(astroidutils.literal_eval('-6'), -6)
        self.assertEqual(astroidutils.literal_eval('3.25'), 3.25)
        self.assertEqual(astroidutils.literal_eval('+3.25'), 3.25)
        self.assertEqual(astroidutils.literal_eval('-3.25'), -3.25)
        self.assertEqual(repr(astroidutils.literal_eval('-0.0')), '-0.0')
        self.assertRaises(ValueError, astroidutils.literal_eval, '++6')
        self.assertRaises(ValueError, astroidutils.literal_eval, '+True')
        self.assertRaises(ValueError, astroidutils.literal_eval, '2+3')

    def test_literal_eval_complex(self):
        # Issue #4907
        self.assertEqual(astroidutils.literal_eval('6j'), 6j)
        self.assertEqual(astroidutils.literal_eval('-6j'), -6j)
        self.assertEqual(astroidutils.literal_eval('6.75j'), 6.75j)
        self.assertEqual(astroidutils.literal_eval('-6.75j'), -6.75j)
        self.assertEqual(astroidutils.literal_eval('3+6j'), 3+6j)
        self.assertEqual(astroidutils.literal_eval('-3+6j'), -3+6j)
        self.assertEqual(astroidutils.literal_eval('3-6j'), 3-6j)
        self.assertEqual(astroidutils.literal_eval('-3-6j'), -3-6j)
        self.assertEqual(astroidutils.literal_eval('3.25+6.75j'), 3.25+6.75j)
        self.assertEqual(astroidutils.literal_eval('-3.25+6.75j'), -3.25+6.75j)
        self.assertEqual(astroidutils.literal_eval('3.25-6.75j'), 3.25-6.75j)
        self.assertEqual(astroidutils.literal_eval('-3.25-6.75j'), -3.25-6.75j)
        self.assertEqual(astroidutils.literal_eval('(3+6j)'), 3+6j)
        self.assertRaises(ValueError, astroidutils.literal_eval, '-6j+3')
        self.assertRaises(ValueError, astroidutils.literal_eval, '-6j+3j')
        self.assertRaises(ValueError, astroidutils.literal_eval, '3+-6j')
        self.assertRaises(ValueError, astroidutils.literal_eval, '3+(0+6j)')
        self.assertRaises(ValueError, astroidutils.literal_eval, '-(3+6j)')
        self.assertRaises(ValueError, astroidutils.literal_eval, 'random()')

    def test_literal_eval_trailing_ws(self):
        self.assertEqual(astroidutils.literal_eval("    -1"), -1)
        self.assertEqual(astroidutils.literal_eval("\t\t-1"), -1)
        self.assertEqual(astroidutils.literal_eval(" \t -1"), -1)

    def test_literal_eval_malformed_lineno(self):
        msg = r'malformed node or string on line 3:'
        with self.assertRaisesRegex(ValueError, msg):
            astroidutils.literal_eval("{'a': 1,\n'b':2,\n'c':++3,\n'd':4}")

        node = astroidutils.nodefactory.UnaryOp("+", operand=astroidutils.nodefactory.UnaryOp("+", operand=astroid.nodes.Const(6)))
        self.assertIsNone(getattr(node, 'lineno', None))
        msg = r'malformed node or string:'
        with self.assertRaisesRegex(ValueError, msg):
            astroidutils.literal_eval(node)

class CopyLocationTests(unittest.TestCase):
    maxDiff = None
    def test_copy_location(self):
        src = astroid.builder.parse('1 + 1').body[0].value

        src.right = astroidutils.copy_location(astroid.nodes.Const(2), src.right)
        self.assertEqual(src.repr_tree(include_linenos=True), '''BinOp(
   lineno=1,
   col_offset=0,
   op='+',
   left=Const(
      lineno=1,
      col_offset=0,
      value=1,
      kind=None),
   right=Const(
      lineno=1,
      col_offset=4,
      value=2,
      kind=None))''')
        
        src = astroid.nodes.Call(col_offset=1, lineno=1, end_lineno=1, end_col_offset=1)
        new = astroidutils.copy_location(src, astroid.nodes.Call(col_offset=None, lineno=None))
        self.assertEqual(new.end_lineno, 1)
        self.assertEqual(new.end_col_offset, 1)
        self.assertEqual(new.lineno, 1)
        self.assertEqual(new.col_offset, 1)

class FixMissingLocationTests(unittest.TestCase):
    maxDiff = None
    def test_fix_missing_locations(self):
        src = astroid.builder.parse('write("spam")')
        src.body.append(astroidutils.nodefactory.Expr(value=astroidutils.nodefactory.Call(func=astroid.nodes.Name('spam'),
                                          args=[astroid.nodes.Const('eggs')], keywords=[])))
        

        self.assertEqual(src.repr_tree(include_linenos=True), '''Module(
   lineno=0,
   col_offset=None,
   name='',
   doc=None,
   file='<?>',
   path=['<?>'],
   package=False,
   pure_python=True,
   future_imports=set(),
   body=[Expr(
         lineno=1,
         col_offset=0,
         value=Call(
            lineno=1,
            col_offset=0,
            func=Name(
               lineno=1,
               col_offset=0,
               name='write'),
            args=[Const(
                  lineno=1,
                  col_offset=6,
                  value='spam',
                  kind=None)],
            keywords=[])),
      Expr(
         lineno=None,
         col_offset=None,
         value=Call(
            lineno=None,
            col_offset=None,
            func=Name(
               lineno=None,
               col_offset=None,
               name='spam'),
            args=[Const(
                  lineno=None,
                  col_offset=None,
                  value='eggs',
                  kind=None)],
            keywords=[]))])''')

        self.assertEqual(src, astroidutils.fix_missing_locations(src))

        self.assertEqual(src.repr_tree(include_linenos=True), '''Module(
   lineno=0,
   col_offset=0,
   name='',
   doc=None,
   file='<?>',
   path=['<?>'],
   package=False,
   pure_python=True,
   future_imports=set(),
   body=[Expr(
         lineno=1,
         col_offset=0,
         value=Call(
            lineno=1,
            col_offset=0,
            func=Name(
               lineno=1,
               col_offset=0,
               name='write'),
            args=[Const(
                  lineno=1,
                  col_offset=6,
                  value='spam',
                  kind=None)],
            keywords=[])),
      Expr(
         lineno=1,
         col_offset=0,
         value=Call(
            lineno=1,
            col_offset=0,
            func=Name(
               lineno=1,
               col_offset=0,
               name='spam'),
            args=[Const(
                  lineno=1,
                  col_offset=0,
                  value='eggs',
                  kind=None)],
            keywords=[]))])''')


# from sphinx-autoapi, we do not currently use the resolve_qualname function, but tests are there anyway.

def generate_module_names():
    for i in range(1, 5):
        yield ".".join("module{}".format(j) for j in range(i))

    yield "package.repeat.repeat"


def imported_basename_cases():
    for module_name in generate_module_names():
        import_ = "import {}".format(module_name)
        basename = "{}.ImportedClass".format(module_name)
        expected = basename

        yield (import_, basename, expected)

        import_ = "import {} as aliased".format(module_name)
        basename = "aliased.ImportedClass"

        yield (import_, basename, expected)

        if "." in module_name:
            from_name, attribute = module_name.rsplit(".", 1)
            import_ = "from {} import {}".format(from_name, attribute)
            basename = "{}.ImportedClass".format(attribute)
            yield (import_, basename, expected)

            import_ += " as aliased"
            basename = "aliased.ImportedClass"
            yield (import_, basename, expected)

        import_ = "from {} import ImportedClass".format(module_name)
        basename = "ImportedClass"
        yield (import_, basename, expected)

        import_ = "from {} import ImportedClass as AliasedClass".format(module_name)
        basename = "AliasedClass"
        yield (import_, basename, expected)


def generate_args():
    for i in range(5):
        yield ", ".join("arg{}".format(j) for j in range(i))


def imported_call_cases():
    for args in generate_args():
        for import_, basename, expected in imported_basename_cases():
            basename += "({})".format(args)
            expected += "()"
            yield import_, basename, expected


class TestAstroidUtils:
    @pytest.mark.parametrize(
        ("import_", "basename", "expected"), list(imported_basename_cases())
    )
    def test_can_get_full_imported_basename(self, import_, basename, expected):
        source = """
        {}
        class ThisClass({}): #@
            pass
        """.format(
            import_, basename
        )
        node = astroid.extract_node(source)
        basenames = astroidutils.resolve_qualname(node, node.basenames[0])
        assert basenames == expected

        # this test also pass with expand_name()
        mod = mod_from_text(source)
        basenames = mod['ThisClass'].expand_name(node.basenames[0])
        assert basenames == expected

    @pytest.mark.parametrize(
        ("import_", "basename", "expected"), list(imported_call_cases())
    )
    def test_can_get_full_function_basename(self, import_, basename, expected):
        source = """
        {}
        class ThisClass({}): #@
            pass
        """.format(
            import_, basename
        )
        node = astroid.extract_node(source)
        basenames = astroidutils.resolve_qualname(node, node.basenames[0])
        assert basenames == expected

    # @pytest.mark.parametrize(
    #     ("source", "expected"),
    #     [
    #         ('a = "a"', ("a", "a")),
    #         ("a = 1", ("a", 1)),
    #         ("a, b, c = (1, 2, 3)", None),
    #         ("a = b = 1", None),
    #     ],
    # )
    # def test_can_get_assign_values(self, source, expected):
    #     node = astroid.extract_node(source)
    #     value = astroid_utils.get_assign_value(node)
    #     assert value == expected

# end from sphinx-autoapi