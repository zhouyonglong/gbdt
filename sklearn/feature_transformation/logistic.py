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
from sklearn import metrics

from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.preprocessing import LabelBinarizer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.pipeline import make_pipeline
from sklearn.grid_search import GridSearchCV

from scipy.sparse import hstack


class TreeTransform(BaseEstimator, TransformerMixin):
    """One-hot encode samples with an ensemble of trees
    
    This transformer first fits an ensemble of trees (e.g. gradient
    boosted trees or a random forest) on the training set.

    Then each leaf of each tree in the ensembles is assigned a fixed
    arbitrary feature index in a new feature space. If you have 100
    trees in the ensemble and 2**3 leafs per tree, the new feature
    space has 100 * 2**3 == 800 dimensions.
    
    Each sample of the training set go through the decisions of each tree
    of the ensemble and ends up in one leaf per tree. The sample if encoded
    by setting features with those leafs to 1 and letting the other feature
    values to 0.
    
    The resulting transformer learn a supervised, sparse, high-dimensional
    categorical embedding of the data.
    
    This transformer is typically meant to be pipelined with a linear model
    such as logistic regression, linear support vector machines or
    elastic net regression.
    
    """

    def __init__(self, estimator,
                 phase, 
                 n_jobs, cv_k_fold, parameters,
                 X_train, y_train,
                 X_test, y_test):
        # estimator : ensemble学習器

        # cv : if train : get best parameter
        if phase == "train":
            clf = GradientBoostingClassifier()
            gscv = GridSearchCV(clf, parameters, 
                                verbose = 10, 
                                scoring = "f1",#scoring = "precision" or "recall"
                                n_jobs = n_jobs, cv = cv_k_fold)
            gscv.fit(X_train, y_train)
            self.best_params = gscv.best_params_
            
            clf.set_params(**gscv.best_params_)
            clf.fit(X_train, y_train)
            train_loss = clf.train_score_
            test_loss = np.empty(len(clf.estimators_))
            for i, pred in enumerate(clf.staged_predict(X_test)):
                test_loss[i] = clf.loss_(y_test, pred)
            plt.plot(np.arange(len(clf.estimators_)) + 1, test_loss, label='Test')
            plt.plot(np.arange(len(clf.estimators_)) + 1, train_loss, label='Train')
            plt.xlabel('the number of weak learner:Boosting Iterations')
            plt.ylabel('Loss')
            plt.legend(loc="best")
            plt.savefig("loss_test_cv.png")
            plt.close()

        estimator.set_params(**gscv.best_params_)
        self.estimator = estimator
        self.one_hot_encoding = None
        
    def fit(self, X, y):
        self.fit_transform(X, y)
        return self
        
    def fit_transform(self, 
                      X, y):
        """
         [estimator]
          <class 'sklearn.ensemble.gradient_boosting.GradientBoostingClassifier'
          GradientBoostingClassifier(init=None, learning_rate=0.1, loss='deviance',
                                     max_depth=2, max_features=None, max_leaf_nodes=2,
                                     min_samples_leaf=1, min_samples_split=2,
                                     min_weight_fraction_leaf=0.0, n_estimators=100,
                                     random_state=0, subsample=0.3, verbose=0, warm_start=False)
         [estimator_.estimators_]
          <type 'numpy.ndarray'>
          ensembles of DecisionTreeRegressor
        """
        # 1. learn data structure by gbdt
        self.estimator_ = clone(self.estimator)#Constructs a new estimator
        self.estimator_.fit(X, y)# fit by gbdt with best parameter

        # 2. get trainsformated feature vectors from self.estimator_
        self.binarizers_ = []
        sparse_applications = []
        # --- np.asarray() ---
        # array()と同様．ただし引数がndarrayの場合，コピーでなく引数そのものを返す
        # np.asarray([1,2,3])
        # >array([1, 2, 3])
        # a = np.array([1,2])
        # b = np.asarray(a)# ndarrayを引数とするため，b = aと同値
        # array([1, 2])
        # --- np.ravel() ---
        # It is equivalent to reshape(-1, order=order).
        # x = np.array([[1, 2, 3], [4, 5, 6]])
        # >array([[1, 2, 3],
        # >       [4, 5, 6]])
        # np.ravel(x)
        # >[1 2 3 4 5 6]
        # x.reshape(-1)
        # [1 2 3 4 5 6]>
        estimators = np.asarray(self.estimator_.estimators_).ravel()
        for index, t in enumerate(estimators):
            # for each weak learner
            # t is weak learner
            # DecisionTreeRegressor(criterion=<sklearn.tree._tree.RegressionCriterion object at 0x350d1e0>,
            #                       max_depth=2, 
            #                       max_features=None, 
            #                       max_leaf_nodes=2,
            #                       min_samples_leaf=1, 
            #                       min_samples_split=2,
            #                       min_weight_fraction_leaf=0.0,
            #                       random_state=<mtrand.RandomState object at 0x2ca3b50>,
            #                       splitter=<sklearn.tree._tree.PresortBestSplitter object at 0x2cdcca0>)
            # [Attributes]
            # t.tree_ : object
            # t.max_features_ : int
            # t.feature_importances_ : ndarray
            lb = LabelBinarizer(sparse_output=True)
            sparse_applications.append(lb.fit_transform(t.tree_.apply(X)))
            #print "%d leaves in %d-th tree(weak learner)" % (len(lb.fit_transform(t.tree_.apply(X_train)).toarray().ravel()),
            #                                                 index)
            #print " max_feature_number:%d, sample_size:%d" % (t.max_features_, len(X_train))
            #26049 leaves in 88-th tree(weak learner)
            # max_feature_number:14, sample_size:26049

            self.binarizers_.append(lb) # add tree as weak learner

        self.one_hot_encoding = hstack(sparse_applications)
        
    def transform(self, X, y=None):
        sparse_applications = []
        estimators = np.asarray(self.estimator_.estimators_).ravel() # estimators are ensamble of decision trees
        for t, lb in zip(estimators, self.binarizers_):
            sparse_applications.append(lb.transform(t.tree_.apply(X)))
        return hstack(sparse_applications)

if __name__ == '__main__':

    local_filename = "%s/%s" % (os.environ["HOME"],
                                "data/gbdt/adult.data.csv")
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
    parameters = {'C': [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0],
                  'penalty' : ["l1","l2"]}
    n_jobs = 3
    num_cv = 5
    clf_cv = GridSearchCV(LogisticRegression(), 
                          parameters, 
                          scoring = "f1",
                          cv = num_cv, n_jobs=1,
                          verbose = 10)#n_jobs=5)
    clf_cv.fit( X_train, y_train )
    [[TP,FP],[FN,TN]] = metrics.confusion_matrix(y_test, clf_cv.predict(X_test))
    accuracy = float(TP + TN) / float(TP + FP + FN + TN)
    precision = float(TP) / float(TP + FP)
    recall = float(TP) / float(TP + FN)
    f = 2.0 * precision * recall / (precision + recall)
    print clf_cv.best_params_
    print "accuracy=%1.5e, precision=%1.5e, recall=%1.5e, f=%1.5e" % (accuracy, precision, recall, f)
