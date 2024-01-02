#!/usr/bin/env python

from . import github_dl

import os.path
install_dir = os.path.dirname(__file__)

version=open(install_dir+"/revhash.txt").read().strip()

__pw = github_dl.PoochWrap('cmsis-svd', 'cmsis-svd-data',
                           version,
                           install_dir+"/registry.txt")

def fetch(filename):
    return __pw.pooch.fetch(filename)

if __name__== "__main__":
    f = fetch('data/Nordic/nrf52.svd')
    print(f)
