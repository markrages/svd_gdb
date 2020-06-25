#!/usr/bin/python3

from setuptools import setup, find_packages

setup(name='svd_gdb',
      version='0.0.2',
      description='Python interface to SVD files through GDB',
      url='http://github.com/markrages/svd_gdb',
      author='Mark Rages',
      author_email='markrages@gmail.com',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Programming Language :: Python :: 3.6',
          'Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator',
      ],
      packages=['svd_gdb', 'svd_gdb.drivers'],
      install_requires=['pySerial', 'cmsis_svd'],
      py_modules=['gdb'],
      zip_safe=False)
