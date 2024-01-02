#!/usr/bin/env python

import pooch

import hashlib
import os.path
install_dir = os.path.dirname(__file__)

class GitBlobHash:
    def __init__(self):
        self.obj = b''
        
    def update(self, obj):
        self.obj += obj

    def hexdigest(self):
        return hashlib.sha1(b'blob %d\0'%len(self.obj)+self.obj).hexdigest()

pooch.hashes.ALGORITHMS_AVAILABLE['git_sha'] = GitBlobHash

class PoochWrap:
    def __init__(self):
        self._pooch = None

    @property
    def pooch(self):
        if not self._pooch:

            version=open(install_dir+"/revhash.txt").read().strip()

            self._pooch = pooch.create(
                path=pooch.os_cache("cmsis_svd_data"),
                base_url="https://github.com/cmsis-svd/cmsis-svd-data/raw/"+version+"/",
                # We'll load it from a file later
                registry=None,
            )

            registry_file = open(install_dir+"/registry.txt")
            # Load this registry file
            self._pooch.load_registry(registry_file)
        return self._pooch

pw = PoochWrap()

def fetch(filename):
    import time
    t0 = time.time()
    ret = pw.pooch.fetch(filename)
    #ret = "/home/markrages/.cache/cmsis_svd_data/"+filename
    t1 = time.time()
    print("time",t1-t0)
    return ret

if __name__== "__main__":    
    f = fetch('data/Nordic/nrf52.svd')
    print(f)
