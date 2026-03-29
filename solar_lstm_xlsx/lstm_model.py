"""LSTM 모델 — build, train, predict, save, load"""

import logging
import pathlib

import numpy as np

from solar_lstm_xlsx.config import (
    SEQ_LEN, NUM_FEATURES, LSTM_UNITS_1, LSTM_UNITS_2,
    DENSE_UNITS_1, DENSE_UNITS_2, DROPOUT_RATE,
    LEARNING_RATE, EPOCHS, BATCH_SIZE, EARLY_STOP_PATIENCE,
    FUTURE_STEPS, MODEL_PATH,
)

logger = logging.getLogger(__name__)


def build_model():
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    model = keras.Sequential([
        layers.Input(shape=(SEQ_LEN, NUM_FEATURES)),
        layers.LSTM(LSTM_UNITS_1, return_sequences=True),
        layers.Dropout(DROPOUT_RATE),
        layers.LSTM(LSTM_UNITS_2, return_sequences=False),
        layers.Dropout(DROPOUT_RATE),
        layers.Dense(DENSE_UNITS_1, activation="relu"),
        layers.Dense(DENSE_UNITS_2, activation="relu"),
        layers.Dense(FUTURE_STEPS, activation="linear"),
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss="mse",
        metrics=["mae"],
    )
    model.summary(print_fn=logger.info)
    return model


def train_model(model, X_train, y_train, X_val, y_val, save_path=None):
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau

    save_path = pathlib.Path(save_path) if save_path else MODEL_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)

    callbacks = [
        EarlyStopping(monitor="val_loss", patience=EARLY_STOP_PATIENCE,
                      restore_best_weights=True, verbose=1),
        ModelCheckpoint(filepath=str(save_path), monitor="val_loss",
                        save_best_only=True, verbose=1),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=5,
                          min_lr=1e-6, verbose=1),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS, batch_size=BATCH_SIZE,
        callbacks=callbacks, verbose=1,
    )
    logger.info("Training complete. Best val_loss: %.6f", min(history.history["val_loss"]))
    return history


def predict(model, X: np.ndarray) -> np.ndarray:
    return model.predict(X, verbose=0)


def save_model(model, path=None):
    path = pathlib.Path(path) if path else MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))
    logger.info("Model saved to %s", path)


def load_model(path=None):
    import tensorflow as tf
    path = pathlib.Path(path) if path else MODEL_PATH
    model = tf.keras.models.load_model(str(path))
    logger.info("Model loaded from %s", path)
    return model
