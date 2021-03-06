# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

import os, gzip, cPickle, sys

from sklearn.cross_validation import train_test_split
from sklearn.cross_validation import cross_val_score
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.metrics import classification_report
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import brier_score_loss
from sklearn import metrics

from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.preprocessing import LabelBinarizer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.svm import LinearSVC
from sklearn.pipeline import make_pipeline
from sklearn.grid_search import GridSearchCV

from scipy.sparse import hstack


def get_prob(clf):
    # [reference]
    # Probability Calinration Curves in sklearn
    if hasttr(clf, "predict_prob"):
        prob_pos = clf.predict_proba(X_test)[:,1]
    else: # use decision function
        prob_pos = clf.decision_function(X_test)
        prob_pos = \
            (prob_pos - prob_pos.min()) / (prob_pos.max() - prob_pos.min()) # scailing [0,1]
        
    return prob_pos

if __name__ == '__main__':

    local_filename = "%s/%s" % (os.environ["HOME"],
                                "data/gbdt/adult.data_test.csv")
    names = ("age, workclass, fnlwgt, education, education-num, marital-status, occupation, relationship, race, sex, capital-gain, capital-loss, hours-per-week, native-country, income").split(', ')
    data = pd.read_csv(local_filename, names=names)
    data_encoded = data.apply(lambda x: pd.factorize(x)[0])
    target_names = data['income'].unique()
    features = data_encoded.drop('income', axis=1)

    X = features.values.astype(np.float32)
    y = (data['income'].values == ' >50K').astype(np.int32)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)

    # 1. Logistic Regression using transformated features
    # determine C by train data
    # [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
    #tolerance for stopping criterion
    parameters = [{'C': [10.0],
                   'loss':['hinge'],
                   'penalty':['l2'],
                   'tol':[1.0e-3],
                   'random_state':[0]},
                  {'C': [10.0],
                   'loss':['squared_hinge'],
                   'penalty':['l1'],
                   'dual':[False],
                   'tol':[1.0e-3],
                   'random_state':[0]}]
    n_jobs_ = 1
    num_cv_ = 5
    clf_cv = GridSearchCV(LinearSVC(), 
                          parameters, 
                          scoring = "f1",
                          cv = num_cv_, n_jobs = n_jobs_,
                          verbose = 10)
    clf_cv.fit(X_train, y_train)
    print clf_cv.best_params_

    clf = LinearSVC()
    clf.set_params(**clf_cv.best_params_)
    del clf_cv
    clf.fit(X_train, y_train)

    if hasattr(clf, "predict_prob"):
        prob_pos = clf.predict_proba(X_test)[:,1]
    else: # use decision function
        prob_pos = clf.decision_function(X_test)
        prob_pos = \
            (prob_pos - prob_pos.min()) / (prob_pos.max() - prob_pos.min()) # scailing [0,1]
    print prob_pos

    [[TP,FP],[FN,TN]] = metrics.confusion_matrix(y_test, clf.predict(X_test))
    accuracy = float(TP + TN) / float(TP + FP + FN + TN)
    precision = float(TP) / float(TP + FP)
    recall = float(TP) / float(TP + FN)
    f = 2.0 * precision * recall / (precision + recall)
    print "accuracy=%1.5e, precision=%1.5e, recall=%1.5e, f=%1.5e" % (accuracy, precision, recall, f)
