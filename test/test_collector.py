import sys

from nose.tools import assert_equal
from nose.exc import SkipTest
from helper import assert_length

import pythoscope

new_style_class = """
class AClass(object):
    def amethod(self):
        pass
"""

old_style_class = """
class OldStyleClass:
    def amethod(self):
        pass
"""

class_without_methods = """
class ClassWithoutMethods(object):
    pass
"""

stand_alone_function = """
def a_function():
    pass
"""

inner_classes_and_function = """
def outer_function():
    def inner_function():
        pass
    class InnerClass(object):
        pass

class OuterClass(object):
    class AnotherInnerClass(object):
        pass
"""

class_with_methods = """
class ClassWithThreeMethods(object):
    def first_method(self):
        pass
    def second_method(self, x):
        pass
    def third_method(self, x, y):
        pass
"""

syntax_error = """
a b c d e f g
"""

indentation_error = """
  def answer():
    42
"""

definitions_inside_try_except = """
try:
    def inside_function(): pass
    class InsideClass(object): pass
except:
    pass
"""

definitions_inside_if = """
if True:
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_while = """
while True:
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_for = """
for x in range(1):
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_with = """
from __future__ import with_statement
with x:
    def inside_function(): pass
    class InsideClass(object): pass
"""

class TestCollector:
    def test_collects_information_about_top_level_classes(self):
        info = pythoscope.collect_information(new_style_class)

        assert_length(info.classes, 1)
        assert_equal("AClass", info.classes[0].name)

    def test_collects_information_about_top_level_functions(self):
        info = pythoscope.collect_information(stand_alone_function)

        assert_length(info.functions, 1)
        assert_equal("a_function", info.functions[0].name)

    def test_doesnt_count_methods_as_functions(self):
        info = pythoscope.collect_information(new_style_class)

        assert_length(info.functions, 0)

    def test_collects_information_about_old_style_classes(self):
        info = pythoscope.collect_information(old_style_class)

        assert_length(info.classes, 1)
        assert_equal("OldStyleClass", info.classes[0].name)

    def test_collects_information_about_classes_without_methods(self):
        info = pythoscope.collect_information(class_without_methods)

        assert_length(info.classes, 1)
        assert_equal("ClassWithoutMethods", info.classes[0].name)

    def test_ignores_inner_classes_and_functions(self):
        info = pythoscope.collect_information(inner_classes_and_function)

        assert_length(info.classes, 1)
        assert_equal("OuterClass", info.classes[0].name)
        assert_length(info.functions, 1)
        assert_equal("outer_function", info.functions[0].name)

    def test_collects_information_about_methods_of_a_class(self):
        info = pythoscope.collect_information(class_with_methods)

        assert_equal(["first_method", "second_method", "third_method"],
                     info.classes[0].methods)

    def test_collector_handles_syntax_errors(self):
        info = pythoscope.collect_information(syntax_error)

        assert_length(info.errors, 1)

    def test_collector_handles_indentation_errors(self):
        info = pythoscope.collect_information(indentation_error)

        assert_length(info.errors, 1)

    def test_collects_information_about_functions_and_classes_inside_other_blocks(self):
        suite = [definitions_inside_try_except, definitions_inside_if,
                 definitions_inside_while, definitions_inside_for]

        for case in suite:
            info = pythoscope.collect_information(case)
            assert_length(info.classes, 1)
            assert_equal("InsideClass", info.classes[0].name)
            assert_length(info.functions, 1)
            assert_equal("inside_function", info.functions[0].name)

    def test_collects_information_about_functions_and_classes_inside_with(self):
        # With statement was introduced in Python 2.5, so skip this test for
        # earlier versions.
        if float(sys.version[:3]) < 2.5:
            raise SkipTest

        info = pythoscope.collect_information(definitions_inside_with)
        assert_length(info.classes, 1)
        assert_equal("InsideClass", info.classes[0].name)
        assert_length(info.functions, 1)
        assert_equal("inside_function", info.functions[0].name)
