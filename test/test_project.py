from pythoscope.store import Project, Module, TestModule, TestCase

from helper import assert_length

class TestProject:
    def setUp(self):
        self._old_test_module_save = TestModule._save
        TestModule._save = lambda self: None

    def tearDown(self):
        TestModule._save = self._old_test_module_save

    def test_attaches_test_case_to_test_module_with_most_test_cases_for_associated_module(self):
        self._create_test_module()
        module = Module()
        irrelevant_test_module = TestModule()
        self.existing_test_case.associated_modules = [module]
        self.project.add_modules([module, irrelevant_test_module])

        new_test_case = TestCase("new", "", "", "", associated_modules=[module])
        self.project.add_test_case(new_test_case, None, False)

        assert new_test_case in self.test_module.test_cases

    def test_doesnt_overwrite_existing_test_cases_by_default(self):
        self._create_test_module()

        test_case = TestCase("existing", "", "", "")
        self.project.add_test_case(test_case, "", False)

        assert_length(list(self.project.test_cases_iter()), 1)

    def _create_test_module(self):
        self.existing_test_case = TestCase("existing", "", "", "")
        self.test_module = TestModule()
        self.test_module.add_test_case(self.existing_test_case)
        self.project = Project(modules=[self.test_module])
