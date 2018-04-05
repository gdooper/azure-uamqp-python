#!/bin/bash
set -e

# To execute this script:
# docker run --rm -v $PWD:/data pyca/cryptography-manylinux1:x86_64 /data/build_many_linux_64bit.sh

# This container is shiped with cmake version 2.8.11.2 pre-installed

export UAMQP_VERSION="0.1.0b2"

export CPATH="/opt/pyca/cryptography/openssl/include"
export LIBRARY_PATH="/opt/pyca/cryptography/openssl/lib"

# Build libuuid
pushd /tmp
wget https://www.kernel.org/pub/linux/utils/util-linux/v2.27/util-linux-2.27.1.tar.gz --no-check-certificate
tar xvf util-linux-2.27.1.tar.gz
cd util-linux-2.27.1
./configure --disable-shared --disable-all-programs --enable-libuuid CFLAGS=-fPIC
make
make install
popd

mkdir /tmp/cmakebuild
pushd /tmp/cmakebuild
cmake28 /data/src/vendor/azure-uamqp-c \
    -Duse_openssl:bool=ON \
    -Duse_default_uuid:bool=ON \
    -Dskip_samples:bool=ON \
    -DOPENSSL_LIBRARIES=/opt/pyca/cryptography/openssl/lib \
    -DOPENSSL_INCLUDE_DIR=/opt/pyca/cryptography/openssl/include \
    -DOPENSSL_ROOT_DIR=/opt/pyca/cryptography/openssl \
    -DCMAKE_POSITION_INDEPENDENT_CODE=TRUE
#    -DOPENSSL_SSL_LIBRARY=/opt/pyca/cryptography/openssl/lib/libssl.a \
#    -DOPENSSL_CRYPTO_LIBRARY=/opt/pyca/cryptography/openssl/lib/libcrypto.a \
#    -DBUILD_MODE=static

cmake28 --build .
popd

# Make sure Cython and Wheel are available in all env
/opt/python/cp34-cp34m/bin/python -m pip install cython==0.27.3 wheel
/opt/python/cp35-cp35m/bin/python -m pip install cython==0.27.3 wheel
/opt/python/cp36-cp36m/bin/python -m pip install cython==0.27.3 wheel

# Build the wheels
pushd /data
/opt/python/cp34-cp34m/bin/python setup.py bdist_wheel
auditwheel repair dist/uamqp-${UAMQP_VERSION}-cp34-cp34m-linux_x86_64.whl

/opt/python/cp35-cp35m/bin/python setup.py bdist_wheel
auditwheel repair dist/uamqp-${UAMQP_VERSION}-cp35-cp35m-linux_x86_64.whl

/opt/python/cp36-cp36m/bin/python setup.py bdist_wheel
auditwheel repair dist/uamqp-${UAMQP_VERSION}-cp36-cp36m-linux_x86_64.whl
popd