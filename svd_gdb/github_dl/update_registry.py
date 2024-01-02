#!/usr/bin/python

URL="https://github.com/cmsis-svd/cmsis-svd-data.git"
REV="HEAD"

import subprocess, tempfile, os

with open('registry.txt', 'w') as of:
    with open('revhash.txt', 'w') as rhf:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            subprocess.check_output('git clone --no-checkout --depth 1'.split() + [URL])
            os.chdir(os.path.basename(URL).rsplit('.',1)[0])
            fd = subprocess.check_output('git ls-tree -r --full-tree'.split() + [REV],
                                     text=True)
            for line in fd.splitlines():
                fields = line.split()
                print(f"{fields[-1]} git_sha:{fields[-2]}", file=of)

            revhash = subprocess.check_output('git rev-parse'.split() + [REV],
                                     text=True).strip()
            print(revhash, file=rhf)
