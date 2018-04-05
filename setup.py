#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import os
import sys
import re
import distutils
from setuptools import find_packages, setup
from distutils.extension import Extension

try:
    from Cython.Build import cythonize
    USE_CYTHON = True
except ImportError:
    USE_CYTHON = False

supress_link_flags = os.environ.get("UAMQP_SUPPRESS_LINK_FLAGS", False)
is_win = sys.platform.startswith('win')
is_mac = sys.platform.startswith('darwin')

# Version extraction inspired from 'requests'
with open(os.path.join('uamqp', '__init__.py'), 'r') as fd:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                        fd.read(), re.MULTILINE).group(1)


cwd = os.path.abspath('.')

# Headers

pxd_inc_dir = os.path.join(cwd, "src", "vendor", "inc")
sys.path.insert(0, pxd_inc_dir)

include_dirs = [
    pxd_inc_dir,
    # azure-c-shared-utility inc
    "./src/vendor/azure-uamqp-c/deps/azure-c-shared-utility/pal/inc",
    "./src/vendor/azure-uamqp-c/deps/azure-c-shared-utility/inc",
    "./src/vendor/azure-uamqp-c/deps/azure-c-shared-utility/pal/windows" if is_win else "./src/vendor/azure-uamqp-c/deps/azure-c-shared-utility/pal/linux",
    # azure-uamqp-c inc
    "./src/vendor/azure-uamqp-c/inc",
]

# Build unique source pyx

c_uamqp_src = None
if USE_CYTHON:
    content_includes = ""
    for f in os.listdir("./src"):
        if is_win and 'openssl' in f:
            continue
        elif not is_win and 'schannel' in f:
            continue
        if f.endswith(".pyx"):
            print("Adding {}".format(f))
            content_includes += "include \"src/" + f + "\"\n"
    c_uamqp_src = os.path.join("uamqp", "c_uamqp.pyx")
    with open(c_uamqp_src, 'w') as lib_file:
        lib_file.write(content_includes)
else:
    c_uamqp_src = "uamqp/c_uamqp.c"


# Libraries and extra compile args

kwargs = {}
if is_win:
    kwargs['extra_compile_args'] = ['/openmp']
    kwargs['libraries'] = [
        'AdvAPI32',
        'Crypt32',
        'ncrypt',
        'Secur32',
        'schannel',
        'RpcRT4',
        'WSock32',
        'WS2_32']
else:
    kwargs['extra_compile_args'] = ['-g', '-O0', "-std=gnu99", "-fPIC"]
    # SSL before crypto matters: https://bugreports.qt.io/browse/QTBUG-62692
    if not supress_link_flags:
        kwargs['libraries'] = ['ssl', 'crypto', 'uuid', 'uamqp', 'aziotsharedutil']
        kwargs['library_dirs'] = [
            # FIXME just to simplify work in progress
            '/tmp/cmakebuild',
            '/tmp/cmakebuild/deps/azure-c-shared-utility/'
        ]
        # kwargs['extra_link_args'] = [
        #     "/data/azure-uamqp-c/cmake/libuamqp.a",
        #     "/data/azure-uamqp-c/cmake/deps/azure-c-shared-utility/libaziotsharedutil.a",
        #     "/usr/lib/x86_64-linux-gnu/libssl.so",
        #     "/usr/lib/x86_64-linux-gnu/libcrypto.so",
        #     "/usr/lib/x86_64-linux-gnu/libuuid.so"]

sources = [
    c_uamqp_src,
]

# Configure the extension

extensions = [Extension(
        "uamqp.c_uamqp",
        sources=sources,
        include_dirs=include_dirs,
        **kwargs)
    ]

with open('README.rst', encoding='utf-8') as f:
    readme = f.read()
with open('HISTORY.rst', encoding='utf-8') as f:
    history = f.read()

if USE_CYTHON:
    extensions = cythonize(extensions)

setup(
    name='uamqp',
    version=version,
    description='AMQP 1.0 Client Library for Python',
    long_description=readme + '\n\n' + history,
    license='MIT License',
    author='Microsoft Corporation',
    author_email='azpysdkhelp@microsoft.com',
    url='https://github.com/Azure/azure-uamqp-python',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Cython',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: MIT License',
    ],
    zip_safe=False,
    include_package_data=True,
    packages=find_packages(exclude=["tests"]),
    ext_modules = extensions
)
