import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, Model

class LSTMAutoencoder:
    def __init__(self, input_shape):
        self.input_shape = input_shape
        self.model = self._build()

    def _build(self):
        inp = layers.Input(shape=self.input_shape)

        x = layers.LSTM(64, return_sequences=True)(inp)
        x = layers.LSTM(32)(x)

        x = layers.RepeatVector(self.input_shape[0])(x)

        x = layers.LSTM(32, return_sequences=True)(x)
        x = layers.LSTM(64, return_sequences=True)(x)

        out = layers.TimeDistributed(layers.Dense(self.input_shape[1]))(x)

        model = Model(inp, out)
        model.compile(optimizer="adam", loss="mse")
        return model

    def train(self, X):
        self.model.fit(X, X, epochs=10, batch_size=32, verbose=1)

    # ✅ REAL anomaly score (0 → 1)
    def score(self, X):
        recon = self.model.predict(X, verbose=0)
        mse = np.mean((X - recon) ** 2, axis=(1, 2))

        # normalize into probability-like score
        return 1 - np.exp(-mse / 50)

    def save(self, path):
        self.model.save(path)