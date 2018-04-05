#!/bin/bash

icc -std=c++11 -O3 -xHost -qopenmp -march=native preprocess.cpp -o preprocess.out -I /users/npark2/.local/usr/include/ -I /users/npark2/.local/usr/include/armadillo_bits -llapack -lboost_system -L /apps/pkg/openblas-0.2.18/rhel7_u2-x86_64-nehalem/gnu/lib -L /users/npark2/.local/usr/lib64 -larmadillo -lblas -I /users/npark2/.local/include/boost -lboost_serialization