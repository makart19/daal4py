#*******************************************************************************
# Copyright 2020 Intel Corporation
# All Rights Reserved.
#
# This software is licensed under the Apache License, Version 2.0 (the
# "License"), the following terms apply:
#
# You may not use this file except in compliance with the License.  You may
# obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.
#*******************************************************************************

# daal4py Decision Forest Classification example for shared memory systems

import daal4py as d4p
import numpy as np
import os
from daal4py.oneapi import sycl_buffer

# let's try to use pandas' fast csv reader
try:
    import pandas
    read_csv = lambda f, c, t=np.float64: pandas.read_csv(f, usecols=c, delimiter=',', header=None, dtype=t)
except:
    # fall back to numpy loadtxt
    read_csv = lambda f, c, t=np.float64: np.loadtxt(f, usecols=c, delimiter=',', ndmin=2, dtype=t)

# Get Intel(R) Data Analytics Acceleration Library (Intel(R) DAAL) version
from daal4py import __daal_link_version__ as dv
daal_version = tuple(map(int, (dv[0:4], dv[4:8])))

try:
    from dpctx import device_context, device_type
    with device_context(device_type.gpu, 0):
        gpu_available=True
except:
    try:
        from daal4py.oneapi import sycl_context
        with sycl_context('gpu'):
            gpu_available=True
    except:
        gpu_available=False

# Commone code for both CPU and GPU computations
def compute(train_data, train_labels, predict_data, method='defaultDense'):
    # Configure a training object (5 classes)
    train_algo = d4p.decision_forest_classification_training(5,
                                                             nTrees=10,
                                                             minObservationsInLeafNode=8,
                                                             featuresPerNode=3,
                                                             engine = d4p.engines_mt19937(seed=777),
                                                             varImportance='MDI',
                                                             bootstrap=True,
                                                             resultsToCompute='computeOutOfBagError',
                                                             method=method
                                                             )
    # Training result provides (depending on parameters) model, outOfBagError, outOfBagErrorPerObservation and/or variableImportance
    train_result = train_algo.compute(train_data, train_labels)

    # now predict using the model from the training above
    if daal_version < (2020,1):
        predict_algo = d4p.decision_forest_classification_prediction(nClasses=5)
    else:
        predict_algo = d4p.decision_forest_classification_prediction(nClasses=5,
            resultsToEvaluate="computeClassLabels|computeClassProbabilities", votingMethod="unweighted")

    predict_result = predict_algo.compute(predict_data, train_result.model)

    return train_result, predict_result

# At this moment with sycl we are working only with numpy arrays
def to_numpy(data):
    try:
        from pandas import DataFrame
        if isinstance(data, DataFrame):
            return np.ascontiguousarray(data.values)
    except:
        pass
    try:
        from scipy.sparse import csr_matrix
        if isinstance(data, csr_matrix):
            return data.toarray()
    except:
        pass
    return data

def main(readcsv=read_csv, method='defaultDense'):
    nFeatures = 3
    # input data file
    train_file = os.path.join('..', 'data', 'batch', 'df_classification_train.csv')
    predict_file = os.path.join('..', 'data', 'batch', 'df_classification_test.csv')

    # Read train data. Let's use 3 features per observation
    train_data   = readcsv(train_file, range(nFeatures), t=np.float32)
    train_labels = readcsv(train_file, range(nFeatures,nFeatures + 1), t=np.float32)
    # Read test data (with same #features)
    predict_data = readcsv(predict_file, range(nFeatures), t=np.float32)
    predict_labels = readcsv(predict_file, range(nFeatures, nFeatures + 1), t=np.float32)

    # Using of the classic way (computations on CPU)
    train_result, predict_result = compute(train_data, train_labels, predict_data, "defaultDense")
    assert predict_result.prediction.shape == (predict_labels.shape[0], 1)
    assert np.mean(np.not_equal(predict_result.prediction - predict_labels, 0)) < 0.03

    train_data   = to_numpy(train_data) 
    train_labels = to_numpy(train_labels)
    predict_data = to_numpy(predict_data)

    try:
        from dpctx import device_context, device_type
        gpu_context = lambda: device_context(device_type.gpu, 0)
    except:
        from daal4py.oneapi import sycl_context
        gpu_context = lambda: sycl_context('gpu')

    # It is possible to specify to make the computations on GPU
    if gpu_available:
        with gpu_context():
            sycl_train_data = sycl_buffer(train_data)
            sycl_train_labels = sycl_buffer(train_labels)
            sycl_predict_data = sycl_buffer(predict_data)
            train_result, predict_result = compute(sycl_train_data, sycl_train_labels, sycl_predict_data, 'hist')
            assert predict_result.prediction.shape == (predict_labels.shape[0], 1)
            assert np.mean(np.not_equal(predict_result.prediction - predict_labels, 0)) < 0.03

    return (train_result, predict_result, predict_labels)


if __name__ == "__main__":
    (train_result, predict_result, plabels) = main()
    print("\nVariable importance results:\n", train_result.variableImportance)
    print("\nOOB error:\n", train_result.outOfBagError)
    print("\nDecision forest prediction results (first 10 rows):\n", predict_result.prediction[0:10])
    if daal_version >= (2020,1):
        print("\nDecision forest probabilities results (first 10 rows):\n", predict_result.probabilities[0:10])
    print("\nGround truth (first 10 rows):\n", plabels[0:10])
    print('All looks good!')
