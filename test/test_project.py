from fixture import TempIO
from nose.tools import assert_equal, assert_raises

from pythoscope.store import Project, Module, Class, Function, TestModule, \
     TestClass, TestMethod, ModuleNotFound

from helper import assert_length, assert_equal_sets

# Let nose know that those aren't test classes.
TestModule.__test__ = False
TestClass.__test__ = False
TestMethod.__test__ = False

class TestProject:
    def test_can_be_saved_and_restored_from_file(self):
        tmpdir = TempIO()
        tmpdir.mkdir(".pythoscope")
        modules = [Module(path='good_module.py',
                          objects=[Class("AClass", ["amethod"]),
                                   Function("afunction")]),
                   Module(path='bad_module.py', errors=["Syntax error"])]

        project = Project(tmpdir, modules)
        project.save()
        project = Project.from_directory(tmpdir)

        assert_equal(2, len(project.modules))
        assert_equal(2, len(project['good_module'].objects))
        assert_equal("AClass", project['good_module'].classes[0].name)
        assert_equal(["amethod"], project['good_module'].classes[0].methods)
        assert_equal("afunction", project['good_module'].functions[0].name)
        assert_equal(["Syntax error"], project['bad_module'].errors)

    def test_can_be_queried_for_modules_by_their_path(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        project = Project(modules=map(Module, paths))

        for path in paths:
            assert_equal(path, project[path].path)

    def test_raises_module_not_found_exception_when_no_module_like_that_is_present(self):
        project = Project()
        assert_raises(ModuleNotFound, lambda: project["whatever"])

    def test_can_be_queried_for_modules_by_their_locator(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        locators = ["module", "sub.dir.module", "package"]
        project = Project(modules=map(Module, paths))

        for path, locator in zip(paths, locators):
            assert_equal(path, project[locator].path)

    def test_replaces_old_module_objects_with_new_ones_during_add_modules(self):
        modules = map(Module, ["module.py", "sub/dir/module.py", "other/module.py"])
        new_module = Module("other/module.py")

        project = Project(modules=modules)
        project.add_modules([new_module])

        assert_length(project.modules, 3)
        assert project["other/module.py"] is new_module

class TestProjectWithTestModule:
    def setUp(self):
        self.existing_test_class = TestClass("TestSomething")
        self.test_module = TestModule()
        self.test_module.add_test_case(self.existing_test_class)
        self.project = Project(modules=[self.test_module])

    def test_attaches_test_class_to_test_module_with_most_test_cases_for_associated_module(self):
        module = Module()
        irrelevant_test_module = TestModule()
        self.existing_test_class.associated_modules = [module]
        self.project.add_modules([module, irrelevant_test_module])

        new_test_class = TestClass("new", associated_modules=[module])
        self.project.add_test_case(new_test_class, None, False)

        assert new_test_class in self.test_module.test_cases

    def test_doesnt_overwrite_existing_test_classes_by_default(self):
        test_class = TestClass("TestSomething")
        self.project.add_test_case(test_class, "", False)

        assert_length(list(self.project.test_cases_iter()), 1)

    def test_adds_new_test_classes_to_existing_test_module(self):
        test_class = TestClass("TestSomethingNew")
        self.project.add_test_case(test_class, "", False)

        assert_equal_sets([self.existing_test_class, test_class],
                          list(self.project.test_cases_iter()))

    def test_adds_new_test_methods_to_existing_test_classes(self):
        test_method = TestMethod("test_new_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_length(list(self.project.test_cases_iter()), 1)
        assert list(self.project.test_cases_iter())[0] is test_method.parent
        assert test_method.parent is not test_class

    def test_after_adding_new_test_case_to_class_its_module_is_marked_as_changed(self):
        self.existing_test_class.add_test_case(TestMethod("test_something_new"))

        assert self.test_module.changed

    def test_doesnt_overwrite_existing_test_methods_by_default(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].test_cases)

        # Let's try adding the same method again.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", test_cases=[new_test_method])
        self.project.add_test_case(new_test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].test_cases)

    def test_overwrites_existing_test_methods_with_force_option(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].test_cases)

        # Let's try adding the same method again with a force option
        # set to True.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", test_cases=[new_test_method])
        self.project.add_test_case(new_test_class, "", True)

        # The class is still the same.
        assert_equal([self.existing_test_class],
                     list(self.project.test_cases_iter()))
        # But the method got replaced.
        assert_equal([new_test_method],
                     list(self.project.test_cases_iter())[0].test_cases)
