"""Check dependency-job gating without waiting on the workflow consuming it."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import github_artifacts as artifacts


class DependencyArtifactTests(unittest.TestCase):
    def request(self,run=None,jobs=None):
        run=run or {'head_sha':'a'*40,'head_branch':'main','status':'in_progress'}
        jobs=jobs if jobs is not None else [{'name':'images','conclusion':'success'}]
        def api(path,token):
            self.assertEqual(token,'scoped-test-token')
            return {'jobs':jobs} if path.endswith('/jobs') else run
        return api

    def test_successful_job_in_running_workflow_is_usable(self):
        with patch.object(artifacts,'api',side_effect=self.request()),patch.object(artifacts,'obtain_artifact',return_value={'ok':True}) as obtain:
            self.assertEqual(artifacts.obtain_job(23,'a'*40,'images.zip','expected-images','images','scoped-test-token',51),{'ok':True})
            obtain.assert_called_once_with(23,'a'*40,'images.zip',51,'scoped-test-token','expected-images')

    def test_different_commit_cannot_supply_images(self):
        with patch.object(artifacts,'api',side_effect=self.request({'head_sha':'b'*40,'head_branch':'main'})),patch.object(artifacts,'obtain_artifact') as obtain:
            with self.assertRaisesRegex(ValueError,'build_identity_mismatch'):
                artifacts.obtain_job(23,'a'*40,'images.zip','expected-images','images','scoped-test-token')
            obtain.assert_not_called()

    def test_different_branch_cannot_supply_images(self):
        with patch.object(artifacts,'api',side_effect=self.request({'head_sha':'a'*40,'head_branch':'other'})),patch.object(artifacts,'obtain_artifact') as obtain:
            with self.assertRaisesRegex(ValueError,'build_identity_mismatch'):
                artifacts.obtain_job(23,'a'*40,'images.zip','expected-images','images','scoped-test-token')
            obtain.assert_not_called()

    def test_missing_failed_or_ambiguous_job_stops_before_download(self):
        for jobs in [[],[{'name':'images','conclusion':'failure'}],[{'name':'images','conclusion':None}],
                     [{'name':'images','conclusion':'success'}]*2]:
            with self.subTest(jobs=jobs),patch.object(artifacts,'api',side_effect=self.request(jobs=jobs)),patch.object(artifacts,'obtain_artifact') as obtain:
                with self.assertRaisesRegex(ValueError,'dependency_job_not_successful'):
                    artifacts.obtain_job(23,'a'*40,'images.zip','expected-images','images','scoped-test-token')
                obtain.assert_not_called()

    def test_legacy_completed_build_keeps_original_selection(self):
        with patch.object(artifacts,'api',return_value={'head_sha':'a'*40,'head_branch':'main','status':'completed','conclusion':'success'}),patch.object(artifacts,'obtain_artifact',return_value={'ok':True}) as obtain:
            self.assertEqual(artifacts.obtain(23,'a'*40,'images.zip',51,'scoped-test-token'),{'ok':True})
            obtain.assert_called_once_with(23,'a'*40,'images.zip',51,'scoped-test-token')


if __name__=='__main__':unittest.main()
