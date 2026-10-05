import tempfile
import unittest
from pathlib import Path
from solvepack.model import validate_manifest, extract_candidates


class ModelTests(unittest.TestCase):
    def test_byte_candidates_are_distinct_nonempty_printable_and_streams_do_not_join(self):
        self.assertEqual(extract_candidates(b'\xffhitcon{alpha} hitcon{} hitcon{bad\x01x} hitcon{alpha} hitcon{split',
                                            b'end} hitcon{beta}\x80'), ['hitcon{alpha}', 'hitcon{beta}'])
        self.assertEqual(extract_candidates(b'hitcon{' * 149000, b''), [])

    def test_paths_with_spaces_and_literal_empty_arguments_work(self):
        with tempfile.TemporaryDirectory(prefix='solve pack ') as directory:
            root = Path(directory)
            (root/'solve.py').write_text('print(1)')
            (root/'input data.bin').write_bytes(b'abc')
            data = dict(schema_version=1, challenge_id='toy', solver='solve.py', args=['', '; touch escaped'],
                        inputs=['input data.bin'], dependencies=[])
            manifest = validate_manifest(root, data)
            self.assertEqual(manifest.args, ['', '; touch escaped'])
            self.assertFalse(manifest.synthetic)
            self.assertEqual(manifest.category, 'Uncategorised')

    def test_escape_symlink_reserved_duplicate_and_bad_types_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'solve.py').write_text('print(1)'); (root/'in.bin').write_bytes(b'a')
            (root/'alias').symlink_to(root/'in.bin')
            (root/'linked').symlink_to(root, target_is_directory=True)
            good = dict(schema_version=1, challenge_id='toy', solver='solve.py', args=[], inputs=['in.bin'], dependencies=[])
            for field, value in [('solver','../solve.py'),('solver',str(root/'solve.py')),('inputs',['alias']),
                                 ('inputs',['linked/in.bin']),('inputs',['missing']),('inputs',['in.bin','in.bin']),
                                 ('inputs',['solve.py']),('inputs',['challenge.json']),('solver','challenge.json'),
                                 ('inputs',['.solvepack/x']),('schema_version',True),('schema_version',2),
                                 ('synthetic','yes'),('args',[None]),('args',['a\0b']),('dependencies',['x','X']),
                                 ('dependencies',['bad package']),('extra','unknown')]:
                with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                    validate_manifest(root, {**good,field:value})


if __name__ == '__main__': unittest.main()
