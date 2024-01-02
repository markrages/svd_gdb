#!/usr/bin/env python

import pooch

import hashlib
import os.path
install_dir = os.path.dirname(__file__)

class GitBlobHash:
    def __init__(self):
        self.obj = []

    def update(self, obj):
        self.obj.append(obj)

    def hexdigest(self):
        obj = b''.join(self.obj)

        return hashlib.sha1(b'blob %d\0'%len(obj)+obj).hexdigest()

pooch.hashes.ALGORITHMS_AVAILABLE['git_sha'] = GitBlobHash

import time

class PoochWrap:
    def __init__(self,
                 github_user, github_project,
                 version, registry_filename):
        self.github_user = github_user
        self.github_project = github_project
        self.version = version
        self.registry_filename = registry_filename

        self._pooch = None

    @property
    def pooch(self):
        if not self._pooch:
            registry_file = open(self.registry_filename)

            # pooch.load_registry() uses shlex.split() and is *very*
            # slow (200 ms for a 1900 line file) so here's a registry
            # reader about 100x faster
            registry = dict(line.strip().split()
                            for line in registry_file
                            if line.strip() and not line.startswith('#'))

            self._pooch = pooch.create(
                path=pooch.os_cache(f"{self.github_project}"),
                base_url=f"https://github.com/{self.github_user}/{self.github_project}/raw/{self.version}/",
                registry=registry,
            )

        return self._pooch
