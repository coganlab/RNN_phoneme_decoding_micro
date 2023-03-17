"""
Training functions for the phoneme encoder decoder model.

Author: Zac Spalding
Adapted from code by Kumar Duraivel
"""

import numpy as np
from sklearn.model_selection import StratifiedKFold
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.models import load_model

from processing_utils.sequence_processing import (predict_sequence,
                                                  one_hot_decode_sequence)


def shuffle_weights(model, weights=None):
    """Randomly permute the weights in `model`, or the given `weights`.
    This is a fast approximation of re-initializing the weights of a model.
    Assumes weights are distributed independently of the dimensions of the
    weight tensors (i.e., the weights have the same distribution along each
    dimension).

    TAKEN FROM: jkleint's (https://gist.github.com/jkleint) answer on Github
    (https://github.com/keras-team/keras/issues/341)

    Args:
        model (Model): Model whose weights will be shuffled.
        weights (list(ndarray), optional):  The model's weights will be
            replaced by a random permutation of these weights.
            Defaults to None.
    """
    if weights is None:
        weights = model.get_weights()
    weights = [np.random.permutation(w.flat).reshape(w.shape) for w in weights]
    # Faster, but less random: only permutes along the first dimension
    # weights = [np.random.permutation(w) for w in weights]
    model.set_weights(weights)


def train_seq2seq_kfold(train_model, inf_enc, inf_dec, X, X_prior, y,
                        num_folds=10, batch_size=32, epochs=800,
                        early_stop=False):
    """Trains a seq2seq encoder-decoder model using k-fold cross validation.

    Uses stratified k-fold cross validation to train a seq2seq encoder-decoder
    model. Requires a training model, as well as inference encoder and decoder
    for predicting sequences. Model is trained with teacher forcing from padded
    versions of the target sequences. *** EARLY STOPPING IS CURRENTLY NOT
    IMPLEMENTED ***.

    Args:
        train_model (Functional): Full encoder-decoder model for training.
        inf_enc (Functional): Inference encoder model.
        inf_dec (Functional): Inference decoder model.
        X (ndarray): Feature data. First dimension should be number of
            observations. Dimensions should be compatible with the input to the
            provided models.
        X_prior (ndarray): Shifted labels for teacher forcing. Dimensions
            should be the same as `y`.
        y (ndarray): Labels. First dimension should be number of observations.
            Final dimension should be length of output sequence.
        num_folds (int, optional): Number of CV folds. Defaults to 10.
        batch_size (int, optional): Training batch size. Defaults to 32.
        epochs (int, optional): Number of training epochs. Defaults to 800.
        early_stop (bool, optional): Whether to stop training early based on
            validation loss performance. Defaults to True.

    Returns:
        (Functional, Dict): Trained encoder-decoder model,
            dictionary containing training performance history for each fold.
            Dictionary structure is:
                {'accuracy': [fold1_acc, fold2_acc, ...],
                'loss': [fold1_loss, fold2_loss, ...],
                'val_accuracy': [fold1_val_acc, fold2_val_acc, ...],
                'val_loss': [fold1_val_loss, fold2_val_loss, ...]}
    """
    # save initial weights to reset model for each fold
    init_train_w = train_model.get_weights()

    n_output = inf_dec.output_shape[-1]  # number of output classes
    seq_len = y.shape[-1]  # length of output sequence

    # define k-fold cross validation
    cv = StratifiedKFold(n_splits=num_folds, shuffle=True)

    # create callbacks for early stopping (model checkpoint included to get
    # best model weights since early stopping returns model after patience
    # epochs, where performance may have started to decline)
    cb = None
    if early_stop:
        es = EarlyStopping(monitor='val_loss', patience=50)
        mc = ModelCheckpoint('best_model.h5', monitor='val_acc', mode='max',
                             save_best_only=True)
        cb = [es, mc]

    # dictionary for tracking history of each fold
    histories = {'accuracy': [], 'loss': [], 'val_accracy': [], 'val_loss': []}

    # cv training
    y_pred_all, y_test_all = [], []
    for train_ind, test_ind in cv.split(X, y):
        X_train, X_test = X[train_ind], X[test_ind]
        X_prior_train, X_prior_test = X_prior[train_ind], X_prior[test_ind]
        y_train, y_test = y[train_ind], y[test_ind]

        # reset model weights for current fold (also resets associated
        # inference weights)
        shuffle_weights(train_model, weights=init_train_w)

        history = train_model.fit([X_train, X_prior_train], y_train,
                                  batch_size=batch_size, epochs=epochs,
                                  validation_data=([X_test, X_prior_test],
                                                   y_test),
                                  callbacks=cb)
        # TODO - figure out how to get inference weights from saved model
        # saved_model = load_model('best_model.h5')

        target = predict_sequence(inf_enc, inf_dec, X_test, X_prior_test,
                                  seq_len, n_output)
        y_test_all.append(one_hot_decode_sequence(y_test))
        y_pred_all.append(one_hot_decode_sequence(target))

        histories['accuracy'].append(history.history['accuracy'])
        histories['loss'].append(history.history['loss'])
        histories['val_accuracy'].append(history.history['val_accuracy'])
        histories['val_loss'].append(history.history['val_loss'])

    return train_model, histories
